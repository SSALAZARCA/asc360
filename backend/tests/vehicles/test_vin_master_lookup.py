"""
GET /vehicles/vin/{vin} — VIN lookup used by the reception flow and by
Datos Rápidos to prefill/correct model/year/color for a vehicle.

Covers four real bugs found while investigating user reports ("el formulario
de moto nueva no completa nada aunque tengo el VIN", later confirmed to also
affect Datos Rápidos):
  1. `VinMasterOut` (backend/app/schemas/vin_master.py) originally expected
     attributes that didn't exist on whatever ORM row it serialized --
     `from_attributes=True` would crash on any real match.
  2. The endpoint only accepted `X-Sonia-Secret`, never a JWT -- no
     browser-based frontend (authFetch, JWT-based) could ever call it.
  3. The service queried the `VinMaster` table, which no import flow ever
     populates -- every lookup 404'd regardless of the VIN. The real,
     populated source is `ShipmentMotoUnit` (packing-list imports, same
     table behind the Imports > Motocicletas tab). `vin_master_service`
     was repointed to query it instead.
  4. Even against `ShipmentMotoUnit`, `model`/`model_year` frequently come
     back empty: those columns only hold a value when that specific unit
     overrides the shipment order's nominal model/year -- most units share
     the order's values and leave the unit-level column NULL. The user saw
     color/year come through but Modelo stay blank for a VIN they could see
     fully populated in Motocicletas. Fixed by falling back to
     `ShipmentMotoUnit.shipment_order.model`/`.model_year`, mirroring the
     exact resolution `_serialize_moto_unit` (imports.py) already uses for
     that tab, so both screens always agree.
"""
import uuid
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_optional_user, CurrentUser
from app.models.imports import ShipmentMotoUnit, ShipmentOrder
from app.models.vehicle import Vehicle
from app.services.vin_master_service import VinLookupResult
import app.api.v1.endpoints.vehicles as vehicles_endpoint


def make_moto_unit(**overrides) -> ShipmentMotoUnit:
    unit = ShipmentMotoUnit(
        id=uuid.uuid4(),
        shipment_order_id=uuid.uuid4(),
        vin_number="9C6JC5820PM123456",
        engine_number="ENG-001",
        model="Renegade 200",
        model_year=2024,
        color="Rojo",
        color_runt="Rojo",
    )
    unit.shipment_order = None  # not relevant unless a test overrides it
    for k, v in overrides.items():
        setattr(unit, k, v)
    return unit


def make_lookup_result(**overrides) -> VinLookupResult:
    result = VinLookupResult(
        id=uuid.uuid4(),
        vin="9C6JC5820PM123456",
        engine_number="ENG-001",
        model="Renegade 200",
        year=2024,
        color="Rojo",
    )
    for k, v in overrides.items():
        setattr(result, k, v)
    return result


def make_client(current_user):
    async def _override_get_db():
        yield MagicMock()

    async def _override_get_optional_user():
        return current_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = _override_get_optional_user
    client = TestClient(app)
    return client


def teardown_overrides():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_optional_user, None)


class TestVinMasterSerialization:
    def test_serializes_a_resolved_lookup_result_without_crashing(self):
        result = make_lookup_result()
        from app.schemas.vin_master import VinMasterOut
        out = VinMasterOut.model_validate(result)
        assert out.model == "Renegade 200"
        assert out.year == 2024
        assert out.color == "Rojo"
        assert out.vin == "9C6JC5820PM123456"


class TestVinMasterLookupEndpoint:
    def test_jwt_authenticated_request_can_reach_a_found_vin(self, monkeypatch):
        result = make_lookup_result()
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=result))
        monkeypatch.setattr(vehicles_endpoint.vehicle_repository, "get_by_vin", AsyncMock(return_value=None))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")
        client = make_client(user)
        try:
            res = client.get("/api/v1/vehicles/vin/9C6JC5820PM123456", headers={"Authorization": "Bearer fake"})
        finally:
            teardown_overrides()
        assert res.status_code == 200
        assert res.json()["model"] == "Renegade 200"

    def test_no_jwt_and_no_bot_secret_is_rejected(self, monkeypatch):
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=make_lookup_result()))
        client = make_client(None)
        try:
            res = client.get("/api/v1/vehicles/vin/9C6JC5820PM123456")
        finally:
            teardown_overrides()
        assert res.status_code == 403

    def test_unknown_vin_returns_404(self, monkeypatch):
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=None))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")
        client = make_client(user)
        try:
            res = client.get("/api/v1/vehicles/vin/0000000000000000X", headers={"Authorization": "Bearer fake"})
        finally:
            teardown_overrides()
        assert res.status_code == 404


class TestVinMasterLookupEnrichment:
    """`GET /vehicles/vin/{vin}` also enriches the packing-list result with
    `brand`/`client_name`/`client_phone` from an already-registered
    `Vehicle` for that VIN (if one exists) -- used by Orden Histórica to
    prefill both the brand (never present in the packing-list data itself)
    and the linked client's contact info when the VIN was already
    delivered/serviced under this system. Purely additive on the existing
    200 path; the 404 path (`test_unknown_vin_returns_404` above) is
    unchanged."""

    def _client_for(self, result, user, vehicle):
        async def _override_get_db():
            yield MagicMock()

        async def _override_get_optional_user():
            return user

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_optional_user] = _override_get_optional_user
        return TestClient(app)

    def test_enriches_brand_and_client_when_an_existing_vehicle_has_a_linked_client(self, monkeypatch):
        result = make_lookup_result()
        client_user = MagicMock(name="Juan Pérez", phone="3001234567")
        client_user.name = "Juan Pérez"
        client_user.phone = "3001234567"
        vehicle = MagicMock(spec=Vehicle)
        vehicle.brand = "UM"
        vehicle.client_id = uuid.uuid4()
        vehicle.client = client_user
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=result))
        monkeypatch.setattr(vehicles_endpoint.vehicle_repository, "get_by_vin", AsyncMock(return_value=vehicle))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")
        client = self._client_for(result, user, vehicle)
        try:
            res = client.get("/api/v1/vehicles/vin/9C6JC5820PM123456", headers={"Authorization": "Bearer fake"})
        finally:
            teardown_overrides()
        assert res.status_code == 200
        body = res.json()
        assert body["brand"] == "UM"
        assert body["client_name"] == "Juan Pérez"
        assert body["client_phone"] == "3001234567"

    def test_enriches_brand_only_when_the_existing_vehicle_has_no_linked_client(self, monkeypatch):
        result = make_lookup_result()
        vehicle = MagicMock(spec=Vehicle)
        vehicle.brand = "UM"
        vehicle.client_id = None
        vehicle.client = None
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=result))
        monkeypatch.setattr(vehicles_endpoint.vehicle_repository, "get_by_vin", AsyncMock(return_value=vehicle))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")
        client = self._client_for(result, user, vehicle)
        try:
            res = client.get("/api/v1/vehicles/vin/9C6JC5820PM123456", headers={"Authorization": "Bearer fake"})
        finally:
            teardown_overrides()
        assert res.status_code == 200
        body = res.json()
        assert body["brand"] == "UM"
        assert body["client_name"] is None
        assert body["client_phone"] is None

    def test_leaves_brand_and_client_blank_when_no_vehicle_is_registered_for_this_vin_yet(self, monkeypatch):
        result = make_lookup_result()
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=result))
        monkeypatch.setattr(vehicles_endpoint.vehicle_repository, "get_by_vin", AsyncMock(return_value=None))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")
        client = self._client_for(result, user, None)
        try:
            res = client.get("/api/v1/vehicles/vin/9C6JC5820PM123456", headers={"Authorization": "Bearer fake"})
        finally:
            teardown_overrides()
        assert res.status_code == 200
        body = res.json()
        assert body["brand"] is None
        assert body["client_name"] is None
        assert body["client_phone"] is None

    def test_unknown_vin_still_404s_and_never_reaches_vehicle_lookup(self, monkeypatch):
        get_by_vin_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=None))
        monkeypatch.setattr(vehicles_endpoint.vehicle_repository, "get_by_vin", get_by_vin_mock)
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")
        client = self._client_for(None, user, None)
        try:
            res = client.get("/api/v1/vehicles/vin/0000000000000000X", headers={"Authorization": "Bearer fake"})
        finally:
            teardown_overrides()
        assert res.status_code == 404
        get_by_vin_mock.assert_not_called()


class TestVinMasterServiceQuery:
    """Pins the real root causes: `query_vin` must hit `ShipmentMotoUnit`
    (the table packing-list imports actually populate), not the dead
    `VinMaster` table, AND must fall back to the parent `ShipmentOrder`'s
    model/year when the unit itself doesn't override them."""

    async def test_returns_none_for_a_non_17_char_vin_without_querying_the_db(self):
        from app.services.vin_master_service import vin_master_service
        db = AsyncMock()
        result = await vin_master_service.query_vin(db, "TOOSHORT")
        assert result is None
        db.execute.assert_not_called()

    async def test_falls_back_to_a_normalized_vin_when_the_exact_match_misses(self):
        from app.services.vin_master_service import vin_master_service
        unit = make_moto_unit()
        exact_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        normalized_result = MagicMock(scalar_one_or_none=MagicMock(return_value=unit))
        db = AsyncMock()
        db.execute.side_effect = [exact_result, normalized_result]

        result = await vin_master_service.query_vin(db, " 9c6jc5820pm123456 ")

        assert result.vin == "9C6JC5820PM123456"
        assert result.model == "RENEGADE 200"
        assert db.execute.call_count == 2

    async def test_falls_back_to_the_shipment_order_model_and_year_when_the_unit_has_none(self):
        # Real-world case that motivated this fix: most units in a shipment
        # share the order's model/year and leave their own columns NULL.
        from app.services.vin_master_service import vin_master_service
        order = ShipmentOrder(id=uuid.uuid4(), pi_number="PI-1", model="Renegade Sport 200", model_year=2026)
        unit = make_moto_unit(model=None, model_year=None, color_runt="Rojo")
        unit.shipment_order = order
        db_result = MagicMock(scalar_one_or_none=MagicMock(return_value=unit))
        db = AsyncMock()
        db.execute.return_value = db_result

        result = await vin_master_service.query_vin(db, unit.vin_number)

        assert result.model == "RENEGADE SPORT 200"
        assert result.year == 2026
        assert result.color == "Rojo"

    async def test_prefers_the_unit_level_model_over_the_order_when_both_are_set(self):
        from app.services.vin_master_service import vin_master_service
        order = ShipmentOrder(id=uuid.uuid4(), pi_number="PI-1", model="Renegade 200", model_year=2024)
        unit = make_moto_unit(model="Renegade Sport 200S", model_year=2026)
        unit.shipment_order = order
        db_result = MagicMock(scalar_one_or_none=MagicMock(return_value=unit))
        db = AsyncMock()
        db.execute.return_value = db_result

        result = await vin_master_service.query_vin(db, unit.vin_number)

        assert result.model == "RENEGADE SPORT 200S"
        assert result.year == 2026
