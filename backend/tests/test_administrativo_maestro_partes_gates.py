"""
Tests for the 2026-08-24 business decision: `administrativo` now matches
`superadmin`, exactly, across Maestro de Partes (`parts_manual.py`).

Covers the role-gate boundary (RED before / GREEN after) for every widened
endpoint that had NO existing test coverage at all:
  - GET  /parts/admin/vehicle-models      (list_vehicle_models)
  - GET  /parts/admin/catalog             (list_catalog)
  - GET  /parts/admin/catalog/export      (export_catalog_excel)
  - DELETE /parts/admin/catalog/part/{fpn} (delete_catalog_part)
  - POST /parts/admin/rotation-import     (import_rotation)
  - GET  /parts/admin/coverage            (get_coverage)
  - GET  /parts/admin/coverage/unordered  (export_unordered)
  - POST /parts/admin/review-tasks/{id}/reject (reject_review_task)

Each endpoint's OWN business logic already has coverage elsewhere (or is
out of scope for this change) -- this file exercises only the guard that
actually changed: `if not (current_user.is_superadmin or
current_user.is_administrativo): raise HTTPException(403, ...)`.

`list_catalog`/`export_catalog_excel` delegate their real query work to
`_list_catalog_impl`, which is mocked out here (their heavy, unrelated SQL
already has other coverage) -- this isolates the guard being tested from
that complexity, same principle `test_backfill_costs.py` and siblings
apply via `FakeAsyncSession`.
"""
import asyncio
import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl
import pytest
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import (
    CatalogListResult,
    delete_catalog_part,
    export_catalog_excel,
    export_unordered,
    get_coverage,
    import_rotation,
    list_catalog,
    list_vehicle_models,
    reject_review_task,
)
from app.models.parts_manual import PartsCodeReviewTask, PartsReference

from tests.imports.conftest import FakeAsyncSession, make_imports_editor


def _superadmin():
    return make_imports_editor(role="superadmin")


def _administrativo():
    return make_imports_editor(role="administrativo")


def _blocked():
    """A role that must stay blocked by every gate in this file --
    `technician` is never superadmin, administrativo, nor imports_editor."""
    return make_imports_editor(role="technician")


class FakeUploadFile:
    """Minimal double for `fastapi.UploadFile` -- the endpoint only ever
    awaits `.read()` (same double `test_description_es_import.py` uses)."""

    def __init__(self, content: bytes):
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _rotation_xlsx(headers: list[str], rows: list[list]) -> FakeUploadFile:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return FakeUploadFile(buf.getvalue())


# ---------------------------------------------------------------------------
# GET /parts/admin/vehicle-models
# ---------------------------------------------------------------------------

def test_list_vehicle_models_blocked_role_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])
    with pytest.raises(Exception) as exc:
        asyncio.run(list_vehicle_models(fake_db, _blocked()))
    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_list_vehicle_models_administrativo_succeeds():
    fake_db = FakeAsyncSession(execute_queue=[[]])
    result = asyncio.run(list_vehicle_models(fake_db, _administrativo()))
    assert result == []


# ---------------------------------------------------------------------------
# GET /parts/admin/catalog
# ---------------------------------------------------------------------------

def test_list_catalog_blocked_role_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])
    with pytest.raises(Exception) as exc:
        asyncio.run(list_catalog(current_user=_blocked(), db=fake_db))
    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_list_catalog_administrativo_passes_the_guard():
    fake_db = FakeAsyncSession(execute_queue=[])
    with patch(
        "app.api.v1.parts_manual._list_catalog_impl",
        new=AsyncMock(return_value=CatalogListResult(total=0, items=[])),
    ) as impl_mock:
        result = asyncio.run(list_catalog(current_user=_administrativo(), db=fake_db))
    impl_mock.assert_awaited_once()
    assert result == CatalogListResult(total=0, items=[])


# ---------------------------------------------------------------------------
# GET /parts/admin/catalog/export
# ---------------------------------------------------------------------------

def test_export_catalog_excel_blocked_role_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])
    with pytest.raises(Exception) as exc:
        asyncio.run(export_catalog_excel(current_user=_blocked(), db=fake_db))
    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_export_catalog_excel_administrativo_passes_the_guard():
    fake_db = FakeAsyncSession(execute_queue=[])
    with patch(
        "app.api.v1.parts_manual._list_catalog_impl",
        new=AsyncMock(return_value=CatalogListResult(total=0, items=[])),
    ):
        result = asyncio.run(export_catalog_excel(current_user=_administrativo(), db=fake_db))
    assert isinstance(result, StreamingResponse)


# ---------------------------------------------------------------------------
# DELETE /parts/admin/catalog/part/{fpn}
# ---------------------------------------------------------------------------

def _ref(factory_part_number="ABC-001", avg_fob_cost=None):
    return PartsReference(
        factory_part_number=factory_part_number,
        um_part_number=factory_part_number,
        description="Test part",
        prev_codes=[],
        avg_fob_cost=avg_fob_cost,
    )


def test_delete_catalog_part_blocked_role_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])
    with pytest.raises(Exception) as exc:
        asyncio.run(delete_catalog_part("ABC-001", fake_db, _blocked()))
    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_delete_catalog_part_administrativo_succeeds():
    # `PartsReference`'s primary key is `factory_part_number`, not `id` --
    # `FakeAsyncSession.get()` only keys on `.id`, so this uses `AsyncMock`
    # instead, matching `test_catalog_confirm_dismiss_suggestion.py`'s
    # established pattern for this same model.
    ref = _ref("ABC-001", avg_fob_cost=None)
    history_count_result = MagicMock()
    history_count_result.scalar_one.return_value = 0
    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(side_effect=[ref, None])  # 1) the reference itself  2) PartCatalog -- no row
    db.execute = AsyncMock(side_effect=[
        history_count_result,  # history_count via scalar_one()
        MagicMock(),            # sa_delete(PartsManualItem) -- unused result
        MagicMock(),            # sa_delete(PartsCodeReviewTask) -- unused result
    ])
    db.delete = AsyncMock()

    asyncio.run(delete_catalog_part("ABC-001", db, _administrativo()))

    db.delete.assert_awaited_once_with(ref)
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# POST /parts/admin/rotation-import
# ---------------------------------------------------------------------------

def test_import_rotation_blocked_role_gets_403_with_no_db_touch():
    file = _rotation_xlsx(["codigo", "rotacion"], [])
    fake_db = FakeAsyncSession(execute_queue=[])
    with pytest.raises(Exception) as exc:
        asyncio.run(import_rotation(file, fake_db, _blocked()))
    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_import_rotation_administrativo_succeeds():
    file = _rotation_xlsx(["codigo", "rotacion"], [])  # header only -- nothing to process
    fake_db = FakeAsyncSession(execute_queue=[])
    result = asyncio.run(import_rotation(file, fake_db, _administrativo()))
    assert result == {"updated": 0, "skipped": 0, "errors": []}


# ---------------------------------------------------------------------------
# GET /parts/admin/coverage
# ---------------------------------------------------------------------------

def test_get_coverage_blocked_role_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])
    with pytest.raises(Exception) as exc:
        asyncio.run(get_coverage(None, fake_db, _blocked()))
    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_get_coverage_administrativo_succeeds():
    # `get_coverage` calls `db.execute(stmt, params)` (2 positional args) --
    # `FakeAsyncSession` only accepts `stmt`, so this uses `AsyncMock`
    # instead, matching `test_code_candidates.py`'s established pattern.
    coverage_result = MagicMock()
    coverage_result.all.return_value = []
    sin_result = MagicMock()
    sin_result.scalar_one.return_value = 0
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=[coverage_result, sin_result])

    result = asyncio.run(get_coverage(None, db, _administrativo()))

    assert result.sin_clasificar == 0
    assert result.buckets == []


# ---------------------------------------------------------------------------
# GET /parts/admin/coverage/unordered
# ---------------------------------------------------------------------------

def test_export_unordered_blocked_role_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])
    with pytest.raises(Exception) as exc:
        asyncio.run(export_unordered(None, fake_db, _blocked()))
    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_export_unordered_administrativo_succeeds():
    # `export_unordered` calls `db.execute(stmt, params)` (2 positional
    # args) -- `FakeAsyncSession` only accepts `stmt`, so this uses
    # `AsyncMock` instead, matching `test_code_candidates.py`'s established
    # pattern.
    rows_result = MagicMock()
    rows_result.all.return_value = []
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(return_value=rows_result)

    result = asyncio.run(export_unordered(None, db, _administrativo()))

    assert isinstance(result, StreamingResponse)


# ---------------------------------------------------------------------------
# POST /parts/admin/review-tasks/{id}/reject
# ---------------------------------------------------------------------------

def test_reject_review_task_blocked_role_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])
    with pytest.raises(Exception) as exc:
        asyncio.run(reject_review_task(str(uuid.uuid4()), fake_db, _blocked()))
    assert getattr(exc.value, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_reject_review_task_administrativo_succeeds():
    task = PartsCodeReviewTask(
        id=uuid.uuid4(),
        existing_code="OLD-1",
        candidate_code="NEW-1",
        similarity_score=0.9,
        status="pending",
    )
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[task])
    actor = _administrativo()

    result = asyncio.run(reject_review_task(str(task.id), fake_db, actor))

    assert result == {"ok": True}
    assert task.status == "rejected"
    assert task.resolved_by == actor.user_id
