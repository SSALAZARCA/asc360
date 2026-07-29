"""
Shared fixtures for `distributor_deliveries` tests — follows the project's
established fake-`CurrentUser`/`NoTouchSession` convention (see
`tests/historical_orders/conftest.py`, `tests/superadmin_data/
test_role_guard_regression.py`).

Phase 3 (this batch) only needs a minimal double: the router stub in
`app/api/v1/distributor_deliveries.py` guards then 501s before touching the
database, and the schema/model contract test doesn't touch a session at
all. The full transactional `FakeDeliverySession` (mirroring
`FakeHistoricalOrderSession`) arrives in PR4 alongside the real service.
"""
import json
import uuid

from app.api.deps import CurrentUser


def make_distribuidor() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()), role="parts_dealer", tenant_id=None, name="Distribuidor"
    )


def make_superadmin() -> CurrentUser:
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def make_jefe_taller() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()),
        role="jefe_taller",
        tenant_id=str(uuid.uuid4()),
        name="Jefe",
    )


class NoTouchSession:
    """Fake DB session that fails the test if the route touches it at all.

    Phase 3's router body is guard-then-501 — no reads/writes are
    legitimate yet. Mirrors `tests/historical_orders/conftest.py`'s
    `NoTouchSession`."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("route touched db.execute() before the guard/stub short-circuited")

    async def get(self, *args, **kwargs):
        raise AssertionError("route touched db.get() before the guard/stub short-circuited")

    def add(self, *args, **kwargs):
        raise AssertionError("route touched db.add() before the guard/stub short-circuited")

    async def commit(self, *args, **kwargs):
        raise AssertionError("route touched db.commit() before the guard/stub short-circuited")

    async def rollback(self, *args, **kwargs):
        raise AssertionError("route touched db.rollback() before the guard/stub short-circuited")

    async def delete(self, *args, **kwargs):
        raise AssertionError("route touched db.delete() before the guard/stub short-circuited")


VALID_DELIVERY_PAYLOAD = {
    "client": {
        "name": "Juan Perez",
        "identification": "123456789",
        "birth_date": "1990-05-10",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "address": "Calle 1 # 2-3",
        "phone": "3001234567",
        "email": "juan@example.com",
    },
    "vehicle": {
        "plate": "ABC123",
        "vin": "1HGCM82633A004352",
        "model": "DSR",
        "color": "Rojo",
        "year": 2026,
        "engine_number": "ENG12345",
    },
    "delivery_date": "2026-07-28",
}

VALID_DELIVERY_PAYLOAD_JSON = json.dumps(VALID_DELIVERY_PAYLOAD)
