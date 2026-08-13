"""
Tests for the confirm/dismiss suggestion endpoints
(`sdd/parts-description-source-of-truth` PR5, design D19/D20, tasks 5.8/5.9),
including the PR5 post-review fix pass:

- finding #1: dismiss must reject 409 `NO_ACTIVE_SUGGESTION` instead of
  silently stamping `suggestion_dismissed_at` when there is nothing to
  dismiss.
- finding #2: `_compute_current_suggestion` now delegates to
  `_resolve_catalog_suggestion` instead of reimplementing the same rule.
- finding #3: confirm's read is now a locking `SELECT ... FOR UPDATE`.
- finding #4: both endpoints wrap their body in the same
  log-then-clean-500 pattern `list_catalog` uses.

Pure unit / async unit tests using AsyncMock, matching
`tests/test_code_candidates.py`'s established pattern for parts_manual
endpoints (`TestLinkCodeCandidateEndpoint`/`TestCreateCodeCandidateEndpoint`)
and `tests/test_update_catalog_item_prev_codes.py`'s compiled-SQL assertion
style for the `with_for_update()` guard.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import (
    ConfirmSuggestionRequest,
    _compute_current_suggestion,
    confirm_catalog_suggestion,
    dismiss_catalog_suggestion,
)
from app.models.parts_manual import PartsReference


def _superadmin() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = True
    return u


def _non_superadmin() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = False
    return u


def _ref(factory_part_number="FPN-1", description_es_manual=None, suggestion_dismissed_at=None) -> MagicMock:
    ref = MagicMock(spec=PartsReference)
    ref.factory_part_number = factory_part_number
    ref.description_es_manual = description_es_manual
    ref.suggestion_dismissed_at = suggestion_dismissed_at
    ref.prev_codes = []
    return ref


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


# ---------------------------------------------------------------------------
# `_compute_current_suggestion` -- single-row recompute, now delegating to
# `_resolve_catalog_suggestion` (fix pass finding #2)
# ---------------------------------------------------------------------------

class TestComputeCurrentSuggestion:
    async def test_confirmed_manual_returns_no_suggestion(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1", description_es_manual="Filtro de aceite")

        text, has_suggestion, source = await _compute_current_suggestion(db, ref)

        assert (text, has_suggestion, source) == (None, False, None)
        db.execute.assert_not_called()

    async def test_exact_code_hit_returns_own_fpn_as_source(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))
        ref = _ref(factory_part_number="FPN-1")

        text, has_suggestion, source = await _compute_current_suggestion(db, ref)

        assert (text, has_suggestion, source) == ("Filtro de aceite", True, "FPN-1")

    async def test_alias_hit_when_exact_is_empty(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="Z1")
        ref.prev_codes = [{"code": "Z0"}]
        all_result = MagicMock()
        all_result.all.return_value = [("Z0", "Empaque de tapa")]
        db.execute = AsyncMock(side_effect=[_scalar_result(None), all_result])

        text, has_suggestion, source = await _compute_current_suggestion(db, ref)

        assert (text, has_suggestion, source) == ("Empaque de tapa", True, "Z0")

    async def test_nothing_found_returns_no_suggestion(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1")
        ref.prev_codes = []
        db.execute = AsyncMock(return_value=_scalar_result(None))

        text, has_suggestion, source = await _compute_current_suggestion(db, ref)

        assert (text, has_suggestion, source) == (None, False, None)

    async def test_respect_dismissal_true_hides_flag_but_keeps_text(self):
        """Dismiss's active-suggestion check (fix #1) needs
        `respect_dismissal=True` to see an already-dismissed row as having
        nothing left to dismiss, even though the underlying text is still
        deterministic (D20: dismiss never blanks the displayed name)."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))
        ref = _ref(factory_part_number="FPN-1", suggestion_dismissed_at=datetime(2026, 1, 1))

        text, has_suggestion, source = await _compute_current_suggestion(db, ref, respect_dismissal=True)

        assert text == "Filtro de aceite"
        assert has_suggestion is False
        assert source is None

    async def test_respect_dismissal_false_ignores_dismissal_for_confirm_staleness(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))
        ref = _ref(factory_part_number="FPN-1", suggestion_dismissed_at=datetime(2026, 1, 1))

        text, has_suggestion, source = await _compute_current_suggestion(db, ref)

        assert text == "Filtro de aceite"
        assert has_suggestion is True
        assert source == "FPN-1"

    async def test_whitespace_only_manual_ignored_falls_back_to_exact_hit(self):
        """PR5 fix pass #9 (CRITICAL): a whitespace-only
        `description_es_manual` (simulating pre-existing bad legacy data --
        write-time normalization now prevents NEW rows from ever reaching
        this state, but this function must still be correct for rows
        already in the DB before that fix shipped) must NOT be treated as a
        confirmed name. `manual and manual.strip()` already handles this
        correctly -- this test locks that behavior against regression and
        proves it matches what `_list_catalog_impl`'s fixed
        `COALESCE(NULLIF(TRIM(...), ''), ...)` now independently computes
        for the identical row (see
        `test_catalog_suggestion_badge.py::TestListCatalogWhitespaceManualLegacyData`)."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))
        ref = _ref(factory_part_number="FPN-1", description_es_manual="   ")

        text, has_suggestion, source = await _compute_current_suggestion(db, ref)

        assert text == "Filtro de aceite"
        assert has_suggestion is True
        assert source == "FPN-1"
        # Confirms the whitespace manual never short-circuited the "already
        # confirmed" branch -- the exact-hit query was actually issued.
        db.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# POST /parts/admin/catalog-confirm-suggestion/{fpn} -- task 5.8
# ---------------------------------------------------------------------------

class TestConfirmCatalogSuggestion:
    async def test_non_superadmin_403_no_db_lookup_writer_not_called(self):
        db = AsyncMock(spec=AsyncSession)
        payload = ConfirmSuggestionRequest(suggested_text="Filtro de aceite")

        with patch(
            "app.services.parts_description_service.set_description_es", new=AsyncMock()
        ) as set_desc_mock:
            with pytest.raises(HTTPException) as exc:
                await confirm_catalog_suggestion("FPN-1", payload, db, _non_superadmin())

        assert exc.value.status_code == 403
        db.execute.assert_not_called()
        set_desc_mock.assert_not_called()
        db.commit.assert_not_called()

    async def test_unknown_fpn_404(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=_scalar_result(None))
        payload = ConfirmSuggestionRequest(suggested_text="Filtro de aceite")

        with pytest.raises(HTTPException) as exc:
            await confirm_catalog_suggestion("FPN-X", payload, db, _superadmin())

        assert exc.value.status_code == 404

    async def test_read_uses_row_lock_for_update(self):
        """Fix pass finding #3: closes the race where a concurrent manual
        edit could be lost-update-overwritten by a suggestion confirm.
        Mirrors `test_update_catalog_item_prev_codes.py`'s compiled-SQL
        assertion style for `assert_prev_codes_free`'s `with_for_update()`
        guard."""
        ref = _ref(factory_part_number="FPN-1")
        captured: list[str] = []

        async def fake_execute(stmt):
            captured.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
            return _scalar_result(ref)

        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(side_effect=fake_execute)
        payload = ConfirmSuggestionRequest(suggested_text="Filtro de aceite")

        with patch(
            "app.api.v1.parts_manual._compute_current_suggestion",
            new=AsyncMock(return_value=("Filtro de aceite", True, "FPN-1")),
        ), patch(
            "app.services.parts_description_service.set_description_es", new=AsyncMock()
        ):
            await confirm_catalog_suggestion("FPN-1", payload, db, _superadmin())

        assert captured, "the locking read must go through db.execute"
        assert "FOR UPDATE" in captured[0]

    async def test_matching_text_calls_set_description_es_once_and_commits(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1")
        db.execute = AsyncMock(return_value=_scalar_result(ref))
        user = _superadmin()
        payload = ConfirmSuggestionRequest(suggested_text="Filtro de aceite")

        with patch(
            "app.api.v1.parts_manual._compute_current_suggestion",
            new=AsyncMock(return_value=("Filtro de aceite", True, "FPN-1")),
        ), patch(
            "app.services.parts_description_service.set_description_es", new=AsyncMock()
        ) as set_desc_mock:
            result = await confirm_catalog_suggestion("FPN-1", payload, db, user)

        set_desc_mock.assert_awaited_once_with(
            db, part_number="FPN-1", value="Filtro de aceite",
            model_applicable=None, current_user=user,
        )
        db.commit.assert_awaited_once()
        assert result == {"ok": True}

    async def test_stale_text_409_writer_not_called(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1")
        db.execute = AsyncMock(return_value=_scalar_result(ref))
        payload = ConfirmSuggestionRequest(suggested_text="Texto viejo")

        with patch(
            "app.api.v1.parts_manual._compute_current_suggestion",
            new=AsyncMock(return_value=("Texto nuevo", True, "FPN-1")),
        ), patch(
            "app.services.parts_description_service.set_description_es", new=AsyncMock()
        ) as set_desc_mock:
            with pytest.raises(HTTPException) as exc:
                await confirm_catalog_suggestion("FPN-1", payload, db, _superadmin())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SUGGESTION_STALE"
        set_desc_mock.assert_not_called()
        db.commit.assert_not_called()

    async def test_never_calls_recalculate_part_cost_fob_inert(self):
        """Exercises the REAL `set_description_es` (not mocked) so this
        actually locks the end-to-end write path, not just the endpoint's
        own body."""
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1")
        # 1st db.execute = the confirm endpoint's own locking read; 2nd =
        # `_find_reference_for_part_number`'s exact-code lookup (hits
        # immediately); 3rd = the mirror bulk UPDATE.
        db.execute = AsyncMock(side_effect=[_scalar_result(ref), _scalar_result(ref), MagicMock()])
        payload = ConfirmSuggestionRequest(suggested_text="Filtro de aceite")

        with patch(
            "app.api.v1.parts_manual._compute_current_suggestion",
            new=AsyncMock(return_value=("Filtro de aceite", True, "FPN-1")),
        ), patch(
            "app.services.pricing_service.recalculate_part_cost", new=AsyncMock()
        ) as recalc_mock:
            await confirm_catalog_suggestion("FPN-1", payload, db, _superadmin())

        assert ref.description_es_manual == "Filtro de aceite"
        recalc_mock.assert_not_called()

    async def test_unexpected_exception_returns_clean_500_and_logs(self):
        """Fix pass finding #4: an unexpected failure gets a clean 500 and
        a logged traceback with context, instead of an unlogged bare
        propagation."""
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1")
        db.execute = AsyncMock(return_value=_scalar_result(ref))
        payload = ConfirmSuggestionRequest(suggested_text="Filtro de aceite")

        with patch(
            "app.api.v1.parts_manual._compute_current_suggestion",
            new=AsyncMock(return_value=("Filtro de aceite", True, "FPN-1")),
        ), patch(
            "app.services.parts_description_service.set_description_es",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ), patch("app.api.v1.parts_manual.logger") as logger_mock:
            with pytest.raises(HTTPException) as exc:
                await confirm_catalog_suggestion("FPN-1", payload, db, _superadmin())

        assert exc.value.status_code == 500
        logger_mock.exception.assert_called_once()


# ---------------------------------------------------------------------------
# POST /parts/admin/catalog-dismiss-suggestion/{fpn} -- task 5.9
# ---------------------------------------------------------------------------

class TestDismissCatalogSuggestion:
    async def test_non_superadmin_403_no_db_lookup(self):
        db = AsyncMock(spec=AsyncSession)

        with pytest.raises(HTTPException) as exc:
            await dismiss_catalog_suggestion("FPN-1", db, _non_superadmin())

        assert exc.value.status_code == 403
        db.get.assert_not_called()
        db.commit.assert_not_called()

    async def test_unknown_fpn_404(self):
        db = AsyncMock(spec=AsyncSession)
        db.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await dismiss_catalog_suggestion("FPN-X", db, _superadmin())

        assert exc.value.status_code == 404

    async def test_sets_dismissed_at_and_commits_when_suggestion_active(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1")
        db.get = AsyncMock(return_value=ref)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))  # active exact-code suggestion

        before = datetime.utcnow()
        result = await dismiss_catalog_suggestion("FPN-1", db, _superadmin())

        assert ref.suggestion_dismissed_at >= before
        db.commit.assert_awaited_once()
        assert result == {"ok": True}

    async def test_no_active_suggestion_returns_409_and_leaves_dismissed_at_untouched(self):
        """Fix pass finding #1: a row with nothing to dismiss (here, a
        confirmed manual name -- no suggestion ever existed) is rejected
        409 `NO_ACTIVE_SUGGESTION` instead of silently stamping
        `suggestion_dismissed_at`."""
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1", description_es_manual="Filtro de aceite")
        db.get = AsyncMock(return_value=ref)

        with pytest.raises(HTTPException) as exc:
            await dismiss_catalog_suggestion("FPN-1", db, _superadmin())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "NO_ACTIVE_SUGGESTION"
        assert ref.suggestion_dismissed_at is None
        db.commit.assert_not_called()

    async def test_already_dismissed_second_call_returns_409_not_re_stamped(self):
        """Fix pass finding #1's other angle: a repeat dismiss call is no
        longer idempotent-200 -- the suggestion is already inactive, so it
        is rejected the same way as "never had one"."""
        db = AsyncMock(spec=AsyncSession)
        already_dismissed = datetime(2026, 1, 1)
        ref = _ref(factory_part_number="FPN-1", suggestion_dismissed_at=already_dismissed)
        db.get = AsyncMock(return_value=ref)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))

        with pytest.raises(HTTPException) as exc:
            await dismiss_catalog_suggestion("FPN-1", db, _superadmin())

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "NO_ACTIVE_SUGGESTION"
        assert ref.suggestion_dismissed_at == already_dismissed  # untouched, not re-stamped
        db.commit.assert_not_called()

    async def test_does_not_touch_description_es_manual(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1", description_es_manual=None)
        db.get = AsyncMock(return_value=ref)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))

        await dismiss_catalog_suggestion("FPN-1", db, _superadmin())

        assert ref.description_es_manual is None

    async def test_never_calls_recalculate_part_cost_fob_inert(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1")
        db.get = AsyncMock(return_value=ref)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))

        with patch(
            "app.services.pricing_service.recalculate_part_cost", new=AsyncMock()
        ) as recalc_mock:
            await dismiss_catalog_suggestion("FPN-1", db, _superadmin())

        recalc_mock.assert_not_called()

    async def test_unexpected_exception_returns_clean_500_and_logs(self):
        db = AsyncMock(spec=AsyncSession)
        ref = _ref(factory_part_number="FPN-1")
        db.get = AsyncMock(return_value=ref)
        db.execute = AsyncMock(return_value=_scalar_result("Filtro de aceite"))
        db.commit = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("app.api.v1.parts_manual.logger") as logger_mock:
            with pytest.raises(HTTPException) as exc:
                await dismiss_catalog_suggestion("FPN-1", db, _superadmin())

        assert exc.value.status_code == 500
        logger_mock.exception.assert_called_once()
