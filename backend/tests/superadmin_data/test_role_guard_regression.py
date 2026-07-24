"""
tests/superadmin_data/test_role_guard_regression.py — Phase 1 role-guard
regression for the superadmin data-editor router.

Every route on `app/api/v1/superadmin_data.py` MUST reject a non-superadmin
caller with 403 *before* touching the database, mirroring the guard pattern
already used in `app/api/v1/settings.py`. This test asserts, for every route,
that a `jefe_taller` caller gets 403 and the fake DB session records zero
reads/writes.
"""
import uuid

from tests.conftest import make_test_client


def make_superadmin() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def make_jefe_taller() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(
        user_id=str(uuid.uuid4()),
        role="jefe_taller",
        tenant_id=str(uuid.uuid4()),
        name="Jefe",
    )


class NoTouchSession:
    """Fake DB session that fails the test if the route touches it at all.

    The role guard MUST short-circuit before any `execute`/`get`/`add`/
    `commit` call, so any interaction here is a bug.
    """

    async def execute(self, *args, **kwargs):
        raise AssertionError("route touched db.execute() before the guard rejected the request")

    async def get(self, *args, **kwargs):
        raise AssertionError("route touched db.get() before the guard rejected the request")

    def add(self, *args, **kwargs):
        raise AssertionError("route touched db.add() before the guard rejected the request")

    async def commit(self, *args, **kwargs):
        raise AssertionError("route touched db.commit() before the guard rejected the request")

    async def delete(self, *args, **kwargs):
        raise AssertionError("route touched db.delete() before the guard rejected the request")

    async def rollback(self, *args, **kwargs):
        raise AssertionError("route touched db.rollback() before the guard rejected the request")


VALID_VEHICLE_PAYLOAD = {
    "plate": "ABC123",
    "brand": "UM",
    "model": "DSR",
    "vin": None,
    "color": "Rojo",
    "year": 2024,
    "mileage": 1000,
}

VALID_ORDER_PAYLOAD = {
    "created_at": "2026-07-01T00:00:00",
    "delivered_at": None,
    "mileage_km": None,
    "service_type": None,
    "confirm_delete_event": False,
}


def test_get_vehicles_rejects_non_superadmin_with_no_db_touch():
    with make_test_client(make_jefe_taller(), NoTouchSession()) as client:
        res = client.get("/api/v1/superadmin/data/vehicles", params={"plate": "ABC123"})
        assert res.status_code == 403


def test_put_vehicle_rejects_non_superadmin_with_no_db_touch():
    with make_test_client(make_jefe_taller(), NoTouchSession()) as client:
        res = client.put(
            f"/api/v1/superadmin/data/vehicles/{uuid.uuid4()}",
            json=VALID_VEHICLE_PAYLOAD,
        )
        assert res.status_code == 403


def test_get_orders_rejects_non_superadmin_with_no_db_touch():
    with make_test_client(make_jefe_taller(), NoTouchSession()) as client:
        res = client.get(
            "/api/v1/superadmin/data/orders",
            params={"plate": "ABC123", "order_id": str(uuid.uuid4())},
        )
        assert res.status_code == 403


def test_put_order_rejects_non_superadmin_with_no_db_touch():
    with make_test_client(make_jefe_taller(), NoTouchSession()) as client:
        res = client.put(
            f"/api/v1/superadmin/data/orders/{uuid.uuid4()}",
            json=VALID_ORDER_PAYLOAD,
        )
        assert res.status_code == 403


def test_superadmin_passes_guard_and_reaches_real_search_logic():
    """Vehicle routes got their real implementation in Phase 2 (see
    `test_vehicle_quick_fix.py`) and Order dates search/update in Phase 3
    (see `test_order_quick_fix_dates.py`) — no route on this router is a
    501 stub anymore. A superadmin caller should clear the guard and reach
    the real search logic (404 on a miss), never a 403."""
    from tests.superadmin_data.conftest import FakeOrderSession

    with make_test_client(make_superadmin(), FakeOrderSession(search_result=[])) as client:
        res = client.get(
            "/api/v1/superadmin/data/orders",
            params={"plate": "ZZZ999"},
        )
        assert res.status_code == 404
