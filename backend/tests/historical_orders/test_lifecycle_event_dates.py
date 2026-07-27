"""
tests/historical_orders/test_lifecycle_event_dates.py — the HEADLINE test
for the whole feature (design failure mode #7): every `VehicleLifecycleEvent`
this flow creates MUST carry the user-provided HISTORICAL date as its
`event_date`, never `datetime.utcnow()` (the column's own default, and the
value every other write path in the codebase stamps — see design's
"Codebase facts verified" table).

RECEPCION is always created at `created_at`. GARANTIA/MANTENIMIENTO (when
applicable) are dated at `completed_at`. ENTREGA is dated at `delivered_at`.
Every event must be `is_automatic="manual"` (Decision 10), and the RECEPCION
summary string must survive `_resync_recepcion_summary`'s
`KM:\\s*\\d+(?:\\.\\d+)?` regex (superadmin_data.py) unchanged.
"""
import re
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from app.api.v1.superadmin_data import _resync_recepcion_summary
from app.models.order import ServiceStatus, ServiceType
from app.models.vehicle_lifecycle import LifecycleEventType
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
        service_type=ServiceType.warranty,
        status=ServiceStatus.completed,
        mileage_km=Decimal("2500"),
        created_at=datetime(2025, 1, 10, 9, 0),
        completed_at=datetime(2025, 1, 12, 17, 0),
        delivered_at=None,
        customer_notes="Ruido en el motor",
        diagnosis="Cambio de piñón bajo garantía",
        general_observations=None,
        technician_id=None,
        acknowledge_duplicate=False,
    )
    data.update(overrides)
    return HistoricalOrderCreate(**data)


async def _run(payload, monkeypatch, **session_kwargs):
    monkeypatch.setattr(
        svc, "generate_and_upload_reception_pdf", AsyncMock(return_value="http://pdf.example/a.pdf")
    )
    fake_db = FakeHistoricalOrderSession(tenant=make_tenant(tenant_id=payload.tenant_id), **session_kwargs)
    order = await svc.create_historical_order(fake_db, payload, make_superadmin())
    return order, fake_db


class TestRecepcionEventIsAlwaysHistorical:
    async def test_recepcion_event_date_equals_created_at_not_utcnow(self, monkeypatch):
        payload = _payload(
            service_type=ServiceType.regular, status=ServiceStatus.received,
            completed_at=None, delivered_at=None, diagnosis=None,
        )
        order, fake_db = await _run(payload, monkeypatch)

        recepcion_events = [
            e for e in fake_db.added
            if e.__class__.__name__ == "VehicleLifecycleEvent" and e.event_type == LifecycleEventType.RECEPCION
        ]
        assert len(recepcion_events) == 1
        event = recepcion_events[0]
        assert event.event_date == datetime(2025, 1, 10, 9, 0)
        assert event.event_date != datetime.utcnow().replace(microsecond=0)
        assert event.is_automatic == "manual"

    async def test_recepcion_summary_survives_resync_regex(self, monkeypatch):
        payload = _payload(
            service_type=ServiceType.regular, status=ServiceStatus.received,
            completed_at=None, delivered_at=None, diagnosis=None, mileage_km=Decimal("3200"),
        )
        order, fake_db = await _run(payload, monkeypatch)

        event = next(
            e for e in fake_db.added
            if e.__class__.__name__ == "VehicleLifecycleEvent" and e.event_type == LifecycleEventType.RECEPCION
        )
        assert re.search(r"KM:\s*\d+(?:\.\d+)?", event.summary)
        resynced = _resync_recepcion_summary(event.summary, 9999)
        assert resynced == "Recepción en taller. KM: 9999. Cliente: Juan Perez."


class TestGarantiaEventDatedAtCompletedAt:
    async def test_garantia_event_date_equals_completed_at(self, monkeypatch):
        payload = _payload(service_type=ServiceType.warranty, status=ServiceStatus.completed)
        order, fake_db = await _run(payload, monkeypatch)

        events = [e for e in fake_db.added if e.__class__.__name__ == "VehicleLifecycleEvent"]
        garantia = next(e for e in events if e.event_type == LifecycleEventType.GARANTIA)
        assert garantia.event_date == datetime(2025, 1, 12, 17, 0)
        assert garantia.event_date != payload.created_at
        assert garantia.is_automatic == "manual"

        # No MANTENIMIENTO event should exist alongside GARANTIA.
        assert not any(e.event_type == LifecycleEventType.MANTENIMIENTO for e in events)


class TestMantenimientoEventDatedAtCompletedAt:
    async def test_mantenimiento_event_date_equals_completed_at(self, monkeypatch):
        payload = _payload(
            service_type=ServiceType.km_review, status=ServiceStatus.completed,
            completed_at=datetime(2025, 2, 1, 10, 0),
        )
        order, fake_db = await _run(payload, monkeypatch)

        events = [e for e in fake_db.added if e.__class__.__name__ == "VehicleLifecycleEvent"]
        mantenimiento = next(e for e in events if e.event_type == LifecycleEventType.MANTENIMIENTO)
        assert mantenimiento.event_date == datetime(2025, 2, 1, 10, 0)
        assert mantenimiento.is_automatic == "manual"
        assert not any(e.event_type == LifecycleEventType.GARANTIA for e in events)


class TestEntregaEventDatedAtDeliveredAt:
    async def test_entrega_event_date_equals_delivered_at_not_completed_at(self, monkeypatch):
        payload = _payload(
            service_type=ServiceType.warranty, status=ServiceStatus.delivered,
            completed_at=datetime(2025, 1, 12, 17, 0), delivered_at=datetime(2025, 1, 14, 11, 30),
        )
        order, fake_db = await _run(payload, monkeypatch)

        events = [e for e in fake_db.added if e.__class__.__name__ == "VehicleLifecycleEvent"]
        entrega = next(e for e in events if e.event_type == LifecycleEventType.ENTREGA)
        assert entrega.event_date == datetime(2025, 1, 14, 11, 30)
        assert entrega.event_date != payload.completed_at
        assert entrega.is_automatic == "manual"

        # Full chain present: RECEPCION + GARANTIA + ENTREGA, all historical.
        by_type = {e.event_type: e.event_date for e in events}
        assert by_type[LifecycleEventType.RECEPCION] == payload.created_at
        assert by_type[LifecycleEventType.GARANTIA] == payload.completed_at
        assert by_type[LifecycleEventType.ENTREGA] == payload.delivered_at
