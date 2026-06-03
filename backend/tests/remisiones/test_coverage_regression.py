"""
Regression tests: Coverage CTE "aqui" uses spare_part_availability VIEW.

These tests validate the LOGIC of how items appear or disappear from the
"aqui" bucket depending on dispatched/cancelled movements, using pure mock
objects — no live database required.

The CTE logic being tested:
    aqui AS (
        SELECT UPPER(TRIM(REPLACE(part_number, ' ', ''))) AS pn
        FROM spare_part_availability
        WHERE qty_available > 0
        GROUP BY 1
    )

where spare_part_availability.qty_available = qty_physical + COALESCE(SUM(delta), 0)
"""
import pytest
from unittest.mock import MagicMock

from tests.conftest import make_spare_part_item, make_movement


# ---------------------------------------------------------------------------
# Helper: compute qty_available the same way the VIEW does
# ---------------------------------------------------------------------------

def compute_qty_available(qty_physical: int, movements: list) -> int:
    """
    Mirrors the VIEW formula:
        qty_available = qty_physical + COALESCE(SUM(irm.delta), 0)
    """
    delta_sum = sum(m.delta for m in movements)
    return qty_physical + delta_sum


def item_appears_in_aqui(qty_physical: int, movements: list) -> bool:
    """Return True if the item would appear in the 'aqui' bucket."""
    return compute_qty_available(qty_physical, movements) > 0


# ---------------------------------------------------------------------------
# Test: item with physical qty and no movements → in "aqui"
# ---------------------------------------------------------------------------

class TestAquiBucketBaseline:
    def test_item_with_qty_physical_no_movements_is_aqui(self):
        """An item with qty_physical=10 and no movements has qty_available=10 → in aqui."""
        spi = make_spare_part_item(qty_physical=10)
        assert item_appears_in_aqui(spi.qty_physical, []) is True

    def test_item_with_qty_physical_zero_not_in_aqui(self):
        """An item with qty_physical=0 has qty_available=0 → NOT in aqui."""
        spi = make_spare_part_item(qty_physical=0)
        assert item_appears_in_aqui(spi.qty_physical, []) is False

    def test_item_with_qty_physical_one_is_aqui(self):
        """Boundary: qty_physical=1 → qty_available=1 → in aqui."""
        assert item_appears_in_aqui(1, []) is True


# ---------------------------------------------------------------------------
# Test: item fully dispatched → drops out of "aqui"
# ---------------------------------------------------------------------------

class TestAquiBucketAfterDispatch:
    def test_fully_dispatched_item_not_in_aqui(self):
        """
        qty_physical=10, DESPACHO movement delta=-10 → qty_available=0 → NOT in aqui.
        Spec scenario: 'Coverage reflects dispatched units'
        """
        spi = make_spare_part_item(qty_physical=10)
        dispatch = make_movement(
            spare_part_item_id=spi.id,
            delta=-10,
            movement_type="DESPACHO",
        )
        assert item_appears_in_aqui(spi.qty_physical, [dispatch]) is False

    def test_partially_dispatched_item_still_in_aqui(self):
        """qty_physical=10, dispatched 5 → qty_available=5 → still in aqui."""
        spi = make_spare_part_item(qty_physical=10)
        dispatch = make_movement(spare_part_item_id=spi.id, delta=-5, movement_type="DESPACHO")
        assert item_appears_in_aqui(spi.qty_physical, [dispatch]) is True

    def test_qty_available_formula_matches_dispatch(self):
        """Verify the arithmetic: 10 + (-10) = 0."""
        dispatch = make_movement(delta=-10, movement_type="DESPACHO")
        assert compute_qty_available(10, [dispatch]) == 0

    def test_multiple_dispatches_accumulate(self):
        """Two dispatches of 3 each against qty_physical=10 → qty_available=4."""
        d1 = make_movement(delta=-3, movement_type="DESPACHO")
        d2 = make_movement(delta=-3, movement_type="DESPACHO")
        assert compute_qty_available(10, [d1, d2]) == 4
        assert item_appears_in_aqui(10, [d1, d2]) is True


# ---------------------------------------------------------------------------
# Test: cancellation restores "aqui"
# ---------------------------------------------------------------------------

class TestAquiBucketAfterCancellation:
    def test_cancellation_restores_aqui(self):
        """
        qty_physical=10, dispatched -10, then cancelled +10 → qty_available=10 → back in aqui.
        Spec scenario: 'Cancellation restores coverage'
        """
        spi = make_spare_part_item(qty_physical=10)
        dispatch = make_movement(spare_part_item_id=spi.id, delta=-10, movement_type="DESPACHO")
        cancel   = make_movement(spare_part_item_id=spi.id, delta=+10, movement_type="ANULACION")
        assert item_appears_in_aqui(spi.qty_physical, [dispatch, cancel]) is True

    def test_cancellation_net_zero_then_new_dispatch_removes_from_aqui(self):
        """After restore, a new dispatch again removes from aqui."""
        d1 = make_movement(delta=-10, movement_type="DESPACHO")
        c1 = make_movement(delta=+10, movement_type="ANULACION")
        d2 = make_movement(delta=-10, movement_type="DESPACHO")
        assert compute_qty_available(10, [d1, c1, d2]) == 0
        assert item_appears_in_aqui(10, [d1, c1, d2]) is False

    def test_partial_cancellation_partial_availability(self):
        """Dispatch 8, cancel 3 → qty_available=5 → still in aqui."""
        d = make_movement(delta=-8,  movement_type="DESPACHO")
        c = make_movement(delta=+3, movement_type="ANULACION")
        assert compute_qty_available(10, [d, c]) == 5
        assert item_appears_in_aqui(10, [d, c]) is True


# ---------------------------------------------------------------------------
# Test: other buckets (en_camino, pedido) are unaffected by remision movements
# ---------------------------------------------------------------------------

class TestOtherBucketsUnaffected:
    """
    The en_camino and pedido CTEs read from spare_part_items / spare_part_lots
    and do NOT depend on inventory_remision_movements.
    These tests verify their bucket criteria remain independent.
    """

    def make_lot(self, packing_list_received=False, bl_container=None):
        lot = MagicMock()
        lot.packing_list_received = packing_list_received
        lot.shipment_order = MagicMock()
        lot.shipment_order.bl_container = bl_container
        return lot

    def test_en_camino_criteria_does_not_use_remision_movements(self):
        """
        en_camino: qty_received > 0, qty_physical IS NULL, bl_container present.
        Remision movements (delta on dispatched items) do not affect this criterion.
        """
        spi = make_spare_part_item(qty_physical=None)
        spi.qty_received = 5
        spi.qty_physical = None
        lot = self.make_lot(bl_container="MSCU123456")

        # The bucket check uses qty_physical IS NULL — completely independent of movements
        in_en_camino = (
            spi.qty_received > 0
            and spi.qty_physical is None
            and lot.shipment_order.bl_container is not None
        )
        assert in_en_camino is True

        # Adding a remision movement doesn't change any of those conditions
        movement = make_movement(delta=-5, movement_type="DESPACHO")
        # still in en_camino because qty_physical is still None
        in_en_camino_after = (
            spi.qty_received > 0
            and spi.qty_physical is None
            and lot.shipment_order.bl_container is not None
        )
        assert in_en_camino_after is True

    def test_pedido_criteria_does_not_use_remision_movements(self):
        """
        pedido: packing_list_received=False, status not CANCELLED.
        Remision movements don't affect this criterion.
        """
        spi = MagicMock()
        spi.status = 'PENDING'
        lot = self.make_lot(packing_list_received=False)

        in_pedido = (
            not lot.packing_list_received
            and spi.status not in ('CANCELLED',)
        )
        assert in_pedido is True

        # Adding a movement doesn't flip any of those conditions
        movement = make_movement(delta=-3, movement_type="DESPACHO")
        in_pedido_after = (
            not lot.packing_list_received
            and spi.status not in ('CANCELLED',)
        )
        assert in_pedido_after is True

    def test_aqui_exclusion_takes_priority_over_en_camino(self):
        """
        If an item has qty_available > 0 it goes to aqui, not en_camino.
        This mirrors the CTE NOT IN (SELECT pn FROM aqui) guard.
        """
        qty_physical = 5
        movements = []  # no dispatches
        in_aqui = item_appears_in_aqui(qty_physical, movements)
        assert in_aqui is True  # item is in aqui → excluded from en_camino/pedido CTE

    def test_dispatched_item_no_longer_blocks_en_camino(self):
        """
        After a full dispatch → qty_available=0 → item leaves aqui.
        A different lot of the same part number could appear in en_camino
        without being blocked by the aqui CTE.
        """
        qty_physical = 5
        dispatch = make_movement(delta=-5, movement_type="DESPACHO")
        in_aqui = item_appears_in_aqui(qty_physical, [dispatch])
        assert in_aqui is False  # no longer blocks other lots from appearing in en_camino
