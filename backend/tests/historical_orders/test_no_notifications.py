"""
tests/historical_orders/test_no_notifications.py — Requirement "No
Notification Dispatch": this flow must NEVER send an SMS/WhatsApp
notification, regardless of resulting status (even when created already
`delivered`). Suppression is achieved by OMISSION (design's "Notification
suppression" section) — the module must never import `app.services.
sms_service` and never create an `OrderOTP` row.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

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
        service_type=ServiceType.warranty,
        status=ServiceStatus.delivered,
        mileage_km=Decimal("2500"),
        created_at=datetime(2025, 1, 10, 9, 0),
        completed_at=datetime(2025, 1, 12, 17, 0),
        delivered_at=datetime(2025, 1, 14, 11, 0),
        customer_notes=None,
        diagnosis="Cambio de piñón bajo garantía",
        general_observations=None,
        technician_id=None,
        acknowledge_duplicate=False,
    )
    data.update(overrides)
    return HistoricalOrderCreate(**data)


class TestNoNotificationDispatch:
    async def test_send_otp_sms_is_never_called_even_when_created_already_delivered(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        import app.services.sms_service as sms_service_module
        spy = AsyncMock(side_effect=AssertionError("send_otp_sms must never be called by historical order entry"))
        monkeypatch.setattr(sms_service_module, "send_otp_sms", spy)

        payload = _payload()
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        spy.assert_not_called()
        assert order.status == ServiceStatus.delivered

    async def test_no_order_otp_row_is_ever_added(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        payload = _payload()
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert not any(obj.__class__.__name__ == "OrderOTP" for obj in fake_db.added)

    def test_historical_order_service_module_never_imports_sms_service(self):
        """Static guard: the service module's own source must never import
        the SMS dispatcher -- the ONLY dispatch function in the codebase
        (design's verified codebase fact)."""
        import inspect
        source = inspect.getsource(svc)
        assert "sms_service" not in source
        assert "send_otp_sms" not in source
