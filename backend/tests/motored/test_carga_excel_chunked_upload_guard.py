"""
Ad-hoc bugfix (not tracked under sdd/*, 2026-09-28): `_parse_excel_upload`
used to do a single unbounded `await file.read()`. A client using chunked
transfer-encoding never sends a `Content-Length` header, so
`_check_content_length_guard` -- which only inspects that header -- lets the
request through with zero size check, and the old unbounded read would then
pull the ENTIRE file into memory regardless of `MOTORED_MAX_UPLOAD_MB`.

This proves the fix: `_parse_excel_upload` must read in bounded chunks and
abort with the same 413 `HTTPException` as soon as the accumulated size
exceeds the configured limit, WITHOUT ever consuming anywhere near the full
stream. See `project_pending_issues.md` entry dated 2026-09-28 (`carga.py`
chunked-upload bypass) for the original finding.
"""
import io
import types

import openpyxl
import pytest
from fastapi import HTTPException

from app.config import settings
from app.motored.api.carga import _parse_excel_upload


class _FakeChunkedUploadFile:
    """Simulates an `UploadFile` fed by a chunked-transfer stream: no usable
    total size upfront, content generated lazily per `read(size)` call. Bytes
    are never materialized beyond what's actually requested, so a test using
    a huge `total_bytes` stays fast/cheap UNLESS the code under test tries to
    read it all at once -- which is exactly the bug this test catches.
    """

    def __init__(self, total_bytes: int, filename: str = "huge.xlsx"):
        self.filename = filename
        self._remaining = total_bytes
        self.max_single_read = 0
        self.total_bytes_served = 0

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self._remaining  # mirrors real `UploadFile.read()` semantics: "read everything"
        chunk = min(size, self._remaining)
        self._remaining -= chunk
        self.max_single_read = max(self.max_single_read, chunk)
        self.total_bytes_served += chunk
        return b"A" * chunk


def _request_without_content_length():
    """A chunked-transfer request never sets `Content-Length` -- `.headers`
    only needs `.get(...)`, matching what `_check_content_length_guard`
    calls."""
    return types.SimpleNamespace(headers={})


async def test_parse_excel_upload_aborts_early_on_oversized_chunked_upload_without_content_length(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_MAX_UPLOAD_MB", 1)
    total_bytes = 500 * 1024 * 1024  # 500MB -- impractical to hold fully in memory in a unit test
    fake_file = _FakeChunkedUploadFile(total_bytes)
    request = _request_without_content_length()

    with pytest.raises(HTTPException) as exc_info:
        await _parse_excel_upload("sucursal", request, fake_file)

    assert exc_info.value.status_code == 413
    assert "1MB" in exc_info.value.detail

    # Bounded proof: the guard must abort as soon as the accumulated size
    # crosses the 1MB limit -- never anywhere near the full 500MB stream, and
    # never a single unbounded read that swallows everything in one shot.
    max_bounded_bytes = 2 * 1024 * 1024  # limit + one chunk of slack
    assert fake_file.total_bytes_served <= max_bounded_bytes
    assert fake_file.max_single_read <= max_bounded_bytes


async def test_parse_excel_upload_still_parses_small_chunked_upload_normally(monkeypatch):
    """The streaming guard must not break the happy path: a small file
    (well under the limit) still parses successfully, chunk-by-chunk."""
    monkeypatch.setattr(settings, "MOTORED_MAX_UPLOAD_MB", 10)
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["Nombre"])
    sheet.append(["CALI NORTE"])
    buffer = io.BytesIO()
    wb.save(buffer)
    file_bytes = buffer.getvalue()

    class _FakeSmallUploadFile:
        def __init__(self, data: bytes, filename: str):
            self.filename = filename
            self._data = data
            self._offset = 0

        async def read(self, size: int = -1) -> bytes:
            if size is None or size < 0:
                size = len(self._data) - self._offset
            chunk = self._data[self._offset : self._offset + size]
            self._offset += len(chunk)
            return chunk

    fake_file = _FakeSmallUploadFile(file_bytes, "sucursales.xlsx")
    request = _request_without_content_length()

    filas = await _parse_excel_upload("sucursal", request, fake_file)

    assert filas == [{"nombre": "CALI NORTE"}]
