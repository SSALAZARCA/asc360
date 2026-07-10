"""
Unit/service tests for `_item_weight` and `recalculate_part_cost`
(`backend/app/services/pricing_service.py`) — `sdd/physical-inspection-cost-recalc`.

Phase 1 (pure helper, no DB, mirrors `test_blend_unit_price.py`) + Phase 2
(service-level weighted-average accumulation and zero-weight guard, using
`FakeAsyncSession`) + Phase 3 (`apply_physical_inspection` trigger wiring).
Plain `def test_...` + `asyncio.run(...)` where async production code is
exercised — matches this project's established convention (see
`test_backorder_reconciliation_service.py` module docstring).
"""
import asyncio

from app.services.pricing_service import _item_weight, recalculate_part_cost
from app.services.imports_service import apply_physical_inspection
from app.models.parts_manual import PartCostHistory, PartsReference

from tests.imports.conftest import FakeAsyncSession, make_lot, make_spare_part_item


# ---------------------------------------------------------------------------
# Phase 1 — `_item_weight` pure helper
# ---------------------------------------------------------------------------

def test_item_weight_uses_physical_when_set():
    """Spec: 'Inspected item uses verified quantity'."""
    lot = make_lot()
    item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
    item.qty_physical = 7
    assert _item_weight(item) == 7


def test_item_weight_falls_back_to_ordered_when_physical_none():
    """Spec: 'Uninspected item preserves current behavior' (regression safety)."""
    lot = make_lot()
    item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
    item.qty_physical = None
    assert _item_weight(item) == 10


def test_item_weight_physical_zero_is_zero_not_fallback():
    """Guards `is not None` vs truthiness — a verified-empty arrival (0) must
    NOT silently fall back to qty_ordered."""
    lot = make_lot()
    item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
    item.qty_physical = 0
    assert _item_weight(item) == 0


# ---------------------------------------------------------------------------
# Phase 2 — `recalculate_part_cost` weighted accumulation + zero-weight guard
# ---------------------------------------------------------------------------

def _make_ref(factory_part_number: str = "ABC-001") -> PartsReference:
    return PartsReference(
        factory_part_number=factory_part_number,
        um_part_number=factory_part_number,
        description="Test part",
        prev_codes=[],
        avg_fob_cost=None,
        total_fob_qty=None,
        last_cost_updated=None,
    )


def test_inspected_item_weighted_by_physical_qty():
    """Spec: 'Mixed inspected and uninspected items combine in one average'."""
    lot = make_lot()
    ref = _make_ref("ABC-001")
    item1 = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, unit_price=8.0)
    item1.qty_physical = 7
    item2 = make_spare_part_item(lot.id, "ABC-001", qty_ordered=5, unit_price=10.0)
    item2.qty_physical = None

    db = FakeAsyncSession(execute_queue=[[ref], [item1, item2]])
    asyncio.run(recalculate_part_cost(db, "ABC-001"))

    # (8*7 + 10*5) / 12 = 106 / 12 = 8.8333...
    assert float(ref.avg_fob_cost) == 8.8333
    assert ref.total_fob_qty == 12


def test_uninspected_only_matches_legacy_average():
    """Regression anchor for D3/scope safety — all items qty_physical=None
    must reproduce the pre-change qty_ordered-weighted average byte-for-byte."""
    lot = make_lot()
    ref = _make_ref("ABC-001")
    item1 = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, unit_price=8.0)
    item1.qty_physical = None
    item2 = make_spare_part_item(lot.id, "ABC-001", qty_ordered=5, unit_price=10.0)
    item2.qty_physical = None

    db = FakeAsyncSession(execute_queue=[[ref], [item1, item2]])
    asyncio.run(recalculate_part_cost(db, "ABC-001"))

    # (8*10 + 10*5) / 15 = 130 / 15 = 8.6666...
    assert float(ref.avg_fob_cost) == 8.6667
    assert ref.total_fob_qty == 15


def test_zero_weight_only_item_skips_update_no_zerodivision():
    """Spec: 'All-zero-weight set does not crash' — must not raise
    ZeroDivisionError, and MUST leave avg_fob_cost/total_fob_qty/
    last_cost_updated untouched (no PartCostHistory row either)."""
    lot = make_lot()
    ref = _make_ref("ABC-001")
    ref.avg_fob_cost = 5.5
    ref.total_fob_qty = 20
    ref.last_cost_updated = "SENTINEL"
    item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, unit_price=8.0)
    item.qty_physical = 0

    db = FakeAsyncSession(execute_queue=[[ref], [item]])
    asyncio.run(recalculate_part_cost(db, "ABC-001", lot_identifier="E0000573-SP"))

    assert float(ref.avg_fob_cost) == 5.5
    assert ref.total_fob_qty == 20
    assert ref.last_cost_updated == "SENTINEL"
    assert db.added_of_type(PartCostHistory) == []


def test_partial_zero_weight_still_computes_from_nonzero_items():
    """Zero-weight items are silently ignored (contribute 0 to both sums)
    when at least one other item carries nonzero weight — no guard trip."""
    lot = make_lot()
    ref = _make_ref("ABC-001")
    item_a = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, unit_price=8.0)
    item_a.qty_physical = 0
    item_b = make_spare_part_item(lot.id, "ABC-001", qty_ordered=4, unit_price=9.0)
    item_b.qty_physical = 4

    db = FakeAsyncSession(execute_queue=[[ref], [item_a, item_b]])
    asyncio.run(recalculate_part_cost(db, "ABC-001"))

    assert float(ref.avg_fob_cost) == 9.0
    assert ref.total_fob_qty == 4


# ---------------------------------------------------------------------------
# Phase 3 — `apply_physical_inspection` triggers the recalc
# ---------------------------------------------------------------------------

def test_apply_physical_inspection_triggers_recalc_for_part_number():
    """Spec: 'Setting qty_physical triggers recalculation'. qty_ordered=10,
    qty_received=5, qty_physical=5 -> not_charged_qty=5>0 (goes through
    `_upsert_backorder`'s existing-check select), physical_shortage=0 (goes
    through the 'else' existing-physical_inspection-backorder select). Then
    the tail-call recalc must run and see the JUST-SET qty_physical=5 (not
    the stale qty_ordered=10), proving the trigger wiring — not merely that
    recalc ran with old data)."""
    lot = make_lot(packing_list_received=True)
    ref = _make_ref("ABC-001")
    item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, unit_price=8.0)
    item.qty_received = 5

    db = FakeAsyncSession(
        execute_queue=[
            [],       # assigned_bos (Backorder select, resolved via origin_pi)
            [],       # _upsert_backorder existing-check (not_charged_qty branch)
            [],       # existing physical_inspection backorder (else branch)
            [ref],    # recalculate_part_cost -> _find_reference_for_part_number
            [item],   # recalculate_part_cost -> select(SparePartItem)
        ],
        get_objects=[lot],
    )

    asyncio.run(apply_physical_inspection(db, item, qty_physical=5))

    assert item.qty_physical == 5
    # weight = qty_physical (5, not the stale qty_ordered=10): 8.0 * 5 / 5 = 8.0
    assert float(ref.avg_fob_cost) == 8.0
    assert ref.total_fob_qty == 5
