"""
Tests for `replace_catalog_code` (POST /admin/catalog-replace/{factory_part_number}).

Regression test for a user-reported bug: replacing a part's factory code
silently wiped rotation_class/avg_fob_cost/preliminary_fob/needs_price_review
because the new PartsReference row never copied them from the old one before
it was deleted. Pure unit / async unit tests using MagicMock/AsyncMock,
matching this repo's established pattern for parts_manual endpoints (see
test_parts_manual_catalog.py).
"""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import replace_catalog_code, ReplaceCodeRequest
from app.models.parts_manual import PartsReference


def _superadmin() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = True
    return u


def _existing_ref() -> MagicMock:
    ref = MagicMock()
    ref.factory_part_number = "OLD-001"
    ref.um_part_number = "UM-OLD"
    ref.description = "Old part"
    ref.description_es_manual = None
    ref.unit = "PZA"
    ref.prev_codes = []
    ref.rotation_class = "alta"
    ref.avg_fob_cost = 12.5
    ref.preliminary_fob = 11.0
    ref.needs_price_review = True
    ref.total_fob_qty = 40
    ref.last_cost_updated = "2026-06-01T00:00:00"
    return ref


async def test_replace_catalog_code_carries_over_rotation_and_pricing_fields():
    """Regression: replacing a factory code must NOT reset rotation_class,
    avg_fob_cost, preliminary_fob, needs_price_review, total_fob_qty, or
    last_cost_updated -- these used to be silently dropped because the new
    PartsReference row never copied them from the old one before it got
    deleted (the endpoint only copied um_part_number/description/unit)."""
    existing_ref = _existing_ref()

    db = AsyncMock(spec=AsyncSession)
    db.get = AsyncMock(side_effect=[
        existing_ref,  # existing_ref lookup
        None,          # conflict check for new_code -- no collision
        None,          # old PartCatalog lookup -- none, skip migration branch
    ])
    db.execute = AsyncMock()  # item-redirect + review-task-close updates

    added = []
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))

    payload = ReplaceCodeRequest(new_code="NEW-001")

    with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
        await replace_catalog_code("OLD-001", payload, db, _superadmin())

    refs_added = [o for o in added if isinstance(o, PartsReference)]
    assert len(refs_added) == 1
    new_ref = refs_added[0]

    assert new_ref.factory_part_number == "NEW-001"
    assert new_ref.rotation_class == "alta"
    assert new_ref.avg_fob_cost == 12.5
    assert new_ref.preliminary_fob == 11.0
    assert new_ref.needs_price_review is True
    assert new_ref.total_fob_qty == 40
    assert new_ref.last_cost_updated == "2026-06-01T00:00:00"

    db.delete.assert_awaited_once_with(existing_ref)


async def test_replace_catalog_code_403_when_not_superadmin():
    db = AsyncMock(spec=AsyncSession)
    non_superadmin = MagicMock()
    non_superadmin.is_superadmin = False

    with pytest.raises(HTTPException) as exc:
        await replace_catalog_code("OLD-001", ReplaceCodeRequest(new_code="NEW-001"), db, non_superadmin)

    assert exc.value.status_code == 403
    db.get.assert_not_called()
