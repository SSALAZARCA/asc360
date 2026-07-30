"""
tests/distributor_deliveries/test_create_delivery.py — Phase 4, task 4.1.
RED tests for `distributor_delivery_service.create_delivery`: the core
lookup-or-create + transactional behavior (Requirement "Single-Submission
Delivery Registration").
"""
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.distributor_delivery import DeliveryCreate
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    make_client_user,
    make_delivery_vehicle,
    make_moto_unit,
    make_valid_photo,
    make_distribuidor,
    make_superadmin,
    VALID_DELIVERY_PAYLOAD,
)


def _payload(**overrides) -> DeliveryCreate:
    data = dict(VALID_DELIVERY_PAYLOAD)
    data.update(overrides)
    return DeliveryCreate(**data)


@pytest.fixture(autouse=True)
def _no_real_minio_upload(monkeypatch):
    monkeypatch.setattr(
        svc, "upload_file_to_minio", AsyncMock(return_value="https://minio.local/acta.jpg")
    )


class TestNewClientAndVehicleCreatedTogether:
    async def test_new_cedula_and_vin_creates_user_and_vehicle(self):
        fake_db = FakeDeliverySession()
        payload = _payload()
        actor = make_distribuidor()

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), actor)

        from app.models.user import User
        from app.models.vehicle import Vehicle

        created_users = [obj for obj in fake_db.added if isinstance(obj, User)]
        created_vehicles = [obj for obj in fake_db.added if isinstance(obj, Vehicle)]
        assert len(created_users) == 1
        assert created_users[0].identification == "123456789"
        assert created_users[0].role.value == "client"
        assert len(created_vehicles) == 1
        assert vehicle.plate == "ABC123"
        assert vehicle.client_id == created_users[0].id
        assert fake_db.committed is True

    async def test_single_commit(self):
        fake_db = FakeDeliverySession()
        payload = _payload()

        await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert fake_db.committed is True
        assert fake_db.rolled_back is False


class TestExistingClientReused:
    async def test_existing_cedula_is_reused_not_duplicated(self):
        existing_client = make_client_user(identification="123456789")
        fake_db = FakeDeliverySession(users=[existing_client])
        payload = _payload()

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        from app.models.user import User
        created_users = [obj for obj in fake_db.added if isinstance(obj, User)]
        assert created_users == []
        assert vehicle.client_id == existing_client.id

    async def test_existing_cedula_gets_fields_refreshed_from_the_new_submission(self):
        """User decision (2026-07-28): re-registering an existing cédula
        must overwrite the stored client's data with what's submitted this
        time -- most recent wins, not "first write sticks". This matters
        for the manual legacy-vehicle backfill flow the whole client-link
        feature was built for."""
        existing_client = make_client_user(
            identification="123456789", name="Nombre Viejo", phone="3000000000"
        )
        existing_client.email = "viejo@example.com"
        existing_client.city = "Cali"
        existing_client.department = "Valle"
        existing_client.address = "Direccion Vieja"
        existing_client.birth_date = date(1980, 1, 1)
        fake_db = FakeDeliverySession(users=[existing_client])
        payload = _payload()  # VALID_DELIVERY_PAYLOAD's client fields, all different

        await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert existing_client.name == "Juan Perez"
        assert existing_client.phone == "3001234567"
        assert existing_client.email == "juan@example.com"
        assert existing_client.city == "Bogotá"
        assert existing_client.department == "Cundinamarca"
        assert existing_client.address == "Calle 1 # 2-3"
        assert existing_client.birth_date == date(1990, 5, 10)


class TestExistingVehicleReused:
    async def test_resubmitting_existing_plate_updates_same_row(self):
        """Legacy backfill (Design ADR 13) -- `register_or_update_vehicle`
        finds the existing row by plate and updates it in place; no
        duplicate `Vehicle` is created."""
        existing_vehicle = make_delivery_vehicle(plate="ABC123")
        existing_vehicle.delivery_date = None
        fake_db = FakeDeliverySession(vehicles=[existing_vehicle])
        payload = _payload()

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_superadmin())

        from app.models.vehicle import Vehicle
        created_vehicles = [obj for obj in fake_db.added if isinstance(obj, Vehicle)]
        assert created_vehicles == []
        assert vehicle.id == existing_vehicle.id
        assert vehicle.delivery_date == date(2026, 7, 28)


class TestVinEnrichment:
    async def test_vin_lookup_autofills_missing_model_and_year(self):
        moto_unit = make_moto_unit(vin_number="1HGCM82633A004352", model="DSR PRO", model_year=2027)
        fake_db = FakeDeliverySession(moto_units=[moto_unit])
        payload = _payload(vehicle={
            "plate": "XYZ999", "vin": "1HGCM82633A004352", "model": None, "color": None,
            "year": None, "engine_number": None,
        })

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert vehicle.model == "DSR PRO"
        assert vehicle.year == 2027


class TestFutureDeliveryDateRejected:
    async def test_future_delivery_date_rejected_with_zero_writes(self):
        fake_db = FakeDeliverySession()
        tomorrow = date.today() + timedelta(days=2)
        payload = _payload(delivery_date=tomorrow.isoformat())

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert exc_info.value.status_code == 422
        assert fake_db.added == []
        assert fake_db.committed is False
        assert fake_db.rolled_back is True


class TestVinRequiredAndMustBeInMaster:
    """Follow-up fix (2026-07-30, user decision): a Distribuidor or
    superadmin can no longer submit a typo'd or nonexistent VIN and have it
    silently accepted -- VIN is mandatory AND must resolve against the VIN
    master catalog, for EVERYONE, no exception (unlike the photo rule,
    which DOES exempt superadmin)."""

    async def test_vin_not_found_in_master_rejected_with_zero_writes(self):
        fake_db = FakeDeliverySession(moto_units=[])
        payload = _payload(vehicle={
            "plate": "ABC123", "vin": "NOTINMASTER123456", "model": None,
            "color": None, "year": None, "engine_number": None,
        })

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert exc_info.value.status_code == 422
        assert fake_db.added == []
        assert fake_db.committed is False
        assert fake_db.rolled_back is True

    async def test_vin_not_found_in_master_rejected_even_for_superadmin(self):
        """No exception for superadmin here -- unlike the mandatory-photo
        rule."""
        fake_db = FakeDeliverySession(moto_units=[])
        payload = _payload(vehicle={
            "plate": "ABC123", "vin": "NOTINMASTER123456", "model": None,
            "color": None, "year": None, "engine_number": None,
        })

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_delivery(fake_db, payload, None, make_superadmin())

        assert exc_info.value.status_code == 422
        assert fake_db.added == []
        assert fake_db.committed is False

    async def test_vin_found_in_master_proceeds_normally(self):
        moto_unit = make_moto_unit(vin_number="1HGCM82633A004352")
        fake_db = FakeDeliverySession(moto_units=[moto_unit])
        payload = _payload()

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert vehicle.vin == "1HGCM82633A004352"
        assert fake_db.committed is True

    def test_missing_vin_entirely_raises_pydantic_validation_error_not_500(self):
        data = dict(VALID_DELIVERY_PAYLOAD)
        vehicle_without_vin = dict(data["vehicle"])
        del vehicle_without_vin["vin"]
        data = {**data, "vehicle": vehicle_without_vin}

        with pytest.raises(ValidationError):
            DeliveryCreate(**data)


class TestRegisteredByTenantIdSetOnCreation:
    """`registered_by_tenant_id` is the Distribuidora whose employee
    registered this delivery -- set from the actor's OWN `tenant_id`
    (follow-up feature, migration `c9d0e1f2a3b4`), covering all three actor
    shapes `create_delivery` can see."""

    async def test_distribuidor_with_tenant_stamps_that_tenant(self):
        tenant_id = uuid.uuid4()
        fake_db = FakeDeliverySession()
        actor = make_distribuidor(tenant_id=tenant_id)

        vehicle = await svc.create_delivery(fake_db, _payload(), make_valid_photo(), actor)

        assert vehicle.registered_by_tenant_id == tenant_id

    async def test_distribuidor_without_tenant_stamps_none(self):
        """Expected, not a bug: nobody sees this row in the filtered
        Distribuidor list -- only superadmin's unfiltered view does."""
        fake_db = FakeDeliverySession()
        actor = make_distribuidor(tenant_id=None)

        vehicle = await svc.create_delivery(fake_db, _payload(), make_valid_photo(), actor)

        assert vehicle.registered_by_tenant_id is None

    async def test_superadmin_backfill_stamps_none(self):
        """A superadmin manual legacy-vehicle backfill isn't "owned" by any
        Distribuidora -- also expected, also `None`."""
        fake_db = FakeDeliverySession()
        actor = make_superadmin()

        vehicle = await svc.create_delivery(fake_db, _payload(), make_valid_photo(), actor)

        assert vehicle.registered_by_tenant_id is None
