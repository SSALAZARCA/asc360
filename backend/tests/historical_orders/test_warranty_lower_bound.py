"""
tests/historical_orders/test_warranty_lower_bound.py --
`sdd/distributor-vehicle-delivery` PR2, task 2.5: RED tests for the
warranty lower-bound invariant wired into `create_historical_order`, right
after `_check_claim_conflict` (Design: File Changes,
`historical_order_service.py` entry; ADR 1-3). Narrowly supersedes this
module's original "no date-range validation" non-goal -- only for a
vehicle that already has a registered `delivery_date`.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
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


class TestWarrantyLowerBoundAtHistoricalEntry:
    async def test_created_at_before_delivery_date_blocks_with_422_and_no_commit(self, monkeypatch):
        """No `commit()` ever happens on the 422 path -- same convention as
        `test_claim_conflict_guard.py`'s guard tests, NOT a bare `added ==
        []` assertion: the client (`_lookup_or_create_client`) is resolved
        BEFORE this check runs (it sits right after `_check_claim_conflict`,
        per the design's placement), so `db.add()`/`db.flush()` may already
        have been called on an uncommitted transaction that gets rolled
        back -- nothing is ever durably written."""
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        vehicle = make_vehicle(plate="ABC123")
        vehicle.delivery_date = date(2025, 6, 1)
        payload = _payload(created_at=datetime(2025, 1, 10, 9, 0))
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            vehicles=[vehicle],
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert exc_info.value.status_code == 422
        assert not fake_db.committed
        assert fake_db.rolled_back

    async def test_no_delivery_date_preserves_the_no_date_validation_non_goal(self, monkeypatch):
        """The pre-existing non-goal ('no date-range validation') is not
        deleted -- it now only applies once the vehicle has a registered
        `delivery_date`. Every vehicle today has none."""
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        vehicle = make_vehicle(plate="ABC123")
        assert vehicle.delivery_date is None
        payload = _payload(created_at=datetime(1999, 1, 1))
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            vehicles=[vehicle],
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())
        assert order.created_at == datetime(1999, 1, 1)

    async def test_created_at_after_delivery_date_succeeds(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        vehicle = make_vehicle(plate="ABC123")
        vehicle.delivery_date = date(2025, 1, 1)
        payload = _payload(created_at=datetime(2025, 1, 10, 9, 0))
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id),
            vehicles=[vehicle],
        )

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())
        assert order is not None
