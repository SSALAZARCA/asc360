"""
tests/services/test_parts_description_service.py -- RED/GREEN tests for
`app.services.parts_description_service` (`sdd/parts-description-source-of-truth`
PR1, design D1-D10): the shared write path every one of the 4 surfaces will
route through, and `assert_name_editor`, the superadmin-only gate reused
everywhere (D10).

Pure unit / async unit tests using MagicMock/AsyncMock, matching this repo's
established pattern for parts_manual/pricing_service tests (see
`test_replace_catalog_code.py`, `test_pricing_service.py`).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import parts_description_service as svc
from app.models.parts_manual import PartsReference


def _user(role: str) -> MagicMock:
    u = MagicMock()
    u.is_superadmin = role == "superadmin"
    # Explicitly set, not left to MagicMock auto-vivification: an unset
    # `.is_administrativo` attribute on a bare MagicMock auto-vivifies as a
    # truthy Mock, which would silently let EVERY role through
    # `assert_name_editor`'s widened `is_superadmin or is_administrativo`
    # OR gate (2026-08-24 business decision) regardless of the role string.
    u.is_administrativo = role == "administrativo"
    u.role = role
    return u


def _ref(factory_part_number="FPN-1", description_es_manual=None, prev_codes=None) -> MagicMock:
    ref = MagicMock(spec=PartsReference)
    ref.factory_part_number = factory_part_number
    ref.description_es_manual = description_es_manual
    ref.prev_codes = prev_codes or []
    return ref


# ---------------------------------------------------------------------------
# assert_name_editor -- Task 1.1/1.2
# ---------------------------------------------------------------------------

NON_SUPERADMIN_ROLES = ["technician", "jefe_taller", "proveedor", "parts_dealer", "client"]


class TestAssertNameEditor:
    def test_superadmin_passes(self):
        svc.assert_name_editor(_user("superadmin"))  # must not raise

    def test_administrativo_passes(self):
        """2026-08-24 business decision: administrativo now matches
        superadmin in Maestro de Partes, exactly -- this gate is shared
        across the confirm/dismiss-suggestion endpoints AND the
        Repuestos-tab field-level name gate (`imports.py`), see
        `tests/imports/test_update_spare_part_item_name_field_gate.py`."""
        svc.assert_name_editor(_user("administrativo"))  # must not raise

    @pytest.mark.parametrize("role", NON_SUPERADMIN_ROLES)
    def test_non_superadmin_raises_403_name_edit_forbidden(self, role):
        with pytest.raises(HTTPException) as exc:
            svc.assert_name_editor(_user(role))
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "NAME_EDIT_FORBIDDEN"


# ---------------------------------------------------------------------------
# set_description_es -- Task 1.3
# ---------------------------------------------------------------------------

class TestSetDescriptionEs:
    async def test_non_superadmin_raises_before_any_lookup(self):
        db = AsyncMock(spec=AsyncSession)
        with patch.object(svc, "_find_reference_for_part_number", new=AsyncMock()) as find_mock:
            with pytest.raises(HTTPException) as exc:
                await svc.set_description_es(
                    db,
                    part_number="FPN-1",
                    value="Nuevo",
                    model_applicable=None,
                    current_user=_user("technician"),
                )
            assert exc.value.status_code == 403
            assert exc.value.detail["code"] == "NAME_EDIT_FORBIDDEN"
            find_mock.assert_not_called()
        db.execute.assert_not_called()

    async def test_administrativo_passes_the_guard_and_writes(self):
        """2026-08-24 business decision: administrativo now matches
        superadmin here."""
        ref = _ref(factory_part_number="FPN-1")
        db = AsyncMock(spec=AsyncSession)
        with patch.object(svc, "_find_reference_for_part_number", new=AsyncMock(return_value=ref)):
            result = await svc.set_description_es(
                db,
                part_number="FPN-1",
                value="Filtro nuevo",
                model_applicable=None,
                current_user=_user("administrativo"),
            )
        assert result is ref
        assert ref.description_es_manual == "Filtro nuevo"

    async def test_miss_raises_409_part_not_in_catalog_no_mirror_write(self):
        db = AsyncMock(spec=AsyncSession)
        with patch.object(svc, "_find_reference_for_part_number", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await svc.set_description_es(
                    db,
                    part_number="GHOST-1",
                    value="Nuevo",
                    model_applicable=None,
                    current_user=_user("superadmin"),
                )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "PART_NOT_IN_CATALOG"
        db.execute.assert_not_called()

    async def test_hit_writes_manual_and_mirrors_fpn_plus_prev_codes(self):
        ref = _ref(factory_part_number="FPN-1", prev_codes=[{"code": "OLD-1"}, "LEGACY-1"])
        db = AsyncMock(spec=AsyncSession)
        with patch.object(svc, "_find_reference_for_part_number", new=AsyncMock(return_value=ref)):
            result = await svc.set_description_es(
                db,
                part_number="ANY-ALIAS",
                value="Filtro nuevo",
                model_applicable=None,
                current_user=_user("superadmin"),
            )
        assert result is ref
        assert ref.description_es_manual == "Filtro nuevo"
        db.execute.assert_awaited_once()
        stmt = db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "spare_part_items" in compiled
        assert "'Filtro nuevo'" in compiled
        assert "'FPN-1'" in compiled
        assert "'OLD-1'" in compiled
        assert "'LEGACY-1'" in compiled

    async def test_hit_never_triggers_fob_recalculation(self):
        ref = _ref()
        db = AsyncMock(spec=AsyncSession)
        with patch.object(svc, "_find_reference_for_part_number", new=AsyncMock(return_value=ref)), \
             patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as recalc:
            await svc.set_description_es(
                db,
                part_number="FPN-1",
                value="X",
                model_applicable=None,
                current_user=_user("superadmin"),
            )
        recalc.assert_not_called()

    async def test_whitespace_only_value_is_stored_as_null_not_whitespace(self):
        """PR5 fix pass #9 (CRITICAL, 5th review): a whitespace-only submitted
        name must be persisted as SQL `NULL`, never as a literal `'   '`
        string -- otherwise it silently survives
        `COALESCE(description_es_manual, spi_latest.description_es)` on the
        read side (Postgres COALESCE only falls back on NULL, not on
        empty/whitespace strings)."""
        ref = _ref(factory_part_number="FPN-1")
        db = AsyncMock(spec=AsyncSession)
        with patch.object(svc, "_find_reference_for_part_number", new=AsyncMock(return_value=ref)):
            await svc.set_description_es(
                db,
                part_number="FPN-1",
                value="   ",
                model_applicable=None,
                current_user=_user("superadmin"),
            )
        assert ref.description_es_manual is None
        db.execute.assert_awaited_once()
        stmt = db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # The mirror write must also carry NULL, not a whitespace string --
        # a bound NULL parameter compiles to the literal `NULL`, never
        # `'   '`.
        assert "'   '" not in compiled
        assert "NULL" in compiled

    async def test_leading_trailing_whitespace_is_trimmed(self):
        ref = _ref(factory_part_number="FPN-1")
        db = AsyncMock(spec=AsyncSession)
        with patch.object(svc, "_find_reference_for_part_number", new=AsyncMock(return_value=ref)):
            await svc.set_description_es(
                db,
                part_number="FPN-1",
                value="  Filtro de aceite  ",
                model_applicable=None,
                current_user=_user("superadmin"),
            )
        assert ref.description_es_manual == "Filtro de aceite"


# ---------------------------------------------------------------------------
# _normalize_manual_name -- PR5 fix pass #9
# ---------------------------------------------------------------------------

class TestNormalizeManualName:
    def test_none_stays_none(self):
        assert svc._normalize_manual_name(None) is None

    def test_empty_string_becomes_none(self):
        assert svc._normalize_manual_name("") is None

    def test_whitespace_only_becomes_none(self):
        assert svc._normalize_manual_name("   ") is None
        assert svc._normalize_manual_name("\t\n") is None

    def test_real_value_is_trimmed(self):
        assert svc._normalize_manual_name("  Filtro de aceite  ") == "Filtro de aceite"

    def test_real_value_without_padding_is_unchanged(self):
        assert svc._normalize_manual_name("Filtro de aceite") == "Filtro de aceite"


# ---------------------------------------------------------------------------
# assert_prev_codes_free -- Task 1.4
# ---------------------------------------------------------------------------

def _select_result(return_value):
    """Builds the `db.execute(...)` return value for a
    `select(...).with_for_update()` collision-check call."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = return_value
    return result_mock


class TestAssertPrevCodesFree:
    async def test_no_newly_added_codes_skips_lookup_entirely(self):
        db = AsyncMock(spec=AsyncSession)
        await svc.assert_prev_codes_free(
            db, factory_part_number="FPN-1", submitted=["OLD-1"], existing=[{"code": "OLD-1"}],
        )
        db.execute.assert_not_called()

    async def test_pre_existing_colliding_code_is_tolerated(self):
        """D6: a code already present in `existing` is NOT re-checked even if
        it collides elsewhere -- only newly-added codes are validated."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_select_result(None))
        await svc.assert_prev_codes_free(
            db, factory_part_number="FPN-1", submitted=["OLD-1", "OLD-2"], existing=["OLD-1"],
        )
        db.execute.assert_awaited_once()
        stmt = db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "'OLD-2'" in compiled

    async def test_new_collision_raises_409_prev_code_collision(self):
        conflict = _ref(factory_part_number="OLD-2")
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_select_result(conflict))
        with pytest.raises(HTTPException) as exc:
            await svc.assert_prev_codes_free(
                db, factory_part_number="FPN-1", submitted=["OLD-2"], existing=[],
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "PREV_CODE_COLLISION"

    async def test_new_code_with_no_conflict_passes(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_select_result(None))
        await svc.assert_prev_codes_free(
            db, factory_part_number="FPN-1", submitted=["NEW-1"], existing=[],
        )

    async def test_collision_check_uses_locking_read(self):
        """Financial-risk fix: the collision check must use a `SELECT ...
        FOR UPDATE` locking read, not a plain unlocked `db.get`, to close
        the TOCTOU window between this check and the caller's later
        commit (mirrors the pessimistic-lock idiom used by
        `remisiones.py`'s `despachar` endpoint)."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_select_result(None))
        await svc.assert_prev_codes_free(
            db, factory_part_number="FPN-1", submitted=["NEW-1"], existing=[],
        )
        db.execute.assert_awaited_once()
        stmt = db.execute.call_args[0][0]
        assert "FOR UPDATE" in str(stmt)

    async def test_multi_collision_report_is_deterministic(self):
        """Fix for non-deterministic reporting: with multiple new colliding
        codes, the FIRST one checked/reported must be the lexicographically
        smallest, not whichever Python's set hash order happens to yield."""
        db = AsyncMock(spec=AsyncSession)
        seen_codes = []

        async def fake_execute(stmt):
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            where_clause = compiled.split("WHERE")[-1]
            code = where_clause.split("= ")[-1].split("FOR UPDATE")[0].strip().strip("'")
            seen_codes.append(code)
            return _select_result(_ref(factory_part_number=code))

        db.execute = AsyncMock(side_effect=fake_execute)
        with pytest.raises(HTTPException) as exc:
            await svc.assert_prev_codes_free(
                db, factory_part_number="FPN-1", submitted=["ZED-1", "ALPHA-1"], existing=[],
            )
        assert seen_codes == ["ALPHA-1"]
        assert exc.value.detail["detail"].startswith("El código 'ALPHA-1'")


# ---------------------------------------------------------------------------
# create_reference -- Task 1.5
# ---------------------------------------------------------------------------

class TestCreateReference:
    async def test_with_source_ref_follows_historied_creation_pattern(self):
        source = _ref(factory_part_number="OLD-1", prev_codes=[{"code": "ANCIENT-1"}])
        source.um_part_number = "UM-OLD"
        source.unit = "PZA"
        source.rotation_class = "alta"

        db = AsyncMock(spec=AsyncSession)
        added = []
        db.add = MagicMock(side_effect=lambda o: added.append(o))

        result = await svc.create_reference(
            db,
            factory_part_number="NEW-1",
            description="Filtro",
            description_es_manual="Filtro ES",
            source_ref=source,
        )

        assert result in added
        assert result.factory_part_number == "NEW-1"
        assert result.um_part_number == "UM-OLD"
        assert result.unit == "PZA"
        assert result.rotation_class == "alta"
        assert result.description == "Filtro"
        assert result.description_es_manual == "Filtro ES"
        assert result.prev_codes[0] == {"code": "OLD-1"}
        assert {"code": "ANCIENT-1"} in result.prev_codes
        db.flush.assert_awaited_once()

    async def test_without_source_ref_creates_orphan_reference(self):
        db = AsyncMock(spec=AsyncSession)
        added = []
        db.add = MagicMock(side_effect=lambda o: added.append(o))

        result = await svc.create_reference(
            db,
            factory_part_number="ORPHAN-1",
            description="Tornillo",
            description_es_manual=None,
        )

        assert result in added
        assert result.factory_part_number == "ORPHAN-1"
        assert result.description == "Tornillo"
        assert result.description_es_manual is None
        assert result.prev_codes == []
        db.flush.assert_awaited_once()

    async def test_whitespace_only_description_es_manual_stored_as_null(self):
        """PR5 fix pass #9: `create_code_candidate`'s orphan path must never
        persist a whitespace-only name, matching `set_description_es`."""
        db = AsyncMock(spec=AsyncSession)
        added = []
        db.add = MagicMock(side_effect=lambda o: added.append(o))

        result = await svc.create_reference(
            db,
            factory_part_number="ORPHAN-2",
            description="Tornillo",
            description_es_manual="   ",
        )

        assert result.description_es_manual is None

    async def test_whitespace_only_with_source_ref_falls_back_to_source_value(self):
        """A whitespace-only submission normalizes to `None`, which then
        follows the same "inherit from source_ref" branch a genuine `None`
        already takes -- it does not blank out the matched candidate's
        existing confirmed name."""
        source = _ref(factory_part_number="OLD-1", description_es_manual="Nombre confirmado")
        db = AsyncMock(spec=AsyncSession)
        db.add = MagicMock()

        result = await svc.create_reference(
            db,
            factory_part_number="NEW-2",
            description="Filtro",
            description_es_manual="   ",
            source_ref=source,
        )

        assert result.description_es_manual == "Nombre confirmado"


# ---------------------------------------------------------------------------
# resolve_names -- Task 1.6
# ---------------------------------------------------------------------------

class TestResolveNames:
    async def test_returns_only_non_empty_manual_names_exact_code(self):
        db = AsyncMock(spec=AsyncSession)
        rows = [("FPN-1", "Filtro"), ("FPN-2", None), ("FPN-3", "")]
        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute = AsyncMock(return_value=result_mock)

        result = await svc.resolve_names(db, ["FPN-1", "FPN-2", "FPN-3"])

        assert result == {"FPN-1": "Filtro"}

    async def test_empty_input_short_circuits_without_querying(self):
        db = AsyncMock(spec=AsyncSession)
        result = await svc.resolve_names(db, [])
        assert result == {}
        db.execute.assert_not_called()
