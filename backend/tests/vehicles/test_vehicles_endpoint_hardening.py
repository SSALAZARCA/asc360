"""
tests/vehicles/test_vehicles_endpoint_hardening.py -- api-security
hardening for `api/v1/endpoints/vehicles.py`
(sdd/vehicle-tenant-checkin-release PR2, Design File Change #10):

1. Mass-assignment / OWASP API1 BOLA: `create_or_update_vehicle` no longer
   forwards a client-controlled `tenant_id` as an authorization decision --
   `register_or_update_vehicle` now takes exactly `(db, vehicle_in)`.
2. `x_tenant_id` arrives as a raw header STRING compared against a UUID
   column -- a malformed value must 400, not crash or silently mismatch.
3. `IntegrityError` -> sanitized 409 (no raw DB text leaked to the
   client) + `logger.exception`; any `HTTPException` passes through
   untouched; anything else is no longer swallowed into a fake 400
   (fail loud, matches Design Decision 2).

Calls the FastAPI path-operation functions directly (no TestClient/DI
overrides needed) -- same convention as the service-layer tests in this
suite; `Depends(...)` defaults are simply not evaluated when the
dependency is passed explicitly.
"""
import logging
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.v1.endpoints import vehicles as vehicles_endpoint
from app.schemas.vehicle import VehicleCreate
from app.services.vehicle_service import vehicle_service

SONIA_SECRET = "test-bot-secret"  # matches backend/conftest.py's env default


def make_vehicle_in(**overrides) -> VehicleCreate:
    data = dict(plate="ABC123", vin=None, brand="UM", model="TEST", color=None, year=None)
    data.update(overrides)
    return VehicleCreate(**data)


class TestGetVehicleByPlateTenantHeaderValidation:
    async def test_invalid_x_tenant_id_header_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.get_vehicle_by_plate(
                plate="ABC123",
                db=AsyncMock(),
                x_sonia_secret=SONIA_SECRET,
                x_tenant_id="not-a-uuid",
                current_user=None,
            )
        assert exc_info.value.status_code == 400

    async def test_valid_x_tenant_id_header_is_coerced_to_uuid_before_the_service_call(self, monkeypatch):
        tenant_id = uuid.uuid4()
        lookup = AsyncMock(return_value=None)
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", lookup)

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.get_vehicle_by_plate(
                plate="ABC123",
                db=AsyncMock(),
                x_sonia_secret=SONIA_SECRET,
                x_tenant_id=str(tenant_id),
                current_user=None,
            )
        assert exc_info.value.status_code == 404

        lookup.assert_awaited_once()
        called_tenant_id = lookup.await_args.args[2]
        assert isinstance(called_tenant_id, uuid.UUID)
        assert called_tenant_id == tenant_id

    async def test_not_found_message_reflects_claim_semantics(self, monkeypatch):
        monkeypatch.setattr(vehicle_service, "get_vehicle_by_plate", AsyncMock(return_value=None))

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.get_vehicle_by_plate(
                plate="ABC123", db=AsyncMock(), x_sonia_secret=SONIA_SECRET,
                x_tenant_id=None, current_user=None,
            )
        assert exc_info.value.detail == "Vehículo no encontrado o en servicio en otro taller."


class TestCreateOrUpdateVehicleMassAssignmentAndErrorMapping:
    async def test_register_or_update_vehicle_is_called_with_no_tenant_id(self, monkeypatch):
        call = AsyncMock(return_value="fake-vehicle")
        monkeypatch.setattr(vehicle_service, "register_or_update_vehicle", call)

        vehicle_in = make_vehicle_in()
        result = await vehicles_endpoint.create_or_update_vehicle(
            vehicle_in=vehicle_in, db=AsyncMock(), x_sonia_secret=SONIA_SECRET,
            current_user=None,
        )

        assert result == "fake-vehicle"
        call.assert_awaited_once()
        assert len(call.await_args.args) == 2
        assert call.await_args.args[1] is vehicle_in

    async def test_integrity_error_returns_sanitized_409_and_logs(self, monkeypatch, caplog):
        raw_db_error = IntegrityError(
            "INSERT INTO vehicles ...", {},
            Exception('duplicate key value violates unique constraint "vehicles_plate_key"'),
        )
        monkeypatch.setattr(
            vehicle_service, "register_or_update_vehicle", AsyncMock(side_effect=raw_db_error)
        )

        with caplog.at_level(logging.ERROR):
            with pytest.raises(HTTPException) as exc_info:
                await vehicles_endpoint.create_or_update_vehicle(
                    vehicle_in=make_vehicle_in(), db=AsyncMock(), x_sonia_secret=SONIA_SECRET,
                    current_user=None,
                )

        assert exc_info.value.status_code == 409
        assert "vehicles_plate_key" not in str(exc_info.value.detail)
        assert "duplicate key" not in str(exc_info.value.detail)
        assert any(record.levelname == "ERROR" for record in caplog.records)

    async def test_http_exception_passes_through_untouched(self, monkeypatch):
        original = HTTPException(status_code=422, detail="algo raro")
        monkeypatch.setattr(
            vehicle_service, "register_or_update_vehicle", AsyncMock(side_effect=original)
        )

        with pytest.raises(HTTPException) as exc_info:
            await vehicles_endpoint.create_or_update_vehicle(
                vehicle_in=make_vehicle_in(), db=AsyncMock(), x_sonia_secret=SONIA_SECRET,
                current_user=None,
            )

        assert exc_info.value is original

    async def test_unexpected_exception_is_no_longer_swallowed_into_a_fake_400(self, monkeypatch):
        monkeypatch.setattr(
            vehicle_service, "register_or_update_vehicle", AsyncMock(side_effect=ValueError("boom"))
        )

        with pytest.raises(ValueError):
            await vehicles_endpoint.create_or_update_vehicle(
                vehicle_in=make_vehicle_in(), db=AsyncMock(), x_sonia_secret=SONIA_SECRET,
                current_user=None,
            )
