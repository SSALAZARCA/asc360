"""
tests/distributor_deliveries/test_audit_log.py — Phase 4, task 4.7.
RED test for Requirement "Mandatory Audit Log Without PII": exactly one
`ImportAuditLog` row per delivery, action `DISTRIBUTOR_VEHICLE_DELIVERY`,
identifying the actor, with identification/birth_date/address absent from
the stored payload. Mirrors `tests/historical_orders/test_audit_log.py`.
"""
import json
import uuid
from unittest.mock import AsyncMock

from app.models.imports import ImportAuditLog
from app.schemas.distributor_delivery import DeliveryCreate
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    make_valid_photo,
    make_distribuidor,
    VALID_DELIVERY_PAYLOAD,
)


def _payload(**overrides) -> DeliveryCreate:
    data = dict(VALID_DELIVERY_PAYLOAD)
    data.update(overrides)
    return DeliveryCreate(**data)


async def test_exactly_one_audit_row_with_correct_action_and_actor(monkeypatch):
    monkeypatch.setattr(
        svc, "upload_file_to_minio", AsyncMock(return_value="https://minio.local/acta.jpg")
    )
    actor = make_distribuidor()
    fake_db = FakeDeliverySession()
    payload = _payload()

    vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), actor)

    audit_rows = [obj for obj in fake_db.added if isinstance(obj, ImportAuditLog)]
    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert row.action == "DISTRIBUTOR_VEHICLE_DELIVERY"
    assert row.entity_type == "Vehicle"
    assert row.entity_id == str(vehicle.id)
    assert row.actor_id == uuid.UUID(actor.user_id)
    assert row.actor_role == "parts_dealer"


async def test_payload_is_fully_json_serializable_and_has_no_pii(monkeypatch):
    monkeypatch.setattr(
        svc, "upload_file_to_minio", AsyncMock(return_value="https://minio.local/acta.jpg")
    )
    fake_db = FakeDeliverySession()
    payload = _payload()

    await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

    row = next(obj for obj in fake_db.added if isinstance(obj, ImportAuditLog))
    serialized = json.dumps(row.payload)  # must not raise
    assert "2026-07-28" in serialized
    assert "identification" not in row.payload
    assert "cedula" not in row.payload
    assert "birth_date" not in row.payload
    assert "address" not in row.payload
