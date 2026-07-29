"""
tests/historical_orders/test_vehicle_client_link.py --
`sdd/distributor-vehicle-delivery` PR2, task 2.7: RED tests for the
opportunistic vehicle-client-link refresh (Design ADR 13b) wired into
`create_historical_order`. Unlike `POST /orders/` (where `client_id` is
optional and may be absent), this path's client is ALWAYS resolved
(lookup-or-create, `_lookup_or_create_client`), so `vehicle.client_id` is
always set/refreshed here.
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


class TestVehicleClientLinkRefreshAtHistoricalEntry:
    async def test_resolved_client_updates_vehicle_client_id(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        vehicle = make_vehicle(plate="ABC123")
        assert vehicle.client_id is None
        payload = _payload()
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            vehicles=[vehicle],
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert vehicle.client_id == order.client_id

    async def test_a_second_order_with_a_different_client_overwrites_the_link(self, monkeypatch):
        """Most-recent-wins (ADR 13b) -- there is no primacy protection at
        this path; whichever historical order is entered last wins."""
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        vehicle = make_vehicle(plate="ABC123")
        vehicle.client_id = uuid.uuid4()

        payload = _payload(client={"name": "Otra Persona", "phone": "3009999999"})
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            vehicles=[vehicle],
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert vehicle.client_id == order.client_id
