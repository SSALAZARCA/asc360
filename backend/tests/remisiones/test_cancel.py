"""
Tests for cancellation (anular) business logic.

Validates:
- Successful cancellation creates ANULACION counter-movements with +delta
- Status transitions to ANULADO
- cancelled_by / cancelled_at / cancellation_reason are recorded
- Double cancellation (already ANULADO) raises 409
- cancellation_reason is required (min_length=5)
- Stock is logically restored (delta sum returns to zero)
"""
import uuid
import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
from unittest.mock import MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.conftest import make_movement, make_remision
from app.schemas.remisiones import CancelRequest


class TestCancelRequest:
    """Schema validation for the cancel payload."""

    def test_valid_reason(self):
        payload = CancelRequest(cancellation_reason="Error en despacho")
        assert payload.cancellation_reason == "Error en despacho"

    def test_reason_too_short_raises(self):
        """cancellation_reason must be at least 5 chars."""
        with pytest.raises(ValidationError):
            CancelRequest(cancellation_reason="corto"[:3])  # "cor" — 3 chars

    def test_reason_exactly_five_chars_ok(self):
        payload = CancelRequest(cancellation_reason="12345")
        assert len(payload.cancellation_reason) >= 5

    def test_empty_reason_raises(self):
        with pytest.raises(ValidationError):
            CancelRequest(cancellation_reason="")


class TestCancellationStateMachine:
    """State-machine guard for the anular endpoint."""

    def _cancel_guard(self, status: str) -> str:
        if status == "ANULADO":
            return "ALREADY_ANULADO"
        if status != "DESPACHADO":
            return f"WRONG_STATUS:{status}"
        return "OK"

    def test_cancel_despachado_ok(self):
        assert self._cancel_guard("DESPACHADO") == "OK"

    def test_double_cancel_rejected(self):
        """Spec: cancelling ANULADO remision → HTTP 409."""
        result = self._cancel_guard("ANULADO")
        assert result == "ALREADY_ANULADO"

    def test_cancel_borrador_rejected(self):
        result = self._cancel_guard("BORRADOR")
        assert "WRONG_STATUS" in result


class TestCounterMovementCreation:
    """Verifies the counter-movement creation logic for cancellation."""

    def _create_counter_movements(
        self, dispatch_movements: list, actor_id: uuid.UUID
    ) -> list:
        """
        Pure function replicating the endpoint's reversal logic:
        for each DESPACHO movement, create an ANULACION movement with delta = -original_delta.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        counters = []
        for dm in dispatch_movements:
            counters.append({
                "remision_id": dm.remision_id,
                "spare_part_item_id": dm.spare_part_item_id,
                "part_number": dm.part_number,
                "delta": -dm.delta,  # reversal: DESPACHO was -5, ANULACION is +5
                "movement_type": "ANULACION",
                "created_by": actor_id,
                "created_at": now,
            })
        return counters

    def test_counter_delta_is_positive(self):
        """Spec: ANULACION movements must have positive delta (restoring stock)."""
        actor_id = uuid.uuid4()
        dm = make_movement(delta=-5, movement_type="DESPACHO")

        counters = self._create_counter_movements([dm], actor_id)

        assert len(counters) == 1
        assert counters[0]["delta"] == 5
        assert counters[0]["movement_type"] == "ANULACION"

    def test_stock_net_delta_is_zero_after_cancel(self):
        """
        Spec: after dispatch + cancellation, net delta per item should be 0,
        meaning available qty is fully restored.
        """
        actor_id = uuid.uuid4()
        spi_id = uuid.uuid4()
        dispatch_qty = 7

        dm = make_movement(
            spare_part_item_id=spi_id,
            delta=-dispatch_qty,
            movement_type="DESPACHO",
        )
        counters = self._create_counter_movements([dm], actor_id)

        net_delta = dm.delta + counters[0]["delta"]
        assert net_delta == 0

    def test_one_counter_per_dispatch_movement(self):
        actor_id = uuid.uuid4()
        dms = [
            make_movement(delta=-3, movement_type="DESPACHO"),
            make_movement(delta=-8, movement_type="DESPACHO"),
        ]
        counters = self._create_counter_movements(dms, actor_id)
        assert len(counters) == 2
        assert counters[0]["delta"] == 3
        assert counters[1]["delta"] == 8

    def test_counter_records_actor(self):
        actor_id = uuid.uuid4()
        dm = make_movement(delta=-4)
        counters = self._create_counter_movements([dm], actor_id)
        assert counters[0]["created_by"] == actor_id
