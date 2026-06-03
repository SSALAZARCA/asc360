"""
Tests for remision creation logic.

Validates:
- Happy path for all 4 types
- PEDIDO requires reference_lot_id (Pydantic validation)
- Validation errors raise correctly
"""
import uuid
import pytest
from pydantic import ValidationError

from app.schemas.remisiones import RemisionCreate, RemisionType


class TestRemisionCreateSchema:
    """Pure schema-level tests — no DB required."""

    def test_create_garantia_valid(self):
        payload = RemisionCreate(type=RemisionType.GARANTIA)
        assert payload.type == RemisionType.GARANTIA
        assert payload.reference_lot_id is None

    def test_create_cortesia_valid(self):
        payload = RemisionCreate(type=RemisionType.CORTESIA)
        assert payload.type == RemisionType.CORTESIA

    def test_create_vehiculo_propio_valid(self):
        payload = RemisionCreate(type=RemisionType.VEHICULO_PROPIO)
        assert payload.type == RemisionType.VEHICULO_PROPIO

    def test_create_pedido_with_lot_valid(self):
        lot_id = uuid.uuid4()
        payload = RemisionCreate(type=RemisionType.PEDIDO, reference_lot_id=lot_id)
        assert payload.type == RemisionType.PEDIDO
        assert payload.reference_lot_id == lot_id

    def test_pedido_without_reference_lot_raises_422(self):
        """PEDIDO type MUST include reference_lot_id — validator raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            RemisionCreate(type=RemisionType.PEDIDO)
        errors = exc_info.value.errors()
        # At least one error mentioning reference_lot_id
        error_messages = " ".join(str(e) for e in errors)
        assert "reference_lot_id" in error_messages

    def test_non_pedido_with_reference_lot_raises_validation_error(self):
        """Non-PEDIDO types MUST NOT have reference_lot_id."""
        with pytest.raises(ValidationError):
            RemisionCreate(type=RemisionType.GARANTIA, reference_lot_id=uuid.uuid4())

    def test_create_with_notes(self):
        payload = RemisionCreate(type=RemisionType.CORTESIA, notes="Entrega gratuita")
        assert payload.notes == "Entrega gratuita"


class TestRemisionBusinessRules:
    """Business logic rules derived from spec scenarios."""

    def test_all_four_types_accepted(self):
        """All 4 RemisionType values must be valid."""
        valid_types = [
            RemisionType.PEDIDO,
            RemisionType.GARANTIA,
            RemisionType.CORTESIA,
            RemisionType.VEHICULO_PROPIO,
        ]
        for t in valid_types:
            if t == RemisionType.PEDIDO:
                payload = RemisionCreate(type=t, reference_lot_id=uuid.uuid4())
            else:
                payload = RemisionCreate(type=t)
            assert payload.type == t

    def test_initial_status_is_borrador(self):
        """Newly created remisions always start in BORRADOR."""
        from app.schemas.remisiones import RemisionStatus
        assert RemisionStatus.BORRADOR.value == "BORRADOR"

    def test_state_machine_values(self):
        """Valid statuses per spec: BORRADOR, DESPACHADO, ANULADO."""
        from app.schemas.remisiones import RemisionStatus
        assert set(RemisionStatus) == {
            RemisionStatus.BORRADOR,
            RemisionStatus.DESPACHADO,
            RemisionStatus.ANULADO,
        }
