"""
Tests for `GET /orders/active/plate/{plate}` (`sdd/order-claim-plate-atomic`,
PR2 Round 1 fix cycle — Judgment Day Issue 2): a superadmin's `tenant_id` is
`None` (see `User.tenant_id`'s "superadmins no tienen tenant" comment), so
the existing tenant-scoped `resolve_order_by_plate`/`active/tenant/{tenant_id}`
never finds a match for them. This endpoint searches by plate across ALL
tenants — safe because `Vehicle.plate` is globally `unique=True`.

Covers:
  - Match found -> 200 with the order's real `tenant_id` in the body.
  - No match -> 404.
  - Excluded statuses (completed/delivered/cancelled) are filtered via the
    query's WHERE clause (asserted on the compiled statement, same style as
    `tests/orders/test_claim_concurrency.py`'s WHERE-clause coverage test).
  - Missing `X-Sonia-Secret` -> 401, no DB query issued.
"""
import uuid

from app.config import settings

from tests.conftest import make_test_client
from tests.orders.conftest import FakeActivePlateSession, make_active_order


def test_match_found_returns_order_with_its_real_tenant_id():
    tenant_id = uuid.uuid4()
    order = make_active_order(tenant_id=tenant_id, plate="NOI82G")
    fake_db = FakeActivePlateSession(order=order)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/active/plate/NOI82G",
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == str(tenant_id)
    assert body["plate"] == "NOI82G"


def test_no_match_returns_404():
    fake_db = FakeActivePlateSession(order=None)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/active/plate/ZZZ99Z",
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 404


def test_query_excludes_completed_delivered_and_cancelled_via_where_clause():
    """
    Locks in the exclusion list regression target: the compiled SELECT must
    filter `ServiceOrder.status` with a `NOT IN` predicate (mirrors
    `get_active_orders_for_tenant`'s existing exclusion list), and must be
    ordered by `created_at DESC` with a `LIMIT` — so an older, already-closed
    order for the same plate never masks a newer active one.
    """
    fake_db = FakeActivePlateSession(order=None)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        client.get(
            "/api/v1/orders/active/plate/ABC12D",
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert len(fake_db.executed_statements) == 1
    sql = str(fake_db.executed_statements[0].compile())
    assert "service_orders.status" in sql
    assert "NOT IN" in sql
    assert "ORDER BY" in sql
    assert "service_orders.created_at DESC" in sql
    assert "LIMIT" in sql


def test_missing_sonia_secret_returns_401():
    fake_db = FakeActivePlateSession(order=None)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get("/api/v1/orders/active/plate/ABC12D")

    assert resp.status_code == 401
    assert fake_db.executed_statements == []
