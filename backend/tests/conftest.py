"""
Top-level pytest conftest — auto-loaded for every test module in `tests/`.

Holds two kinds of shared plumbing:
1. Remisiones fixtures (pure unit tests using MagicMock/AsyncMock — no live
   database required, keeps tests fast, no test DATABASE_URL needed).
2. The project's first HTTP-layer test harness (`make_test_client`): a
   `starlette.testclient.TestClient` factory wrapping `app.main.app` with
   `get_db`/`get_current_user` overridden via FastAPI's
   `app.dependency_overrides` — real routing/DI, no live DB, no live HTTP
   server. Lives here (not in `tests/imports/conftest.py`) specifically so
   any future tier/module can `from tests.conftest import make_test_client`.

To run: pytest backend/tests/ -v
"""
import uuid
import pytest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user


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
    item.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
    m.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
    r.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    r.updated_at = None
    r.items = items if items is not None else []
    r.movements = movements if movements is not None else []
    return r


# ---------------------------------------------------------------------------
# HTTP-layer test harness — TestClient + FastAPI dependency overrides.
# Reused by any test module/tier: `from tests.conftest import make_test_client`.
# ---------------------------------------------------------------------------

@contextmanager
def make_test_client(current_user, fake_db_session):
    """
    Yields a `TestClient` for `app.main.app` with `get_db` and
    `get_current_user` overridden — real FastAPI routing/DI, no live DB,
    no JWT/auth header needed.

    `current_user`: a `CurrentUser` instance (see `make_actor`/
    `make_imports_editor` in module-specific conftests) returned directly
    by the `get_current_user` override.

    `fake_db_session`: any object exposing the subset of `AsyncSession`'s
    surface the endpoint under test needs (e.g. `imports.conftest.
    FakeAsyncSession`), yielded directly by the `get_db` override.

    Overrides are removed on exit so later tests/modules start clean, even
    if the caller's `with` block raises.
    """
    async def _override_get_db():
        yield fake_db_session

    async def _override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
