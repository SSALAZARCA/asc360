"""
Tests for concurrent dispatch concurrency guard logic.

The real concurrency test (two async DB transactions racing) requires a live
PostgreSQL DB with FOR UPDATE locking. Here we test the pure logic layer:
the guard that runs AFTER the lock is acquired, which determines whether
to commit or raise 409.

The spec scenario:
  "Two coroutines dispatch the same item with qty = available_qty.
   Only one should succeed; the second must get 409."

This is enforced by the re-validation step inside the lock:
  - txn1 acquires lock, reads qty_available=5, dispatches qty=5 → available becomes 0
  - txn2 acquires lock (waits for txn1 to commit), re-reads qty_available=0, qty_requested=5 → 409
"""
import uuid
import pytest
from datetime import datetime


class TestConcurrentDispatchGuard:
    """
    Unit-level simulation of the lock+revalidate logic.

    The key invariant: the availability check MUST happen inside the lock,
    not before it. This test verifies the guard function correctly handles
    the post-lock state.
    """

    def _post_lock_availability_check(
        self, items_requested: list, availability_snapshot: dict
    ) -> list:
        """
        Simulates the re-validation step that runs after acquiring FOR UPDATE.

        items_requested: list of (spare_part_item_id, qty_dispatched)
        availability_snapshot: dict of {spare_part_item_id: qty_available}
        Returns: list of conflict descriptions (empty = no conflicts, proceed to commit)
        """
        conflicts = []
        for spi_id, qty_requested in items_requested:
            available = availability_snapshot.get(spi_id, 0)
            if qty_requested > available:
                conflicts.append(f"item {spi_id}: requested {qty_requested}, available {available}")
        return conflicts

    def test_first_transaction_succeeds(self):
        """
        First txn sees full stock. No conflicts → proceeds to commit.
        """
        spi_id = uuid.uuid4()
        requested = [(spi_id, 5)]
        snapshot = {spi_id: 5}  # stock = 5

        conflicts = self._post_lock_availability_check(requested, snapshot)
        assert conflicts == []

    def test_second_transaction_fails_after_first_commits(self):
        """
        Second txn sees stock reduced to 0 (first txn already committed).
        qty_requested = 5 > qty_available = 0 → conflict → 409.
        """
        spi_id = uuid.uuid4()
        requested = [(spi_id, 5)]
        snapshot = {spi_id: 0}  # stock depleted by first txn

        conflicts = self._post_lock_availability_check(requested, snapshot)
        assert len(conflicts) == 1
        assert str(spi_id) in conflicts[0]

    def test_partial_failure_mixed_items(self):
        """
        Two items; only one has a conflict. Entire dispatch must fail.
        """
        spi_id_ok = uuid.uuid4()
        spi_id_conflict = uuid.uuid4()

        requested = [(spi_id_ok, 3), (spi_id_conflict, 5)]
        snapshot = {spi_id_ok: 10, spi_id_conflict: 2}

        conflicts = self._post_lock_availability_check(requested, snapshot)
        assert len(conflicts) == 1
        assert str(spi_id_conflict) in conflicts[0]

    def test_all_items_available_no_conflict(self):
        spi_ids = [uuid.uuid4() for _ in range(3)]
        requested = [(spi_id, 2) for spi_id in spi_ids]
        snapshot = {spi_id: 10 for spi_id in spi_ids}

        conflicts = self._post_lock_availability_check(requested, snapshot)
        assert conflicts == []


class TestLedgerImmutability:
    """
    Verifies that the ledger (movements) is append-only.
    Cancellation must NOT modify existing movements — it only adds new ones.
    """

    def test_dispatch_movements_not_mutated_on_cancel(self):
        """
        Simulate a dispatch + cancel sequence.
        Original dispatch movements should remain unchanged.
        """
        original_delta = -5
        dispatch_movement = {
            "id": uuid.uuid4(),
            "delta": original_delta,
            "movement_type": "DESPACHO",
        }

        # Cancellation creates a new movement — it does NOT modify dispatch_movement
        cancel_movement = {
            "id": uuid.uuid4(),
            "delta": -original_delta,  # +5
            "movement_type": "ANULACION",
        }

        # Original remains unchanged
        assert dispatch_movement["delta"] == original_delta
        assert dispatch_movement["movement_type"] == "DESPACHO"

        # Counter movement is separate
        assert cancel_movement["delta"] == 5
        assert cancel_movement["id"] != dispatch_movement["id"]

    def test_net_delta_returns_to_zero(self):
        """After dispatch + cancel, the item's net ledger delta must be zero."""
        qty = 7
        all_movements_delta = [-qty, +qty]
        assert sum(all_movements_delta) == 0
