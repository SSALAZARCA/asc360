"""
tests/historical_orders/test_auth.py — Phase 1 role-guard for
`POST /superadmin/data/historical-orders`.

Mirrors `tests/superadmin_data/test_role_guard_regression.py`: a
non-superadmin caller gets 403 before the DB is ever touched, and a request
with no `Authorization` header at all gets 401 from the real
`get_current_user` dependency (the SAME one the frontend's `authFetch`
feeds — never the Sonia secret, never `get_optional_user`; design failure
mode #2). A superadmin caller clears the guard and reaches the Phase 1
stub, which returns 501 (the real service is wired in PR2).
"""
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user

from tests.historical_orders.conftest import (
    make_superadmin,
    make_jefe_taller,
    NoTouchSession,
    VALID_HISTORICAL_ORDER_PAYLOAD,
)


def _override_db_only():
    async def _get_db():
        yield NoTouchSession()
    app.dependency_overrides[get_db] = _get_db


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_superadmin_reaches_the_stub():
    _override_db_only()

    async def _get_current_user():
        return make_superadmin()
    app.dependency_overrides[get_current_user] = _get_current_user

    try:
        with TestClient(app) as client:
            res = client.post(
                "/api/v1/superadmin/data/historical-orders",
                json=VALID_HISTORICAL_ORDER_PAYLOAD,
            )
        assert res.status_code == 501
    finally:
        _teardown()


def test_jefe_taller_is_rejected_with_no_db_touch():
    _override_db_only()

    async def _get_current_user():
        return make_jefe_taller()
    app.dependency_overrides[get_current_user] = _get_current_user

    try:
        with TestClient(app) as client:
            res = client.post(
                "/api/v1/superadmin/data/historical-orders",
                json=VALID_HISTORICAL_ORDER_PAYLOAD,
            )
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
        with TestClient(app) as client:
            res = client.post(
                "/api/v1/superadmin/data/historical-orders",
                json=VALID_HISTORICAL_ORDER_PAYLOAD,
            )
        assert res.status_code == 401
    finally:
        _teardown()
