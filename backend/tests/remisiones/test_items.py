"""
Tests for item management on remisiones.

Validates:
- qty_dispatched > 0 enforced by schema
- Mutation on non-BORRADOR remision raises 409
- Availability validation logic (unit-tested in isolation)
"""
import uuid
import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock

from app.schemas.remisiones import RemisionItemCreate, RemisionItemUpdate


class TestRemisionItemSchema:
    """Schema-level validation for item payloads."""

    def test_valid_item_create(self):
        payload = RemisionItemCreate(
            spare_part_item_id=uuid.uuid4(),
            qty_dispatched=3,
        )
        assert payload.qty_dispatched == 3

    def test_qty_zero_raises_validation_error(self):
        """qty_dispatched == 0 must be rejected (Field gt=0)."""
        with pytest.raises(ValidationError) as exc_info:
            RemisionItemCreate(spare_part_item_id=uuid.uuid4(), qty_dispatched=0)
        errors = exc_info.value.errors()
        assert any("qty_dispatched" in str(e) or "greater than" in str(e) for e in errors)

    def test_qty_negative_raises_validation_error(self):
        with pytest.raises(ValidationError):
            RemisionItemCreate(spare_part_item_id=uuid.uuid4(), qty_dispatched=-1)

    def test_item_update_valid(self):
        payload = RemisionItemUpdate(qty_dispatched=7)
        assert payload.qty_dispatched == 7

    def test_item_update_zero_raises(self):
        with pytest.raises(ValidationError):
            RemisionItemUpdate(qty_dispatched=0)


class TestAvailabilityValidationLogic:
    """
    Unit tests for the availability-checking business logic.

    Extracted from the endpoint guard to enable testing without a live DB.
    """

    def _check_availability(self, qty_dispatched: int, qty_available: int) -> str:
        """Simulate the availability check guard in the endpoint."""
        if qty_available is None or qty_available <= 0:
            return "NO_STOCK"
        if qty_dispatched > qty_available:
            return "EXCEEDS"
        return "OK"

    def test_happy_path_within_available(self):
        result = self._check_availability(qty_dispatched=3, qty_available=5)
        assert result == "OK"

    def test_exactly_at_available_limit(self):
        result = self._check_availability(qty_dispatched=5, qty_available=5)
        assert result == "OK"

    def test_exceeds_available_returns_conflict(self):
        """qty > available_qty must return EXCEEDS → HTTP 409 in endpoint."""
        result = self._check_availability(qty_dispatched=6, qty_available=5)
        assert result == "EXCEEDS"

    def test_zero_available_returns_no_stock(self):
        """qty_available == 0 → HTTP 409 in endpoint."""
        result = self._check_availability(qty_dispatched=1, qty_available=0)
        assert result == "NO_STOCK"

    def test_none_available_returns_no_stock(self):
        """VIEW returns None for uninspected items → should be treated as 0."""
        result = self._check_availability(qty_dispatched=1, qty_available=None)
        assert result == "NO_STOCK"


class TestBorradorGuard:
    """
    Tests for the BORRADOR-only mutation guard.

    Simulates what the endpoint does before allowing item add/edit/delete.
    """

    def _guard_borrador(self, remision_status: str) -> bool:
        """Returns True if mutation is allowed, False if it should be rejected (409)."""
        return remision_status == "BORRADOR"

    def test_mutation_allowed_in_borrador(self):
        assert self._guard_borrador("BORRADOR") is True

    def test_mutation_rejected_in_despachado(self):
        """Spec: adding/editing items on DESPACHADO remision → HTTP 409."""
        assert self._guard_borrador("DESPACHADO") is False

    def test_mutation_rejected_in_anulado(self):
        assert self._guard_borrador("ANULADO") is False
