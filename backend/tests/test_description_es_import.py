"""
Tests for `import_description_es` (POST /admin/description-es-import,
`parts_manual.py`).

Feature: bulk-upload Spanish translations for catalog references via Excel,
mirroring `import_rotation`'s exact shape (column-alias matching, per-row
error tracking, `{"updated", "skipped", "errors"}` response). The one
business rule that matters most: a bulk upload must NEVER overwrite a
translation someone already typed by hand via the inline-edit cell -- only
fills references where `description_es_manual` is currently NULL (same
"don't clobber already-classified data" safety `import_rotation` already
has for `rotation_class`).

Mirrors `test_backfill_costs.py`'s harness: `FakeAsyncSession` (plain
`def test_...` + `asyncio.run(...)`, no live DB, no HTTP layer). The file
upload itself is a real `.xlsx` built with `openpyxl` (already a hard
dependency), read through a minimal `FakeUploadFile` double -- same
approach `tests/distributor_deliveries/conftest.py`'s `FakeUploadFile`
uses, redefined locally here to avoid a cross-package test import.
"""
import asyncio
import io

import openpyxl

from app.api.v1.parts_manual import import_description_es
from app.models.parts_manual import PartsReference

from tests.imports.conftest import FakeAsyncSession, make_imports_editor


class FakeUploadFile:
    """Minimal double for `fastapi.UploadFile` -- the endpoint only ever
    awaits `.read()`."""

    def __init__(self, content: bytes):
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _xlsx(headers: list[str], rows: list[list]) -> FakeUploadFile:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return FakeUploadFile(buf.getvalue())


def _ref(factory_part_number="ABC-001", description_es_manual=None):
    return PartsReference(
        factory_part_number=factory_part_number,
        um_part_number=factory_part_number,
        description="Test part",
        description_es_manual=description_es_manual,
    )


def _superadmin():
    return make_imports_editor(role="superadmin")


def test_non_superadmin_non_administrativo_gets_403_with_no_db_touch():
    """2026-08-24 business decision: administrativo now matches superadmin
    here (see `test_administrativo_can_import_description_es` below) --
    technician stays blocked, same as before."""
    file = _xlsx(["part_code", "description_es"], [["ABC-001", "Tornillo"]])
    fake_db = FakeAsyncSession(execute_queue=[])
    try:
        asyncio.run(import_description_es(file, fake_db, make_imports_editor(role="technician")))
        assert False, "expected HTTPException"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_client_gets_403_with_no_db_touch():
    file = _xlsx(["part_code", "description_es"], [["ABC-001", "Tornillo"]])
    fake_db = FakeAsyncSession(execute_queue=[])
    try:
        asyncio.run(import_description_es(file, fake_db, make_imports_editor(role="client")))
        assert False, "expected HTTPException"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_administrativo_can_import_description_es():
    """2026-08-24 business decision: administrativo now matches superadmin
    in Maestro de Partes, exactly."""
    file = _xlsx(["part_code", "description_es"], [["ABC-001", "Tornillo M6"]])
    ref = _ref("ABC-001", description_es_manual=None)
    fake_db = FakeAsyncSession(execute_queue=[[ref]])

    result = asyncio.run(import_description_es(file, fake_db, make_imports_editor(role="administrativo")))

    assert result == {"updated": 1, "skipped": 0, "errors": []}


def test_fills_description_es_when_missing():
    # A raw sa_update(...) core statement, same as import_rotation -- the
    # fake session's queued item count simulates rowcount, it doesn't mutate
    # the Python object (a real DB would apply it directly to the row).
    file = _xlsx(["part_code", "description_es"], [["ABC-001", "Tornillo M6"]])
    ref = _ref("ABC-001", description_es_manual=None)
    fake_db = FakeAsyncSession(execute_queue=[[ref]])  # 1 queued row => rowcount=1

    result = asyncio.run(import_description_es(file, fake_db, _superadmin()))

    assert result == {"updated": 1, "skipped": 0, "errors": []}


def test_never_overwrites_an_existing_manual_translation():
    """The SQL-level `.where(description_es_manual.is_(None))` filter means
    an already-translated reference simply doesn't match -- rowcount 0."""
    file = _xlsx(["part_code", "description_es"], [["ABC-002", "Arandela"]])
    fake_db = FakeAsyncSession(execute_queue=[[]])  # already-translated ref never matches, rowcount=0

    result = asyncio.run(import_description_es(file, fake_db, _superadmin()))

    assert result == {"updated": 0, "skipped": 1, "errors": [{"row": 2, "code": "ABC-002", "reason": "part_not_found"}]}


def test_missing_part_code_in_a_row_is_skipped():
    file = _xlsx(["part_code", "description_es"], [[None, "Tuerca"]])
    fake_db = FakeAsyncSession(execute_queue=[])

    result = asyncio.run(import_description_es(file, fake_db, _superadmin()))

    assert result == {"updated": 0, "skipped": 1, "errors": [{"row": 2, "code": None, "reason": "missing_part_code"}]}


def test_missing_description_value_in_a_row_is_skipped():
    file = _xlsx(["part_code", "description_es"], [["ABC-003", None]])
    fake_db = FakeAsyncSession(execute_queue=[])

    result = asyncio.run(import_description_es(file, fake_db, _superadmin()))

    assert result == {"updated": 0, "skipped": 1, "errors": [{"row": 2, "code": "ABC-003", "reason": "missing_description_es"}]}


def test_code_with_no_matching_reference_is_skipped():
    file = _xlsx(["part_code", "description_es"], [["NOPE", "Algo"]])
    fake_db = FakeAsyncSession(execute_queue=[[]])

    result = asyncio.run(import_description_es(file, fake_db, _superadmin()))

    assert result == {"updated": 0, "skipped": 1, "errors": [{"row": 2, "code": "NOPE", "reason": "part_not_found"}]}


def test_blank_rows_are_skipped_silently_not_counted_as_errors():
    file = _xlsx(["part_code", "description_es"], [[None, None], ["ABC-004", "Perno"]])
    ref = _ref("ABC-004", description_es_manual=None)
    fake_db = FakeAsyncSession(execute_queue=[[ref]])

    result = asyncio.run(import_description_es(file, fake_db, _superadmin()))

    assert result == {"updated": 1, "skipped": 0, "errors": []}


def test_missing_required_columns_returns_422():
    file = _xlsx(["some_other_column"], [["x"]])
    fake_db = FakeAsyncSession(execute_queue=[])
    try:
        asyncio.run(import_description_es(file, fake_db, _superadmin()))
        assert False, "expected HTTPException"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
    assert fake_db.executed_statements == []


def test_recognizes_alternate_column_aliases():
    file = _xlsx(["codigo", "traduccion"], [["ABC-005", "Rodamiento"]])
    ref = _ref("ABC-005", description_es_manual=None)
    fake_db = FakeAsyncSession(execute_queue=[[ref]])

    result = asyncio.run(import_description_es(file, fake_db, _superadmin()))

    assert result == {"updated": 1, "skipped": 0, "errors": []}
