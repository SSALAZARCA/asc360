"""
GET /vehicles/vin/{vin} — VIN master lookup used by the reception flow to
prefill model/year/color for a new vehicle.

Covers two real bugs found while investigating a user report ("el formulario
de moto nueva no completa nada aunque tengo el VIN"):
  1. `VinMasterOut` (backend/app/schemas/vin_master.py) expected `.model`,
     `.brand`, `.displacement`, `.warranty_status`, `.expected_reviews`,
     `.completed_reviews` attributes that don't exist on the `VinMaster` ORM
     model (only `.model_name`, `.model_code` -- no brand column at all) --
     `from_attributes=True` would crash on any real match.
  2. The endpoint only accepted `X-Sonia-Secret`, never a JWT -- the
     reception frontend (authFetch, JWT-based) could never call it.
"""
import uuid
from datetime import date
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_optional_user, CurrentUser
from app.models.vin_master import VinMaster
import app.api.v1.endpoints.vehicles as vehicles_endpoint


def make_vin_master(**overrides) -> VinMaster:
    vm = VinMaster(
        id=uuid.uuid4(),
        vin="9C6JC5820PM123456",
        engine_number="ENG-001",
        model_code="RNG200",
        model_name="Renegade 200",
        year=2024,
        color="Rojo",
        assembly_date=date(2024, 1, 15),
    )
    for k, v in overrides.items():
        setattr(vm, k, v)
    return vm


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
        vm = make_vin_master()
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
        vm = make_vin_master()
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
        monkeypatch.setattr(vehicles_endpoint.vin_master_service, "query_vin", AsyncMock(return_value=make_vin_master()))
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
