import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RemisionType(str, Enum):
    PEDIDO = "PEDIDO"
    GARANTIA = "GARANTIA"
    CORTESIA = "CORTESIA"
    VEHICULO_PROPIO = "VEHICULO_PROPIO"


class RemisionStatus(str, Enum):
    BORRADOR = "BORRADOR"
    DESPACHADO = "DESPACHADO"
    ANULADO = "ANULADO"


class MovementType(str, Enum):
    DESPACHO = "DESPACHO"
    ANULACION = "ANULACION"


# ---------------------------------------------------------------------------
# Item schemas
# ---------------------------------------------------------------------------

class RemisionItemCreate(BaseModel):
    spare_part_item_id: uuid.UUID
    qty_dispatched: int = Field(..., gt=0, description="Must be > 0")


class RemisionItemUpdate(BaseModel):
    qty_dispatched: int = Field(..., gt=0, description="Must be > 0")


class RemisionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    remision_id: uuid.UUID
    spare_part_item_id: uuid.UUID
    part_number: str
    qty_dispatched: int
    created_at: datetime
    # Populated at query time from the VIEW — not a DB column on this model
    qty_available: Optional[int] = None


# ---------------------------------------------------------------------------
# Movement schemas
# ---------------------------------------------------------------------------

class RemisionMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    remision_id: uuid.UUID
    spare_part_item_id: uuid.UUID
    part_number: str
    delta: int
    movement_type: str
    created_by: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Remision header schemas
# ---------------------------------------------------------------------------

class RemisionCreate(BaseModel):
    type: RemisionType
    reference_lot_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_pedido_requires_lot(self) -> "RemisionCreate":
        if self.type == RemisionType.PEDIDO and self.reference_lot_id is None:
            raise ValueError("reference_lot_id is required when type is PEDIDO")
        if self.type != RemisionType.PEDIDO and self.reference_lot_id is not None:
            raise ValueError("reference_lot_id must be null for non-PEDIDO types")
        return self


class RemisionUpdate(BaseModel):
    type: RemisionType
    reference_lot_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    items: List[RemisionItemCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pedido_requires_lot(self) -> "RemisionUpdate":
        if self.type == RemisionType.PEDIDO and self.reference_lot_id is None:
            raise ValueError("reference_lot_id is required when type is PEDIDO")
        if self.type != RemisionType.PEDIDO and self.reference_lot_id is not None:
            raise ValueError("reference_lot_id must be null for non-PEDIDO types")
        return self


class RemisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    status: str
    reference_lot_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    remision_number: Optional[str] = None
    dispatched_by: Optional[uuid.UUID] = None
    dispatched_at: Optional[datetime] = None
    cancelled_by: Optional[uuid.UUID] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None


class RemisionDetail(RemisionRead):
    items: List[RemisionItemRead] = []
    movements: List[RemisionMovementRead] = []


# ---------------------------------------------------------------------------
# Action schemas
# ---------------------------------------------------------------------------

class DispatchResponse(RemisionDetail):
    """Full remision detail returned after a successful dispatch."""
    pass


class CancelRequest(BaseModel):
    cancellation_reason: str = Field(..., min_length=5)


# ---------------------------------------------------------------------------
# Availability schema (from VIEW spare_part_availability)
# ---------------------------------------------------------------------------

class AvailabilityItem(BaseModel):
    spare_part_item_id: uuid.UUID
    part_number: str
    lot_id: uuid.UUID
    qty_available: int


# ---------------------------------------------------------------------------
# List response
# ---------------------------------------------------------------------------

class RemisionListResponse(BaseModel):
    items: List[RemisionRead]
    total: int
    skip: int
    limit: int
