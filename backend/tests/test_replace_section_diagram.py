"""
Tests for the standalone "replace section diagram" endpoint.

Follows project pattern: pure unit / async unit tests using MagicMock / AsyncMock.
No live database or HTTP server required (same convention as
test_parts_manual_catalog.py's `load_section` tests).

Scenarios covered:
  replace_section_diagram — 403 (non-superadmin), 404 (unknown section),
                             422 (unsupported content-type), success (exact
                             bytes uploaded unchanged + diagram_url updated).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import replace_section_diagram, PARTS_BUCKET, _diagram_public_url
from app.models.parts_manual import PartsManualSection


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _superadmin(user_id: str | None = None) -> MagicMock:
    u = MagicMock()
    u.is_superadmin = True
    u.user_id = user_id or str(uuid.uuid4())
    return u


def _non_superadmin() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = False
    return u


def _image_file(content_type: str = "image/png", content: bytes = b"\x89PNG-fake-bytes") -> AsyncMock:
    f = AsyncMock()
    f.filename = "diagram.png"
    f.content_type = content_type
    f.read = AsyncMock(return_value=content)
    return f


def _section(model_code: str = "RENEGADE", section_code: str = "B01") -> MagicMock:
    s = MagicMock(spec=PartsManualSection)
    s.id = uuid.uuid4()
    s.model_code = model_code
    s.section_code = section_code
    s.diagram_url = None
    return s


# ---------------------------------------------------------------------------
# Async: replace_section_diagram
# ---------------------------------------------------------------------------

async def test_replace_diagram_403_when_not_superadmin():
    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock()

    with patch("app.api.v1.parts_manual._minio_client") as minio_client:
        with pytest.raises(HTTPException) as exc:
            await replace_section_diagram(
                str(uuid.uuid4()), _image_file(), db, _non_superadmin()
            )

    assert exc.value.status_code == 403
    db.get.assert_not_called()
    db.execute.assert_not_called()
    db.commit.assert_not_called()
    minio_client.assert_not_called()


async def test_replace_diagram_404_when_section_not_found():
    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=None)

    with patch("app.api.v1.parts_manual._minio_client") as minio_client:
        with pytest.raises(HTTPException) as exc:
            await replace_section_diagram(
                str(uuid.uuid4()), _image_file(), db, _superadmin()
            )

    assert exc.value.status_code == 404
    db.commit.assert_not_called()
    minio_client.assert_not_called()


async def test_replace_diagram_422_when_content_type_not_allowed():
    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock()

    with patch("app.api.v1.parts_manual._minio_client") as minio_client:
        with pytest.raises(HTTPException) as exc:
            await replace_section_diagram(
                str(uuid.uuid4()), _image_file(content_type="application/pdf"), db, _superadmin()
            )

    assert exc.value.status_code == 422
    db.get.assert_not_called()
    db.commit.assert_not_called()
    minio_client.assert_not_called()


async def test_replace_diagram_success_uploads_exact_bytes_and_updates_url():
    section = _section(model_code="RENEGADE", section_code="B01")
    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=section)
    db.commit = AsyncMock()

    raw_bytes = b"\x89PNG-exact-untouched-bytes"
    image_file = _image_file(content_type="image/png", content=raw_bytes)

    fake_client = MagicMock()
    fake_client.bucket_exists.return_value = True

    with patch("app.api.v1.parts_manual._minio_client", return_value=fake_client):
        result = await replace_section_diagram(
            str(section.id), image_file, db, _superadmin()
        )

    fake_client.put_object.assert_called_once()
    _, kwargs = fake_client.put_object.call_args
    assert kwargs["bucket_name"] == PARTS_BUCKET
    assert kwargs["object_name"] == "RENEGADE/B01.png"
    assert kwargs["data"].read() == raw_bytes
    assert kwargs["length"] == len(raw_bytes)

    expected_url = _diagram_public_url("RENEGADE/B01.png")
    assert section.diagram_url == expected_url
    assert result["diagram_url"] == expected_url
    db.commit.assert_called_once()
