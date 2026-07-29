"""
tests/vehicles/test_get_by_plate_client.py -- `GET /vehicles/{plate}`
(sdd/distributor-vehicle-delivery PR5, design-dual-channel ADR 19/20):

1. `VehicleOut.client` moves from `Optional[Any]` (always `None`, dead
   field) to a real nested `VehicleClientOut` (`name`/`phone`/`email`/
   `address`), so `Vehicle.client_id`/`Vehicle.client` (added PR1) convert
   automatically via `from_attributes` -- no route-body change needed
   (`vehicles.py:69` stays `return vehicle`).
2. Pre-existing, untested behaviour discovered in
   `vehicle_repository.get_by_plate`: a "Inyectar ultimo cliente" block
   overwrote `vehicle.client`/`vehicle.client_id` with the MOST RECENT
   SERVICE ORDER's client (an incomplete `{id,name,phone}` dict, no
   email/address) whenever `vehicle.service_orders` was non-empty --
   sourced from a DIFFERENT concept (order's client) than the
   Distribuidor-delivery buyer (`Vehicle.client_id` FK, ADR 12/13). This
   both violated ADR 19's shape contract (missing email/address) and
   risked a `MissingGreenlet` crash in the untouched branch (FK set,
   relationship not eagerly loaded, no service_orders yet -- exactly the
   "vehicle just delivered, first-ever service" scenario this PR exists
   to support). Confirmed via `test_get_by_plate_visibility.py`'s own
   docstring that this block was explicitly "out of scope" / untested
   there. Fixed by eager-loading `Vehicle.client` and removing the
   override so the FK is the single source of truth, matching ADR 19's
   assumption.
3. `GET /vehicles/{plate}` accepts EITHER `x-sonia-secret` (bot) OR a JWT
   (staff), same dual-auth already covering `GET /vin/{vin}`/`POST /`.
4. Response shape matches `mini_app_get_vehicle`'s `client` shape exactly
   (`name`/`phone`/`email`/`address`) -- the cross-endpoint parity the
   design's "same logic always" correction requires.

No live DB: endpoint-level tests monkeypatch `vehicle_service.
get_vehicle_by_plate` and drive the real route/response_model through
`TestClient` (same convention as `test_vin_master_lookup.py`). The
repository-level tests use the `FakeVehicleLookupSession` pattern from
`test_get_by_plate_visibility.py` plus real (transient, unattached)
`SimpleNamespace` vehicle/order stand-ins, matching `test_mini_app_
get_vehicle_claim.py`'s convention.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_optional_user, CurrentUser
from app.repositories.vehicle_repository import vehicle_repository
from app.schemas.vehicle import VehicleOut, VehicleClientOut
import app.api.v1.endpoints.vehicles as vehicles_endpoint
from app.services.vehicle_service import vehicle_service

SONIA_SECRET = "test-bot-secret"  # matches backend/conftest.py's env default


# ---------------------------------------------------------------------------
# Schema-level: VehicleOut.client actually converts a linked User now
# ---------------------------------------------------------------------------

class TestVehicleOutClientSchema:
    def test_linked_client_converts_to_the_shared_shape(self):
        fake_user = SimpleNamespace(name="Juan Perez", phone="3001234567", email="juan@x.com", address="Calle 1")
        fake_vehicle = SimpleNamespace(
            id=uuid.uuid4(), plate="ABC123", vin=None, brand="UM", model="DSR",
            year=2024, color=None, mileage=0,
            claimed_by_tenant_id=None, claimed_by_tenant_name=None,
            client_id=uuid.uuid4(), client=fake_user,
            latest_mileage=None, active_order=None, service_orders_summary=None,
        )

        out = VehicleOut.model_validate(fake_vehicle)

        assert out.client == VehicleClientOut(
            name="Juan Perez", phone="3001234567", email="juan@x.com", address="Calle 1",
        )

    def test_unlinked_vehicle_has_null_client(self):
        fake_vehicle = SimpleNamespace(
            id=uuid.uuid4(), plate="ABC123", vin=None, brand="UM", model="DSR",
            year=2024, color=None, mileage=0,
            claimed_by_tenant_id=None, claimed_by_tenant_name=None,
            client_id=None, client=None,
            latest_mileage=None, active_order=None, service_orders_summary=None,
        )

        out = VehicleOut.model_validate(fake_vehicle)

        assert out.client is None
        assert out.client_id is None


# ---------------------------------------------------------------------------
# Repository-level: the stale "latest order client" override is gone; the
# FK (`Vehicle.client_id`/`Vehicle.client`) is the single source of truth.
# ---------------------------------------------------------------------------

class _VehicleScalars:
    def __init__(self, vehicle):
        self._vehicle = vehicle

    def scalars(self):
        return self

    def first(self):
        return self._vehicle


class FakeVehicleLookupSession:
    def __init__(self, vehicle):
        self._vehicle = vehicle
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _VehicleScalars(self._vehicle)


def make_client(**overrides):
    data = dict(id=uuid.uuid4(), name="Cliente FK", phone="3000000000", email="fk@x.com", address="Dir FK")
    data.update(overrides)
    return SimpleNamespace(**data)


def make_order(client=None, created_at=None):
    from datetime import datetime
    return SimpleNamespace(
        client=client, reception=None, status=SimpleNamespace(value="in_progress"),
        created_at=created_at or datetime.utcnow(), tenant=None,
    )


class TestGetByPlateDoesNotOverrideClientFromLatestOrder:
    async def test_client_from_the_fk_survives_even_with_a_different_order_client(self):
        """The (now-removed) override used to replace `vehicle.client`/
        `client_id` with the LATEST SERVICE ORDER's client. After the fix,
        a vehicle whose FK-linked client differs from the latest order's
        client keeps the FK-linked one untouched."""
        fk_client = make_client(name="Comprador Distribuidor")
        order_client = make_client(name="Cliente de la Orden", id=uuid.uuid4())
        vehicle = SimpleNamespace(
            id=uuid.uuid4(), plate="ABC123",
            client_id=fk_client.id, client=fk_client,
            service_orders=[make_order(client=order_client)],
        )
        db = FakeVehicleLookupSession(vehicle)

        result = await vehicle_repository.get_by_plate(db, "ABC123", None)

        assert result.client is fk_client
        assert result.client_id == fk_client.id

    async def test_no_service_orders_and_no_client_link_stays_none_without_crashing(self):
        vehicle = SimpleNamespace(
            id=uuid.uuid4(), plate="ABC123",
            client_id=None, client=None,
            service_orders=[],
        )
        db = FakeVehicleLookupSession(vehicle)

        result = await vehicle_repository.get_by_plate(db, "ABC123", None)

        assert result.client is None
        assert result.client_id is None

    async def test_no_service_orders_but_client_link_already_set_is_preserved(self):
        """The scenario this PR exists for: a Distribuidor-delivered
        vehicle (`client_id` set) with NO service history yet -- the old
        code never touched `client`/`client_id` in this branch either, but
        never eager-loaded `Vehicle.client` for it, which would crash a
        real AsyncSession. Here we assert the (already-loaded, per the
        fix) value simply passes through untouched."""
        fk_client = make_client()
        vehicle = SimpleNamespace(
            id=uuid.uuid4(), plate="ABC123",
            client_id=fk_client.id, client=fk_client,
            service_orders=[],
        )
        db = FakeVehicleLookupSession(vehicle)

        result = await vehicle_repository.get_by_plate(db, "ABC123", None)

        assert result.client is fk_client
        assert result.client_id == fk_client.id


# ---------------------------------------------------------------------------
# Endpoint-level: GET /vehicles/{plate}, dual-auth, response shape.
# ---------------------------------------------------------------------------

def make_fake_vehicle(client=None, client_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(), plate="ABC123", vin=None, brand="UM", model="DSR",
        year=2024, color=None, mileage=0,
        claimed_by_tenant_id=None, claimed_by_tenant_name=None,
        client_id=client_id, client=client,
        latest_mileage=None, active_order=None, service_orders_summary=None,
    )


def make_test_client(current_user):
    async def _override_get_db():
        yield MagicMock()

    async def _override_get_optional_user():
        return current_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = _override_get_optional_user
    return TestClient(app)


def teardown_overrides():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_optional_user, None)


class TestGetVehicleByPlateReturnsLinkedClient:
    def test_bot_auth_returns_client_when_linked(self, monkeypatch):
        client_data = SimpleNamespace(name="Juan Perez", phone="3001234567", email="juan@x.com", address="Calle 1")
        fake_vehicle = make_fake_vehicle(client=client_data, client_id=uuid.uuid4())
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=fake_vehicle))

        client = make_test_client(None)
        try:
            res = client.get("/api/v1/vehicles/ABC123", headers={"x-sonia-secret": SONIA_SECRET})
        finally:
            teardown_overrides()

        assert res.status_code == 200
        body = res.json()
        assert body["client_id"] == str(fake_vehicle.client_id)
        assert body["client"] == {
            "name": "Juan Perez", "phone": "3001234567", "email": "juan@x.com", "address": "Calle 1",
        }

    def test_jwt_auth_returns_client_when_linked(self, monkeypatch):
        client_data = SimpleNamespace(name="Ana Gomez", phone="3009999999", email=None, address=None)
        fake_vehicle = make_fake_vehicle(client=client_data, client_id=uuid.uuid4())
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=fake_vehicle))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")

        client = make_test_client(user)
        try:
            res = client.get("/api/v1/vehicles/ABC123", headers={"Authorization": "Bearer fake"})
        finally:
            teardown_overrides()

        assert res.status_code == 200
        body = res.json()
        assert body["client"]["name"] == "Ana Gomez"
        assert body["client"]["email"] is None

    def test_client_is_null_when_vehicle_has_no_link(self, monkeypatch):
        fake_vehicle = make_fake_vehicle(client=None, client_id=None)
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=fake_vehicle))

        client = make_test_client(None)
        try:
            res = client.get("/api/v1/vehicles/ABC123", headers={"x-sonia-secret": SONIA_SECRET})
        finally:
            teardown_overrides()

        assert res.status_code == 200
        body = res.json()
        assert body["client"] is None
        assert body["client_id"] is None

    def test_no_auth_at_all_is_still_rejected(self, monkeypatch):
        fake_vehicle = make_fake_vehicle()
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=fake_vehicle))

        client = make_test_client(None)
        try:
            res = client.get("/api/v1/vehicles/ABC123")
        finally:
            teardown_overrides()

        assert res.status_code == 403
