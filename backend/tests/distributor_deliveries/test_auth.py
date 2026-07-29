"""
tests/distributor_deliveries/test_auth.py — role-guard for
`POST /distributor/deliveries`.

Mirrors `tests/historical_orders/test_auth.py`'s post-PR2 shape: a caller
with neither `parts_dealer` nor `superadmin` gets 403 before the DB is ever
touched, and a request with no `Authorization` header at all gets 401 from
the real `get_current_user` dependency (the SAME one the frontend's
`authFetch` feeds — never the Sonia secret, never `get_optional_user`).
A `parts_dealer` OR `superadmin` caller clears the guard and reaches the
REAL transactional service (wired in Phase 4, replacing the Phase 3 501
stub) — 201.
"""
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    make_distribuidor,
    make_superadmin,
    make_jefe_taller,
    NoTouchSession,
    VALID_DELIVERY_PAYLOAD_JSON,
)


def _override_db_only():
    async def _get_db():
        yield NoTouchSession()
    app.dependency_overrides[get_db] = _get_db


def _override_db_with(fake_db):
    async def _get_db():
        yield fake_db
    app.dependency_overrides[get_db] = _get_db


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _post(files=None):
    with TestClient(app) as client:
        return client.post(
            "/api/v1/distributor/deliveries",
            data={"payload": VALID_DELIVERY_PAYLOAD_JSON},
            files=files,
        )


def test_distribuidor_reaches_the_real_service_and_gets_201(monkeypatch):
    # Distribuidor MUST always attach the photo (Design ADR 17/18) --
    # without one this would be a 422, not a 201, so the guard-clearing
    # assertion here needs a photo attached.
    monkeypatch.setattr(
        svc, "upload_file_to_minio", AsyncMock(return_value="https://minio.local/acta.jpg")
    )
    fake_db = FakeDeliverySession()
    _override_db_with(fake_db)

    async def _get_current_user():
        return make_distribuidor()
    app.dependency_overrides[get_current_user] = _get_current_user

    try:
        res = _post(files={"photo": ("acta.jpg", b"fake-bytes", "image/jpeg")})
        assert res.status_code == 201
        assert res.json()["plate"] == "ABC123"
    finally:
        _teardown()


def test_superadmin_reaches_the_real_service_and_gets_201():
    fake_db = FakeDeliverySession()
    _override_db_with(fake_db)

    async def _get_current_user():
        return make_superadmin()
    app.dependency_overrides[get_current_user] = _get_current_user

    try:
        res = _post()
        assert res.status_code == 201
        assert res.json()["plate"] == "ABC123"
    finally:
        _teardown()


def test_jefe_taller_is_rejected_with_no_db_touch():
    _override_db_only()

    async def _get_current_user():
        return make_jefe_taller()
    app.dependency_overrides[get_current_user] = _get_current_user

    try:
        res = _post()
        assert res.status_code == 403
    finally:
        _teardown()


def test_missing_authorization_header_returns_401():
    # `get_current_user` is deliberately NOT overridden here -- this proves
    # the route depends on the REAL JWT dependency (not a mock, not
    # `get_optional_user`), so a request with no header hits the real
    # credentials_exception path in `app/api/deps.py`.
    _override_db_only()

    try:
        res = _post()
        assert res.status_code == 401
    finally:
        _teardown()
