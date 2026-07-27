"""
tests/historical_orders/test_audit_log.py — Requirement "Mandatory Audit
Log": exactly one `ImportAuditLog` row, `action="MANUAL_HISTORICAL_ORDER"`,
identifying the creating (super)actor, referencing the created order, with
a fully JSON-serializable payload (a raw `datetime`/`Decimal` in a JSONB
column caused a real production 500 before -- `superadmin_data.py:507-509`
per the design's codebase facts). No cédula/identification key anywhere.
"""
import json
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from app.models.imports import ImportAuditLog
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


class TestMandatoryAuditLog:
    async def test_exactly_one_audit_row_with_correct_action_and_actor(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        actor = make_superadmin()
        payload = _payload()
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        order = await svc.create_historical_order(fake_db, payload, actor)

        audit_rows = [obj for obj in fake_db.added if isinstance(obj, ImportAuditLog)]
        assert len(audit_rows) == 1
        row = audit_rows[0]
        assert row.action == "MANUAL_HISTORICAL_ORDER"
        assert row.entity_type == "ServiceOrder"
        assert row.entity_id == str(order.id)
        assert row.actor_id == uuid.UUID(actor.user_id)
        assert row.actor_role == "superadmin"

    async def test_payload_is_fully_json_serializable(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        payload = _payload(
            completed_at=datetime(2025, 1, 12, 10, 0), delivered_at=None,
            status=ServiceStatus.completed,
        )
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        await svc.create_historical_order(fake_db, payload, make_superadmin())

        row = next(obj for obj in fake_db.added if isinstance(obj, ImportAuditLog))
        # Must not raise -- a raw datetime/Decimal would blow up json.dumps.
        serialized = json.dumps(row.payload)
        assert "2025-01-10" in serialized
        assert "2025-01-12" in serialized

    async def test_payload_has_no_identification_or_cedula_key(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        payload = _payload()
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        await svc.create_historical_order(fake_db, payload, make_superadmin())

        row = next(obj for obj in fake_db.added if isinstance(obj, ImportAuditLog))
        assert "identification" not in row.payload
        assert "cedula" not in row.payload

    async def test_payload_records_duplicate_acknowledged_flag(self, monkeypatch):
        monkeypatch.setattr(
            svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
        )
        payload = _payload(acknowledge_duplicate=True)
        fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id))

        await svc.create_historical_order(fake_db, payload, make_superadmin())

        row = next(obj for obj in fake_db.added if isinstance(obj, ImportAuditLog))
        assert row.payload["duplicate_acknowledged"] is True
