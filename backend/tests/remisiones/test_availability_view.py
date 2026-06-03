"""
Tests for the spare_part_availability VIEW logic.

The VIEW computes:
    qty_available = qty_physical + COALESCE(SUM(delta), 0)

These tests validate that formula in isolation (pure Python),
simulating what the PostgreSQL VIEW produces.

Real VIEW tests against a live DB would require a test DATABASE_URL;
those are left as integration tests for a future CI setup.
"""
import uuid
import pytest
from typing import List, Optional


def compute_qty_available(qty_physical: Optional[int], deltas: List[int]) -> Optional[int]:
    """
    Pure Python implementation of the VIEW formula.

    qty_physical = None → item not yet inspected → excluded from VIEW
    (The VIEW has WHERE spi.qty_physical IS NOT NULL)
    """
    if qty_physical is None:
        return None  # Not in VIEW (excluded by WHERE clause)
    return qty_physical + sum(deltas)


class TestAvailabilityViewFormula:

    def test_no_movements_equals_physical(self):
        """Without any movements, qty_available == qty_physical."""
        assert compute_qty_available(qty_physical=10, deltas=[]) == 10

    def test_dispatch_reduces_available(self):
        """DESPACHO movement (delta = -qty) reduces available qty."""
        assert compute_qty_available(qty_physical=10, deltas=[-3]) == 7

    def test_cancel_restores_available(self):
        """ANULACION movement (delta = +qty) restores available qty."""
        assert compute_qty_available(qty_physical=10, deltas=[-3, +3]) == 10

    def test_multiple_dispatches_accumulate(self):
        """Multiple dispatch movements all reduce from the same physical base."""
        assert compute_qty_available(qty_physical=20, deltas=[-5, -3]) == 12

    def test_partial_cancel_partially_restores(self):
        """Partial restoration via ANULACION."""
        assert compute_qty_available(qty_physical=10, deltas=[-6, +3]) == 7

    def test_uninspected_item_excluded_from_view(self):
        """qty_physical IS NULL → item is not in the VIEW."""
        assert compute_qty_available(qty_physical=None, deltas=[]) is None

    def test_uninspected_item_with_movements_still_excluded(self):
        """Even if movements exist, NULL qty_physical means item is not in VIEW."""
        assert compute_qty_available(qty_physical=None, deltas=[-2]) is None

    def test_zero_physical_with_no_movements(self):
        """qty_physical=0 is inspected (not NULL) → qty_available = 0."""
        assert compute_qty_available(qty_physical=0, deltas=[]) == 0

    def test_full_depletion(self):
        """All stock dispatched → qty_available == 0."""
        assert compute_qty_available(qty_physical=5, deltas=[-5]) == 0

    def test_net_sum_matches_physical_after_dispatch_and_cancel(self):
        """
        Spec scenario: dispatch then full cancellation → qty_available = qty_physical.
        """
        qty_physical = 15
        dispatch_delta = -10
        cancel_delta = +10
        result = compute_qty_available(qty_physical, [dispatch_delta, cancel_delta])
        assert result == qty_physical


class TestAvailabilityViewFilter:
    """Tests the WHERE qty_available > 0 filter applied by the /availability endpoint."""

    def _filter_available(self, items: list) -> list:
        """Simulates the endpoint filter: only return items with qty_available > 0."""
        return [i for i in items if i["qty_available"] > 0]

    def test_items_with_stock_returned(self):
        items = [
            {"id": uuid.uuid4(), "qty_available": 5},
            {"id": uuid.uuid4(), "qty_available": 0},
            {"id": uuid.uuid4(), "qty_available": 2},
        ]
        result = self._filter_available(items)
        assert len(result) == 2
        assert all(i["qty_available"] > 0 for i in result)

    def test_all_zero_returns_empty(self):
        items = [
            {"id": uuid.uuid4(), "qty_available": 0},
            {"id": uuid.uuid4(), "qty_available": 0},
        ]
        assert self._filter_available(items) == []

    def test_all_positive_all_returned(self):
        items = [
            {"id": uuid.uuid4(), "qty_available": 3},
            {"id": uuid.uuid4(), "qty_available": 1},
        ]
        result = self._filter_available(items)
        assert len(result) == 2
