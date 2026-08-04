"""
tests/distributor_deliveries/test_registered_by_tenant.py — which
Distribuidora gets attributed a sale.

A tenant-scoped actor (Distribuidor) always gets their OWN `tenant_id`
attributed, server-side, regardless of anything the payload sends --
`registered_by_tenant_id` must never let a Distribuidor spoof a different
Distribuidora. Superadmin has no tenant of their own, so they must
explicitly select one, both on CREATE and on EDIT (PATCH).
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
    make_distribuidor,
    make_superadmin,
    make_tenant,
    make_valid_photo,
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


class TestTenantActorCannotSpoofRegisteredByTenant:
    async def test_distribuidor_payload_tenant_id_is_ignored(self):
        own_tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        fake_db = FakeDeliverySession()
        actor = make_distribuidor(tenant_id=own_tenant_id)
        payload = _payload(registered_by_tenant_id=str(other_tenant_id))

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), actor)

        assert vehicle.registered_by_tenant_id == own_tenant_id
        assert vehicle.registered_by_tenant_id != other_tenant_id

    async def test_distribuidor_with_no_tenant_id_gets_none_even_with_payload_value(self):
        fake_db = FakeDeliverySession()
        actor = make_distribuidor(tenant_id=None)
        payload = _payload(registered_by_tenant_id=str(uuid.uuid4()))

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), actor)

        assert vehicle.registered_by_tenant_id is None


class TestSuperadminMustExplicitlySelectTenant:
    async def test_missing_registered_by_tenant_id_rejected(self):
        fake_db = FakeDeliverySession()
        payload = _payload()  # no registered_by_tenant_id

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_delivery(fake_db, payload, make_valid_photo(), make_superadmin())

        assert exc_info.value.status_code == 422
        assert fake_db.committed is False

    async def test_nonexistent_registered_by_tenant_id_rejected(self):
        fake_db = FakeDeliverySession(tenants=[])
        payload = _payload(registered_by_tenant_id=str(uuid.uuid4()))

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_delivery(fake_db, payload, make_valid_photo(), make_superadmin())

        assert exc_info.value.status_code == 422
        assert fake_db.committed is False

    async def test_valid_registered_by_tenant_id_is_applied(self):
        tenant = make_tenant(name="Moto Total S.A.S")
        fake_db = FakeDeliverySession(tenants=[tenant])
        payload = _payload(registered_by_tenant_id=str(tenant.id))

        vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_superadmin())

        assert vehicle.registered_by_tenant_id == tenant.id
        assert fake_db.committed is True


class TestEditRegisteredByTenant:
    async def test_superadmin_can_reassign_registered_by_tenant(self):
        old_tenant = make_tenant(name="Vieja Distribuidora")
        new_tenant = make_tenant(name="Nueva Distribuidora")
        vehicle = make_delivery_vehicle(
            plate="ABC123", delivery_date=date(2026, 7, 1),
            registered_by_tenant_id=old_tenant.id,
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle], tenants=[new_tenant])
        payload = DeliveryEditIn(registered_by_tenant_id=new_tenant.id)

        result = await svc.edit_delivery(fake_db, vehicle.id, payload)

        assert result.registered_by_tenant_id == new_tenant.id
        assert fake_db.committed is True

    async def test_nonexistent_registered_by_tenant_id_rejected_and_not_persisted(self):
        vehicle = make_delivery_vehicle(plate="ABC123", delivery_date=date(2026, 7, 1))
        fake_db = FakeDeliverySession(vehicles=[vehicle], tenants=[])
        payload = DeliveryEditIn(registered_by_tenant_id=uuid.uuid4())

        with pytest.raises(HTTPException) as exc_info:
            await svc.edit_delivery(fake_db, vehicle.id, payload)

        assert exc_info.value.status_code == 422
        assert fake_db.committed is False


class TestGetDeliveryDetailIncludesRegisteredByTenant:
    async def test_detail_includes_tenant_id_and_name(self):
        tenant = make_tenant(name="Moto Total S.A.S")
        vehicle = make_delivery_vehicle(
            plate="ABC123", delivery_date=date(2026, 7, 28),
            registered_by_tenant_id=tenant.id, registered_by_tenant=tenant,
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])

        detail = await svc.get_delivery_detail(fake_db, vehicle.id)

        assert detail.registered_by_tenant_id == tenant.id
        assert detail.registered_by_tenant_name == "Moto Total S.A.S"
