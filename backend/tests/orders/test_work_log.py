"""
Tests for `POST /orders/{order_id}/work-log` and
`POST /orders/{order_id}/work-log/photos`.

Background: `add_work_log`'s only caller in the whole repo is the bot's
`post_work_log` (telegram-bot/bot/services/api.py), which never sends a
JWT — only Sonia's shared secret exists on that side. The endpoint
previously required `get_current_user` (JWT), so every diagnosis a
technician gave Sonia silently failed with 401 even though the bot
sometimes told the technician it was saved. Both endpoints now use the
same bot-only `verify_sonia_secret` pattern as `resolve_order_by_plate`/
`claim_order`.
"""
from unittest.mock import AsyncMock, patch

from app.config import settings

from tests.conftest import make_test_client
from tests.orders.conftest import FakeWorkLogSession, make_active_order


def test_add_work_log_requires_sonia_secret():
    order = make_active_order()
    fake_db = FakeWorkLogSession(order=order)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.post(
            f"/api/v1/orders/{order.id}/work-log",
            json={"diagnosis": "Freno trasero gastado"},
        )

    assert resp.status_code == 401
    assert fake_db.added == []


def test_add_work_log_saves_diagnosis_with_sonia_secret():
    order = make_active_order()
    fake_db = FakeWorkLogSession(order=order)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.post(
            f"/api/v1/orders/{order.id}/work-log",
            json={"diagnosis": "Freno trasero gastado", "recorded_by_telegram_id": "123"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["diagnosis"] == "Freno trasero gastado"
    assert fake_db.committed is True
    work_logs = [obj for obj in fake_db.added if type(obj).__name__ == "OrderWorkLog"]
    assert len(work_logs) == 1
    assert work_logs[0].diagnosis == "Freno trasero gastado"
    assert work_logs[0].recorded_by_telegram_id == "123"


def test_add_work_log_404_when_order_missing():
    fake_db = FakeWorkLogSession(order=None)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        import uuid
        resp = client.post(
            f"/api/v1/orders/{uuid.uuid4()}/work-log",
            json={"diagnosis": "Freno trasero gastado"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 404
    assert fake_db.added == []


def test_add_work_log_photos_requires_sonia_secret():
    order = make_active_order()
    fake_db = FakeWorkLogSession(order=order)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.post(
            f"/api/v1/orders/{order.id}/work-log/photos",
            files=[("files", ("foto.jpg", b"fake-bytes", "image/jpeg"))],
            data={"diagnosis": "Así quedó el carburador"},
        )

    assert resp.status_code == 401
    assert fake_db.added == []


def test_add_work_log_photos_uploads_and_saves_media_urls():
    order = make_active_order()
    fake_db = FakeWorkLogSession(order=order)

    with patch(
        "app.api.v1.orders.upload_file_to_minio",
        new=AsyncMock(return_value="https://minio.local/foto.jpg"),
    ):
        with make_test_client(current_user=None, fake_db_session=fake_db) as client:
            resp = client.post(
                f"/api/v1/orders/{order.id}/work-log/photos",
                files=[("files", ("foto.jpg", b"fake-bytes", "image/jpeg"))],
                data={"diagnosis": "Así quedó el carburador", "recorded_by_telegram_id": "999"},
                headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["media_urls"] == ["https://minio.local/foto.jpg"]
    assert body["diagnosis"] == "Así quedó el carburador"
    work_logs = [obj for obj in fake_db.added if type(obj).__name__ == "OrderWorkLog"]
    assert len(work_logs) == 1
    assert work_logs[0].media_urls == ["https://minio.local/foto.jpg"]
    assert work_logs[0].recorded_by_telegram_id == "999"


def test_add_work_log_photos_falls_back_to_default_diagnosis_when_caption_empty():
    order = make_active_order()
    fake_db = FakeWorkLogSession(order=order)

    with patch(
        "app.api.v1.orders.upload_file_to_minio",
        new=AsyncMock(return_value="https://minio.local/foto.jpg"),
    ):
        with make_test_client(current_user=None, fake_db_session=fake_db) as client:
            resp = client.post(
                f"/api/v1/orders/{order.id}/work-log/photos",
                files=[("files", ("foto.jpg", b"fake-bytes", "image/jpeg"))],
                data={"diagnosis": ""},
                headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
            )

    assert resp.status_code == 201
    assert resp.json()["diagnosis"] == "Evidencia fotográfica"


def test_add_work_log_photos_rejects_disallowed_mime_type():
    order = make_active_order()
    fake_db = FakeWorkLogSession(order=order)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.post(
            f"/api/v1/orders/{order.id}/work-log/photos",
            files=[("files", ("nota.pdf", b"fake-bytes", "application/pdf"))],
            data={"diagnosis": "Algo"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 422
    assert fake_db.added == []


def test_add_work_log_photos_rejects_oversized_file():
    order = make_active_order()
    fake_db = FakeWorkLogSession(order=order)
    oversized = b"x" * (10 * 1024 * 1024 + 1)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.post(
            f"/api/v1/orders/{order.id}/work-log/photos",
            files=[("files", ("foto.jpg", oversized, "image/jpeg"))],
            data={"diagnosis": "Algo"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 413
    assert fake_db.added == []
