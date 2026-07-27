"""
tests/historical_orders/test_order_history_chain.py — the fabricated
OrderHistory chain for an already-final historical order (design's
"OrderHistory for an already-final order" section, Decision 9: no
`in_progress` row).

Covers: row count / `from_status`->`to_status` per row / `changed_at` /
`duration_minutes` back-fill (mirrors `update_order_status`/`claim_order`'s
existing pattern — previous row's duration = next row's `changed_at` minus
its own); the 422 guard when `payload.status` doesn't match what the
closing dates justify.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.order import OrderHistory, ServiceStatus, ServiceType
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


async def _run(payload, monkeypatch):
    monkeypatch.setattr(
        svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
    )
    fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))
    order = await svc.create_historical_order(fake_db, payload, make_superadmin())
    return order, fake_db


def _history_rows(fake_db):
    return sorted(
        [obj for obj in fake_db.added if isinstance(obj, OrderHistory)],
        key=lambda row: row.changed_at,
    )


class TestReceivedOnlyChain:
    async def test_single_received_row_no_in_progress(self, monkeypatch):
        payload = _payload(status=ServiceStatus.received)
        order, fake_db = await _run(payload, monkeypatch)

        rows = _history_rows(fake_db)
        assert len(rows) == 1
        assert rows[0].from_status is None
        assert rows[0].to_status == ServiceStatus.received
        assert rows[0].changed_at == payload.created_at
        assert rows[0].duration_minutes is None
        assert not any(r.to_status == ServiceStatus.in_progress for r in rows)
        assert not any(r.from_status == ServiceStatus.in_progress for r in rows)


class TestCompletedChain:
    async def test_two_rows_with_duration_backfilled_on_first(self, monkeypatch):
        payload = _payload(
            status=ServiceStatus.completed,
            completed_at=datetime(2025, 1, 12, 15, 0),
        )
        order, fake_db = await _run(payload, monkeypatch)

        rows = _history_rows(fake_db)
        assert len(rows) == 2
        assert (rows[0].from_status, rows[0].to_status) == (None, ServiceStatus.received)
        assert (rows[1].from_status, rows[1].to_status) == (ServiceStatus.received, ServiceStatus.completed)
        assert rows[1].changed_at == payload.completed_at

        expected_minutes = (payload.completed_at - payload.created_at).total_seconds() / 60.0
        assert rows[0].duration_minutes is not None
        assert abs(float(rows[0].duration_minutes) - expected_minutes) < 0.01
        assert rows[1].duration_minutes is None


class TestDeliveredAfterCompletedChain:
    async def test_three_rows_full_chain_with_two_durations_backfilled(self, monkeypatch):
        payload = _payload(
            service_type=ServiceType.warranty,
            status=ServiceStatus.delivered,
            completed_at=datetime(2025, 1, 12, 15, 0),
            delivered_at=datetime(2025, 1, 14, 10, 0),
        )
        order, fake_db = await _run(payload, monkeypatch)

        rows = _history_rows(fake_db)
        assert len(rows) == 3
        assert (rows[0].from_status, rows[0].to_status) == (None, ServiceStatus.received)
        assert (rows[1].from_status, rows[1].to_status) == (ServiceStatus.received, ServiceStatus.completed)
        assert (rows[2].from_status, rows[2].to_status) == (ServiceStatus.completed, ServiceStatus.delivered)
        assert rows[2].changed_at == payload.delivered_at
        assert rows[2].duration_minutes is None
        assert rows[0].duration_minutes is not None
        assert rows[1].duration_minutes is not None


class TestDeliveredWithoutCompletedChain:
    async def test_delivered_direct_from_received_when_never_completed(self, monkeypatch):
        payload = _payload(
            status=ServiceStatus.delivered,
            completed_at=None,
            delivered_at=datetime(2025, 1, 11, 10, 0),
        )
        order, fake_db = await _run(payload, monkeypatch)

        rows = _history_rows(fake_db)
        assert len(rows) == 2
        assert (rows[0].from_status, rows[0].to_status) == (None, ServiceStatus.received)
        assert (rows[1].from_status, rows[1].to_status) == (ServiceStatus.received, ServiceStatus.delivered)


class TestStatusDateMismatchIs422:
    async def test_delivered_status_without_delivered_at_returns_422(self, monkeypatch):
        payload = _payload(status=ServiceStatus.delivered, completed_at=None, delivered_at=None)
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert exc_info.value.status_code == 422
        assert fake_db.added == []
        assert fake_db.committed is False

    async def test_completed_status_without_completed_at_returns_422(self, monkeypatch):
        payload = _payload(status=ServiceStatus.completed, completed_at=None, delivered_at=None)
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert exc_info.value.status_code == 422
