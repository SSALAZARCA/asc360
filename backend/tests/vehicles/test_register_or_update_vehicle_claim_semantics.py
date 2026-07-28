"""
tests/vehicles/test_register_or_update_vehicle_claim_semantics.py -- pins
the sdd/vehicle-tenant-checkin-release PR2 live-bug fix:
`vehicle_service.register_or_update_vehicle` MUST have zero tenant
semantics.

Before this change, `vehicle_in.tenant_id = tenant_id` (deleted) put
`tenant_id` into `BaseRepository.update`'s `model_dump(exclude_unset=True)`
dump on every UPDATE -- silently rewriting a vehicle's owning taller any
time ANY tenant serviced it. `get_by_plate` was also called WITH the
requesting tenant_id, so a vehicle claimed/serviced by tenant A was
invisible to tenant B even after A delivered.

Both defects are pinned as call-argument assertions, not just "it works"
happy-path checks -- a regression that reintroduces either one must fail
here first.
"""
import inspect
from unittest.mock import AsyncMock, MagicMock

from app.services.vehicle_service import vehicle_service
from app.schemas.vehicle import VehicleCreate


def make_vehicle_in(**overrides) -> VehicleCreate:
    data = dict(plate="ABC123", vin=None, brand="UM", model="TEST", color=None, year=None)
    data.update(overrides)
    return VehicleCreate(**data)


def patch_repository(monkeypatch, **overrides):
    defaults = dict(
        get_by_plate=AsyncMock(return_value=None),
        create=AsyncMock(side_effect=lambda db, v: v),
        update=AsyncMock(side_effect=lambda db, existing, v: existing),
    )
    defaults.update(overrides)
    monkeypatch.setattr(vehicle_service, "repository", MagicMock(**defaults))


class TestRegisterOrUpdateVehicleSignatureHasNoTenantId:
    def test_signature_is_exactly_db_and_vehicle_in(self):
        sig = inspect.signature(vehicle_service.register_or_update_vehicle)
        assert list(sig.parameters.keys()) == ["db", "vehicle_in"]

    def test_tenant_id_parameter_does_not_exist(self):
        sig = inspect.signature(vehicle_service.register_or_update_vehicle)
        assert "tenant_id" not in sig.parameters


class TestRegisterOrUpdateVehicleFindsByPlateRegardlessOfClaim:
    async def test_get_by_plate_is_called_with_tenant_id_none(self, monkeypatch):
        """Pins Design's File Change #5: `get_by_plate(db, clean_plate,
        tenant_id)` -> `get_by_plate(db, clean_plate, None)`. Finding a
        vehicle by plate must NOT depend on who is asking -- claim
        visibility is enforced at order creation (Decision 1), not here."""
        get_by_plate = AsyncMock(return_value=None)
        patch_repository(monkeypatch, get_by_plate=get_by_plate)

        vehicle_in = make_vehicle_in(plate="abc 123")
        await vehicle_service.register_or_update_vehicle(AsyncMock(), vehicle_in)

        get_by_plate.assert_awaited_once()
        args = get_by_plate.await_args.args
        assert args[1] == "ABC123"
        assert args[2] is None


class TestRegisterOrUpdateVehicleNeverStealsOwnership:
    async def test_update_payload_carries_no_tenant_id(self, monkeypatch):
        """Pins the live bug: `vehicle_in.tenant_id = tenant_id` (deleted)
        used to put `tenant_id` into `BaseRepository.update`'s
        `model_dump(exclude_unset=True)` dump, silently rewriting the
        vehicle's owning taller on every update."""
        existing = MagicMock()
        update = AsyncMock(return_value=existing)
        patch_repository(monkeypatch, get_by_plate=AsyncMock(return_value=existing), update=update)

        vehicle_in = make_vehicle_in()
        await vehicle_service.register_or_update_vehicle(AsyncMock(), vehicle_in)

        update.assert_awaited_once()
        passed_vehicle_in = update.await_args.args[2]
        dumped = passed_vehicle_in.model_dump(exclude_unset=True)
        assert "tenant_id" not in dumped
