"""
tests/orders/test_mini_app_get_vehicle_client.py -- `GET
/orders/mini-app/vehicle/{plate}` (sdd/distributor-vehicle-delivery PR5,
design-dual-channel ADR 14/19): `mini_app_get_vehicle` gains a
`Vehicle.client` eager load (`selectinload`, alongside the existing
`service_orders` one) and returns the REAL `client_id`/`client` instead of
the hardcoded `"client_id": None` it always returned before. `client` is a
nested `{name, phone, email, address}` dict when `vehicle.client_id` is
set, `null` when it is not -- the SAME shape `GET /vehicles/{plate}`
returns via `VehicleClientOut` (ADR 19), so both reception surfaces agree.

Same `FakeMiniAppSession` (dispatch by `len(stmt.column_descriptions)`)
and `make_current_user`/`make_vehicle` convention as `test_mini_app_
get_vehicle_claim.py` -- no live DB.
"""
import uuid
from types import SimpleNamespace

from app.api.v1 import orders as orders_module

from tests.orders.test_mini_app_get_vehicle_claim import (
    FakeMiniAppSession,
    make_current_user,
    make_vehicle,
)


def make_client_user(**overrides) -> SimpleNamespace:
    data = dict(name="Juan Perez", phone="3001234567", email="juan@x.com", address="Calle 1")
    data.update(overrides)
    return SimpleNamespace(**data)


class TestMiniAppGetVehicleReturnsLinkedClient:
    async def test_returns_real_client_and_client_id_when_linked(self):
        client_user = make_client_user()
        client_id = uuid.uuid4()
        vehicle = make_vehicle(client_id=client_id, client=client_user)
        db = FakeMiniAppSession(vehicle=vehicle)

        result = await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(role="superadmin"),
        )

        assert result["client_id"] == str(client_id)
        assert result["client"] == {
            "name": "Juan Perez", "phone": "3001234567", "email": "juan@x.com", "address": "Calle 1",
        }

    async def test_client_and_client_id_are_none_when_unlinked(self):
        vehicle = make_vehicle(client_id=None, client=None)
        db = FakeMiniAppSession(vehicle=vehicle)

        result = await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(role="superadmin"),
        )

        assert result["client_id"] is None
        assert result["client"] is None

    async def test_default_make_vehicle_still_has_no_client_link(self):
        """Regression: the pre-existing `make_vehicle()` factory (no
        `client`/`client_id` args) must keep working for every OTHER test
        in `test_mini_app_get_vehicle_claim.py` that doesn't care about
        the client link."""
        vehicle = make_vehicle()
        db = FakeMiniAppSession(vehicle=vehicle)

        result = await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(role="superadmin"),
        )

        assert result["client_id"] is None
        assert result["client"] is None
