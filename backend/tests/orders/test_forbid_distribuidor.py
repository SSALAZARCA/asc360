"""
tests/orders/test_forbid_distribuidor.py -- backend gap-close: the frontend
already restricts `parts_dealer` (Distribuidor) to only `/distribuidor/
entrega`, hiding Kanban/Gestión de Órdenes from the UI -- but the backend
endpoints those screens call had NO role check at all (only "is someone
logged in"). A Distribuidor's valid JWT could still hit these endpoints
directly (curl/Postman), bypassing the UI entirely.

`forbid_distribuidor` is the INVERSE of `app/api/v1/distributor_deliveries.
py`'s `require_distribuidor` guard -- same public-function, called-as-first-
line-in-the-body shape, just blocking the role instead of requiring it.

Covers every endpoint actually guarded (see `orders.py` for the ones
deliberately left alone -- bot-only or already role-restricted):
  - `POST /` (create_service_order)
  - `PUT /{order_id}/status` (update_order_status)
  - `GET /{order_id}/detail` (get_order_detail)
  - `POST /{order_id}/parts` (add_order_parts)
  - `GET /analytics/services` (get_services_analytics)
  - `POST /{order_id}/otp/send` (send_otp)
  - `POST /{order_id}/otp/verify` (verify_otp)
  - `POST /{order_id}/otp/resend` (resend_otp)

For each: a `parts_dealer` caller gets 403 with the DB never touched (proves
the guard runs before any query), and a non-Distribuidor caller (JWT or,
where applicable, Sonia's `X-Sonia-Secret` bot path) is completely
unaffected -- reaches the endpoint's OWN pre-existing logic (proven via a
DB fake that returns "not found", so the endpoint's normal 404 fires --
NOT the new 403 -- confirming the guard let it straight through).

All endpoints here are called directly as plain async functions (NOT
through `TestClient`), matching the established convention in
`test_order_creation_conflict_guard.py`/`test_create_order_otp_toggle.py`
for the `Optional[CurrentUser]` + bot-secret endpoints, and extended here
to the plain `CurrentUser`-only endpoints too, so every guarded endpoint in
this file uses one consistent test shape.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1 import orders as orders_module
from app.api.deps import CurrentUser
from app.models.order import ServiceStatus
from app.schemas.order import OrderStatusUpdate as OrderStatusUpdateSchema, PartCreate

from tests.orders.test_create_order_otp_toggle import (
    FakeCreateOrderSession,
    _fake_pdf,
    _order_payload,
    vehicle_and_tenant,
)


def make_current_user(role: str, tenant_id=None) -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()), role=role,
        tenant_id=str(tenant_id) if tenant_id else None, name="T",
    )


class NoTouchSession:
    """Fake DB session that fails the test if the route touches it at all --
    proves `forbid_distribuidor` short-circuits BEFORE any query. Mirrors
    `tests/distributor_deliveries/conftest.py`'s `NoTouchSession`."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("endpoint touched db.execute() before forbid_distribuidor short-circuited")

    async def get(self, *args, **kwargs):
        raise AssertionError("endpoint touched db.get() before forbid_distribuidor short-circuited")

    def add(self, *args, **kwargs):
        raise AssertionError("endpoint touched db.add() before forbid_distribuidor short-circuited")

    async def commit(self):
        raise AssertionError("endpoint touched db.commit() before forbid_distribuidor short-circuited")


class _EmptyResult:
    """Fakes every result-reading method these endpoints use
    (`.scalar_one_or_none()`, `.all()`, `.scalars().all()`) as "nothing
    found" -- enough to let a non-Distribuidor caller pass the guard and
    reach the endpoint's OWN pre-existing "not found"/empty-list behavior,
    proving the guard doesn't change their outcome."""

    def scalar_one_or_none(self):
        return None

    def all(self):
        return []

    def scalars(self):
        return self


class OrderNotFoundSession:
    """Minimal fake DB session: any `.execute()` returns "nothing found".
    No writes are legitimate on this path (every guarded endpoint below
    bails out on a 404/empty-list before ever calling `.add()`/`.commit()`)."""

    def __init__(self):
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _EmptyResult()


DISTRIBUIDOR = make_current_user("parts_dealer")


# ---------------------------------------------------------------------------
# GET /{order_id}/detail -- get_order_detail
# ---------------------------------------------------------------------------

async def test_get_order_detail_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.get_order_detail(
            order_id=uuid.uuid4(), db=NoTouchSession(), current_user=DISTRIBUIDOR
        )
    assert exc_info.value.status_code == 403


async def test_get_order_detail_other_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.get_order_detail(
            order_id=uuid.uuid4(),
            db=OrderNotFoundSession(),
            current_user=make_current_user("technician"),
        )
    assert exc_info.value.status_code == 404  # endpoint's own "not found", not the new 403


# ---------------------------------------------------------------------------
# POST /{order_id}/parts -- add_order_parts
# ---------------------------------------------------------------------------

async def test_add_order_parts_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.add_order_parts(
            order_id=uuid.uuid4(),
            parts_in=[PartCreate(reference="R1")],
            db=NoTouchSession(),
            current_user=DISTRIBUIDOR,
        )
    assert exc_info.value.status_code == 403


async def test_add_order_parts_other_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.add_order_parts(
            order_id=uuid.uuid4(),
            parts_in=[PartCreate(reference="R1")],
            db=OrderNotFoundSession(),
            current_user=make_current_user("superadmin"),
        )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# GET /analytics/services -- get_services_analytics
# ---------------------------------------------------------------------------

async def test_get_services_analytics_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.get_services_analytics(
            service_type=None, city=None, db=NoTouchSession(), current_user=DISTRIBUIDOR
        )
    assert exc_info.value.status_code == 403


async def test_get_services_analytics_other_roles_unaffected():
    result = await orders_module.get_services_analytics(
        service_type=None,
        city=None,
        db=OrderNotFoundSession(),
        current_user=make_current_user("jefe_taller", tenant_id=uuid.uuid4()),
    )
    assert result == []  # normal empty-result response, not a 403


# ---------------------------------------------------------------------------
# GET /analytics/kpis -- get_kpi_analytics (sibling of /analytics/services,
# same "management dashboard" data class -- missed in the first guard pass,
# caught by a second review-risk pass)
# ---------------------------------------------------------------------------

async def test_get_kpi_analytics_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.get_kpi_analytics(db=NoTouchSession(), current_user=DISTRIBUIDOR)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# POST /{order_id}/otp/send -- send_otp
# ---------------------------------------------------------------------------

async def test_send_otp_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.send_otp(
            order_id=uuid.uuid4(), db=NoTouchSession(), current_user=DISTRIBUIDOR
        )
    assert exc_info.value.status_code == 403


async def test_send_otp_other_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.send_otp(
            order_id=uuid.uuid4(),
            db=OrderNotFoundSession(),
            current_user=make_current_user("technician"),
        )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST / -- create_service_order (Optional[CurrentUser] + bot-secret branch)
# ---------------------------------------------------------------------------

async def test_create_service_order_blocks_distribuidor_before_any_query(vehicle_and_tenant):
    vehicle, tenant = vehicle_and_tenant
    order_in = _order_payload(vehicle.id, tenant.id)

    with pytest.raises(HTTPException) as exc_info:
        await orders_module.create_service_order(
            order_in, db=NoTouchSession(), x_sonia_secret=None, current_user=DISTRIBUIDOR
        )
    assert exc_info.value.status_code == 403


async def test_create_service_order_other_jwt_roles_unaffected(monkeypatch, vehicle_and_tenant):
    vehicle, tenant = vehicle_and_tenant
    monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

    session = FakeCreateOrderSession("true", vehicle, tenant, claim_row=None)
    order_in = _order_payload(vehicle.id, tenant.id)

    # No bot secret -- pure JWT path, non-Distribuidor role.
    await orders_module.create_service_order(
        order_in, db=session, x_sonia_secret=None, current_user=make_current_user("jefe_taller")
    )

    assert session.commits >= 1  # order was actually created, exactly as before


async def test_create_service_order_sonia_bot_path_untouched(monkeypatch, vehicle_and_tenant):
    vehicle, tenant = vehicle_and_tenant
    monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

    session = FakeCreateOrderSession("true", vehicle, tenant, claim_row=None)
    order_in = _order_payload(vehicle.id, tenant.id)

    # Sonia's real path: current_user is None, x_sonia_secret is the real secret.
    await orders_module.create_service_order(
        order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
    )

    assert session.commits >= 1


# ---------------------------------------------------------------------------
# PUT /{order_id}/status -- update_order_status (Optional[CurrentUser] + bot)
# ---------------------------------------------------------------------------

def _status_update() -> OrderStatusUpdateSchema:
    return OrderStatusUpdateSchema(status=ServiceStatus.completed)


async def test_update_order_status_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.update_order_status(
            order_id=uuid.uuid4(),
            status_update=_status_update(),
            db=NoTouchSession(),
            current_user=DISTRIBUIDOR,
            x_sonia_secret=None,
        )
    assert exc_info.value.status_code == 403


async def test_update_order_status_other_jwt_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.update_order_status(
            order_id=uuid.uuid4(),
            status_update=_status_update(),
            db=OrderNotFoundSession(),
            current_user=make_current_user("superadmin"),
            x_sonia_secret=None,
        )
    assert exc_info.value.status_code == 404


async def test_update_order_status_sonia_bot_path_untouched():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.update_order_status(
            order_id=uuid.uuid4(),
            status_update=_status_update(),
            db=OrderNotFoundSession(),
            current_user=None,
            x_sonia_secret="test-bot-secret",
        )
    assert exc_info.value.status_code == 404  # order-not-found, never the 403 guard


# ---------------------------------------------------------------------------
# POST /{order_id}/otp/verify -- verify_otp (Optional[CurrentUser] + bot)
# ---------------------------------------------------------------------------

async def test_verify_otp_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.verify_otp(
            order_id=uuid.uuid4(),
            body={"code": "123456"},
            db=NoTouchSession(),
            current_user=DISTRIBUIDOR,
            x_sonia_secret=None,
        )
    assert exc_info.value.status_code == 403


async def test_verify_otp_other_jwt_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.verify_otp(
            order_id=uuid.uuid4(),
            body={"code": "123456"},
            db=OrderNotFoundSession(),
            current_user=make_current_user("jefe_taller"),
            x_sonia_secret=None,
        )
    assert exc_info.value.status_code == 404


async def test_verify_otp_sonia_bot_path_untouched():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.verify_otp(
            order_id=uuid.uuid4(),
            body={"code": "123456"},
            db=OrderNotFoundSession(),
            current_user=None,
            x_sonia_secret="test-bot-secret",
        )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /{order_id}/otp/resend -- resend_otp (Optional[CurrentUser] + bot)
# ---------------------------------------------------------------------------

async def test_resend_otp_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.resend_otp(
            order_id=uuid.uuid4(), db=NoTouchSession(), current_user=DISTRIBUIDOR, x_sonia_secret=None
        )
    assert exc_info.value.status_code == 403


async def test_resend_otp_other_jwt_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.resend_otp(
            order_id=uuid.uuid4(),
            db=OrderNotFoundSession(),
            current_user=make_current_user("superadmin"),
            x_sonia_secret=None,
        )
    assert exc_info.value.status_code == 404


async def test_resend_otp_sonia_bot_path_untouched():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.resend_otp(
            order_id=uuid.uuid4(), db=OrderNotFoundSession(), current_user=None, x_sonia_secret="test-bot-secret"
        )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# GET /{order_id}/exit-pdf -- download_exit_order_pdf (Optional[CurrentUser] + bot)
# ---------------------------------------------------------------------------

async def test_download_exit_order_pdf_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.download_exit_order_pdf(
            order_id=uuid.uuid4(), db=NoTouchSession(), current_user=DISTRIBUIDOR, x_sonia_secret=None
        )
    assert exc_info.value.status_code == 403


async def test_download_exit_order_pdf_other_jwt_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.download_exit_order_pdf(
            order_id=uuid.uuid4(),
            db=OrderNotFoundSession(),
            current_user=make_current_user("technician"),
            x_sonia_secret=None,
        )
    assert exc_info.value.status_code == 404  # endpoint's own "not found", not the new 403


async def test_download_exit_order_pdf_sonia_bot_path_untouched():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.download_exit_order_pdf(
            order_id=uuid.uuid4(), db=OrderNotFoundSession(), current_user=None, x_sonia_secret="test-bot-secret"
        )
    assert exc_info.value.status_code == 404  # order-not-found, never the 403 guard


# ---------------------------------------------------------------------------
# GET /{order_id}/pdf -- download_reception_pdf (plain CurrentUser, no bot path)
# ---------------------------------------------------------------------------

async def test_download_reception_pdf_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.download_reception_pdf(
            order_id=uuid.uuid4(), db=NoTouchSession(), current_user=DISTRIBUIDOR
        )
    assert exc_info.value.status_code == 403


async def test_download_reception_pdf_other_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.download_reception_pdf(
            order_id=uuid.uuid4(), db=OrderNotFoundSession(), current_user=make_current_user("technician")
        )
    assert exc_info.value.status_code == 404  # endpoint's own "not found", not the new 403


# ---------------------------------------------------------------------------
# GET /pending-otp -- get_pending_otp_orders (Optional[CurrentUser] + bot)
# ---------------------------------------------------------------------------

async def test_get_pending_otp_orders_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.get_pending_otp_orders(
            db=NoTouchSession(), current_user=DISTRIBUIDOR, x_sonia_secret=None
        )
    assert exc_info.value.status_code == 403


async def test_get_pending_otp_orders_other_jwt_roles_unaffected():
    result = await orders_module.get_pending_otp_orders(
        db=OrderNotFoundSession(), current_user=make_current_user("jefe_taller", tenant_id=uuid.uuid4()),
        x_sonia_secret=None,
    )
    assert result == []  # normal empty-result response, not a 403


async def test_get_pending_otp_orders_sonia_bot_path_untouched():
    result = await orders_module.get_pending_otp_orders(
        db=OrderNotFoundSession(), current_user=None, x_sonia_secret="test-bot-secret"
    )
    assert result == []  # bot path reaches the endpoint's own logic, never the 403 guard


# ---------------------------------------------------------------------------
# GET /pending-otp/plate/{plate} -- get_pending_otp_by_plate (Optional[CurrentUser] + bot)
# ---------------------------------------------------------------------------

async def test_get_pending_otp_by_plate_blocks_distribuidor_before_any_query():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.get_pending_otp_by_plate(
            plate="ABC12D", db=NoTouchSession(), current_user=DISTRIBUIDOR, x_sonia_secret=None
        )
    assert exc_info.value.status_code == 403


async def test_get_pending_otp_by_plate_other_jwt_roles_unaffected():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.get_pending_otp_by_plate(
            plate="ABC12D",
            db=OrderNotFoundSession(),
            current_user=make_current_user("technician"),
            x_sonia_secret=None,
        )
    assert exc_info.value.status_code == 404  # endpoint's own "not found", not the new 403


async def test_get_pending_otp_by_plate_sonia_bot_path_untouched():
    with pytest.raises(HTTPException) as exc_info:
        await orders_module.get_pending_otp_by_plate(
            plate="ABC12D", db=OrderNotFoundSession(), current_user=None, x_sonia_secret="test-bot-secret"
        )
    assert exc_info.value.status_code == 404  # order-not-found, never the 403 guard
