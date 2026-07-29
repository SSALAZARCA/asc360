"""
tests/distributor_deliveries/test_act_photo.py — Phase 4, task 4.5.
RED tests for `POST /distributor/deliveries/{vehicle_id}/act-photo`, the
retry/replace path kept alongside the inline create-time photo field
(Design ADR 6/18).
"""
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    make_delivery_vehicle,
    make_distribuidor,
)


def _override(fake_db, actor):
    async def _get_db():
        yield fake_db
    app.dependency_overrides[get_db] = _get_db

    async def _get_current_user():
        return actor
    app.dependency_overrides[get_current_user] = _get_current_user


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_act_photo_retry_uploads_and_persists_url():
    vehicle = make_delivery_vehicle()
    fake_db = FakeDeliverySession(vehicles=[vehicle])
    _override(fake_db, make_distribuidor())

    try:
        with patch(
            "app.services.distributor_delivery_service.upload_file_to_minio",
            new=AsyncMock(return_value="https://minio.local/acta-retry.jpg"),
        ):
            with TestClient(app) as client:
                res = client.post(
                    f"/api/v1/distributor/deliveries/{vehicle.id}/act-photo",
                    files={"photo": ("acta.jpg", b"fake-bytes", "image/jpeg")},
                )
        assert res.status_code == 200
        assert vehicle.delivery_act_url == "https://minio.local/acta-retry.jpg"
        assert fake_db.committed is True
    finally:
        _teardown()


def test_unsupported_content_type_rejected_with_422():
    vehicle = make_delivery_vehicle()
    fake_db = FakeDeliverySession(vehicles=[vehicle])
    _override(fake_db, make_distribuidor())

    try:
        with TestClient(app) as client:
            res = client.post(
                f"/api/v1/distributor/deliveries/{vehicle.id}/act-photo",
                files={"photo": ("acta.txt", b"fake-bytes", "text/plain")},
            )
        assert res.status_code == 422
        assert vehicle.delivery_act_url is None
        assert fake_db.committed is False
    finally:
        _teardown()


def test_pdf_act_is_accepted():
    """The acta de entrega for a NEW motorcycle sale is a different business
    document than a workshop's damage-reception photos -- Distribuidor actas
    are commonly scanned/signed as PDF, so PDF must be accepted alongside
    images (user decision, 2026-07-29)."""
    vehicle = make_delivery_vehicle()
    fake_db = FakeDeliverySession(vehicles=[vehicle])
    _override(fake_db, make_distribuidor())

    try:
        with patch(
            "app.services.distributor_delivery_service.upload_file_to_minio",
            new=AsyncMock(return_value="https://minio.local/acta-retry.pdf"),
        ):
            with TestClient(app) as client:
                res = client.post(
                    f"/api/v1/distributor/deliveries/{vehicle.id}/act-photo",
                    files={"photo": ("acta.pdf", b"fake-bytes", "application/pdf")},
                )
        assert res.status_code == 200
        assert vehicle.delivery_act_url == "https://minio.local/acta-retry.pdf"
        assert fake_db.committed is True
    finally:
        _teardown()


def test_oversized_photo_rejected_with_413():
    vehicle = make_delivery_vehicle()
    fake_db = FakeDeliverySession(vehicles=[vehicle])
    _override(fake_db, make_distribuidor())

    oversized_bytes = b"0" * (10 * 1024 * 1024 + 1)
    try:
        with TestClient(app) as client:
            res = client.post(
                f"/api/v1/distributor/deliveries/{vehicle.id}/act-photo",
                files={"photo": ("acta.jpg", oversized_bytes, "image/jpeg")},
            )
        assert res.status_code == 413
        assert vehicle.delivery_act_url is None
        assert fake_db.committed is False
    finally:
        _teardown()


def test_unknown_vehicle_returns_404():
    fake_db = FakeDeliverySession(vehicles=[])
    _override(fake_db, make_distribuidor())

    try:
        with TestClient(app) as client:
            res = client.post(
                f"/api/v1/distributor/deliveries/{uuid.uuid4()}/act-photo",
                files={"photo": ("acta.jpg", b"fake-bytes", "image/jpeg")},
            )
        assert res.status_code == 404
    finally:
        _teardown()
