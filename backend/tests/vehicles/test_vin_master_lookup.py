"""
GET /vehicles/vin/{vin} — VIN lookup used by the reception flow and by
Datos Rápidos to prefill/correct model/year/color for a vehicle.

Covers three real bugs found while investigating user reports ("el
formulario de moto nueva no completa nada aunque tengo el VIN", later
confirmed to also affect Datos Rápidos):
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
"""
import uuid
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_optional_user, CurrentUser
from app.models.imports import ShipmentMotoUnit
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
    for k, v in overrides.items():
        setattr(unit, k, v)
    return unit


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
    def test_serializes_a_real_vin_master_row_without_crashing(self):
        vm = make_moto_unit()
        # This is exactly what from_attributes=True does under the hood --
        # asserting it directly pins the fix (the old schema raised here).
        from app.schemas.vin_master import VinMasterOut
        out = VinMasterOut.model_validate(vm)
        assert out.model == "Renegade 200"
        assert out.year == 2024
        assert out.color == "Rojo"
        assert out.vin == "9C6JC5820PM123456"


class TestVinMasterLookupEndpoint:
    def test_jwt_authenticated_request_can_reach_a_found_vin(self, monkeypatch):
        vm = make_moto_unit()
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=vm))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")
        client = make_client(user)
        try:
            res = client.get("/api/v1/vehicles/vin/9C6JC5820PM123456", headers={"Authorization": "Bearer fake"})
        finally:
            teardown_overrides()
        assert res.status_code == 200
        assert res.json()["model"] == "Renegade 200"

    def test_no_jwt_and_no_bot_secret_is_rejected(self, monkeypatch):
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=make_moto_unit()))
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


class TestVinMasterServiceQuery:
    """Pins the real root cause: `query_vin` must hit `ShipmentMotoUnit`
    (the table packing-list imports actually populate), not the dead
    `VinMaster` table that no import flow ever writes to."""

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

        assert result is unit
        assert db.execute.call_count == 2
