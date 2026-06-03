"""
Shared fixtures for remisiones tests.

These tests follow the project's established pattern of pure unit tests
using MagicMock / AsyncMock objects — no live database required.
This avoids needing a test DATABASE_URL in CI and keeps tests fast.

To run: pytest backend/tests/ -v
"""
import uuid
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Factory helpers — build lightweight mock objects that simulate ORM models
# ---------------------------------------------------------------------------

def make_spare_part_item(
    part_number: str = "REF001",
    qty_physical: int = 10,
    lot_id: uuid.UUID = None,
) -> MagicMock:
    spi = MagicMock()
    spi.id = uuid.uuid4()
    spi.part_number = part_number
    spi.qty_physical = qty_physical
    spi.lot_id = lot_id or uuid.uuid4()
    return spi


def make_remision_item(
    spare_part_item_id: uuid.UUID = None,
    part_number: str = "REF001",
    qty_dispatched: int = 5,
    remision_id: uuid.UUID = None,
) -> MagicMock:
    item = MagicMock()
    item.id = uuid.uuid4()
    item.remision_id = remision_id or uuid.uuid4()
    item.spare_part_item_id = spare_part_item_id or uuid.uuid4()
    item.part_number = part_number
    item.qty_dispatched = qty_dispatched
    item.created_at = datetime.utcnow()
    return item


def make_movement(
    remision_id: uuid.UUID = None,
    spare_part_item_id: uuid.UUID = None,
    part_number: str = "REF001",
    delta: int = -5,
    movement_type: str = "DESPACHO",
    created_by: uuid.UUID = None,
) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.remision_id = remision_id or uuid.uuid4()
    m.spare_part_item_id = spare_part_item_id or uuid.uuid4()
    m.part_number = part_number
    m.delta = delta
    m.movement_type = movement_type
    m.created_by = created_by or uuid.uuid4()
    m.created_at = datetime.utcnow()
    return m


def make_remision(
    type: str = "GARANTIA",
    status: str = "BORRADOR",
    reference_lot_id: uuid.UUID = None,
    items: list = None,
    movements: list = None,
    created_by: uuid.UUID = None,
) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.type = type
    r.status = status
    r.reference_lot_id = reference_lot_id
    r.notes = None
    r.remision_number = None
    r.dispatched_by = None
    r.dispatched_at = None
    r.cancelled_by = None
    r.cancelled_at = None
    r.cancellation_reason = None
    r.created_by = created_by or uuid.uuid4()
    r.created_at = datetime.utcnow()
    r.updated_at = None
    r.items = items if items is not None else []
    r.movements = movements if movements is not None else []
    return r
