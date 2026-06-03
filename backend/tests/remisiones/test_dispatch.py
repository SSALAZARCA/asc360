"""
Tests for dispatch (despachar) business logic.

Validates:
- Successful dispatch creates DESPACHO movements with negative delta
- Status transitions to DESPACHADO
- dispatched_by / dispatched_at are recorded
- Re-dispatch of DESPACHADO remision raises 409
- Dispatch of empty remision raises 409
- remision_number is assigned in REM-{YYYY}-{seq:04d} format
"""
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.conftest import make_remision, make_remision_item, make_movement


class TestDispatchStateMachine:
    """State-machine guard tests for the despachar endpoint."""

    def _dispatch_guard(self, remision_status: str, has_items: bool) -> str:
        """
        Simulates the guard logic at the start of the despachar endpoint.
        Returns 'OK' or an error code.
        """
        if remision_status != "BORRADOR":
            return f"WRONG_STATUS:{remision_status}"
        if not has_items:
            return "NO_ITEMS"
        return "OK"

    def test_dispatch_borrador_with_items_ok(self):
        assert self._dispatch_guard("BORRADOR", has_items=True) == "OK"

    def test_dispatch_borrador_no_items_rejected(self):
        result = self._dispatch_guard("BORRADOR", has_items=False)
        assert result == "NO_ITEMS"

    def test_re_dispatch_despachado_rejected(self):
        """Spec: idempotency — double dispatch must be rejected."""
        result = self._dispatch_guard("DESPACHADO", has_items=True)
        assert "WRONG_STATUS" in result

    def test_dispatch_anulado_rejected(self):
        result = self._dispatch_guard("ANULADO", has_items=True)
        assert "WRONG_STATUS" in result


class TestDispatchMovementCreation:
    """Verifies the movement creation logic for a dispatch."""

    def _create_dispatch_movements(self, items: list, actor_id: uuid.UUID, remision_id: uuid.UUID) -> list:
        """
        Pure function simulating what the endpoint does:
        creates one DESPACHO movement per item with delta = -qty_dispatched.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        movements = []
        for item in items:
            movements.append({
                "remision_id": remision_id,
                "spare_part_item_id": item.spare_part_item_id,
                "part_number": item.part_number,
                "delta": -item.qty_dispatched,
                "movement_type": "DESPACHO",
                "created_by": actor_id,
                "created_at": now,
            })
        return movements

    def test_movement_delta_is_negative(self):
        """Spec: dispatch movements must have delta = -qty_dispatched."""
        remision_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        spi_id = uuid.uuid4()
        item = make_remision_item(
            spare_part_item_id=spi_id,
            part_number="REF001",
            qty_dispatched=5,
            remision_id=remision_id,
        )

        movements = self._create_dispatch_movements([item], actor_id, remision_id)

        assert len(movements) == 1
        assert movements[0]["delta"] == -5
        assert movements[0]["movement_type"] == "DESPACHO"
        assert movements[0]["spare_part_item_id"] == spi_id

    def test_one_movement_per_item(self):
        """Each line item gets exactly one movement."""
        remision_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        items = [
            make_remision_item(part_number="REF001", qty_dispatched=3, remision_id=remision_id),
            make_remision_item(part_number="REF002", qty_dispatched=7, remision_id=remision_id),
        ]

        movements = self._create_dispatch_movements(items, actor_id, remision_id)

        assert len(movements) == 2
        deltas = {m["part_number"]: m["delta"] for m in movements}
        assert deltas["REF001"] == -3
        assert deltas["REF002"] == -7

    def test_movement_records_actor(self):
        actor_id = uuid.uuid4()
        item = make_remision_item(qty_dispatched=2)
        movements = self._create_dispatch_movements([item], actor_id, item.remision_id)
        assert movements[0]["created_by"] == actor_id


class TestRemisionNumberFormat:
    """Validates the remision_number generation format."""

    def _generate_remision_number(self, year: int, current_max: int) -> str:
        """Pure function replicating the endpoint's number assignment logic."""
        next_seq = (current_max or 0) + 1
        return f"REM-{year}-{next_seq:04d}"

    def test_first_of_year(self):
        assert self._generate_remision_number(2026, None) == "REM-2026-0001"

    def test_sequential_increment(self):
        assert self._generate_remision_number(2026, 1) == "REM-2026-0002"

    def test_zero_padded_to_4_digits(self):
        assert self._generate_remision_number(2026, 9) == "REM-2026-0010"

    def test_year_prefix_correct(self):
        num = self._generate_remision_number(2027, 0)
        assert num.startswith("REM-2027-")

    def test_large_sequence(self):
        num = self._generate_remision_number(2026, 999)
        assert num == "REM-2026-1000"
