"""
tests/vehicles/test_delete_vehicle.py -- `DELETE /vehicles/{plate}`
(root-cause fix for the orphaned-vehicle bug: Sonia's reception flow used
to create `Vehicle` then, in a SEPARATE fire-and-forget step, create the
`ServiceOrder`; if order creation failed the vehicle was left registered
with zero orders forever). This endpoint is the compensating-transaction
rollback the bot calls when that happens: "undo the vehicle I *just*
created because the order that was supposed to follow it failed".

Three layers, mirroring this suite's existing conventions:

1. `TestVehicleRepositoryDeleteVehicle` -- repository method, fake session
   (same `FakeVehicleLookupSession`-style convention as
   `test_get_by_plate_visibility.py`), asserts `db.delete`/`db.flush`.
2. `TestVehicleServiceDeleteVehicleByPlate` -- service method, mocked
   repository (same `patch_repository` convention as
   `test_register_or_update_vehicle_claim_semantics.py`), a stateful fake
   repo so "row genuinely gone" / "row NOT deleted" can be verified by
   re-fetching rather than only asserting a mock was called.
3. `TestDeleteVehicleEndpoint` -- direct path-operation-function call (same
   convention as `test_client_edit_endpoint.py`), asserts status
   codes/auth semantics.

Endpoint auth is deliberately BOT-ONLY (unlike `GET /{plate}` and `PATCH
/{plate}/client`, both dual-auth): this is an internal rollback mechanism
for the bot's own compensating transaction, not a general admin-delete
feature. A valid staff JWT (`current_user`) alone must NOT be enough.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import vehicles as vehicles_endpoint
from app.api.deps import CurrentUser
from app.repositories.vehicle_repository import vehicle_repository
from app.services.vehicle_service import vehicle_service

SONIA_SECRET = "test-bot-secret"  # matches backend/conftest.py's env default


def make_vehicle(service_orders=None, **overrides):
    data = dict(id=uuid.uuid4(), plate="ABC123", service_orders=service_orders or [])
    data.update(overrides)
    return SimpleNamespace(**data)


# ---------------------------------------------------------------------------
# 1. Repository layer
# ---------------------------------------------------------------------------

class FakeDeleteSession:
    def __init__(self):
        self.deleted = []
        self.flushed = False

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        self.flushed = True


class TestVehicleRepositoryDeleteVehicle:
    async def test_deletes_and_flushes_the_given_vehicle(self):
        db = FakeDeleteSession()
        vehicle = make_vehicle()

        await vehicle_repository.delete_vehicle(db, vehicle)

        assert db.deleted == [vehicle]
        assert db.flushed is True


# ---------------------------------------------------------------------------
# 2. Service layer -- stateful fake repo so deletion can be verified by
#    re-fetching, not just by asserting a mock call.
# ---------------------------------------------------------------------------

class StatefulFakeVehicleRepo:
    """Holds vehicles in a dict keyed by plate; `delete_vehicle` actually
    removes the entry so a subsequent `get_by_plate` genuinely returns
    `None` -- lets the tests assert "row genuinely gone" / "row NOT
    deleted" by re-fetching, same guarantee the task asked for."""

    def __init__(self, vehicles: dict):
        self._vehicles = vehicles
        self.delete_calls = []

    async def get_by_plate(self, db, plate, tenant_id=None):
        return self._vehicles.get(plate)

    async def delete_vehicle(self, db, vehicle):
        self.delete_calls.append(vehicle)
        self._vehicles.pop(vehicle.plate, None)


def patch_repository(monkeypatch, repo):
    monkeypatch.setattr(vehicle_service, "repository", repo)


class TestVehicleServiceDeleteVehicleByPlate:
    async def test_deletes_an_orderless_vehicle_and_row_is_genuinely_gone(self, monkeypatch):
        vehicle = make_vehicle(plate="ABC123", service_orders=[])
        repo = StatefulFakeVehicleRepo({"ABC123": vehicle})
        patch_repository(monkeypatch, repo)

        result = await vehicle_service.delete_vehicle_by_plate(AsyncMock(), "ABC123")

        assert result == "deleted"
        assert repo.delete_calls == [vehicle]
        # Re-fetch: the row must genuinely be gone.
        assert await repo.get_by_plate(AsyncMock(), "ABC123") is None

    async def test_rejects_deletion_when_vehicle_has_service_orders(self, monkeypatch):
        vehicle = make_vehicle(plate="ABC123", service_orders=[MagicMock()])
        repo = StatefulFakeVehicleRepo({"ABC123": vehicle})
        patch_repository(monkeypatch, repo)

        result = await vehicle_service.delete_vehicle_by_plate(AsyncMock(), "ABC123")

        assert result == "has_orders"
        assert repo.delete_calls == []
        # Re-fetch: the row must NOT have been deleted.
        assert await repo.get_by_plate(AsyncMock(), "ABC123") is vehicle

    async def test_returns_not_found_for_unknown_plate(self, monkeypatch):
        repo = StatefulFakeVehicleRepo({})
        patch_repository(monkeypatch, repo)

        result = await vehicle_service.delete_vehicle_by_plate(AsyncMock(), "ZZZ999")

        assert result == "not_found"
        assert repo.delete_calls == []

    async def test_cleans_and_uppercases_the_plate_before_lookup(self, monkeypatch):
        vehicle = make_vehicle(plate="ABC123", service_orders=[])
        repo = StatefulFakeVehicleRepo({"ABC123": vehicle})
        patch_repository(monkeypatch, repo)

        result = await vehicle_service.delete_vehicle_by_plate(AsyncMock(), "abc 123")

        assert result == "deleted"


# ---------------------------------------------------------------------------
# 3. Endpoint layer
# ---------------------------------------------------------------------------

class TestDeleteVehicleEndpointAuth:
    async def test_no_auth_at_all_is_rejected_403(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", AsyncMock(return_value="deleted"))

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.delete_vehicle(
                plate="ABC123", db=AsyncMock(), x_sonia_secret=None, x_tenant_id=None,
                current_user=None,
            )
        assert exc_info.value.status_code == 403

    async def test_bot_secret_alone_is_accepted(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", AsyncMock(return_value="deleted"))

        result = await vehicles_endpoint.delete_vehicle(
            plate="ABC123", db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=None,
            current_user=None,
        )
        assert result is None

    async def test_valid_staff_jwt_alone_is_NOT_enough_unlike_get_and_patch(self, monkeypatch):
        """This endpoint is bot-only (internal rollback mechanism) --
        unlike `GET /{plate}` and `PATCH /{plate}/client`, a valid staff
        JWT with no bot secret must still be rejected with 403."""
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", AsyncMock(return_value="deleted"))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=str(uuid.uuid4()), name="Admin")

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.delete_vehicle(
                plate="ABC123", db=AsyncMock(), x_sonia_secret=None, x_tenant_id=None,
                current_user=user,
            )
        assert exc_info.value.status_code == 403

    async def test_wrong_bot_secret_is_rejected_403_even_with_jwt(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", AsyncMock(return_value="deleted"))
        user = CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=str(uuid.uuid4()), name="Admin")

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.delete_vehicle(
                plate="ABC123", db=AsyncMock(), x_sonia_secret="wrong-secret", x_tenant_id=None,
                current_user=user,
            )
        assert exc_info.value.status_code == 403


class TestDeleteVehicleEndpointResultMapping:
    async def test_deleted_returns_204_no_body(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", AsyncMock(return_value="deleted"))

        result = await vehicles_endpoint.delete_vehicle(
            plate="ABC123", db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=None,
            current_user=None,
        )
        assert result is None

    async def test_not_found_returns_404(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", AsyncMock(return_value="not_found"))

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.delete_vehicle(
                plate="ZZZ999", db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=None,
                current_user=None,
            )
        assert exc_info.value.status_code == 404

    async def test_has_orders_returns_409_with_expected_message(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", AsyncMock(return_value="has_orders"))

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.delete_vehicle(
                plate="ABC123", db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=None,
                current_user=None,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "No se puede eliminar: el vehículo ya tiene órdenes de servicio."


class TestDeleteVehicleEndpointTenantHeader:
    async def test_invalid_x_tenant_id_header_returns_400(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", AsyncMock(return_value="deleted"))

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.delete_vehicle(
                plate="ABC123", db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id="not-a-uuid",
                current_user=None,
            )
        assert exc_info.value.status_code == 400

    async def test_valid_x_tenant_id_header_is_coerced_to_uuid_before_the_service_call(self, monkeypatch):
        tenant_id = uuid.uuid4()
        call = AsyncMock(return_value="deleted")
        monkeypatch.setattr(vehicle_service, "delete_vehicle_by_plate", call)

        await vehicles_endpoint.delete_vehicle(
            plate="ABC123", db=AsyncMock(), x_sonia_secret=SONIA_SECRET, x_tenant_id=str(tenant_id),
            current_user=None,
        )

        call.assert_awaited_once()
        called_tenant_id = call.await_args.args[2]
        assert isinstance(called_tenant_id, uuid.UUID)
        assert called_tenant_id == tenant_id
