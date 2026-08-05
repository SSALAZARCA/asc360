"""
tests/distributor_deliveries/test_vehicle_ownership_conflict.py

Bugfix: `create_delivery`/`edit_delivery` used to let a plate or VIN that
already belonged to a DIFFERENT client silently steal that vehicle's
ownership (`vehicle_service.register_or_update_vehicle` finds-then-updates
by plate, so the DB's `unique=True` constraint never fires; `vin` has no
uniqueness constraint at all). `_reject_if_vehicle_owned_by_another_client`
blocks that with a 422, while preserving the legitimate cases: a vehicle
with no client yet, or the SAME client resubmitting (Design ADR 11 backfill
flow, `TestExistingVehicleReused` in `test_create_delivery.py`).
"""
import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.schemas.distributor_delivery import DeliveryCreate, DeliveryEditIn
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    make_client_user,
    make_delivery_vehicle,
    make_valid_photo,
    make_distribuidor,
    VALID_DELIVERY_PAYLOAD,
)


@pytest.fixture(autouse=True)
def _no_real_minio_upload(monkeypatch):
    monkeypatch.setattr(
        svc, "upload_file_to_minio", AsyncMock(return_value="https://minio.local/acta.jpg")
    )


def _payload(**overrides) -> DeliveryCreate:
    data = dict(VALID_DELIVERY_PAYLOAD)
    data.update(overrides)
    return DeliveryCreate(**data)


class TestCreateBlockedOnOwnershipConflict:
    async def test_blocked_when_plate_belongs_to_a_different_client(self):
        # `FakeDeliverySession.execute` returns EVERY fixture `User` for any
        # `select(User)` query, unfiltered -- it doesn't emulate a SQL WHERE.
        # `_lookup_or_create_client`'s cédula lookup would therefore treat
        # ANY fixture user as "the match" regardless of identification, so
        # `other_client` is deliberately kept OUT of `users=` here (`users`
        # stays empty -- the payload's cédula genuinely creates a NEW
        # client) and the conflicting vehicle's `client_id` is a bare,
        # unregistered UUID instead. `db.get(User, id)` (used only for the
        # error message's owner name) DOES filter correctly in this fake, so
        # an id with no matching fixture user falls back to the generic
        # "otro cliente" wording -- asserted below instead of a real name.
        other_owner_id = uuid.uuid4()
        other_vehicle = make_delivery_vehicle(plate="ABC123", vin="DIFFERENTVIN0001")
        other_vehicle.client_id = other_owner_id
        fake_db = FakeDeliverySession(vehicles=[other_vehicle])
        # VALID_DELIVERY_PAYLOAD's plate is "ABC123" -- same plate, new cédula.
        payload = _payload()

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert exc_info.value.status_code == 422
        assert "otro cliente" in exc_info.value.detail.lower()
        assert fake_db.committed is False

    async def test_blocked_when_vin_belongs_to_a_different_client(self):
        other_owner_id = uuid.uuid4()
        # Different plate, but the SAME VIN as VALID_DELIVERY_PAYLOAD.
        other_vehicle = make_delivery_vehicle(plate="ZZZ999", vin="1HGCM82633A004352")
        other_vehicle.client_id = other_owner_id
        fake_db = FakeDeliverySession(vehicles=[other_vehicle])
        payload = _payload(vehicle={
            "plate": "NEWPLATE1", "vin": "1HGCM82633A004352", "model": "DSR",
            "color": "Rojo", "year": 2026, "engine_number": "ENG1",
        })

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert exc_info.value.status_code == 422
        assert fake_db.committed is False

    async def test_unrelated_vehicles_in_the_session_do_not_cause_a_false_positive(self):
        """`FakeDeliverySession.execute` returns every fixture `Vehicle` for
        any `select(Vehicle)` query, unfiltered (it doesn't emulate SQL
        WHERE) -- the service itself must filter by plate/VIN in Python, not
        just rely on the query's WHERE clause. An unrelated vehicle, owned
        by someone else, with a completely different plate/VIN must never
        block an unrelated new registration."""
        # `users` is deliberately empty here too, for the same reason as
        # `TestCreateBlockedOnOwnershipConflict` above -- a non-empty fixture
        # `users` list would make `_lookup_or_create_client`'s (unfiltered,
        # in this fake) lookup collapse this into a same-client scenario.
        unrelated_vehicle = make_delivery_vehicle(plate="QQQ111", vin="TOTALLYUNRELATED9")
        unrelated_vehicle.client_id = uuid.uuid4()
        fake_db = FakeDeliverySession(vehicles=[unrelated_vehicle])
        payload = _payload()  # plate ABC123 / vin 1HGCM82633A004352 -- no overlap

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert vehicle.plate == "ABC123"
        assert fake_db.committed is True


class TestCreateAllowedWhenNoRealConflict:
    async def test_allowed_when_existing_vehicle_has_no_client_yet(self):
        existing_vehicle = make_delivery_vehicle(plate="ABC123", vin="1HGCM82633A004352")
        existing_vehicle.client_id = None
        fake_db = FakeDeliverySession(vehicles=[existing_vehicle])
        payload = _payload()

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert vehicle.id == existing_vehicle.id
        assert fake_db.committed is True

    async def test_allowed_when_the_same_client_resubmits(self):
        """Design ADR 11 legacy-backfill flow: the same cédula re-delivering
        the same plate/VIN must keep working exactly as before."""
        same_client = make_client_user(identification="123456789", name="Juan Perez")
        existing_vehicle = make_delivery_vehicle(plate="ABC123", vin="1HGCM82633A004352")
        existing_vehicle.client_id = same_client.id
        fake_db = FakeDeliverySession(users=[same_client], vehicles=[existing_vehicle])
        payload = _payload()  # same cédula "123456789" as `same_client`

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

        assert vehicle.id == existing_vehicle.id
        assert vehicle.client_id == same_client.id
        assert fake_db.committed is True


class TestEditBlockedOnOwnershipConflict:
    async def test_blocked_when_new_plate_belongs_to_a_different_client(self):
        own_client = make_client_user(identification="123456789", name="Dueño Actual")
        vehicle = make_delivery_vehicle(plate="ABC123", vin="VIN-OWN", delivery_date=date(2026, 7, 1))
        vehicle.client_id = own_client.id

        other_client = make_client_user(identification="999888777", name="Otro Cliente")
        other_vehicle = make_delivery_vehicle(plate="TAKEN99", vin="VIN-OTHER")
        other_vehicle.client_id = other_client.id

        fake_db = FakeDeliverySession(
            users=[own_client, other_client], vehicles=[vehicle, other_vehicle]
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.edit_delivery(fake_db, vehicle.id, DeliveryEditIn(plate="TAKEN99"))

        assert exc_info.value.status_code == 422
        assert "Otro Cliente" in exc_info.value.detail
        assert vehicle.plate == "ABC123"  # untouched -- rejected before mutation

    async def test_blocked_when_new_vin_belongs_to_a_different_client(self):
        own_client = make_client_user(identification="123456789", name="Dueño Actual")
        vehicle = make_delivery_vehicle(plate="ABC123", vin="VIN-OWN", delivery_date=date(2026, 7, 1))
        vehicle.client_id = own_client.id

        other_client = make_client_user(identification="999888777", name="Otro Cliente")
        other_vehicle = make_delivery_vehicle(plate="TAKEN99", vin="1HGCM82633A004999")
        other_vehicle.client_id = other_client.id

        fake_db = FakeDeliverySession(
            users=[own_client, other_client],
            vehicles=[vehicle, other_vehicle],
            moto_units=[],
        )
        from tests.distributor_deliveries.conftest import make_moto_unit
        fake_db._moto_units = [make_moto_unit(vin_number="1HGCM82633A004999")]

        with pytest.raises(HTTPException) as exc_info:
            await svc.edit_delivery(fake_db, vehicle.id, DeliveryEditIn(vin="1HGCM82633A004999"))

        assert exc_info.value.status_code == 422
        assert vehicle.vin == "VIN-OWN"  # untouched -- rejected before mutation


class TestEditAllowedWhenNoRealConflict:
    async def test_not_falsely_blocked_by_editing_itself(self):
        """The vehicle being edited must be excluded from its own
        conflict check -- otherwise every edit that keeps the plate/VIN
        the same, or changes an unrelated field, would false-positive."""
        client = make_client_user(identification="123456789", name="Juan")
        vehicle = make_delivery_vehicle(plate="ABC123", vin="VIN-OWN", delivery_date=date(2026, 7, 1))
        vehicle.client_id = client.id
        fake_db = FakeDeliverySession(users=[client], vehicles=[vehicle])

        result = await svc.edit_delivery(fake_db, vehicle.id, DeliveryEditIn(color="Azul"))

        assert result.color == "Azul"
        assert fake_db.committed is True

    async def test_allowed_when_new_plate_belongs_to_no_one(self):
        client = make_client_user(identification="123456789", name="Juan")
        vehicle = make_delivery_vehicle(plate="ABC123", vin="VIN-OWN", delivery_date=date(2026, 7, 1))
        vehicle.client_id = client.id
        fake_db = FakeDeliverySession(users=[client], vehicles=[vehicle])

        result = await svc.edit_delivery(fake_db, vehicle.id, DeliveryEditIn(plate="FREEPLATE"))

        assert result.plate == "FREEPLATE"
        assert fake_db.committed is True
