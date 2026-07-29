"""
tests/distributor_deliveries/test_photo_requirement.py — Phase 4, task 4.3.
RED tests for the role-conditional delivery-act photo requirement (Design
ADR 17/18): Distribuidor MUST always attach the photo; superadmin MAY omit
it (legacy-vehicle backfill).
"""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.schemas.distributor_delivery import DeliveryCreate
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    make_valid_photo,
    make_distribuidor,
    make_superadmin,
    VALID_DELIVERY_PAYLOAD,
)


def _payload(**overrides) -> DeliveryCreate:
    data = dict(VALID_DELIVERY_PAYLOAD)
    data.update(overrides)
    return DeliveryCreate(**data)


async def test_superadmin_without_photo_succeeds_with_null_delivery_act_url():
    fake_db = FakeDeliverySession()
    payload = _payload()

    vehicle = await svc.create_delivery(fake_db, payload, None, make_superadmin())

    assert vehicle.delivery_act_url is None
    assert fake_db.committed is True


async def test_distribuidor_without_photo_rejected_with_zero_writes():
    fake_db = FakeDeliverySession()
    payload = _payload()

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_delivery(fake_db, payload, None, make_distribuidor())

    assert exc_info.value.status_code == 422
    assert fake_db.added == []
    assert fake_db.committed is False


async def test_distribuidor_with_photo_succeeds(monkeypatch):
    monkeypatch.setattr(
        svc, "upload_file_to_minio", AsyncMock(return_value="https://minio.local/acta.jpg")
    )
    fake_db = FakeDeliverySession()
    payload = _payload()

    vehicle = await svc.create_delivery(fake_db, payload, make_valid_photo(), make_distribuidor())

    assert vehicle.delivery_act_url == "https://minio.local/acta.jpg"
    assert fake_db.committed is True
