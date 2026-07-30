"""
tests/distributor_deliveries/test_get_delivery_detail.py — `GET
/distributor/deliveries/{vehicle_id}` (follow-up bugfix, 2026-07-30).

The superadmin-only "Editar Registro" edit modal pre-fills its form from
`DeliveryListItemOut` (the LIST row), which only carries a handful of
fields -- client cédula/birth_date/city/department/address/email/phone and
vehicle color/year/engine_number were all captured at creation time but
never surfaced back, so the edit modal opened blank for most fields. This
new read-only endpoint feeds the modal on open with EVERY field it needs to
prefill, mirroring `edit_delivery`'s superadmin-only guard and 404 check
verbatim (same access boundary as the `PATCH` of the same resource, per the
user's explicit decision that fetch-for-editing and editing itself must
never diverge in who can reach them).
"""
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    NoTouchSession,
    make_client_user,
    make_delivery_vehicle,
    make_distribuidor,
)


class TestSuperadminGetsFullDetailForVehicleWithLinkedClient:
    async def test_every_field_correctly_populated(self):
        client = make_client_user(
            name="Juan Perez", identification="123456789", phone="3001234567"
        )
        client.birth_date = date(1990, 5, 10)
        client.city = "Bogotá"
        client.department = "Cundinamarca"
        client.address = "Calle 1 # 2-3"
        client.email = "juan@example.com"

        vehicle = make_delivery_vehicle(
            plate="ABC123",
            vin="1HGCM82633A004352",
            model="DSR",
            color="Rojo",
            year=2026,
            delivery_date=date(2026, 7, 28),
            client=client,
        )
        vehicle.client_id = client.id
        vehicle.engine_number = "ENG12345"

        fake_db = FakeDeliverySession(vehicles=[vehicle])

        result = await svc.get_delivery_detail(fake_db, vehicle.id)

        assert result.id == vehicle.id
        assert result.plate == "ABC123"
        assert result.vin == "1HGCM82633A004352"
        assert result.model == "DSR"
        assert result.color == "Rojo"
        assert result.year == 2026
        assert result.engine_number == "ENG12345"
        assert result.delivery_date == date(2026, 7, 28)
        assert result.client_name == "Juan Perez"
        assert result.client_identification == "123456789"
        assert result.client_birth_date == date(1990, 5, 10)
        assert result.client_city == "Bogotá"
        assert result.client_department == "Cundinamarca"
        assert result.client_address == "Calle 1 # 2-3"
        assert result.client_phone == "3001234567"
        assert result.client_email == "juan@example.com"


class TestVehicleWithNoLinkedClientReturnsNoneClientFields:
    async def test_client_fields_are_none_not_an_error(self):
        vehicle = make_delivery_vehicle(
            plate="ABC123", delivery_date=date(2026, 7, 28), client=None
        )
        vehicle.client_id = None
        fake_db = FakeDeliverySession(vehicles=[vehicle])

        result = await svc.get_delivery_detail(fake_db, vehicle.id)

        assert result.plate == "ABC123"
        assert result.client_name is None
        assert result.client_identification is None
        assert result.client_birth_date is None
        assert result.client_city is None
        assert result.client_department is None
        assert result.client_address is None
        assert result.client_phone is None
        assert result.client_email is None


class TestDistribuidorGets403WithZeroDbTouch:
    def test_distribuidor_is_rejected_before_any_db_read(self):
        async def _get_db():
            yield NoTouchSession()

        app.dependency_overrides[get_db] = _get_db

        async def _get_current_user():
            return make_distribuidor()

        app.dependency_overrides[get_current_user] = _get_current_user

        try:
            with TestClient(app) as client:
                res = client.get(f"/api/v1/distributor/deliveries/{uuid.uuid4()}")
            assert res.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


class TestNonexistentOrNonDeliveryVehicleGets404:
    async def test_nonexistent_vehicle_id_gets_404(self):
        fake_db = FakeDeliverySession()

        with pytest.raises(HTTPException) as exc_info:
            await svc.get_delivery_detail(fake_db, uuid.uuid4())

        assert exc_info.value.status_code == 404

    async def test_vehicle_without_delivery_date_gets_404(self):
        vehicle = make_delivery_vehicle(delivery_date=None)
        fake_db = FakeDeliverySession(vehicles=[vehicle])

        with pytest.raises(HTTPException) as exc_info:
            await svc.get_delivery_detail(fake_db, vehicle.id)

        assert exc_info.value.status_code == 404
