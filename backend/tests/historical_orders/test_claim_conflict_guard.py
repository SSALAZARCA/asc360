"""
tests/historical_orders/test_claim_conflict_guard.py --
`historical_order_service._check_claim_conflict`
(`sdd/vehicle-tenant-checkin-release` PR3, Design File Change #9): a
historical/backdated order must not claim-jump a vehicle another taller
currently holds -- same conflict rule as `POST /orders/`
(`test_order_creation_conflict_guard.py`), but this path fires NO Telegram
notification (superadmin is the actor; see `test_no_notifications.py`'s
static guard, extended in this PR to also cover `notification_service`).

Uses `FakeHistoricalOrderSession` (extended in `conftest.py` for PR3 to
also fake `get_open_claim`'s `SELECT (ServiceOrder, Tenant)` read) -- no
live DB.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.order import ServiceStatus, ServiceType
from app.schemas.historical_order import HistoricalOrderCreate
from app.services import historical_order_service as svc

from tests.historical_orders.conftest import (
    FakeHistoricalOrderSession,
    make_superadmin,
    make_tenant,
)


def _payload(**overrides) -> HistoricalOrderCreate:
    data = dict(
        tenant_id=uuid.uuid4(),
        vehicle={"plate": "ABC123", "brand": "UM", "model": "DSR"},
        client={"name": "Juan Perez", "phone": "3001234567"},
        service_type=ServiceType.regular,
        status=ServiceStatus.received,
        mileage_km=Decimal("1000"),
        created_at=datetime(2025, 1, 10, 9, 0),
        completed_at=None,
        delivered_at=None,
        customer_notes=None,
        diagnosis=None,
        general_observations=None,
        technician_id=None,
        acknowledge_duplicate=False,
    )
    data.update(overrides)
    return HistoricalOrderCreate(**data)


def _claim_row(tenant_id, order_status=ServiceStatus.in_progress):
    order = SimpleNamespace(id=uuid.uuid4(), status=order_status, created_at=datetime(2025, 1, 1))
    tenant = SimpleNamespace(id=tenant_id, name="Taller Rival", ciudad="Medellín")
    return (order, tenant)


class TestOpenStatusBlockedByConflict:
    async def test_open_status_into_a_vehicle_claimed_by_another_tenant_is_409(self, monkeypatch):
        monkeypatch.setattr(svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf"))
        other_tenant_id = uuid.uuid4()
        payload = _payload(status=ServiceStatus.received)
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            claim_row=_claim_row(other_tenant_id),
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "VEHICLE_CLAIMED_BY_OTHER_TENANT"
        assert not fake_db.committed

    async def test_open_status_into_a_vehicle_claimed_by_the_same_tenant_succeeds(self, monkeypatch):
        monkeypatch.setattr(svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf"))
        payload = _payload(status=ServiceStatus.received)
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            claim_row=_claim_row(payload.tenant_id),
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert order.status == ServiceStatus.received

    async def test_no_open_claim_succeeds_normally(self, monkeypatch):
        monkeypatch.setattr(svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf"))
        payload = _payload(status=ServiceStatus.received)
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            claim_row=None,
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert order.status == ServiceStatus.received


class TestReleasingStatusNeverBlocked:
    async def test_born_delivered_order_never_triggers_the_conflict_check(self, monkeypatch):
        """Even if some OTHER conflicting claim technically exists, a
        born-`delivered` order can never itself hold a claim -- the check
        is skipped entirely for `RELEASING_STATUSES`, before ever issuing
        the `get_open_claim` SELECT."""
        monkeypatch.setattr(svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf"))
        other_tenant_id = uuid.uuid4()
        payload = _payload(
            status=ServiceStatus.delivered,
            completed_at=datetime(2025, 1, 12, 17, 0),
            delivered_at=datetime(2025, 1, 14, 11, 0),
        )
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            claim_row=_claim_row(other_tenant_id),
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert order.status == ServiceStatus.delivered
        assert not any(len(stmt.column_descriptions) == 2 for stmt in fake_db.executed_statements)

    async def test_cancelled_status_also_skips_the_check(self, monkeypatch):
        monkeypatch.setattr(svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf"))
        other_tenant_id = uuid.uuid4()
        payload = _payload(status=ServiceStatus.cancelled)
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            claim_row=_claim_row(other_tenant_id),
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())
        assert order.status == ServiceStatus.cancelled


class TestNoNotificationOnConflict:
    async def test_conflict_never_touches_notification_service(self, monkeypatch):
        import app.services.notification_service as notification_module

        spy = AsyncMock()
        monkeypatch.setattr(notification_module, "notify_claim_conflict", spy)
        monkeypatch.setattr(svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf"))

        other_tenant_id = uuid.uuid4()
        payload = _payload(status=ServiceStatus.received)
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            claim_row=_claim_row(other_tenant_id),
        )

        with pytest.raises(HTTPException):
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        spy.assert_not_called()

    def test_historical_order_service_module_never_imports_notification_service(self):
        """Static guard, mirroring `test_no_notifications.py`'s own
        pattern: the historical/backdated order path fires NO Telegram
        notification on conflict -- superadmin is the actor."""
        import inspect
        source = inspect.getsource(svc)
        assert "notification_service" not in source
        assert "notify_claim_conflict" not in source
