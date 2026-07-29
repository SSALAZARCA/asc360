"""
tests/superadmin_data/test_warranty_lower_bound.py --
`sdd/distributor-vehicle-delivery` PR2, task 2.9: RED tests for the
warranty lower-bound invariant wired into `PUT /superadmin/data/orders/{id}`
(`update_order`), immediately after the pre-existing
`_ensure_delivered_after_created` block and before any `setattr` (Design:
File Changes, `superadmin_data.py` entry). No `client_id` write on this
path (ADR 13 exclusion) -- confirmed by `test_no_client_id_write_on_this_path`.
"""
import uuid
from datetime import date, datetime

from tests.conftest import make_test_client
from tests.superadmin_data.conftest import FakeOrderSession, make_order, make_vehicle


def make_superadmin() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def base_payload(created_at: str, delivered_at=None) -> dict:
    return {
        "created_at": created_at,
        "delivered_at": delivered_at,
        "mileage_km": None,
        "service_type": None,
        "confirm_delete_event": False,
    }


def test_backdating_created_at_below_delivery_date_returns_422_and_order_unmutated():
    vehicle = make_vehicle(plate="ABC123")
    vehicle.delivery_date = date(2026, 7, 10)
    order = make_order(vehicle=vehicle, created_at=datetime(2026, 7, 15), delivered_at=None)
    fake_db = FakeOrderSession(get_object=order, vehicle=vehicle)

    payload = base_payload("2026-07-05T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 422
    assert fake_db.added == []
    assert fake_db.committed is False
    assert order.created_at == datetime(2026, 7, 15)


def test_backdating_created_at_at_or_after_delivery_date_succeeds():
    vehicle = make_vehicle(plate="ABC123")
    vehicle.delivery_date = date(2026, 7, 10)
    order = make_order(vehicle=vehicle, created_at=datetime(2026, 7, 15), delivered_at=None)
    fake_db = FakeOrderSession(get_object=order, vehicle=vehicle)

    payload = base_payload("2026-07-10T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["created_at"].startswith("2026-07-10")


def test_no_delivery_date_leaves_backdating_unblocked():
    vehicle = make_vehicle(plate="ABC123")
    assert vehicle.delivery_date is None
    order = make_order(vehicle=vehicle, created_at=datetime(2026, 7, 15), delivered_at=None)
    fake_db = FakeOrderSession(get_object=order, vehicle=vehicle)

    payload = base_payload("2020-01-01T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200


def test_no_client_id_write_on_this_path():
    """ADR 13 exclusion: this path never touches `client_id`, even though
    it now shares the warranty helper with the two paths that do."""
    vehicle = make_vehicle(plate="ABC123")
    vehicle.client_id = None
    order = make_order(vehicle=vehicle, created_at=datetime(2026, 7, 15), delivered_at=None)
    fake_db = FakeOrderSession(get_object=order, vehicle=vehicle)

    payload = base_payload("2026-07-16T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert vehicle.client_id is None
