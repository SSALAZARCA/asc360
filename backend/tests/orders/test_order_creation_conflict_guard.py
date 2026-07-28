"""
tests/orders/test_order_creation_conflict_guard.py -- `POST /orders/`'s
claim conflict guard (`sdd/vehicle-tenant-checkin-release` PR3, Design
Decision 1: the guard sits at order creation, atomic with the act that
creates the claim).

Reuses `FakeCreateOrderSession` (extended in `test_create_order_otp_
toggle.py` for PR3 to also fake `get_open_claim`'s
`SELECT (ServiceOrder, Tenant)` read, dispatched by column count exactly
like `tests/orders/test_mini_app_get_vehicle_claim.py`'s
`FakeMiniAppSession`) and its `vehicle_and_tenant`/`_order_payload`/
`_fake_pdf` helpers -- no live DB.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import orders as orders_module
from app.models.order import ServiceOrder, ServiceStatus, ServiceType
from app.models.tenant import Tenant

from tests.orders.test_create_order_otp_toggle import (
    FakeCreateOrderSession,
    _fake_pdf,
    _order_payload,
    vehicle_and_tenant,
)


def _claim_row(tenant_id: uuid.UUID, status: ServiceStatus = ServiceStatus.in_progress):
    order = SimpleNamespace(id=uuid.uuid4(), status=status, created_at=datetime(2025, 1, 1))
    tenant = SimpleNamespace(id=tenant_id, name="Taller Rival", ciudad="Medellín")
    return (order, tenant)


class TestConflictBlocksCreation:
    async def test_open_claim_by_another_tenant_returns_409_with_code_and_creates_no_order(
        self, monkeypatch, vehicle_and_tenant
    ):
        vehicle, requesting_tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        holder_tenant_id = uuid.uuid4()
        session = FakeCreateOrderSession(
            "true", vehicle, requesting_tenant, claim_row=_claim_row(holder_tenant_id)
        )
        order_in = _order_payload(vehicle.id, requesting_tenant.id)

        with pytest.raises(HTTPException) as exc_info:
            await orders_module.create_service_order(
                order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "VEHICLE_CLAIMED_BY_OTHER_TENANT"
        assert session.added_of(ServiceOrder) == []
        assert session.commits == 0

    async def test_no_open_claim_creates_the_order_normally(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSession("true", vehicle, tenant, claim_row=None)
        order_in = _order_payload(vehicle.id, tenant.id)

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
        )

        [order] = session.added_of(ServiceOrder)
        assert order.status == ServiceStatus.pending_signature

    async def test_open_claim_by_the_SAME_tenant_is_not_a_conflict(self, monkeypatch, vehicle_and_tenant):
        """Re-opening a new order for a vehicle your OWN taller already
        holds is not the conflict this guard exists for."""
        vehicle, tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSession("true", vehicle, tenant, claim_row=_claim_row(tenant.id))
        order_in = _order_payload(vehicle.id, tenant.id)

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
        )

        [order] = session.added_of(ServiceOrder)
        assert order.status == ServiceStatus.pending_signature


class TestConflictNotification:
    async def test_conflict_dispatches_notify_claim_conflict_with_claim_and_requesting_tenant(
        self, monkeypatch, vehicle_and_tenant
    ):
        vehicle, requesting_tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        import app.services.notification_service as notification_module

        captured = {}

        async def _spy(db, claim, plate, tenant):
            captured["claim_tenant_id"] = claim.tenant_id
            captured["plate"] = plate
            captured["requesting_tenant"] = tenant

        monkeypatch.setattr(notification_module, "notify_claim_conflict", _spy)

        holder_tenant_id = uuid.uuid4()
        session = FakeCreateOrderSession(
            "true", vehicle, requesting_tenant, claim_row=_claim_row(holder_tenant_id)
        )
        order_in = _order_payload(vehicle.id, requesting_tenant.id)

        with pytest.raises(HTTPException):
            await orders_module.create_service_order(
                order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
            )

        assert captured["claim_tenant_id"] == holder_tenant_id
        assert captured["plate"] == vehicle.plate
        assert captured["requesting_tenant"] is requesting_tenant

    async def test_notification_failure_never_masks_or_reverses_the_409(self, monkeypatch, vehicle_and_tenant):
        """Task 3.3 / security requirement: a Telegram failure must NEVER
        break or reverse the conflict-block -- the 409 must still be
        raised, and still with zero rows created."""
        vehicle, requesting_tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        import app.services.notification_service as notification_module

        async def _raise(*args, **kwargs):
            raise RuntimeError("telegram is down")

        monkeypatch.setattr(notification_module, "notify_claim_conflict", _raise)

        holder_tenant_id = uuid.uuid4()
        session = FakeCreateOrderSession(
            "true", vehicle, requesting_tenant, claim_row=_claim_row(holder_tenant_id)
        )
        order_in = _order_payload(vehicle.id, requesting_tenant.id)

        with pytest.raises(HTTPException) as exc_info:
            await orders_module.create_service_order(
                order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "VEHICLE_CLAIMED_BY_OTHER_TENANT"
        assert session.added_of(ServiceOrder) == []


class TestTallerAToBRoundTrip:
    """Task 3.11 -- narrative integration scenario chaining several
    `create_service_order` calls. There is no live DB across calls, so
    each step's `claim_row` is set to the derived claim state a real
    database WOULD report at that point in the story (unclaimed once A's
    order is delivered, held by B once B's order is open, etc.) -- the
    same primitive `get_open_claim` compiles against in production."""

    async def test_a_delivers_b_claims_c_blocked_while_b_open_then_unblocked_on_delivery(
        self, monkeypatch, vehicle_and_tenant
    ):
        vehicle, tenant_a = vehicle_and_tenant
        tenant_b = Tenant(id=uuid.uuid4(), name="Taller B", subdomain="taller-b", tenant_type="service_center")
        tenant_c = Tenant(id=uuid.uuid4(), name="Taller C", subdomain="taller-c", tenant_type="service_center")
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        # Step 1: Taller A's order already exists and was delivered --
        # unclaimed from here on (`RELEASING_STATUSES`), so B's lookup
        # finds no open claim.
        session_b = FakeCreateOrderSession("true", vehicle, tenant_b, claim_row=None)
        order_in_b = _order_payload(vehicle.id, tenant_b.id)
        await orders_module.create_service_order(
            order_in_b, db=session_b, x_sonia_secret="test-bot-secret", current_user=None
        )
        [order_b] = session_b.added_of(ServiceOrder)
        assert order_b.tenant_id == tenant_b.id

        # Step 2: while B's order is still open, Taller C is blocked.
        session_c = FakeCreateOrderSession(
            "true", vehicle, tenant_c, claim_row=_claim_row(tenant_b.id)
        )
        order_in_c = _order_payload(vehicle.id, tenant_c.id)
        with pytest.raises(HTTPException) as exc_info:
            await orders_module.create_service_order(
                order_in_c, db=session_c, x_sonia_secret="test-bot-secret", current_user=None
            )
        assert exc_info.value.status_code == 409
        assert session_c.added_of(ServiceOrder) == []

        # Step 3: once B delivers (claim released), C is unblocked.
        session_c2 = FakeCreateOrderSession("true", vehicle, tenant_c, claim_row=None)
        order_in_c2 = _order_payload(vehicle.id, tenant_c.id)
        await orders_module.create_service_order(
            order_in_c2, db=session_c2, x_sonia_secret="test-bot-secret", current_user=None
        )
        [order_c] = session_c2.added_of(ServiceOrder)
        assert order_c.tenant_id == tenant_c.id
