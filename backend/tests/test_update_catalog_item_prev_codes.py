"""
Tests for the `prev_codes` collision guard in `update_catalog_item`
(PATCH /admin/catalog/{factory_part_number}) -- `sdd/parts-description-source-of-truth`
PR1, tasks 1.7/1.8 (design D6): only NEWLY-added `prev_codes` entries are
checked against live `PartsReference` primary keys elsewhere; pre-existing
colliding aliases (already in prod) are tolerated so old corruption doesn't
permanently 409 unrelated edits. The guard must sit ABOVE
`recalculate_part_cost` so a rejected collision never triggers an FOB
recalculation (financial-correctness risk #4 in the design).

Pure unit / async unit tests using MagicMock/AsyncMock, matching this
repo's established pattern for parts_manual endpoints (see
`test_replace_catalog_code.py`).
"""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import update_catalog_item, CatalogItemUpdate
from app.models.parts_manual import PartsReference


def _superadmin() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = True
    u.is_administrativo = False
    return u


def _administrativo() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = False
    u.is_administrativo = True
    return u


def _blocked() -> MagicMock:
    """A role blocked from `update_catalog_item` -- NOT superadmin, NOT
    administrativo (2026-08-24: administrativo now matches superadmin
    here). Both flags must be explicitly False: a bare MagicMock's un-set
    `.is_administrativo` attribute auto-vivifies as a truthy Mock, which
    would silently let this "blocked" actor through the widened OR gate."""
    u = MagicMock()
    u.is_superadmin = False
    u.is_administrativo = False
    return u


def _ref(factory_part_number="FPN-1", prev_codes=None) -> MagicMock:
    ref = MagicMock(spec=PartsReference)
    ref.factory_part_number = factory_part_number
    ref.prev_codes = prev_codes or []
    return ref


def _locked_select_result(return_value):
    """`assert_prev_codes_free`'s collision check now goes through
    `db.execute(select(...).with_for_update())`, not `db.get` -- these
    tests mock the `db.execute` result accordingly."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = return_value
    return result_mock


async def test_blocked_role_gets_403_with_no_db_touch():
    db = AsyncMock(spec=AsyncSession)
    payload = CatalogItemUpdate(description="Nueva descripcion")

    with pytest.raises(HTTPException) as exc:
        await update_catalog_item("FPN-1", payload, db, _blocked())

    assert exc.value.status_code == 403
    db.get.assert_not_called()
    db.commit.assert_not_called()


async def test_administrativo_can_update_catalog_item():
    """2026-08-24 business decision: administrativo now matches superadmin
    in Maestro de Partes, exactly."""
    ref = _ref(factory_part_number="FPN-1", prev_codes=[])
    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=ref)

    payload = CatalogItemUpdate(description="Nueva descripcion")

    result = await update_catalog_item("FPN-1", payload, db, _administrativo())

    assert result == {"ok": True}
    assert ref.description == "Nueva descripcion"
    db.commit.assert_awaited_once()


async def test_new_colliding_prev_code_rejected_409_no_recalculation():
    ref = _ref(factory_part_number="FPN-1", prev_codes=[])
    conflict = _ref(factory_part_number="OLD-2")

    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=ref)  # ref lookup
    db.execute = AsyncMock(return_value=_locked_select_result(conflict))  # collision lookup

    payload = CatalogItemUpdate(prev_codes=["OLD-2"])

    with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as recalc:
        with pytest.raises(HTTPException) as exc:
            await update_catalog_item("FPN-1", payload, db, _superadmin())

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "PREV_CODE_COLLISION"
    recalc.assert_not_called()
    db.commit.assert_not_called()


async def test_pre_existing_colliding_prev_code_tolerated_and_saves():
    ref = _ref(factory_part_number="FPN-1", prev_codes=[{"code": "OLD-2"}])

    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=ref)  # only the ref lookup -- OLD-2 isn't newly added

    payload = CatalogItemUpdate(prev_codes=["OLD-2"])

    with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as recalc:
        await update_catalog_item("FPN-1", payload, db, _superadmin())

    recalc.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert db.get.await_count == 1


async def test_guard_runs_before_recalculate_part_cost_call_order():
    """Mock call-order assertion (task 1.8's explicit requirement): the
    collision guard must execute before `recalculate_part_cost`, not after
    -- otherwise a rejected collision could still trigger an FOB
    recalculation before the exception unwinds."""
    ref = _ref(factory_part_number="FPN-1", prev_codes=[])
    call_order = []

    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=ref)

    async def fake_execute(stmt):
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        code = compiled.split("WHERE")[-1].split("= ")[-1].split("FOR UPDATE")[0].strip().strip("'")
        call_order.append(("collision_check", code))
        return _locked_select_result(None)

    db.execute = AsyncMock(side_effect=fake_execute)

    async def fake_recalc(*args, **kwargs):
        call_order.append(("recalculate_part_cost",))

    payload = CatalogItemUpdate(prev_codes=["NEW-1"])

    with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock(side_effect=fake_recalc)):
        await update_catalog_item("FPN-1", payload, db, _superadmin())

    assert call_order == [("collision_check", "NEW-1"), ("recalculate_part_cost",)]


async def test_duplicate_submitted_prev_codes_are_deduplicated_preserving_order():
    """Fix: a payload with repeated codes (e.g. from a sloppy client-side
    edit) must not persist duplicates in `prev_codes`. Order of first
    appearance is preserved."""
    ref = _ref(factory_part_number="FPN-1", prev_codes=[])

    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(return_value=ref)
    db.execute = AsyncMock(return_value=_locked_select_result(None))

    payload = CatalogItemUpdate(prev_codes=["B-1", "A-1", "B-1", "A-1", "C-1"])

    with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
        await update_catalog_item("FPN-1", payload, db, _superadmin())

    assert ref.prev_codes == [{"code": "B-1"}, {"code": "A-1"}, {"code": "C-1"}]
