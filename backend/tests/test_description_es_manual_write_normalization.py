"""
Tests for write-time normalization of `description_es_manual` at the two
`parts_manual.py` endpoints that write it DIRECTLY, bypassing
`parts_description_service.set_description_es`
(`sdd/parts-description-source-of-truth` PR5 fix pass #9, CRITICAL finding
from a 5th independent review):

- `update_catalog_item` (PATCH /admin/catalog/{fpn})
- `replace_catalog_code` (POST /admin/catalog-replace/{fpn})

Without normalization, a whitespace-only submitted name is stored verbatim
and silently survives
`COALESCE(description_es_manual, spi_latest.description_es)` on the read
side (Postgres COALESCE only falls back on SQL NULL, not on `''`/
whitespace), corrupting the unconfirmed-name suggestion badge. See
`app.services.parts_description_service._normalize_manual_name`'s
docstring for the full rationale; `set_description_es` (the shared write
path used by every OTHER surface) already normalizes through that same
helper -- these two endpoints need their own call to it since they never
go through `set_description_es`.

Pure unit / async unit tests using MagicMock/AsyncMock, matching this
repo's established pattern (see `test_update_catalog_item_prev_codes.py`,
`test_replace_catalog_code.py`).
"""
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import (
    CatalogItemUpdate,
    ReplaceCodeRequest,
    replace_catalog_code,
    update_catalog_item,
)
from app.models.parts_manual import PartsReference


def _superadmin() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = True
    return u


class TestUpdateCatalogItemNormalization:
    async def test_whitespace_only_description_es_manual_stored_as_null(self):
        ref = MagicMock(spec=PartsReference)
        ref.factory_part_number = "FPN-1"

        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=ref)

        payload = CatalogItemUpdate(description_es_manual="   ")

        await update_catalog_item("FPN-1", payload, db, _superadmin())

        assert ref.description_es_manual is None

    async def test_leading_trailing_whitespace_is_trimmed(self):
        ref = MagicMock(spec=PartsReference)
        ref.factory_part_number = "FPN-1"

        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=ref)

        payload = CatalogItemUpdate(description_es_manual="  Filtro de aceite  ")

        await update_catalog_item("FPN-1", payload, db, _superadmin())

        assert ref.description_es_manual == "Filtro de aceite"

    async def test_real_value_still_persists_normally(self):
        ref = MagicMock(spec=PartsReference)
        ref.factory_part_number = "FPN-1"

        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=ref)

        payload = CatalogItemUpdate(description_es_manual="Filtro de aceite")

        await update_catalog_item("FPN-1", payload, db, _superadmin())

        assert ref.description_es_manual == "Filtro de aceite"


class TestReplaceCatalogCodeNormalization:
    def _existing_ref(self) -> MagicMock:
        ref = MagicMock()
        ref.factory_part_number = "OLD-001"
        ref.um_part_number = "UM-OLD"
        ref.description = "Old part"
        ref.description_es_manual = None
        ref.unit = "PZA"
        ref.prev_codes = []
        ref.rotation_class = None
        ref.avg_fob_cost = None
        ref.preliminary_fob = None
        ref.needs_price_review = False
        ref.total_fob_qty = None
        ref.last_cost_updated = None
        return ref

    async def test_whitespace_only_description_es_manual_stored_as_null(self):
        existing_ref = self._existing_ref()

        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(side_effect=[existing_ref, None, None])
        db.execute = AsyncMock()

        added = []
        db.add = MagicMock(side_effect=lambda obj: added.append(obj))

        payload = ReplaceCodeRequest(new_code="NEW-001", description_es_manual="   ")

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            await replace_catalog_code("OLD-001", payload, db, _superadmin())

        refs_added = [o for o in added if isinstance(o, PartsReference)]
        assert len(refs_added) == 1
        assert refs_added[0].description_es_manual is None
