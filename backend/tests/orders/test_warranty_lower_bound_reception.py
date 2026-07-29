"""
tests/orders/test_warranty_lower_bound_reception.py --
`sdd/distributor-vehicle-delivery` PR2, task 2.1: RED tests for the
warranty lower-bound invariant wired into `POST /orders/`
(`create_service_order`), reusing the already-loaded `vehicle_obj` from
the pre-existing claim guard (Design: File Changes, `orders.py` entry;
ADR 1-3).

Uses large (5-day) offsets from "today" rather than a fixed clock so the
test is not flaky around UTC/local-timezone skew between the test host
and `datetime.utcnow()`'s effective "now" inside `create_service_order`.
"""
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.api.v1 import orders as orders_module
from app.models.order import ServiceOrder

from tests.orders.test_create_order_otp_toggle import (
    FakeCreateOrderSession,
    _fake_pdf,
    _order_payload,
    vehicle_and_tenant,
)


class TestWarrantyLowerBoundAtReception:
    async def test_future_delivery_date_blocks_creation_with_422_and_zero_writes(
        self, monkeypatch, vehicle_and_tenant
    ):
        vehicle, tenant = vehicle_and_tenant
        vehicle.delivery_date = date.today() + timedelta(days=5)
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSession("true", vehicle, tenant)
        order_in = _order_payload(vehicle.id, tenant.id)

        with pytest.raises(HTTPException) as exc_info:
            await orders_module.create_service_order(
                order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
            )

        assert exc_info.value.status_code == 422
        assert session.added_of(ServiceOrder) == []
        assert session.commits == 0

    async def test_no_delivery_date_leaves_creation_unchanged(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        assert vehicle.delivery_date is None
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSession("true", vehicle, tenant)
        order_in = _order_payload(vehicle.id, tenant.id)

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
        )

        [order] = session.added_of(ServiceOrder)
        assert order.tenant_id == tenant.id

    async def test_past_delivery_date_does_not_block_creation(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        vehicle.delivery_date = date.today() - timedelta(days=30)
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSession("true", vehicle, tenant)
        order_in = _order_payload(vehicle.id, tenant.id)

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
        )

        [order] = session.added_of(ServiceOrder)
        assert order is not None
