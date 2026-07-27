"""
tests/historical_orders/test_duplicate_warning.py — Requirement "Duplicate
Warning, Never Blocking": an existing order matching the same plate+date
must warn (409 `DUPLICATE_ORDER_WARNING`) but never hard-block; re-POSTing
with `acknowledge_duplicate=True` must succeed.

The scenario seeds an ALREADY-EXISTING vehicle (by plate) and an
ALREADY-EXISTING client (by phone) so `register_or_update_vehicle`/
`_lookup_or_create_client` both take their UPDATE/lookup-hit paths, not the
create path -- this is what makes "zero adds" on the warned pass a REAL
assertion (not incidentally true): the only thing that would legitimately
get added on that pass is the ServiceOrder/reception/etc chain, and the
duplicate check runs BEFORE any of those exist.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.order import ServiceStatus, ServiceType
from app.schemas.historical_order import HistoricalOrderCreate
from app.services import historical_order_service as svc

from tests.historical_orders.conftest import (
    FakeHistoricalOrderSession,
    make_client_user,
    make_existing_order,
    make_superadmin,
    make_tenant,
    make_vehicle,
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


class TestDuplicateWarningNeverBlocks:
    async def test_first_post_without_acknowledgement_returns_409_with_zero_adds(self, monkeypatch):
        tenant_id = uuid.uuid4()
        vehicle = make_vehicle(plate="ABC123", tenant_id=tenant_id)
        client = make_client_user(tenant_id=tenant_id, phone="3001234567")
        existing_order = make_existing_order(
            vehicle_id=vehicle.id, created_at=datetime(2025, 1, 10, 8, 0),
        )
        pdf_spy = AsyncMock(return_value="http://pdf.example/a.pdf")
        monkeypatch.setattr(svc, "generate_and_upload_reception_pdf", pdf_spy)

        payload = _payload(tenant_id=tenant_id, acknowledge_duplicate=False)
        fake_db = FakeHistoricalOrderSession(
            users=[client],
            vehicles=[vehicle],
            existing_orders=[existing_order],
            tenant=make_tenant(tenant_id=tenant_id),
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_ORDER_WARNING"
        assert len(exc_info.value.detail["matches"]) == 1
        assert exc_info.value.detail["matches"][0]["order_id"] == str(existing_order.id)

        assert fake_db.added == []
        assert fake_db.committed is False
        assert fake_db.rolled_back is True
        pdf_spy.assert_not_called()

    async def test_second_post_with_acknowledgement_succeeds(self, monkeypatch):
        tenant_id = uuid.uuid4()
        vehicle = make_vehicle(plate="ABC123", tenant_id=tenant_id)
        client = make_client_user(tenant_id=tenant_id, phone="3001234567")
        existing_order = make_existing_order(
            vehicle_id=vehicle.id, created_at=datetime(2025, 1, 10, 8, 0),
        )
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )

        payload = _payload(tenant_id=tenant_id, acknowledge_duplicate=True)
        fake_db = FakeHistoricalOrderSession(
            users=[client],
            vehicles=[vehicle],
            existing_orders=[existing_order],
            tenant=make_tenant(tenant_id=tenant_id),
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert order.status == ServiceStatus.received
        assert fake_db.committed is True

    async def test_no_matching_date_does_not_warn(self, monkeypatch):
        tenant_id = uuid.uuid4()
        vehicle = make_vehicle(plate="ABC123", tenant_id=tenant_id)
        client = make_client_user(tenant_id=tenant_id, phone="3001234567")
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )

        payload = _payload(tenant_id=tenant_id, acknowledge_duplicate=False)
        fake_db = FakeHistoricalOrderSession(
            users=[client],
            vehicles=[vehicle],
            existing_orders=[],  # no orders at all on this plate
            tenant=make_tenant(tenant_id=tenant_id),
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())
        assert order.status == ServiceStatus.received
        assert fake_db.committed is True
