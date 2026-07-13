"""
Unit tests for `_build_lot_summary` and its extracted sub-helpers
(`_compute_lot_fob`, `_compute_lot_pl_value`, `_compute_rotation_pct`) in
`app/api/v1/imports.py` — Phase 1 (task 1.4) of
`sdd/imports-oversized-functions-refactor-tier1`.

Pure-function tests: plain ORM instances, no DB session, no HTTP — matches
the design's "Unit (pure)" testing-strategy row.
"""
from app.api.v1.imports import (
    _build_lot_summary,
    _compute_lot_fob,
    _compute_lot_pl_value,
    _compute_rotation_pct,
)
from tests.imports.conftest import make_lot, make_spare_part_item


def test_build_lot_summary_empty_items_returns_schema_defaults():
    lot = make_lot()
    lot.items = []

    read = _build_lot_summary(lot, rotation_map={}, confirmed_lot_ids=set())

    assert read.items_count == 0
    assert read.total_qty_ordered == 0
    assert read.pct_received == 0.0
    assert read.models == []
    assert read.fob_value is None
    assert read.fob_value_is_estimate is False
    assert read.pl_value is None
    assert read.rotation_pct == {}


def test_build_lot_summary_confirmed_unit_price_is_not_flagged_as_estimate():
    lot = make_lot()
    item = make_spare_part_item(lot.id, "PN-A", qty_ordered=5, unit_price=10, status="RECEIVED")
    lot.items = [item]

    read = _build_lot_summary(lot, rotation_map={}, confirmed_lot_ids=set())

    assert read.fob_value == 50.0
    assert read.fob_value_is_estimate is False


def test_build_lot_summary_fob_pi_only_is_flagged_as_estimate():
    lot = make_lot()
    item = make_spare_part_item(lot.id, "PN-B", qty_ordered=2, fob_pi=8, status="PENDING")
    lot.items = [item]

    read = _build_lot_summary(lot, rotation_map={}, confirmed_lot_ids=set())

    assert read.fob_value == 16.0
    assert read.fob_value_is_estimate is True


def test_build_lot_summary_cancelled_items_excluded_from_fob():
    lot = make_lot()
    item = make_spare_part_item(lot.id, "PN-C", qty_ordered=100, unit_price=999, status="CANCELLED")
    lot.items = [item]

    read = _build_lot_summary(lot, rotation_map={}, confirmed_lot_ids=set())

    assert read.fob_value is None
    assert read.fob_value_is_estimate is False


def test_build_lot_summary_pl_value_gated_on_packing_list_received():
    lot = make_lot(packing_list_received=False)
    item = make_spare_part_item(
        lot.id, "PN-A", qty_ordered=5, qty_received=3, unit_price=10, status="RECEIVED"
    )
    lot.items = [item]

    read = _build_lot_summary(lot, rotation_map={}, confirmed_lot_ids=set())

    assert read.pl_value is None


def test_build_lot_summary_pl_value_computed_when_packing_list_received():
    lot = make_lot(packing_list_received=True)
    item = make_spare_part_item(
        lot.id, "PN-A", qty_ordered=5, qty_received=3, unit_price=10, status="RECEIVED"
    )
    lot.items = [item]

    read = _build_lot_summary(lot, rotation_map={}, confirmed_lot_ids=set())

    assert read.pl_value == 30.0


def test_build_lot_summary_sin_clasificar_bucket():
    lot = make_lot()
    item_a = make_spare_part_item(lot.id, "PN-A", qty_ordered=1, status="RECEIVED")
    item_b = make_spare_part_item(lot.id, "PN-B", qty_ordered=1, status="RECEIVED")
    lot.items = [item_a, item_b]

    read = _build_lot_summary(lot, rotation_map={"PN-A": "FAST"}, confirmed_lot_ids=set())

    assert read.rotation_pct == {"FAST": 50.0, "sin_clasificar": 50.0}


def test_build_lot_summary_reconciliation_confirmed_true_when_lot_id_in_set():
    lot = make_lot()
    lot.items = []

    read = _build_lot_summary(lot, rotation_map={}, confirmed_lot_ids={lot.id})

    assert read.reconciliation_confirmed is True


def test_build_lot_summary_reconciliation_confirmed_false_when_lot_id_not_in_set():
    lot = make_lot()
    lot.items = []

    read = _build_lot_summary(lot, rotation_map={}, confirmed_lot_ids=set())

    assert read.reconciliation_confirmed is False


# --- Direct sub-helper tests (no lot/pydantic wrapper needed) --------------

def test_compute_lot_fob_no_priced_items_returns_none():
    item = make_spare_part_item(None, "PN-X", qty_ordered=1, status="PENDING")

    value, is_estimate = _compute_lot_fob([item])

    assert value is None
    assert is_estimate is False


def test_compute_rotation_pct_all_unclassified():
    item_a = make_spare_part_item(None, "PN-A", qty_ordered=1)
    item_b = make_spare_part_item(None, "PN-B", qty_ordered=1)

    result = _compute_rotation_pct([item_a, item_b], rotation_map={})

    assert result == {"sin_clasificar": 100.0}


def test_compute_lot_pl_value_none_when_not_received():
    lot = make_lot(packing_list_received=False)
    item = make_spare_part_item(lot.id, "PN-A", qty_ordered=1, qty_received=1, unit_price=5)
    lot.items = [item]

    assert _compute_lot_pl_value(lot) is None
