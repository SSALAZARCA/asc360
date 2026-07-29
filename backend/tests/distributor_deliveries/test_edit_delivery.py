"""
tests/distributor_deliveries/test_edit_delivery.py — `PATCH
/distributor/deliveries/{vehicle_id}` (follow-up feature, migration
`c9d0e1f2a3b4`). Superadmin-only edit of a delivery record's basic info --
Distribuidor is explicitly EXCLUDED, even for a record they created
themselves (user's explicit requirement), so the router does NOT reuse
`require_distribuidor` here.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user
from app.schemas.distributor_delivery import DeliveryEditIn
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    NoTouchSession,
    make_client_user,
    make_delivery_vehicle,
    make_distribuidor,
)


class TestSuperadminCanEditAllFields:
    async def test_full_edit_updates_vehicle_and_linked_client(self):
        client = make_client_user(name="Nombre Viejo", phone="3000000000")
        vehicle = make_delivery_vehicle(plate="ABC123", vin="OLDVIN", delivery_date=date(2026, 7, 1))
        vehicle.client_id = client.id
        fake_db = FakeDeliverySession(users=[client], vehicles=[vehicle])
        payload = DeliveryEditIn(
            client_name="Nombre Nuevo",
            client_phone="3009999999",
            plate="XYZ999",
            vin="NEWVIN",
            delivery_date=date(2026, 7, 15),
        )

        result = await svc.edit_delivery(fake_db, vehicle.id, payload)

        assert result.plate == "XYZ999"
        assert result.vin == "NEWVIN"
        assert result.delivery_date == date(2026, 7, 15)
        assert client.name == "Nombre Nuevo"
        assert client.phone == "3009999999"
        assert fake_db.committed is True


class TestDistribuidorCannotEditEvenTheirOwnRecord:
    def test_distribuidor_gets_403_with_no_db_touch(self):
        async def _get_db():
            yield NoTouchSession()

        app.dependency_overrides[get_db] = _get_db

        async def _get_current_user():
            return make_distribuidor()

        app.dependency_overrides[get_current_user] = _get_current_user

        try:
            with TestClient(app) as client:
                res = client.patch(
                    f"/api/v1/distributor/deliveries/{uuid.uuid4()}",
                    json={"plate": "ZZZ999"},
                )
            assert res.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


class TestNonexistentOrNonDeliveryVehicleGets404:
    async def test_nonexistent_vehicle_id_gets_404(self):
        fake_db = FakeDeliverySession()

        with pytest.raises(HTTPException) as exc_info:
            await svc.edit_delivery(fake_db, uuid.uuid4(), DeliveryEditIn(plate="X"))

        assert exc_info.value.status_code == 404

    async def test_vehicle_without_delivery_date_gets_404(self):
        vehicle = make_delivery_vehicle(delivery_date=None)
        fake_db = FakeDeliverySession(vehicles=[vehicle])

        with pytest.raises(HTTPException) as exc_info:
            await svc.edit_delivery(fake_db, vehicle.id, DeliveryEditIn(plate="X"))

        assert exc_info.value.status_code == 404


class TestFutureDeliveryDateRejectedWithZeroWrites:
    async def test_future_date_422_with_no_mutation_and_no_commit(self):
        vehicle = make_delivery_vehicle(plate="ABC123", delivery_date=date(2026, 7, 1))
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        tomorrow = date.today() + timedelta(days=2)

        with pytest.raises(HTTPException) as exc_info:
            await svc.edit_delivery(fake_db, vehicle.id, DeliveryEditIn(delivery_date=tomorrow))

        assert exc_info.value.status_code == 422
        assert vehicle.plate == "ABC123"
        assert vehicle.delivery_date == date(2026, 7, 1)
        assert fake_db.committed is False


class TestPartialUpdateDoesNotClobberOtherFields:
    async def test_only_plate_provided_leaves_vin_date_and_client_untouched(self):
        client = make_client_user(name="Juan", phone="3001111111")
        vehicle = make_delivery_vehicle(plate="ABC123", vin="VIN1", delivery_date=date(2026, 7, 1))
        vehicle.client_id = client.id
        fake_db = FakeDeliverySession(users=[client], vehicles=[vehicle])

        result = await svc.edit_delivery(fake_db, vehicle.id, DeliveryEditIn(plate="NEWPLATE"))

        assert result.plate == "NEWPLATE"
        assert result.vin == "VIN1"
        assert result.delivery_date == date(2026, 7, 1)
        assert client.name == "Juan"
        assert client.phone == "3001111111"


class TestClientFieldsNoOpWhenVehicleHasNoLinkedClient:
    async def test_client_name_and_phone_are_silently_ignored_without_client_id(self):
        vehicle = make_delivery_vehicle(plate="ABC123", delivery_date=date(2026, 7, 1))
        vehicle.client_id = None
        fake_db = FakeDeliverySession(vehicles=[vehicle])

        result = await svc.edit_delivery(
            fake_db,
            vehicle.id,
            DeliveryEditIn(client_name="Should Not Apply", plate="NEWPLATE"),
        )

        assert result.plate == "NEWPLATE"
        assert fake_db.committed is True
