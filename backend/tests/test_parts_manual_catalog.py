"""
Tests for catalog section upload and history endpoints.

Follows project pattern: pure unit / async unit tests using MagicMock / AsyncMock.
No live database or HTTP server required.

Scenarios covered:
  _parse_section_filename  — pure unit, all filename formats
  load_section             — 403, 422 (no parts), 409 (section exists), force+snapshot
  get_section_history      — 403, list returned
  restore_section          — 404, items recreated from snapshot
"""
import os
import uuid
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import (
    _parse_section_filename,
    load_section,
    get_section_history,
    restore_section_from_history,
)
from app.models.parts_manual import (
    PartsManualSection,
    PartsManualItem,
    PartsManualSectionHistory,
    PartsReference,
)


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


def _upload_file(filename: str = "MODEL_B01_FRAME.pdf") -> AsyncMock:
    f = AsyncMock()
    f.filename = filename
    f.read = AsyncMock(return_value=b"%PDF-fake")
    return f


def _scalar(value):
    """Mock that supports .scalar_one_or_none() and .scalar_one()."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalar_one.return_value = value
    return r


def _scalars(items: list):
    """Mock that supports .scalars().all()."""
    r = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    r.scalars.return_value = scalars_mock
    return r


# ---------------------------------------------------------------------------
# Pure unit: _parse_section_filename
# ---------------------------------------------------------------------------

class TestParseSectionFilename:

    def test_three_part_format_extracts_code_and_name(self):
        code, name = _parse_section_filename("RENEGADE 200 SPORT_B1_FRAME.pdf")
        assert code == "B1"
        assert name == "FRAME"

    def test_multiple_name_parts_joined_with_slash(self):
        code, name = _parse_section_filename(
            "RENEGADE 200 SPORT_B12_REAR FENDER_REAR TURN SIGNAL.pdf"
        )
        assert code == "B12"
        assert name == "REAR FENDER / REAR TURN SIGNAL"

    def test_two_part_format(self):
        code, name = _parse_section_filename("B01_BODY COMP FRAME.pdf")
        assert code == "B01"
        assert name == "BODY COMP FRAME"

    def test_dash_separator_format(self):
        code, name = _parse_section_filename("B01 - AIR CLEANER ASSY.pdf")
        assert code == "B01"
        assert name == "AIR CLEANER ASSY"

    def test_space_only_separator(self):
        code, name = _parse_section_filename("B04 FOOTREST & PEDALS.pdf")
        assert code == "B04"
        assert name == "FOOTREST & PEDALS"


# ---------------------------------------------------------------------------
# Async: load_section
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_pdf(tmp_path):
    """Real writable fd + path — satisfies os.fdopen(fd, 'wb') inside the endpoint."""
    p = tmp_path / "section.pdf"
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    return fd, str(p)


async def test_load_section_403_when_not_superadmin():
    pdf = _upload_file()
    db = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc:
        await load_section(pdf, "RENEGADE", "Renegade 200", False, db, _non_superadmin())

    assert exc.value.status_code == 403
    db.execute.assert_not_called()


async def test_load_section_422_when_pdf_yields_no_parts(tmp_pdf):
    fd, path = tmp_pdf
    db = AsyncMock(spec=AsyncSession)
    # `vehicle_model_exists` check runs unconditionally BEFORE parsing —
    # queue a truthy result so it passes without masking the parse failure.
    db.execute = AsyncMock(side_effect=[_scalar("Renegade 200")])

    with patch("app.api.v1.parts_manual._parse_parts_table", return_value=[]), \
         patch("tempfile.mkstemp", return_value=(fd, path)), \
         patch("os.unlink"):

        with pytest.raises(HTTPException) as exc:
            await load_section(_upload_file(), "RENEGADE", "Renegade 200", False, db, _superadmin())

    assert exc.value.status_code == 422
    assert "No se detectaron partes" in exc.value.detail
    # DB is touched exactly once (the vehicle_model_exists check), but no
    # further section/snapshot queries run once parsing fails.
    assert db.execute.await_count == 1


async def test_load_section_409_when_section_has_data_and_no_force(tmp_pdf):
    fd, path = tmp_pdf

    existing = MagicMock()
    existing.id = uuid.uuid4()

    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=[
        _scalar("Renegade 200"),  # vehicle_model_exists check
        _scalar(existing),   # select section
        _scalar(5),          # count items in section
    ])

    parts = [{"factory_part_number": "REF001", "order_num": "1", "description": "Frame"}]

    with patch("app.api.v1.parts_manual._parse_parts_table", return_value=parts), \
         patch("tempfile.mkstemp", return_value=(fd, path)), \
         patch("os.unlink"):

        with pytest.raises(HTTPException) as exc:
            await load_section(_upload_file(), "RENEGADE", "Renegade 200", False, db, _superadmin())

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "section_exists"
    assert exc.value.detail["existing_parts"] == 5
    # Snapshot must NOT be created — the section was not overwritten
    db.add.assert_not_called()


async def test_load_section_force_saves_snapshot_before_overwriting(tmp_pdf):
    fd, path = tmp_pdf

    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.model_code = "RENEGADE"
    existing.section_code = "B01"
    existing.section_name = "FRAME"
    existing.diagram_url = None

    old_item = MagicMock()
    old_item.order_num = "1"
    old_item.factory_part_number = "REF001"

    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=None)   # SystemConfig/logo → None, refs → None, catalog map → None
    db.execute = AsyncMock(side_effect=[
        _scalar("Renegade 200"),    # vehicle_model_exists check
        _scalar(existing),          # check if section exists
        _scalars([old_item]),       # snapshot: items in old section
        MagicMock(),                # sa_delete section
    ])

    added = []
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))

    parts = [{"factory_part_number": "REF001", "order_num": "1", "description": "Frame"}]

    with patch("app.api.v1.parts_manual._parse_parts_table", return_value=parts), \
         patch("tempfile.mkstemp", return_value=(fd, path)), \
         patch("os.unlink"), \
         patch("fitz.open", side_effect=Exception("no fitz in test")), \
         patch("app.api.v1.parts_manual._minio_client", side_effect=Exception("no minio in test")):

        result = await load_section(_upload_file(), "RENEGADE", "Renegade 200", True, db, _superadmin())

    # One PartsManualSectionHistory object must have been added
    history_added = [o for o in added if isinstance(o, PartsManualSectionHistory)]
    assert len(history_added) == 1, "Expected exactly one snapshot saved to history"

    snap = history_added[0]
    assert snap.model_code == "RENEGADE"
    assert snap.section_code == "B01"
    assert snap.parts_count == 1
    assert snap.snapshot == [{"order_num": "1", "factory_part_number": "REF001"}]

    # New section and its items must have been added
    sections_added = [o for o in added if isinstance(o, PartsManualSection)]
    items_added = [o for o in added if isinstance(o, PartsManualItem)]
    assert len(sections_added) == 1
    assert len(items_added) == 1

    assert result.parts_loaded == 1


async def test_load_section_force_reload_preserves_existing_reference_fields(tmp_pdf):
    """The guarantee behind "reloading a catalog never resets a part's
    rotation_class/price/etc": load_section only INSERTS a new
    PartsReference when none exists for that factory_part_number -- it
    must never mutate an existing one. Regression pin for a user report
    (91 Rockville 200 parts appearing "sin rotación" after a reload); a
    manual code audit found no path that resets these fields on reload,
    this test locks that invariant so a future change can't silently
    break it."""
    fd, path = tmp_pdf

    existing_section = MagicMock()
    existing_section.id = uuid.uuid4()
    existing_section.model_code = "RENEGADE"
    existing_section.section_code = "B01"
    existing_section.section_name = "FRAME"
    existing_section.diagram_url = None

    old_item = MagicMock()
    old_item.order_num = "1"
    old_item.factory_part_number = "REF001"

    existing_ref = MagicMock()
    existing_ref.rotation_class = "alta"
    existing_ref.avg_fob_cost = 12.5
    existing_ref.preliminary_fob = None
    existing_ref.description_es_manual = "Marco"
    existing_ref.needs_price_review = True

    def fake_get(model, key=None):
        return existing_ref if model is PartsReference else None

    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(side_effect=fake_get)
    db.execute = AsyncMock(side_effect=[
        _scalar("Renegade 200"),    # vehicle_model_exists check
        _scalar(existing_section),  # check if section exists
        _scalars([old_item]),       # snapshot: items in old section
        MagicMock(),                # sa_delete section
    ])

    added = []
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))

    parts = [{"factory_part_number": "REF001", "order_num": "1", "description": "Frame"}]

    with patch("app.api.v1.parts_manual._parse_parts_table", return_value=parts), \
         patch("tempfile.mkstemp", return_value=(fd, path)), \
         patch("os.unlink"), \
         patch("fitz.open", side_effect=Exception("no fitz in test")), \
         patch("app.api.v1.parts_manual._minio_client", side_effect=Exception("no minio in test")):

        await load_section(_upload_file(), "RENEGADE", "Renegade 200", True, db, _superadmin())

    # No NEW PartsReference must be created for a code that already has one.
    refs_added = [o for o in added if isinstance(o, PartsReference)]
    assert refs_added == [], "load_section must not insert a duplicate PartsReference when one already exists"

    # The EXISTING reference's fields must be untouched -- proves load_section
    # never mutates rotation_class/price/etc on reload.
    assert existing_ref.rotation_class == "alta"
    assert existing_ref.avg_fob_cost == 12.5
    assert existing_ref.description_es_manual == "Marco"
    assert existing_ref.needs_price_review is True


# ---------------------------------------------------------------------------
# Async: get_section_history
# ---------------------------------------------------------------------------

async def test_get_section_history_403_when_not_superadmin():
    db = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc:
        await get_section_history("RENEGADE", db, _non_superadmin())

    assert exc.value.status_code == 403


async def test_get_section_history_returns_list_for_model():
    db = AsyncMock(spec=AsyncSession)

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.model_code = "RENEGADE"
    entry.section_code = "B01"
    entry.section_name = "FRAME"
    entry.parts_count = 3
    entry.replaced_at = datetime(2026, 6, 26, 12, 0, 0)

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [entry]
    db.execute = AsyncMock(return_value=result_mock)

    data = await get_section_history("RENEGADE", db, _superadmin())

    assert len(data) == 1
    assert data[0]["section_code"] == "B01"
    assert data[0]["parts_count"] == 3
    assert data[0]["replaced_at"] == "2026-06-26T12:00:00"


# ---------------------------------------------------------------------------
# Async: restore_section_from_history
# ---------------------------------------------------------------------------

async def test_restore_section_404_when_history_entry_missing():
    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await restore_section_from_history("RENEGADE", str(uuid.uuid4()), db, _superadmin())

    assert exc.value.status_code == 404


async def test_restore_section_recreates_items_from_snapshot():
    db = AsyncMock(spec=AsyncSession)

    history_id = uuid.uuid4()
    entry = MagicMock()
    entry.model_code = "RENEGADE"
    entry.section_code = "B01"
    entry.section_name = "FRAME"
    entry.diagram_url = None
    entry.snapshot = [
        {"order_num": "1", "factory_part_number": "REF001"},
        {"order_num": "2", "factory_part_number": "REF002"},
    ]

    ref1, ref2 = MagicMock(spec=PartsReference), MagicMock(spec=PartsReference)

    # db.get call order: [PartsManualSectionHistory, PartsReference/REF001, PartsReference/REF002]
    db.get = AsyncMock(side_effect=[entry, ref1, ref2])
    # db.execute: check for current section (returns None — no existing section to snapshot)
    db.execute = AsyncMock(return_value=_scalar(None))

    added = []
    db.add = MagicMock(side_effect=lambda o: added.append(o))
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    result = await restore_section_from_history("RENEGADE", str(history_id), db, _superadmin())

    assert result["restored_parts"] == 2
    assert result["section_code"] == "B01"

    sections = [o for o in added if isinstance(o, PartsManualSection)]
    items = [o for o in added if isinstance(o, PartsManualItem)]
    assert len(sections) == 1
    assert len(items) == 2
    db.commit.assert_called_once()
