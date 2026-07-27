"""
Shared fixtures for `historical_orders` tests — follows the project's
established fake-`AsyncSession` convention (see `tests/superadmin_data/
conftest.py`).

PR1 (this batch) only needs a minimal double: the router stub in
`app/api/v1/superadmin_historical_orders.py` guards then 501s before
touching the database, and the contract-lock/schema tests don't touch a
session at all. The full transactional `FakeHistoricalOrderSession`
(mirroring `FakeOrderSession`) arrives in PR2 alongside the real service.
"""
import uuid

from app.api.deps import CurrentUser


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

    Phase 1's router body is guard-then-501 — no reads/writes are
    legitimate yet. Mirrors `tests/superadmin_data/test_role_guard_
    regression.py`'s `NoTouchSession`."""

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


VALID_HISTORICAL_ORDER_PAYLOAD = {
    "tenant_id": str(uuid.uuid4()),
    "vehicle": {"plate": "ABC123", "vin": None, "brand": "UM", "model": "DSR", "year": 2024, "color": "Rojo"},
    "client": {"name": "Juan Perez", "phone": "3001234567"},
    "service_type": "regular",
    "status": "received",
    "mileage_km": "1000",
    "created_at": "2025-01-10T09:00:00",
    "completed_at": None,
    "delivered_at": None,
    "customer_notes": None,
    "diagnosis": None,
    "general_observations": None,
    "technician_id": None,
    "acknowledge_duplicate": False,
}
