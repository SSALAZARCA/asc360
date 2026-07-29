"""
tests/orders/test_vehicle_client_link.py -- `sdd/distributor-vehicle-delivery`
PR2, task 2.3: RED tests for the opportunistic vehicle-client-link refresh
(Design ADR 13b) wired into `POST /orders/` (`create_service_order`).
Secondary/bonus mechanism -- most-recent-wins, no-op when the order carries
no `client_id`.
"""
import uuid

from app.api.v1 import orders as orders_module
from app.schemas.order import OrderCreate, ReceptionBase

from tests.orders.test_create_order_otp_toggle import (
    FakeCreateOrderSession,
    _fake_pdf,
    vehicle_and_tenant,
)


def _order_payload_with_client(vehicle_id, tenant_id, client_id=None):
    return OrderCreate(
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        client_id=client_id,
        service_type=orders_module.ServiceType.regular,
        reception=ReceptionBase(mileage_km=1000),
    )


class TestVehicleClientLinkRefresh:
    async def test_client_id_present_updates_vehicle_client_id(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        assert vehicle.client_id is None
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSession("true", vehicle, tenant)
        client_id = uuid.uuid4()
        order_in = _order_payload_with_client(vehicle.id, tenant.id, client_id=client_id)

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
        )

        assert vehicle.client_id == client_id

    async def test_client_id_absent_leaves_vehicle_client_id_untouched(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        existing_client_id = uuid.uuid4()
        vehicle.client_id = existing_client_id
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSession("true", vehicle, tenant)
        order_in = _order_payload_with_client(vehicle.id, tenant.id, client_id=None)

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
        )

        assert vehicle.client_id == existing_client_id

    async def test_a_newer_client_id_overwrites_the_previous_one(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        vehicle.client_id = uuid.uuid4()
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSession("true", vehicle, tenant)
        new_client_id = uuid.uuid4()
        order_in = _order_payload_with_client(vehicle.id, tenant.id, client_id=new_client_id)

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
        )

        assert vehicle.client_id == new_client_id
