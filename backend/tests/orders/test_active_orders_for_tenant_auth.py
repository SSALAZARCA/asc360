"""
tests/orders/test_active_orders_for_tenant_auth.py -- `GET
/orders/active/tenant/{tenant_id}` (function `get_active_orders_for_tenant`)
had NO authentication requirement at all -- not even "must be logged in" --
despite its own docstring claiming it's "Para rol Admin".

A first fix pass made this endpoint require a real JWT (`get_current_user`).
That broke a LIVE feature: Sonia's Telegram bot calls this exact endpoint
(`telegram-bot/bot/services/api.py`'s `get_tenant_active_orders`) with NO
`Authorization` header at all, wired to the "Órdenes Activas" command for
`jefe_taller` (see `telegram-bot/bot/handlers/technician.py` and
`telegram-bot/bot/handlers/general.py`). Requiring a JWT made every one of
those calls 401.

It ALSO left a cross-tenant IDOR open: the query filtered strictly by the
path's `tenant_id` with no ownership check, so ANY authenticated JWT user
(any role, any tenant) could read ANY OTHER tenant's full active-orders board
just by guessing/knowing a UUID.

This closes BOTH gaps at once, following the exact dual-auth pattern already
used by sibling endpoints in this file (`get_pending_otp_orders`,
`download_exit_order_pdf`):
  - Accepts EITHER `X-Sonia-Secret` (bot, trusted infra, explicit tenant_id,
    no ownership check -- same trust model as `claim_order`/`add_work_log`)
    OR a JWT (`get_optional_user`), with a 401 if neither is present.
  - On the JWT path only: `forbid_distribuidor` (Distribuidor is blocked from
    this Kanban-equivalent data, same as the other 10 guarded endpoints in
    this file) AND a tenant-ownership check (`current_user.tenant_id !=
    tenant_id` -> 403), unless the caller is superadmin.

Mirrors `tests/vehicles/test_get_by_plate_client.py`'s HTTP-layer,
dependency-override convention for a dual-auth (`get_optional_user` +
`X-Sonia-Secret`) endpoint tested via `TestClient`.
"""
import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_optional_user, CurrentUser
from app.config import settings
from app.models.order import ServiceOrder, ServiceStatus, ServiceType
from app.models.vehicle import Vehicle

SONIA_SECRET = settings.SONIA_BOT_SECRET  # matches backend/conftest.py's env default


def make_current_user(role: str = "jefe_taller", tenant_id=None) -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()), role=role,
        tenant_id=str(tenant_id) if tenant_id else None, name="T",
    )


class NoTouchSession:
    """Fake DB session that fails the test if the route touches it at all --
    mirrors `tests/distributor_deliveries/conftest.py`'s `NoTouchSession`."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("route touched db.execute() before auth short-circuited")

    async def get(self, *args, **kwargs):
        raise AssertionError("route touched db.get() before auth short-circuited")


class _ScalarsAllResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class FakeActiveTenantSession:
    """Minimal fake for `GET /orders/active/tenant/{tenant_id}` -- a single
    `SELECT` read via `.scalars().all()`, no writes."""

    def __init__(self, orders):
        self._orders = orders
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _ScalarsAllResult(self._orders)


def _make_order(tenant_id, plate="ABC12D"):
    vehicle_id = uuid.uuid4()
    order = ServiceOrder(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        status=ServiceStatus.in_progress,
        service_type=ServiceType.regular,
        created_at=datetime.utcnow(),
    )
    order.vehicle = Vehicle(id=vehicle_id, plate=plate, brand="UM", model="TEST")
    order.reception = None
    order.work_logs = []
    order.parts = []
    return order


def _override_db(fake_db):
    async def _get_db():
        yield fake_db
    app.dependency_overrides[get_db] = _get_db


def _override_user(current_user):
    async def _get_optional_user():
        return current_user
    app.dependency_overrides[get_optional_user] = _get_optional_user


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_optional_user, None)


def _get(tenant_id, headers=None):
    with TestClient(app) as client:
        return client.get(f"/api/v1/orders/active/tenant/{tenant_id}", headers=headers or {})


def test_missing_authorization_and_missing_sonia_secret_returns_401():
    # Neither a JWT (`get_optional_user` -> None) nor a valid bot secret --
    # must 401 before touching the DB.
    tenant_id = uuid.uuid4()
    _override_db(NoTouchSession())
    _override_user(None)

    try:
        resp = _get(tenant_id)
        assert resp.status_code == 401
    finally:
        _teardown()


def test_authenticated_own_tenant_returns_the_order_list():
    tenant_id = uuid.uuid4()
    order = _make_order(tenant_id)
    _override_db(FakeActiveTenantSession([order]))
    _override_user(make_current_user(role="technician", tenant_id=tenant_id))

    try:
        resp = _get(tenant_id)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["tenant_id"] == str(tenant_id)
    finally:
        _teardown()


def test_sonia_bot_secret_with_no_jwt_returns_data_not_401():
    """Proves the live-regression fix: Sonia's bot calls this endpoint with
    no Authorization header at all, only `X-Sonia-Secret`."""
    tenant_id = uuid.uuid4()
    order = _make_order(tenant_id)
    _override_db(FakeActiveTenantSession([order]))
    _override_user(None)  # no JWT, exactly like Sonia's real call

    try:
        resp = _get(tenant_id, headers={"x-sonia-secret": SONIA_SECRET})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["tenant_id"] == str(tenant_id)
    finally:
        _teardown()


def test_jwt_user_with_mismatched_tenant_id_gets_403_not_the_other_tenants_data():
    """Proves the IDOR is closed: an authenticated JWT user for tenant A
    cannot read tenant B's board just by putting B's UUID in the path."""
    own_tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    fake_db = FakeActiveTenantSession([_make_order(other_tenant_id)])
    _override_db(fake_db)
    _override_user(make_current_user(role="jefe_taller", tenant_id=own_tenant_id))

    try:
        resp = _get(other_tenant_id)
        assert resp.status_code == 403
        assert fake_db.executed_statements == []
    finally:
        _teardown()


def test_distribuidor_jwt_for_own_tenant_still_gets_403():
    """Proves Distribuidor is blocked even for their OWN tenant_id --
    `forbid_distribuidor` must fire regardless of tenant ownership."""
    tenant_id = uuid.uuid4()
    fake_db = FakeActiveTenantSession([_make_order(tenant_id)])
    _override_db(fake_db)
    _override_user(make_current_user(role="parts_dealer", tenant_id=tenant_id))

    try:
        resp = _get(tenant_id)
        assert resp.status_code == 403
        assert fake_db.executed_statements == []
    finally:
        _teardown()


def test_superadmin_can_read_any_tenant_id():
    superadmin_own_tenant = None  # superadmins have no tenant_id (see User.tenant_id)
    target_tenant_id = uuid.uuid4()
    order = _make_order(target_tenant_id)
    _override_db(FakeActiveTenantSession([order]))
    _override_user(make_current_user(role="superadmin", tenant_id=superadmin_own_tenant))

    try:
        resp = _get(target_tenant_id)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["tenant_id"] == str(target_tenant_id)
    finally:
        _teardown()
