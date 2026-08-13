"""
Tests for the unconfirmed-name suggestion badge sub-feature
(`sdd/parts-description-source-of-truth` PR5, design D15-D17).

Pure unit / async unit tests using AsyncMock, matching this repo's
established pattern for `_list_catalog_impl` (see
`tests/test_parts_manual_catalog.py`, `tests/test_code_candidates.py`).
No live DATABASE_URL exists in this suite -- the `only_suggested` SQL
predicate's structural correctness is asserted by compiling the statement
to text (the same technique `test_code_candidates.py` uses for
`_find_code_candidates`'s raw-SQL EXISTS block), not by executing it
against real data.

Column order of the inner select as of PR5 (`_list_catalog_impl`):
  0 fpn, 1 description, 2 description_es (COALESCE), 3 public_price,
  4 section_code, 5 section_name, 6 model_code, 7 vehicle_model_pattern,
  8 task_id, 9 candidate_code, 10 score, 11 avg_fob_cost, 12
  rotation_class, 13 needs_price_review, 14 preliminary_fob, 15
  description_es_manual (NEW), 16 suggestion_dismissed_at (NEW).

PR5 fix pass #9 (CRITICAL, 5th independent review): column 2's COALESCE
changed from `COALESCE(description_es_manual, spi_latest.description_es)`
to `COALESCE(NULLIF(TRIM(description_es_manual), ''),
spi_latest.description_es)` -- Postgres COALESCE only falls back on SQL
NULL, never on `''`/whitespace, so a whitespace-only manual value used to
survive verbatim into this column instead of falling back. These tests
build `rows` by hand (see `_row` below), so they represent whatever the SQL
layer WOULD have already produced -- there is no live DB to exercise the
new `NULLIF(TRIM(...))` wrapper directly; see
`TestListCatalogSuggestionWhitespaceManual` below for the row shape a
whitespace-only manual now corresponds to post-fix.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.parts_manual import (
    _list_catalog_impl,
    _resolve_catalog_suggestion,
    list_catalog,
)


def _superadmin() -> MagicMock:
    u = MagicMock()
    u.is_superadmin = True
    return u


def _row(
    fpn,
    description_es=None,
    description_es_manual=None,
    suggestion_dismissed_at=None,
    section_code="B1",
):
    """One row of the inner select, PR5 shape (17 columns)."""
    return (
        fpn, "English desc", description_es, None, section_code, "FRAME",
        "MODELX", None, None, None, None, None, None, False, None,
        description_es_manual, suggestion_dismissed_at,
    )


class _AllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ScalarsAllResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        r = MagicMock()
        r.all.return_value = list(self._items)
        return r


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


def _run_list_catalog(
    rows,
    *,
    prev_codes_by_fpn: dict | None = None,
    alias_rows: list | None = None,
    only_suggested: bool = False,
):
    """Wires an `AsyncMock` session's `execute` side_effect to the exact
    call sequence `_list_catalog_impl` issues, mirroring the branch
    conditions in the real implementation so tests don't have to guess."""
    prev_codes_by_fpn = prev_codes_by_fpn or {}
    fpns = [r[0] for r in rows]

    side_effects = [
        _ScalarsAllResult([]),          # get_pricing_factors
        _ScalarOneResult(len(rows)),    # count_q
        _AllResult(rows),               # rows_q
    ]
    if fpns:
        side_effects.append(_ScalarsAllResult([]))  # subs_q
        refs_rows = [(fpn, prev_codes_by_fpn.get(fpn, [])) for fpn in fpns]
        side_effects.append(_AllResult(refs_rows))  # refs_q (prev_codes)

        pending_alias_fpns = {
            r[0] for r in rows if not r[2] and prev_codes_by_fpn.get(r[0])
        }
        alias_codes = sorted({
            code for fpn in pending_alias_fpns for code in prev_codes_by_fpn.get(fpn, [])
        })
        if alias_codes:
            side_effects.append(_AllResult(alias_rows or []))  # alias_sq

        side_effects.append(_AllResult([]))  # cov_q

    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=side_effects)

    return _list_catalog_impl(
        search="", model_code="", only_pending=False, only_price_review=False,
        rotation_class="", coverage_status="", sort_col="section_code", sort_dir="asc",
        page=1, page_size=50, db=db, only_suggested=only_suggested,
    ), db


# ---------------------------------------------------------------------------
# 5.4 -- has_unconfirmed_suggestion truth table (pure function)
# ---------------------------------------------------------------------------

class TestResolveCatalogSuggestionTruthTable:
    def test_manual_set_never_suggests(self):
        es, flag, source = _resolve_catalog_suggestion(
            manual="Filtro de aceite", coalesced_description_es="Filtro de aceite",
            dismissed_at=None, fpn="FPN-1",
        )
        assert (es, flag, source) == ("Filtro de aceite", False, None)

    def test_manual_null_with_spi_text_suggests_from_own_code(self):
        es, flag, source = _resolve_catalog_suggestion(
            manual=None, coalesced_description_es="Filtro de aceite",
            dismissed_at=None, fpn="FPN-1",
        )
        assert es == "Filtro de aceite"
        assert flag is True
        assert source == "FPN-1"

    def test_manual_null_with_no_spi_text_does_not_suggest(self):
        es, flag, source = _resolve_catalog_suggestion(
            manual=None, coalesced_description_es=None,
            dismissed_at=None, fpn="FPN-1",
        )
        assert (es, flag, source) == (None, False, None)

    def test_empty_string_manual_treated_as_null(self):
        """`coalesced_description_es="Filtro de aceite"` alongside a
        whitespace-only `manual` is now exactly what the real SQL layer
        produces post-fix (PR5 fix pass #9): `_list_catalog_impl`'s
        `COALESCE(NULLIF(TRIM(description_es_manual), ''),
        spi_latest.description_es)` nullifies the whitespace manual BEFORE
        this function ever sees it, so it correctly falls back to the
        spi-latest text. Before that fix, production SQL would have handed
        this function `coalesced_description_es="   "` instead (COALESCE
        only falls back on NULL, not on whitespace) -- a combination this
        test never exercised, which is exactly the gap the 5th review
        flagged. See `TestListCatalogWhitespaceManualLegacyData` below for
        the end-to-end proof at the `_list_catalog_impl` level, and
        `test_catalog_confirm_dismiss_suggestion.py`'s
        `test_whitespace_only_manual_ignored_falls_back_to_exact_hit` for
        the confirm/dismiss side agreeing on the same row."""
        es, flag, source = _resolve_catalog_suggestion(
            manual="   ", coalesced_description_es="Filtro de aceite",
            dismissed_at=None, fpn="FPN-1",
        )
        assert es == "Filtro de aceite"
        assert flag is True
        assert source == "FPN-1"

    def test_dismissed_hides_badge_but_keeps_displayed_text(self):
        es, flag, source = _resolve_catalog_suggestion(
            manual=None, coalesced_description_es="Filtro de aceite",
            dismissed_at=datetime(2026, 1, 1), fpn="FPN-1",
        )
        assert es == "Filtro de aceite"
        assert flag is False
        assert source is None

    def test_alias_case_suggests_from_alias_source_code(self):
        es, flag, source = _resolve_catalog_suggestion(
            manual=None, coalesced_description_es=None, dismissed_at=None,
            fpn="Z1", alias_text="Empaque de tapa", alias_source_code="Z0",
        )
        assert es == "Empaque de tapa"
        assert flag is True
        assert source == "Z0"

    def test_dismissed_alias_case_keeps_text_hides_badge(self):
        es, flag, source = _resolve_catalog_suggestion(
            manual=None, coalesced_description_es=None,
            dismissed_at=datetime(2026, 1, 1), fpn="Z1",
            alias_text="Empaque de tapa", alias_source_code="Z0",
        )
        assert es == "Empaque de tapa"
        assert flag is False
        assert source is None


# ---------------------------------------------------------------------------
# 5.5 -- wired end-to-end through `_list_catalog_impl` / `_build_item`
# ---------------------------------------------------------------------------

class TestListCatalogSuggestionField:
    async def test_confirmed_row_no_badge(self):
        rows = [_row("FPN-1", description_es="Filtro de aceite", description_es_manual="Filtro de aceite")]
        coro, db = _run_list_catalog(rows)
        result = await coro

        item = result.items[0]
        assert item.has_unconfirmed_suggestion is False
        assert item.suggestion_source_code is None
        assert item.description_es == "Filtro de aceite"

    async def test_unconfirmed_row_shows_badge_and_source_is_own_code(self):
        rows = [_row("FPN-1", description_es="Filtro de aceite", description_es_manual=None)]
        coro, _ = _run_list_catalog(rows)
        result = await coro

        item = result.items[0]
        assert item.has_unconfirmed_suggestion is True
        assert item.suggestion_source_code == "FPN-1"
        assert item.description_es == "Filtro de aceite"

    async def test_row_with_no_name_anywhere_no_badge(self):
        rows = [_row("FPN-2", description_es=None, description_es_manual=None)]
        coro, _ = _run_list_catalog(rows)
        result = await coro

        item = result.items[0]
        assert item.has_unconfirmed_suggestion is False
        assert item.suggestion_source_code is None
        assert item.description_es is None

    async def test_dismissed_row_no_badge_but_text_still_shown(self):
        rows = [_row(
            "FPN-1", description_es="Filtro de aceite", description_es_manual=None,
            suggestion_dismissed_at=datetime(2026, 1, 1),
        )]
        coro, _ = _run_list_catalog(rows)
        result = await coro

        item = result.items[0]
        assert item.has_unconfirmed_suggestion is False
        assert item.description_es == "Filtro de aceite"

    async def test_no_extra_query_for_a_page_with_no_alias_eligible_rows(self):
        """Perf lock (D15): a page where every row already has an exact-code
        answer (or genuinely has nothing) must not issue the alias query."""
        rows = [
            _row("FPN-1", description_es="Filtro de aceite", description_es_manual="Filtro de aceite"),
            _row("FPN-2", description_es=None, description_es_manual=None),
        ]
        coro, db = _run_list_catalog(rows, prev_codes_by_fpn={"FPN-1": [], "FPN-2": []})
        await coro
        # pricing + count + rows + subs + refs + cov = 6 calls, no alias call
        assert db.execute.await_count == 6


# ---------------------------------------------------------------------------
# PR5 fix pass #9 -- whitespace-only `description_es_manual` (legacy data,
# or a client that bypasses write-time normalization) must resolve the
# SAME way through the list endpoint as it does through
# `_compute_current_suggestion` (confirm/dismiss's single-row recompute).
# ---------------------------------------------------------------------------

class TestListCatalogWhitespaceManualLegacyData:
    async def test_whitespace_manual_falls_back_to_exact_hit_not_shown_as_confirmed(self):
        """Row shape as it would appear AFTER the SQL fix
        (`COALESCE(NULLIF(TRIM(description_es_manual), ''),
        spi_latest.description_es)`) for a legacy row whose
        `description_es_manual` is `'   '` (written before write-time
        normalization shipped, or by a client that bypasses it): column 2
        (`description_es`, the COALESCE result) is the REAL spi-latest
        text, not the whitespace itself -- the fixed SQL already nullified
        it. Column 15 (the raw `description_es_manual`) still carries the
        raw `'   '`, unaffected by the COALESCE fix, exactly like a real
        `SELECT description_es_manual` would return it verbatim."""
        rows = [_row(
            "FPN-1", description_es="Filtro de aceite", description_es_manual="   ",
        )]
        coro, _ = _run_list_catalog(rows)
        result = await coro

        item = result.items[0]
        # Matches `_compute_current_suggestion`'s independent recompute for
        # an identical row (see
        # `test_catalog_confirm_dismiss_suggestion.py::TestComputeCurrentSuggestion
        # ::test_whitespace_only_manual_ignored_falls_back_to_exact_hit`) --
        # both now agree, closing the drift that used to cause a spurious
        # 409 SUGGESTION_STALE on confirm even when nothing had changed.
        assert item.has_unconfirmed_suggestion is True
        assert item.suggestion_source_code == "FPN-1"
        assert item.description_es == "Filtro de aceite"

    async def test_description_es_coalesce_nullifies_whitespace_manual_in_sql(self):
        """Structural proof of the ACTUAL SQL fix, not just the Python-side
        row simulation above: `_row()`-based tests hand-construct what the
        row would look like, so they cannot catch a regression in the SQL
        expression itself. This compiles the real statement
        `_list_catalog_impl` builds for the page-fetch query and asserts
        the `description_es` column's SQL text contains both `NULLIF` and
        `TRIM` wrapping `description_es_manual` -- the same
        compiled-statement-to-text technique
        `test_only_suggested_predicate_compiles_with_expected_sql_shape`
        uses for the `only_suggested` predicate, for the same reason (no
        live DATABASE_URL exists in this repo to execute the SQL for
        real)."""
        captured: list[str] = []

        class _CapturingSession:
            async def execute(self, stmt):
                captured.append(str(stmt))
                if len(captured) == 1:
                    return _ScalarsAllResult([])  # get_pricing_factors
                if len(captured) == 2:
                    return _ScalarOneResult(0)    # count_q
                return _AllResult([])             # rows_q -> empty page

        await _list_catalog_impl(
            search="", model_code="", only_pending=False, only_price_review=False,
            rotation_class="", coverage_status="", sort_col="section_code",
            sort_dir="asc", page=1, page_size=50, db=_CapturingSession(),
        )

        # call #3 = rows_q, the page-fetch query that selects `inner_sq`
        # (whose column list includes the `description_es` COALESCE label).
        rows_sql = captured[2]
        assert "NULLIF" in rows_sql.upper()
        assert "TRIM" in rows_sql.upper()
        assert "description_es_manual" in rows_sql


# ---------------------------------------------------------------------------
# 5.6 -- alias-aware suggestion resolution (design D16)
# ---------------------------------------------------------------------------

class TestAliasAwareSuggestionResolution:
    async def test_suggestion_found_only_under_a_prev_codes_alias(self):
        rows = [_row("Z1", description_es=None, description_es_manual=None)]
        coro, db = _run_list_catalog(
            rows,
            prev_codes_by_fpn={"Z1": ["Z0"]},
            alias_rows=[("Z0", "Empaque de tapa")],
        )
        result = await coro

        item = result.items[0]
        assert item.has_unconfirmed_suggestion is True
        assert item.suggestion_source_code == "Z0"
        assert item.description_es == "Empaque de tapa"
        # pricing + count + rows + subs + refs + alias + cov = 7 calls
        assert db.execute.await_count == 7

    async def test_exact_beats_alias_when_both_exist(self):
        rows = [_row("FPN-1", description_es="Filtro de aceite", description_es_manual=None)]
        # This row already has an exact hit -> alias branch must not even
        # be considered for it (no alias query issued at all on this page).
        coro, db = _run_list_catalog(rows, prev_codes_by_fpn={"FPN-1": ["OLD-1"]})
        result = await coro

        item = result.items[0]
        assert item.suggestion_source_code == "FPN-1"
        assert db.execute.await_count == 6  # no alias query

    async def test_legacy_plain_string_prev_codes_resolve_too(self):
        rows = [_row("Z1", description_es=None, description_es_manual=None)]
        coro, db = _run_list_catalog(
            rows,
            prev_codes_by_fpn={"Z1": ["LEGACY-CODE"]},
            alias_rows=[("LEGACY-CODE", "Nombre legado")],
        )
        result = await coro
        assert result.items[0].description_es == "Nombre legado"

    async def test_zero_extra_queries_when_no_row_qualifies_for_alias(self):
        rows = [_row("FPN-1", description_es="Filtro de aceite", description_es_manual="Filtro de aceite")]
        coro, db = _run_list_catalog(rows, prev_codes_by_fpn={"FPN-1": ["OLD-1"]})
        await coro
        assert db.execute.await_count == 6


# ---------------------------------------------------------------------------
# 5.7 -- only_suggested filter (design D17) + mandatory parity test
# ---------------------------------------------------------------------------

class TestOnlySuggestedFilterWiring:
    async def test_list_catalog_forwards_only_suggested_to_impl(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(side_effect=[
            _ScalarsAllResult([]),
            _ScalarOneResult(0),
            _AllResult([]),
        ])
        result = await list_catalog(
            search="", model_code="", only_pending=False, only_price_review=False,
            only_suggested=True, rotation_class="", coverage_status="",
            sort_col="section_code", sort_dir="asc", page=1, page_size=50,
            db=db, current_user=_superadmin(),
        )
        assert result.total == 0

    async def test_only_suggested_predicate_compiles_with_expected_sql_shape(self):
        """Compiles the actual statements `_list_catalog_impl` builds for
        `only_suggested=True` and asserts the WHERE clause references the
        same 3 conditions `_resolve_catalog_suggestion` checks (manual
        empty, not dismissed, spi/alias text present) -- the closest thing
        to a live parity check without a real DATABASE_URL (see module
        docstring). If this assertion and `_resolve_catalog_suggestion`'s
        logic are ever changed independently, THIS is the seam that can
        drift -- design D17's own documented risk.

        `coverage_status=""` here specifically so `jsonb_array_elements`
        can only appear because of the `only_suggested` alias-EXISTS
        block, not one of the (also jsonb-based) coverage filters."""
        captured: list[str] = []

        class _CapturingSession:
            async def execute(self, stmt):
                captured.append(str(stmt))
                if len(captured) == 1:
                    return _ScalarsAllResult([])  # get_pricing_factors
                if len(captured) == 2:
                    return _ScalarOneResult(0)    # count_q
                return _AllResult([])

        await _list_catalog_impl(
            search="", model_code="", only_pending=False, only_price_review=False,
            rotation_class="", coverage_status="", sort_col="section_code",
            sort_dir="asc", page=1, page_size=50, db=_CapturingSession(),
            only_suggested=True,
        )

        # call #1 = get_pricing_factors, call #2 = count_q (the first query
        # to actually pass through `_base_joins`'s WHERE clause).
        count_sql = captured[1]
        assert "suggestion_dismissed_at" in count_sql
        assert "description_es_manual" in count_sql
        assert "jsonb_array_elements" in count_sql
