"""
Tests for the not-yet-cataloged-code superadmin flow --
`sdd/parts-description-source-of-truth` PR3, Phase 3 (design D4/D5, spec's
"Not-Yet-Cataloged Code — Model-Scoped Candidate Search / Superadmin Path /
Non-Superadmin Block" requirements).

Covers:
- `_find_code_candidates`: read-only, model-scoped trigram search reusing
  `_detect_code_changes`'s JOIN chain (task 3.1)
- `GET /parts/admin/code-candidates` (task 3.2)
- `_approve_code_substitution`, extracted from `approve_review_task`
  (task 3.3, design D5), and `approve_review_task` regression-locked after
  the extraction
- `POST /parts/admin/code-candidates/link` (task 3.3) -- FOB: exactly one
  `recalculate_part_cost` call, with the surviving code
- `POST /parts/admin/code-candidates/create` (task 3.4) -- FOB: the new
  orphan code receives a cost
- Non-superadmin stays hard-blocked on every new surface (task 3.5) -- no
  local write, no queuing

Pure unit / async unit tests using MagicMock/AsyncMock, matching this
repo's established pattern for parts_manual endpoints (see
`test_replace_catalog_code.py`, `test_update_catalog_item_prev_codes.py`).
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import (
    _find_code_candidates,
    _approve_code_substitution,
    get_code_candidates,
    link_code_candidate,
    create_code_candidate,
    approve_review_task,
    LinkCodeCandidateRequest,
    CreateCodeCandidateRequest,
)
from app.models.parts_manual import PartsReference, PartsCodeReviewTask


def _superadmin() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = True
    u.is_administrativo = False
    u.user_id = "admin-1"
    return u


def _administrativo() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = False
    u.is_administrativo = True
    u.user_id = "admin-2"
    return u


def _non_superadmin() -> MagicMock:
    """A role blocked from `approve_review_task`/`reject_review_task` --
    NOT superadmin, NOT administrativo (2026-08-24: administrativo now
    matches superadmin here, see `_administrativo()`). Both flags must be
    explicitly False: a bare MagicMock's un-set `.is_administrativo`
    attribute auto-vivifies as a truthy Mock, which would silently let
    this "blocked" actor through the widened OR gate."""
    u = MagicMock()
    u.is_superadmin = False
    u.is_administrativo = False
    return u


def _ref(factory_part_number="FPN-1", **kwargs) -> MagicMock:
    ref = MagicMock(spec=PartsReference)
    ref.factory_part_number = factory_part_number
    ref.um_part_number = kwargs.get("um_part_number", "UM-1")
    ref.description = kwargs.get("description", "Part")
    ref.description_es_manual = kwargs.get("description_es_manual")
    ref.unit = kwargs.get("unit", "PZA")
    ref.prev_codes = kwargs.get("prev_codes", [])
    ref.rotation_class = kwargs.get("rotation_class")
    return ref


def _row(factory_part_number, description, description_es_manual, score):
    row = MagicMock()
    row.factory_part_number = factory_part_number
    row.description = description
    row.description_es_manual = description_es_manual
    row.score = score
    return row


# ---------------------------------------------------------------------------
# _find_code_candidates -- Task 3.1
# ---------------------------------------------------------------------------

class TestFindCodeCandidates:
    async def test_returns_empty_and_skips_similarity_query_when_no_spi_description(self):
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)  # no threshold config -> default
        first_result = MagicMock()
        first_result.first.return_value = None
        db.execute = AsyncMock(return_value=first_result)

        result = await _find_code_candidates(db, part_number="P1", model_applicable="MODELX")

        assert result == []
        db.execute.assert_awaited_once()

    async def test_scopes_query_to_model_and_returns_scored_candidates(self):
        db = AsyncMock(spec=AsyncSession)
        threshold_record = MagicMock()
        threshold_record.value = "0.85"
        db.get = AsyncMock(return_value=threshold_record)

        desc_result = MagicMock()
        desc_result.first.return_value = ("Filtro de aceite",)
        candidates_result = MagicMock()
        candidates_result.all.return_value = [
            _row("FPN-2", "Filtro de aceite viejo", "Filtro ES", 0.91),
        ]
        db.execute = AsyncMock(side_effect=[desc_result, candidates_result])

        result = await _find_code_candidates(db, part_number="P1", model_applicable="MODELX")

        assert result == [{
            "factory_part_number": "FPN-2",
            "description": "Filtro de aceite viejo",
            "description_es_manual": "Filtro ES",
            "similarity_score": 0.91,
        }]

        candidates_stmt, candidates_params = db.execute.call_args_list[1][0]
        compiled = str(candidates_stmt)
        assert "vehicle_catalog_map" in compiled
        assert "parts_manual_sections" in compiled
        assert "parts_manual_items" in compiled
        assert candidates_params["model"] == "MODELX"
        assert candidates_params["description"] == "Filtro de aceite"
        assert candidates_params["code"] == "P1"
        assert candidates_params["threshold"] == 0.85

    async def test_is_read_only_no_commit_no_add(self):
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)
        desc_result = MagicMock()
        desc_result.first.return_value = ("Desc",)
        candidates_result = MagicMock()
        candidates_result.all.return_value = []
        db.execute = AsyncMock(side_effect=[desc_result, candidates_result])

        await _find_code_candidates(db, part_number="P1", model_applicable="MODELX")

        db.commit.assert_not_called()
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# GET /parts/admin/code-candidates -- Task 3.2
# ---------------------------------------------------------------------------

class TestGetCodeCandidatesEndpoint:
    async def test_non_superadmin_403(self):
        db = AsyncMock(spec=AsyncSession)
        with pytest.raises(HTTPException) as exc:
            await get_code_candidates("P1", "MODELX", db, _non_superadmin())
        assert exc.value.status_code == 403
        db.execute.assert_not_called()

    async def test_superadmin_returns_candidates(self):
        db = AsyncMock(spec=AsyncSession)
        with patch(
            "app.api.v1.parts_manual._find_code_candidates",
            new=AsyncMock(return_value=[{
                "factory_part_number": "FPN-2",
                "description": "Filtro viejo",
                "description_es_manual": None,
                "similarity_score": 0.9,
            }]),
        ) as find_mock:
            result = await get_code_candidates("P1", "MODELX", db, _superadmin())

        find_mock.assert_awaited_once_with(db, part_number="P1", model_applicable="MODELX")
        assert len(result) == 1
        assert result[0].factory_part_number == "FPN-2"
        assert result[0].similarity_score == 0.9


# ---------------------------------------------------------------------------
# _approve_code_substitution -- Task 3.3 (extraction, design D5)
# ---------------------------------------------------------------------------

class TestApproveCodeSubstitution:
    async def test_existing_code_not_found_404(self):
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await _approve_code_substitution(
                db, existing_code="OLD-1", candidate_code="NEW-1", actor=_superadmin(),
            )
        assert exc.value.status_code == 404

    async def test_candidate_missing_creates_new_ref_inheriting_from_existing(self):
        existing_ref = _ref(
            factory_part_number="OLD-1", um_part_number="UM-OLD", description="Old part",
            description_es_manual="Vieja", unit="PZA", prev_codes=[], rotation_class="alta",
        )
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(side_effect=[existing_ref, None])  # existing, then candidate lookup miss
        added = []
        db.add = MagicMock(side_effect=lambda o: added.append(o))

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as recalc:
            result = await _approve_code_substitution(
                db, existing_code="OLD-1", candidate_code="NEW-1", actor=_superadmin(),
            )

        assert result in added
        assert result.factory_part_number == "NEW-1"
        assert result.um_part_number == "UM-OLD"
        assert result.rotation_class == "alta"
        assert result.description_es_manual == "Vieja"
        assert result.prev_codes[0] == {"code": "OLD-1"}
        db.delete.assert_awaited_once_with(existing_ref)
        recalc.assert_awaited_once_with(db, "NEW-1")

    async def test_candidate_exists_merges_prev_codes_and_inherits_missing_fields(self):
        existing_ref = _ref(
            factory_part_number="OLD-1", description_es_manual="Vieja", rotation_class="media",
        )
        candidate_ref = _ref(
            factory_part_number="NEW-1", description_es_manual=None, rotation_class=None,
            prev_codes=[],
        )
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(side_effect=[existing_ref, candidate_ref])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as recalc:
            result = await _approve_code_substitution(
                db, existing_code="OLD-1", candidate_code="NEW-1", actor=_superadmin(),
            )

        assert result is candidate_ref
        assert candidate_ref.prev_codes == [{"code": "OLD-1"}]
        assert candidate_ref.rotation_class == "media"
        assert candidate_ref.description_es_manual == "Vieja"
        db.delete.assert_awaited_once_with(existing_ref)
        recalc.assert_awaited_once_with(db, "NEW-1")

    async def test_does_not_commit_caller_responsibility(self):
        existing_ref = _ref(factory_part_number="OLD-1")
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(side_effect=[existing_ref, None])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            await _approve_code_substitution(
                db, existing_code="OLD-1", candidate_code="NEW-1", actor=_superadmin(),
            )

        db.commit.assert_not_called()

    async def test_logs_audit_trail_with_actor_and_codes(self, caplog):
        """Fix #2 (fix pass): money-moving merge must leave an audit trail
        recording who did it, keyed to actor.user_id (same identifier
        `approve_review_task` already stores as `resolved_by`)."""
        existing_ref = _ref(factory_part_number="OLD-1")
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(side_effect=[existing_ref, None])
        actor = _superadmin()

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            with caplog.at_level(logging.INFO, logger="app.api.v1.parts_manual"):
                await _approve_code_substitution(
                    db, existing_code="OLD-1", candidate_code="NEW-1", actor=actor,
                )

        assert "OLD-1" in caplog.text
        assert "NEW-1" in caplog.text
        assert "admin-1" in caplog.text


# ---------------------------------------------------------------------------
# approve_review_task regression -- must behave identically after extraction
# ---------------------------------------------------------------------------

class TestApproveReviewTaskRegression:
    async def test_non_superadmin_403(self):
        db = AsyncMock(spec=AsyncSession)
        with pytest.raises(HTTPException) as exc:
            await approve_review_task("task-1", db, _non_superadmin())
        assert exc.value.status_code == 403
        db.get.assert_not_called()

    async def test_administrativo_passes_the_guard(self):
        """2026-08-24 business decision: administrativo now matches
        superadmin in Maestro de Partes, exactly."""
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await approve_review_task(str(__import__("uuid").uuid4()), db, _administrativo())
        # Passes the role guard -- reaches the 404 (task not found) branch,
        # not a 403.
        assert exc.value.status_code == 404

    async def test_task_not_found_404(self):
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await approve_review_task(str(__import__("uuid").uuid4()), db, _superadmin())
        assert exc.value.status_code == 404

    async def test_happy_path_resolves_task_and_rejects_siblings(self):
        task = MagicMock(spec=PartsCodeReviewTask)
        task.id = "task-1"
        task.status = "pending"
        task.existing_code = "OLD-1"
        task.candidate_code = "NEW-1"

        with patch(
            "app.api.v1.parts_manual._approve_code_substitution", new=AsyncMock()
        ) as substitute_mock:
            db = AsyncMock(spec=AsyncSession)
            db.get = AsyncMock(return_value=task)
            db.execute = AsyncMock()

            result = await approve_review_task(str(__import__("uuid").uuid4()), db, _superadmin())

        substitute_mock.assert_awaited_once()
        _, call_kwargs = substitute_mock.call_args
        assert call_kwargs["existing_code"] == "OLD-1"
        assert call_kwargs["candidate_code"] == "NEW-1"
        assert task.status == "approved"
        assert task.resolved_by == "admin-1"
        db.execute.assert_awaited_once()  # sibling-rejection update
        db.commit.assert_awaited_once()
        assert result == {"ok": True, "new_code": "NEW-1"}


# ---------------------------------------------------------------------------
# POST /parts/admin/code-candidates/link -- Task 3.3
# ---------------------------------------------------------------------------

class TestLinkCodeCandidateEndpoint:
    async def test_non_superadmin_403_no_substitution_attempted(self):
        db = AsyncMock(spec=AsyncSession)
        payload = LinkCodeCandidateRequest(part_number="P1", existing_code="FPN-2")
        with patch(
            "app.api.v1.parts_manual._approve_code_substitution", new=AsyncMock()
        ) as substitute_mock:
            with pytest.raises(HTTPException) as exc:
                await link_code_candidate(payload, db, _non_superadmin())
        assert exc.value.status_code == 403
        substitute_mock.assert_not_called()
        db.commit.assert_not_called()

    async def test_superadmin_links_and_saves_pending_description(self):
        candidate_ref = _ref(factory_part_number="P1")
        db = AsyncMock(spec=AsyncSession)
        payload = LinkCodeCandidateRequest(
            part_number="P1", existing_code="FPN-2", description_es_manual="Filtro nuevo",
        )

        with patch(
            "app.api.v1.parts_manual._approve_code_substitution",
            new=AsyncMock(return_value=candidate_ref),
        ) as substitute_mock, patch(
            "app.services.parts_description_service.set_description_es", new=AsyncMock()
        ) as set_desc_mock:
            user = _superadmin()
            result = await link_code_candidate(payload, db, user)

        substitute_mock.assert_awaited_once_with(
            db, existing_code="FPN-2", candidate_code="P1", actor=user,
        )
        set_desc_mock.assert_awaited_once_with(
            db, part_number="P1", value="Filtro nuevo", model_applicable=None, current_user=user,
        )
        db.commit.assert_awaited_once()
        assert result == {"ok": True, "factory_part_number": "P1"}

    async def test_no_pending_description_skips_write_path(self):
        candidate_ref = _ref(factory_part_number="P1")
        db = AsyncMock(spec=AsyncSession)
        payload = LinkCodeCandidateRequest(part_number="P1", existing_code="FPN-2")

        with patch(
            "app.api.v1.parts_manual._approve_code_substitution",
            new=AsyncMock(return_value=candidate_ref),
        ), patch(
            "app.services.parts_description_service.set_description_es", new=AsyncMock()
        ) as set_desc_mock:
            await link_code_candidate(payload, db, _superadmin())

        set_desc_mock.assert_not_called()

    async def test_self_link_rejected_with_clean_error_no_db_interaction(self):
        """Fix #1 (fix pass): linking a code to itself must fail cleanly
        BEFORE `_approve_code_substitution`/`db.delete`/`db.commit` are ever
        reached -- no partial DB interaction attempted."""
        db = AsyncMock(spec=AsyncSession)
        payload = LinkCodeCandidateRequest(part_number="P1", existing_code="P1")
        with patch(
            "app.api.v1.parts_manual._approve_code_substitution", new=AsyncMock()
        ) as substitute_mock:
            with pytest.raises(HTTPException) as exc:
                await link_code_candidate(payload, db, _superadmin())

        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "SELF_LINK_NOT_ALLOWED"
        substitute_mock.assert_not_called()
        db.get.assert_not_called()
        db.delete.assert_not_called()
        db.commit.assert_not_called()

    async def test_fob_recalculation_happens_exactly_once_with_surviving_code(self):
        """FOB risk (task 3.3): the link path moves money -- assert
        `recalculate_part_cost` fires exactly once, keyed to the surviving
        code, end-to-end through the real `_approve_code_substitution` (not
        mocked here, unlike the tests above)."""
        existing_ref = _ref(factory_part_number="FPN-2")
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(side_effect=[existing_ref, None])
        payload = LinkCodeCandidateRequest(part_number="P1", existing_code="FPN-2")

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as recalc:
            await link_code_candidate(payload, db, _superadmin())

        recalc.assert_awaited_once_with(db, "P1")


# ---------------------------------------------------------------------------
# POST /parts/admin/code-candidates/create -- Task 3.4
# ---------------------------------------------------------------------------

class TestCreateCodeCandidateEndpoint:
    async def test_non_superadmin_403(self):
        db = AsyncMock(spec=AsyncSession)
        payload = CreateCodeCandidateRequest(part_number="P1")
        with pytest.raises(HTTPException) as exc:
            await create_code_candidate(payload, db, _non_superadmin())
        assert exc.value.status_code == 403
        db.get.assert_not_called()

    async def test_code_already_exists_409(self):
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=_ref(factory_part_number="P1"))
        payload = CreateCodeCandidateRequest(part_number="P1")
        with pytest.raises(HTTPException) as exc:
            await create_code_candidate(payload, db, _superadmin())
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "CODE_ALREADY_EXISTS"

    async def test_superadmin_creates_orphan_reference_and_gets_a_cost(self):
        """FOB risk (task 3.4): the new orphan code must receive a cost --
        intended behavior, assert it. `description` is resolved server-side
        from the order's own `spare_part_items` row (fix #3), not accepted
        from the payload."""
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)  # no existing ref for P1
        added = []
        db.add = MagicMock(side_effect=lambda o: added.append(o))
        payload = CreateCodeCandidateRequest(part_number="P1")

        with patch(
            "app.api.v1.parts_manual._latest_spare_part_description",
            new=AsyncMock(return_value="Filtro"),
        ), patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as recalc:
            result = await create_code_candidate(payload, db, _superadmin())

        assert len(added) == 1
        new_ref = added[0]
        assert new_ref.factory_part_number == "P1"
        assert new_ref.description == "Filtro"
        recalc.assert_awaited_once_with(db, "P1")
        db.commit.assert_awaited_once()
        assert result == {"ok": True, "factory_part_number": "P1"}

    async def test_description_resolved_server_side_from_order_not_blank(self):
        """Fix #3: the created reference's `description` is populated from
        the order's actual stored `spare_part_items.description`, not
        blank -- `_find_code_candidates`'s own description source, re-used
        server-side instead of trusting a client-supplied English text."""
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)
        added = []
        db.add = MagicMock(side_effect=lambda o: added.append(o))
        payload = CreateCodeCandidateRequest(part_number="P1")

        with patch(
            "app.api.v1.parts_manual._latest_spare_part_description",
            new=AsyncMock(return_value="Descripción real del pedido"),
        ) as desc_mock, patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            await create_code_candidate(payload, db, _superadmin())

        desc_mock.assert_awaited_once_with(db, "P1")
        assert added[0].description == "Descripción real del pedido"
        assert added[0].description != ""

    async def test_mirrors_spanish_name_via_set_description_es(self):
        """Fix #4: `create_code_candidate` must mirror the Spanish name the
        same way `link_code_candidate` does -- through `set_description_es`
        (which fans out to `spare_part_items.description_es`), not just by
        passing it into `create_reference`'s constructor."""
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()
        payload = CreateCodeCandidateRequest(part_number="P1", description_es_manual="Filtro nuevo")
        user = _superadmin()

        with patch(
            "app.api.v1.parts_manual._latest_spare_part_description",
            new=AsyncMock(return_value="Oil filter"),
        ), patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()), patch(
            "app.services.parts_description_service.set_description_es", new=AsyncMock()
        ) as set_desc_mock:
            await create_code_candidate(payload, db, user)

        set_desc_mock.assert_awaited_once_with(
            db, part_number="P1", value="Filtro nuevo", model_applicable=None, current_user=user,
        )

    async def test_no_description_es_manual_skips_mirror_write(self):
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()
        payload = CreateCodeCandidateRequest(part_number="P1")

        with patch(
            "app.api.v1.parts_manual._latest_spare_part_description",
            new=AsyncMock(return_value="Oil filter"),
        ), patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()), patch(
            "app.services.parts_description_service.set_description_es", new=AsyncMock()
        ) as set_desc_mock:
            await create_code_candidate(payload, db, _superadmin())

        set_desc_mock.assert_not_called()

    async def test_integrity_error_race_converted_to_clean_409(self):
        """Fix #5: the pre-check passes but the actual insert loses a
        `factory_part_number` PK race to a concurrent request -- must
        surface as the same clean 409 CODE_ALREADY_EXISTS, not a raw
        `IntegrityError`/unhandled 500."""
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)  # pre-check: not found
        db.rollback = AsyncMock()
        payload = CreateCodeCandidateRequest(part_number="P1")

        with patch(
            "app.api.v1.parts_manual._latest_spare_part_description",
            new=AsyncMock(return_value="Oil filter"),
        ), patch(
            "app.services.parts_description_service.create_reference",
            new=AsyncMock(side_effect=IntegrityError("insert", {}, Exception("duplicate key"))),
        ):
            with pytest.raises(HTTPException) as exc:
                await create_code_candidate(payload, db, _superadmin())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "CODE_ALREADY_EXISTS"
        db.rollback.assert_awaited_once()
        db.commit.assert_not_called()

    async def test_logs_audit_trail_on_creation(self, caplog):
        """Fix #2 (fix pass): creating a brand-new reference must leave an
        audit trail recording who created it and for which code."""
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()
        payload = CreateCodeCandidateRequest(part_number="P1")
        actor = _superadmin()

        with patch(
            "app.api.v1.parts_manual._latest_spare_part_description",
            new=AsyncMock(return_value="Oil filter"),
        ), patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            with caplog.at_level(logging.INFO, logger="app.api.v1.parts_manual"):
                await create_code_candidate(payload, db, actor)

        assert "P1" in caplog.text
        assert "admin-1" in caplog.text


# ---------------------------------------------------------------------------
# Non-superadmin hard block on uncatalogued codes -- Task 3.5
# (spec: "Not-Yet-Cataloged Code — Non-Superadmin Block")
# ---------------------------------------------------------------------------

class TestNonSuperadminBlockedOnUncatalogedCode:
    async def test_candidate_search_endpoint_blocked(self):
        db = AsyncMock(spec=AsyncSession)
        with pytest.raises(HTTPException) as exc:
            await get_code_candidates("P4", "MODELY", db, _non_superadmin())
        assert exc.value.status_code == 403
        db.execute.assert_not_called()

    async def test_link_endpoint_blocked_no_local_write(self):
        db = AsyncMock(spec=AsyncSession)
        payload = LinkCodeCandidateRequest(part_number="P4", existing_code="FPN-9")
        with pytest.raises(HTTPException) as exc:
            await link_code_candidate(payload, db, _non_superadmin())
        assert exc.value.status_code == 403
        db.get.assert_not_called()
        db.add.assert_not_called()
        db.commit.assert_not_called()

    async def test_create_endpoint_blocked_no_local_write(self):
        db = AsyncMock(spec=AsyncSession)
        payload = CreateCodeCandidateRequest(part_number="P4")
        with pytest.raises(HTTPException) as exc:
            await create_code_candidate(payload, db, _non_superadmin())
        assert exc.value.status_code == 403
        db.get.assert_not_called()
        db.add.assert_not_called()

    async def test_original_write_path_still_blocked_before_reaching_catalog_lookup(self):
        """Regression: `set_description_es` gates on `assert_name_editor`
        BEFORE the `PART_NOT_IN_CATALOG` lookup (PR1), so a non-superadmin
        editing an uncatalogued code never even reaches this PR's candidate
        flow -- they get 403 NAME_EDIT_FORBIDDEN, not 409, and nothing is
        written or queued anywhere."""
        from app.services import parts_description_service as svc

        db = AsyncMock(spec=AsyncSession)
        with patch.object(svc, "_find_reference_for_part_number", new=AsyncMock()) as find_mock:
            with pytest.raises(HTTPException) as exc:
                await svc.set_description_es(
                    db, part_number="P4", value="Nuevo", model_applicable="MODELY",
                    current_user=_non_superadmin(),
                )
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "NAME_EDIT_FORBIDDEN"
        find_mock.assert_not_called()
        db.execute.assert_not_called()
        db.add.assert_not_called()
