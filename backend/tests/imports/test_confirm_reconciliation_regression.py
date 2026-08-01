"""
Regression tests for `confirm_reconciliation` (Phase 3 of the Tier 3
reconcile/confirm decomposition change).

Purpose: pin TODAY's observable behavior of `confirm_reconciliation`
(`backend/app/services/imports_service.py`) — the per-`ReconciliationResult`
item mutations (Pass 1), the EXTRA-to-open-Backorder FIFO fill (Pass 2), and
the final sealing/commit — BEFORE it gets decomposed into helpers (Phase 4),
so the exact same assertions can be re-run AFTER that refactor to prove it is
byte-for-byte behavior-preserving. Per tasks 3.1-3.6.

This is RED-only approval testing: these tests currently PASS against the
unrefactored function (task 3.6 baseline), they are not failing-first TDD for
new behavior. No production code is touched in this PR.

Every assertion below pins CURRENT behavior exactly as specified in
`sdd/imports-oversized-functions-refactor-tier3/spec`, including two known
quirks that are locked verbatim, not fixed:
  - Note 1: COMPLETE sets `status="DECLARED"`, even though the function's own
    docstring says "RECEIVED". The code is the pinned behavior.
  - Note 3 (design): Pass 2's Backorder fill is NOT scoped to the confirming
    lot — it fills the oldest open Backorder for the part_number system-wide,
    reassigning `expected_in_pi` to this lot's `origin_pi`.
  - Note 4: MISSING's `qty_pending` computation has no `max(0, ...)` floor
    (unlike PARTIAL), and does not reset `item.status` to "BACKORDER" when
    `item.qty_received` is already nonzero.

FIXED (no longer a locked quirk, see `sdd/confirm-reconciliation-extra-surplus-fix`):
Pass 2 used to offer the FULL `rr.qty_in_packing` as backorder-fill surplus
for a MATCHED EXTRA row, even though Pass 1 already applied the ordered
portion to the item — a double-count. It now offers only the true excess
(`qty_in_packing - qty_ordered`, double-clamped). See
`TestConfirmMatchedExtraSurplusIsTrueExcess` below.

These tests exercise the REAL `confirm_reconciliation` function against a
`FakeAsyncSession` (see tests/imports/conftest.py) — no live database, no
HTTP server, matching this repo's established test pattern (see
test_reconcile_lot_packing_list_regression.py, this module's sibling).
"""
import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock

from app.services.imports_service import confirm_reconciliation
from app.models.imports import Backorder
from tests.imports.conftest import (
    make_lot,
    make_spare_part_item,
    make_reconciliation_result,
    make_backorder,
    make_actor,
    FakeAsyncSession,
)


def _session(results, get_objects=None, backorder_selects=None) -> FakeAsyncSession:
    """Builds a FakeAsyncSession with the execute-queue order
    `confirm_reconciliation` issues today:
      1. `select(ReconciliationResult).where(lot_id == lot.id)` — always
      2. Pass 1: one `select(Backorder)...` per PARTIAL/MISSING row whose
         pending delta > 0 (via `_upsert_backorder`), in `results` order
      3. Pass 2: one `select(Backorder)...` per EXTRA row with
         `qty_in_packing > 0`, in `results` order

    `SparePartItem` lookups go through `db.get(...)`, not `execute()` — pass
    them via `get_objects`, not the queue.
    """
    return FakeAsyncSession(
        execute_queue=[results] + list(backorder_selects or []),
        get_objects=get_objects or [],
    )


class TestConfirmCompleteMatch:

    async def test_complete_sets_declared_not_received(self):
        """Locks Note 1: docstring says RECEIVED, code sets DECLARED."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, qty_received=0, status="PENDING")
        rr = make_reconciliation_result(
            lot.id, "ABC-001", result="COMPLETE",
            spare_part_item_id=item.id, qty_ordered=10, qty_in_packing=10,
        )
        db = _session([rr], get_objects=[item])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            result = await confirm_reconciliation(db, lot, make_actor())

        assert result == {
            "confirmed": 1,
            "backorders_created": 0,
            "backorders_assigned_by_extra": 0,
            "lot_id": str(lot.id),
        }
        assert item.qty_received == 10
        assert item.qty_pending == 0
        assert item.status == "DECLARED"  # NOT "RECEIVED" — pinned per Note 1
        assert rr.confirmed_by is not None
        assert rr.confirmed_at is not None
        assert lot.packing_list_received is True


class TestConfirmPartialMatch:

    async def test_partial_creates_backorder_for_pending_qty(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, qty_received=0, status="PENDING")
        rr = make_reconciliation_result(
            lot.id, "ABC-001", result="PARTIAL",
            spare_part_item_id=item.id, qty_ordered=10, qty_in_packing=4,
        )
        db = _session([rr], get_objects=[item], backorder_selects=[[]])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            result = await confirm_reconciliation(db, lot, make_actor())

        assert item.qty_received == 4
        assert item.qty_pending == 6
        assert item.status == "PARTIAL"
        assert result["confirmed"] == 1
        assert result["backorders_created"] == 1

        bo_rows = db.added_of_type(Backorder)
        assert len(bo_rows) == 1
        assert bo_rows[0].qty_pending == 6
        assert bo_rows[0].origin_pi == lot.lot_identifier


class TestConfirmMissingItem:

    async def test_missing_with_zero_received_sets_backorder_status(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, qty_received=0, status="PENDING")
        rr = make_reconciliation_result(
            lot.id, "ABC-001", result="MISSING",
            spare_part_item_id=item.id, qty_ordered=10, qty_in_packing=0,
        )
        db = _session([rr], get_objects=[item], backorder_selects=[[]])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            result = await confirm_reconciliation(db, lot, make_actor())

        assert item.status == "BACKORDER"
        assert item.qty_pending == 10
        assert result["backorders_created"] == 1

    async def test_missing_does_not_reset_nonzero_prior_qty_received(self):
        """Locks Note 4: no `max(0, ...)` floor on MISSING's qty_pending, and
        status is NOT forced back to BACKORDER when qty_received is already
        nonzero (unlike a fresh, never-received item)."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, qty_received=3, status="PARTIAL")
        rr = make_reconciliation_result(
            lot.id, "ABC-001", result="MISSING",
            spare_part_item_id=item.id, qty_ordered=10, qty_in_packing=0,
        )
        db = _session([rr], get_objects=[item], backorder_selects=[[]])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            result = await confirm_reconciliation(db, lot, make_actor())

        assert item.status == "PARTIAL"  # NOT forced to "BACKORDER"
        assert item.qty_pending == 7  # 10 - 3, unfloored
        assert result["backorders_created"] == 1


class TestConfirmPureExtraFifoFill:

    async def test_pure_extra_fills_and_resolves_cross_lot_backorder(self):
        """Locks the FIFO-fill core + Note 3 (design): a pure EXTRA row
        (no matching SparePartItem) fills the oldest open Backorder for the
        same part_number system-wide, even when that backorder originated
        from a DIFFERENT PI — proving cross-lot reassignment, not a bug."""
        lot = make_lot(lot_identifier="E0000700-SP")
        rr = make_reconciliation_result(
            lot.id, "XYZ-001", result="EXTRA",
            spare_part_item_id=None, qty_ordered=None, qty_in_packing=6,
        )
        bo = make_backorder(
            spare_part_item_id=uuid.uuid4(), part_number="XYZ-001",
            origin_pi="OTHER-PI-999", qty_pending=6, resolved=False,
        )
        db = _session([rr], backorder_selects=[[bo]])

        result = await confirm_reconciliation(db, lot, make_actor())

        # Pure EXTRA has no spare_part_item_id -> Pass 1 skips it entirely.
        assert result["confirmed"] == 0
        assert result["backorders_assigned_by_extra"] == 1

        assert bo.qty_pending == 0
        assert bo.resolved is True
        assert bo.resolved_at is not None
        assert bo.expected_in_pi == lot.lot_identifier  # reassigned cross-lot
        events = [h["event"] for h in bo.history]
        assert events == ["FILLED_BY_EXTRA", "ASSIGNED_TO_PI_BY_EXTRA"]

        assert rr.result == "EXTRA_APPLIED"
        assert rr.confirmed_at is not None  # sealed like every other row


class TestConfirmMatchedExtraSurplusIsTrueExcess:

    async def test_matched_extra_offers_only_excess_over_qty_ordered(self):
        """Fix verification: Pass 1 already applies the FULL `qty_in_packing`
        to the matched item, so the ordered portion is already accounted for
        there. Pass 2 must therefore only offer the TRUE excess
        (`qty_in_packing - qty_ordered`) to fill OTHER open backorders, not
        the full `qty_in_packing` again — otherwise the ordered portion gets
        double-counted as surplus. See `sdd/confirm-reconciliation-extra-surplus-fix`."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-002", qty_ordered=10, qty_received=0, status="PENDING")
        rr = make_reconciliation_result(
            lot.id, "ABC-002", result="EXTRA",
            spare_part_item_id=item.id, qty_ordered=10, qty_in_packing=15,
        )
        bo = make_backorder(
            spare_part_item_id=item.id, part_number="ABC-002",
            origin_pi="OTHER-PI-111", qty_pending=20, resolved=False,
        )
        db = _session([rr], get_objects=[item], backorder_selects=[[bo]])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            result = await confirm_reconciliation(db, lot, make_actor())

        # Pass 1: matched EXTRA applies the full declared qty to the item.
        assert item.qty_received == 15
        assert item.qty_pending == 0
        assert item.status == "DECLARED"
        assert result["confirmed"] == 1

        # Pass 2: surplus = qty_in_packing - qty_ordered (5), true excess only.
        assert bo.qty_pending == 15  # 20 - 5
        assert bo.resolved is False
        events = [h["event"] for h in bo.history]
        assert events[-1] == "PARTIAL_ASSIGNMENT_BY_EXTRA"
        assert rr.result == "EXTRA_APPLIED"
        assert result["backorders_assigned_by_extra"] == 0  # not fully resolved
        assert rr.confirmed_at is not None

    async def test_pure_extra_surplus_unchanged_by_fix(self):
        """Pure EXTRA (`qty_ordered is None`, no matching order item) is
        unaffected by the matched-EXTRA fix: the full `qty_in_packing` is
        still genuine surplus. Uses numbers distinct from the matched-EXTRA
        test above to avoid confusion between the two paths."""
        lot = make_lot()
        rr = make_reconciliation_result(
            lot.id, "ABC-003", result="EXTRA",
            spare_part_item_id=None, qty_ordered=None, qty_in_packing=8,
        )
        bo = make_backorder(
            spare_part_item_id=uuid.uuid4(), part_number="ABC-003",
            origin_pi="OTHER-PI-222", qty_pending=20, resolved=False,
        )
        db = _session([rr], backorder_selects=[[bo]])

        result = await confirm_reconciliation(db, lot, make_actor())

        # Pure EXTRA has no spare_part_item_id -> Pass 1 skips it entirely.
        assert result["confirmed"] == 0

        # Pass 2: surplus = full qty_in_packing (8), unchanged from before the fix.
        assert bo.qty_pending == 12  # 20 - 8
        assert bo.resolved is False
        events = [h["event"] for h in bo.history]
        assert events[-1] == "PARTIAL_ASSIGNMENT_BY_EXTRA"
        assert rr.result == "EXTRA_APPLIED"

    async def test_negative_qty_ordered_clamps_surplus_to_qty_in_packing(self):
        """Data-entry-error simulation: a matched EXTRA row with a negative
        `qty_ordered` (unreachable via normal reconciliation-build logic, but
        reachable via the unconstrained PATCH endpoint on SparePartItem — see
        design's double-clamp rationale) must never let surplus exceed
        `qty_in_packing`. Constructs the `ReconciliationResult` directly via
        the test factory, bypassing `_build_reconciliation_result_row`."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-004", qty_ordered=10, qty_received=0, status="PENDING")
        rr = make_reconciliation_result(
            lot.id, "ABC-004", result="EXTRA",
            spare_part_item_id=item.id, qty_ordered=-5, qty_in_packing=3,
        )
        bo = make_backorder(
            spare_part_item_id=item.id, part_number="ABC-004",
            origin_pi="OTHER-PI-333", qty_pending=10, resolved=False,
        )
        db = _session([rr], get_objects=[item], backorder_selects=[[bo]])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            result = await confirm_reconciliation(db, lot, make_actor())

        assert result["confirmed"] == 1

        # Surplus offered must be capped at qty_in_packing (3), never inflated
        # to qty_in_packing - qty_ordered = 3 - (-5) = 8.
        assert bo.qty_pending == 7  # 10 - 3, NOT 2 (10 - 8)
        events = [h["event"] for h in bo.history]
        assert events[-1] == "PARTIAL_ASSIGNMENT_BY_EXTRA"
        assert rr.result == "EXTRA_APPLIED"


class TestConfirmExtraFillSyncsBeneficiaryItem:
    """Per `sdd/matched-extra-qty-received-beneficiary-sync`: Pass 2
    (`_fill_backorders_from_extras`) must additively credit the beneficiary
    `SparePartItem` it fills a backorder for, mirroring
    `_apply_backorder_confirm_line`, WITHOUT double-crediting an item Pass 1
    already wrote in this same `confirm_reconciliation` call."""

    async def test_matched_extra_does_not_double_credit_own_reuploaded_backorder(self):
        """Non-vacuous double-credit guard: a stale open Backorder for the
        SAME item a matched-EXTRA row just declared (re-upload scenario)
        must NOT get its qty_received incremented a second time by Pass 2 —
        Pass 1 already set the absolute qty_received for this item this
        call. Only the backorder's own qty_pending legitimately reduces."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "REUP-001", qty_ordered=10, qty_received=0, status="PENDING")
        rr = make_reconciliation_result(
            lot.id, "REUP-001", result="EXTRA",
            spare_part_item_id=item.id, qty_ordered=10, qty_in_packing=12,
        )
        bo = make_backorder(
            spare_part_item_id=item.id, part_number="REUP-001",
            origin_pi="OTHER-PI-444", qty_pending=4, resolved=False,
        )
        db = _session([rr], get_objects=[item], backorder_selects=[[bo]])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            result = await confirm_reconciliation(db, lot, make_actor())

        assert result["confirmed"] == 1
        # Pass 1 already set qty_received=12 (the declared qty). Pass 2 must
        # NOT additively credit it again to 14.
        assert item.qty_received == 12
        assert item.status == "DECLARED"  # NOT overwritten by Pass 2's credit path
        # The backorder's own qty_pending still legitimately reduces by the
        # surplus (12 - 10 = 2) applied to it — this is pre-existing Pass-2
        # behavior, unrelated to the item-credit guard.
        assert bo.qty_pending == 2
        assert bo.resolved is False

    async def test_pure_extra_fill_syncs_cross_lot_beneficiary_item(self):
        """Positive case: a pure EXTRA (no matching order item, so Pass 1
        skips it entirely) fills a cross-lot backorder — the beneficiary
        item's qty_received/qty_pending/status must now be synced, not left
        stale after the Backorder is marked resolved."""
        lot = make_lot()
        other_lot_id = uuid.uuid4()
        item_y = make_spare_part_item(other_lot_id, "XYZ-002", qty_ordered=6, qty_received=0, status="PENDING")
        rr = make_reconciliation_result(
            lot.id, "XYZ-002", result="EXTRA",
            spare_part_item_id=None, qty_ordered=None, qty_in_packing=6,
        )
        bo = make_backorder(
            spare_part_item_id=item_y.id, part_number="XYZ-002",
            origin_pi="OTHER-PI-555", qty_pending=6, resolved=False,
        )
        db = _session([rr], get_objects=[item_y], backorder_selects=[[bo]])

        result = await confirm_reconciliation(db, lot, make_actor())

        assert result["backorders_assigned_by_extra"] == 1
        assert bo.qty_pending == 0
        assert bo.resolved is True

        assert item_y.qty_received == 6
        assert item_y.qty_pending == 0
        assert item_y.status == "RECEIVED"

    async def test_extra_fill_additively_credits_prior_received_beneficiary(self):
        """Additive, not overwrite: a beneficiary item that already had a
        nonzero qty_received (e.g. partially received in a prior lot) must
        have the newly-applied surplus ADDED, not clobber the prior value."""
        lot = make_lot()
        other_lot_id = uuid.uuid4()
        item_y = make_spare_part_item(other_lot_id, "XYZ-003", qty_ordered=20, qty_received=3, status="PARTIAL")
        rr = make_reconciliation_result(
            lot.id, "XYZ-003", result="EXTRA",
            spare_part_item_id=None, qty_ordered=None, qty_in_packing=5,
        )
        bo = make_backorder(
            spare_part_item_id=item_y.id, part_number="XYZ-003",
            origin_pi="OTHER-PI-666", qty_pending=17, resolved=False,
        )
        db = _session([rr], get_objects=[item_y], backorder_selects=[[bo]])

        await confirm_reconciliation(db, lot, make_actor())

        assert item_y.qty_received == 8  # 3 + 5, additive not overwritten to 5
        assert item_y.qty_pending == 12  # 20 - 8
        assert item_y.status == "PARTIAL"
        assert bo.qty_pending == 12  # 17 - 5


class TestConfirmAlreadyConfirmedGuard:

    async def test_already_confirmed_rejected_without_mutation(self):
        lot = make_lot()
        rr = make_reconciliation_result(
            lot.id, "ABC-001", result="COMPLETE",
            spare_part_item_id=uuid.uuid4(), qty_ordered=10, qty_in_packing=10,
        )
        rr.confirmed_at = datetime.utcnow()
        db = _session([rr])

        result = await confirm_reconciliation(db, lot, make_actor())

        assert result == {"error": "ALREADY_CONFIRMED"}
        assert lot.packing_list_received is False
        assert db.added == []


class TestConfirmTriggersPriceRecalculation:
    """Regression: confirming a reconciliation must recalculate the catalog's
    avg_fob_cost for every part touched -- previously this step was missing
    entirely, so a price declared on a packing list (SparePartItem.unit_price)
    never propagated to PartsReference, leaving Maestro de Partes showing no
    price even though the underlying data existed."""

    async def test_recalculate_called_once_per_distinct_part_number(self):
        lot = make_lot()
        item_a = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, qty_received=0, status="PENDING")
        item_b = make_spare_part_item(lot.id, "ABC-001", qty_ordered=5, qty_received=0, status="PENDING")
        rr_a = make_reconciliation_result(
            lot.id, "ABC-001", result="COMPLETE",
            spare_part_item_id=item_a.id, qty_ordered=10, qty_in_packing=10,
        )
        rr_b = make_reconciliation_result(
            lot.id, "ABC-001", result="COMPLETE",
            spare_part_item_id=item_b.id, qty_ordered=5, qty_in_packing=5,
        )
        db = _session([rr_a, rr_b], get_objects=[item_a, item_b])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as mocked_recalc:
            await confirm_reconciliation(db, lot, make_actor())

        # Same part_number on two rows -> recalculated once, not twice.
        mocked_recalc.assert_awaited_once_with(db, "ABC-001", lot_identifier=lot.lot_identifier)

    async def test_recalculate_not_called_for_pure_extra_with_no_item(self):
        """A pure EXTRA (no spare_part_item_id) never touched a
        SparePartItem's price, so there's nothing to recalculate."""
        lot = make_lot()
        rr = make_reconciliation_result(
            lot.id, "XYZ-001", result="EXTRA",
            spare_part_item_id=None, qty_ordered=None, qty_in_packing=6,
        )
        db = _session([rr], backorder_selects=[[]])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()) as mocked_recalc:
            await confirm_reconciliation(db, lot, make_actor())

        mocked_recalc.assert_not_awaited()


class TestConfirmNoResults:

    async def test_no_results_returns_error(self):
        lot = make_lot()
        db = _session([])

        result = await confirm_reconciliation(db, lot, make_actor())

        assert "error" in result
        assert result["error"] != "ALREADY_CONFIRMED"
        assert lot.packing_list_received is False
