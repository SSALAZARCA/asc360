"""
tests/vehicles/test_client_edit_endpoint.py -- `PATCH
/vehicles/{plate}/client` (sdd/distributor-vehicle-delivery PR5,
design-dual-channel ADR 20/22): the SINGLE shared endpoint both the
Telegram bot (PR6) and the Mini App (PR8) will call to persist an
advisor's edits to a returning vehicle's linked client. Mirrors `GET
/{plate}`'s existing dual-auth signature verbatim (`x-sonia-secret` OR
JWT, `endpoints/vehicles.py:40-51`) -- a process-identity check only
(ADR 22), no per-advisor accountability, same as every other
bot-originated write in this codebase.

Direct-call convention (same as `test_vehicles_endpoint_hardening.py`):
calls the FastAPI path-operation function directly with explicit
`Depends(...)` args, `vehicle_service.get_vehicle_by_plate` monkeypatched
-- no TestClient/live DB needed for the auth/plate-scoping/exclude_unset
matrix. `db` is an `AsyncMock` so `commit`/`refresh` are awaitable no-ops.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import vehicles as vehicles_endpoint
from app.api.deps import CurrentUser
from app.schemas.vehicle import ClientEditIn
from app.services.vehicle_service import vehicle_service

SONIA_SECRET = "test-bot-secret"  # matches backend/conftest.py's env default


def make_linked_vehicle(**client_overrides) -> SimpleNamespace:
    client_data = dict(name="Juan Perez", phone="3001234567", email="juan@x.com", address="Calle 1")
    client_data.update(client_overrides)
    client = SimpleNamespace(**client_data)
    return SimpleNamespace(id=uuid.uuid4(), plate="ABC123", client_id=uuid.uuid4(), client=client)


class TestDualAuth:
    async def test_no_auth_at_all_is_rejected(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=make_linked_vehicle()))

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.update_vehicle_client(
                plate="ABC123", client_in=ClientEditIn(name="Nuevo"),
                db=AsyncMock(), x_sonia_secret=None, x_tenant_id=None, current_user=None,
            )
        assert exc_info.value.status_code == 403

    async def test_bot_secret_alone_is_accepted(self, monkeypatch):
        vehicle = make_linked_vehicle()
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=vehicle))

        result = await vehicles_endpoint.update_vehicle_client(
            plate="ABC123", client_in=ClientEditIn(name="Nuevo Nombre"),
            db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=None, current_user=None,
        )
        assert result.name == "Nuevo Nombre"

    async def test_jwt_alone_is_accepted(self, monkeypatch):
        vehicle = make_linked_vehicle()
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=vehicle))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="admin", tenant_id=str(uuid.uuid4()), name="Asesor")

        result = await vehicles_endpoint.update_vehicle_client(
            plate="ABC123", client_in=ClientEditIn(name="Nuevo Nombre"),
            db=AsyncMock(), x_sonia_secret=None, x_tenant_id=None, current_user=user,
        )
        assert result.name == "Nuevo Nombre"


class TestExcludeUnsetOnlyUpdatesSubmittedFields:
    async def test_only_submitted_fields_change(self, monkeypatch):
        vehicle = make_linked_vehicle(name="Original", phone="3000000000", email="orig@x.com", address="Dir Orig")
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=vehicle))

        result = await vehicles_endpoint.update_vehicle_client(
            plate="ABC123", client_in=ClientEditIn(phone="3009999999"),
            db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=None, current_user=None,
        )

        assert result.phone == "3009999999"
        assert result.name == "Original"
        assert result.email == "orig@x.com"
        assert result.address == "Dir Orig"

    async def test_commits_and_refreshes_the_client(self, monkeypatch):
        vehicle = make_linked_vehicle()
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=vehicle))
        db = AsyncMock()

        await vehicles_endpoint.update_vehicle_client(
            plate="ABC123", client_in=ClientEditIn(name="X"),
            db=db, x_sonia_secret=SONIA_SECRET, x_tenant_id=None, current_user=None,
        )

        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(vehicle.client)


class TestPlateScopingReusesGetVehicleByPlate:
    async def test_reapplies_the_same_tenant_visibility_lookup_as_get_by_plate(self, monkeypatch):
        vehicle = make_linked_vehicle()
        lookup = AsyncMock(return_value=vehicle)
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", lookup)
        tenant_id = uuid.uuid4()

        await vehicles_endpoint.update_vehicle_client(
            plate="abc123", client_in=ClientEditIn(name="X"),
            db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=str(tenant_id), current_user=None,
        )

        lookup.assert_awaited_once()
        assert lookup.await_args.args[1] == "abc123"
        assert lookup.await_args.args[2] == tenant_id


class TestNotFoundCases:
    async def test_unknown_plate_is_404(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=None))

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.update_vehicle_client(
                plate="ZZZ999", client_in=ClientEditIn(name="X"),
                db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=None, current_user=None,
            )
        assert exc_info.value.status_code == 404

    async def test_plate_with_no_linked_client_is_404(self, monkeypatch):
        vehicle = SimpleNamespace(id=uuid.uuid4(), plate="ABC123", client_id=None, client=None)
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=vehicle))

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.update_vehicle_client(
                plate="ABC123", client_in=ClientEditIn(name="X"),
                db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=None, current_user=None,
            )
        assert exc_info.value.status_code == 404
