"""
tests/historical_orders/test_transaction.py — the whole flow runs on ONE
session with a SINGLE `commit()` at the very end (design's "Technical
Approach"). Any failure anywhere in the pipeline must roll back everything,
never leave a half-created order.

- An exception raised INSIDE the PDF step (`generate_and_upload_reception_
  pdf` itself raising, not just returning "") must roll back, never commit.
- A DB-level `IntegrityError` at `commit()` time must roll back and surface
  as a clean, sanitized 409 (never the raw driver message).
- Any other unexpected exception at `commit()` time must roll back and
  surface as a sanitized 500.
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


class TestExceptionAtPdfStepRollsBack:
    async def test_pdf_generation_raising_rolls_back_and_never_commits(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf",
            AsyncMock(side_effect=RuntimeError("weasyprint blew up")),
        )
        payload = _payload()
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert exc_info.value.status_code == 500
        assert fake_db.rolled_back is True
        assert fake_db.committed is False


class TestIntegrityErrorAtCommitIsSanitized409:
    async def test_integrity_error_rolls_back_and_returns_generic_409(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        payload = _payload()
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id), raise_integrity_error=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert exc_info.value.status_code == 409
        assert "duplicate key" not in str(exc_info.value.detail)
        assert fake_db.rolled_back is True
        assert fake_db.committed is False


class TestUnexpectedErrorAtCommitIsSanitized500:
    async def test_generic_exception_rolls_back_and_returns_generic_500(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        payload = _payload()
        fake_db = FakeHistoricalOrderSession(
            tenant=make_tenant(tenant_id=payload.tenant_id), raise_generic_error=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert exc_info.value.status_code == 500
        assert "boom" not in str(exc_info.value.detail)
        assert fake_db.rolled_back is True
        assert fake_db.committed is False


class TestHappyPathCommitsExactlyOnce:
    async def test_successful_creation_commits_once_never_rolls_back(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        payload = _payload()
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        order = await svc.create_historical_order(fake_db, payload, make_superadmin())

        assert order is not None
        assert fake_db.committed is True
        assert fake_db.rolled_back is False
