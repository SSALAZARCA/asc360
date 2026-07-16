"""
Tests for `GET /orders/resolve/plate` (dedicated plate-resolution endpoint
for the Sonia bot).

Motivation (see task background): voice transcription of a spoken plate is
unreliable (the same real plate "JEK15I" can arrive as "JKL15I", "JKE15I",
"KJEK15I"), and the existing `get_active_orders_for_tenant`/
`get_active_order_by_plate` exclusion list (`[completed, delivered,
cancelled]`) makes a `completed` order unfindable — but `delivered` must be
settable AFTER `completed`, so a technician can never say "ya se la
entregué" for a `completed` order today. This endpoint is a SEPARATE,
dedicated lookup that:
  - excludes ONLY `[delivered, cancelled]` (completed orders ARE findable —
    this is the whole point of the fix), and
  - falls back to `difflib`-ranked candidates when there is no exact plate
    match, so Sonia can offer a technician a short list of "did you mean"
    options instead of a bare 404.

Does NOT touch `get_active_orders_for_tenant`/`get_active_order_by_plate`
or the button-driven "motos activas" menu — those keep excluding
`completed` intentionally and are out of scope here.
"""
import uuid
from datetime import datetime, timedelta

from app.config import settings
from app.models.order import ServiceStatus

from tests.conftest import make_test_client
from tests.orders.conftest import FakeResolvePlateSession, make_active_order


def test_exact_match_found_any_tenant():
    order = make_active_order(plate="JEK15I")
    fake_db = FakeResolvePlateSession(exact_match=order)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "JEK15I"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match"] is not None
    assert body["match"]["plate"] == "JEK15I"
    assert body["match"]["id"] == str(order.id)
    assert body["candidates"] == []


def test_exact_match_found_tenant_scoped():
    tenant_id = uuid.uuid4()
    order = make_active_order(tenant_id=tenant_id, plate="NOI82G")
    fake_db = FakeResolvePlateSession(exact_match=order)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "NOI82G", "tenant_id": str(tenant_id)},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match"]["tenant_id"] == str(tenant_id)
    assert body["candidates"] == []

    # Locks in that the tenant filter actually reaches the exact-match
    # query when tenant_id is provided.
    sql = str(fake_db.executed_statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "service_orders.tenant_id = " in sql
    assert tenant_id.hex in sql.replace("-", "")


def test_completed_status_order_is_found_via_exact_match():
    """
    Regression test for the bug motivating this feature: a `completed`
    order MUST be findable by exact plate match so it can subsequently be
    marked `delivered`. This is the most important test in this file.
    """
    order = make_active_order(status=ServiceStatus.completed, plate="JEK15I")
    fake_db = FakeResolvePlateSession(exact_match=order)

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "JEK15I"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match"] is not None
    assert body["match"]["status"] == "completed"


def test_query_excludes_only_delivered_and_cancelled_not_completed():
    """
    Locks in the exclusion list: exactly `[delivered, cancelled]`, via the
    compiled SQL with literal binds — `completed` must NOT appear among the
    excluded values (mirrors `test_active_order_by_plate.py`'s WHERE-clause
    coverage style, but also asserts on the literal excluded values since
    the whole point here is that the exclusion set differs from the
    existing endpoints').
    """
    fake_db = FakeResolvePlateSession(exact_match=None, pool=[])

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "ABC12D"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert len(fake_db.executed_statements) == 2
    for stmt in fake_db.executed_statements:
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "NOT IN" in sql
        assert "'delivered'" in sql
        assert "'cancelled'" in sql
        assert "'completed'" not in sql


def test_delivered_and_cancelled_are_not_suggested_as_candidates():
    """
    Since the fake pool is exactly what production's SQL WHERE clause would
    have already filtered down to, a delivered/cancelled order never
    appearing in `pool` here mirrors the real, DB-enforced exclusion (see
    the WHERE-clause-level lock-in test above). This test exercises that a
    pool free of delivered/cancelled orders never surfaces one as a
    candidate — i.e. the ranking step does not need to (and does not)
    re-introduce excluded statuses.
    """
    similar_but_excluded_from_pool = make_active_order(
        status=ServiceStatus.delivered, plate="JEK15I"
    )
    # Pool passed to the fake represents what the DB would return AFTER
    # excluding delivered/cancelled — so the excluded order is deliberately
    # absent here, only a completed one (still eligible) is present.
    still_eligible = make_active_order(status=ServiceStatus.completed, plate="KJEK15I")
    fake_db = FakeResolvePlateSession(exact_match=None, pool=[still_eligible])

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "JEK15I"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match"] is None
    plates = [c["plate"] for c in body["candidates"]]
    assert "JEK15I" not in plates  # the delivered order never entered the pool
    assert "KJEK15I" in plates
    # sanity: the object we built but never fed into the pool stays unused
    assert similar_but_excluded_from_pool.status == ServiceStatus.delivered


def test_no_exact_match_returns_ranked_candidates_best_first():
    now = datetime.utcnow()
    best = make_active_order(plate="KJEK15I", created_at=now)  # ratio ~0.923
    second = make_active_order(plate="JKL15I", created_at=now - timedelta(days=1))  # ratio ~0.833
    too_different = make_active_order(plate="ZZZ999Q", created_at=now)  # ratio 0.0, filtered out

    fake_db = FakeResolvePlateSession(
        exact_match=None,
        pool=[second, too_different, best],  # deliberately not pre-sorted
    )

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "JEK15I"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match"] is None
    plates = [c["plate"] for c in body["candidates"]]
    assert plates == ["KJEK15I", "JKL15I"]  # best ratio first, too-different dropped


def test_candidate_ratio_ties_broken_by_created_at_descending():
    now = datetime.utcnow()
    # All three share the same ~0.8333 ratio against target "JEK15I".
    newest = make_active_order(plate="JKE15I", created_at=now)
    middle = make_active_order(plate="JKL15I", created_at=now - timedelta(hours=1))
    oldest = make_active_order(plate="JEK15A", created_at=now - timedelta(hours=2))

    fake_db = FakeResolvePlateSession(
        exact_match=None,
        pool=[middle, oldest, newest],
    )

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "JEK15I"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    body = resp.json()
    plates = [c["plate"] for c in body["candidates"]]
    assert plates == ["JKE15I", "JKL15I", "JEK15A"]


def test_candidate_pool_query_is_tenant_scoped():
    """
    Regression test: `test_exact_match_found_tenant_scoped` only locks in the
    tenant filter on the exact-match query (`executed_statements[0]`). The
    candidate-pool query (`executed_statements[1]`) must independently apply
    the same `tenant_id` filter — otherwise a tenant-scoped technician could
    be shown another tenant's orders as "did you mean" candidates.
    """
    tenant_id = uuid.uuid4()
    similar = make_active_order(tenant_id=tenant_id, plate="KJEK15I")
    fake_db = FakeResolvePlateSession(exact_match=None, pool=[similar])

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "JEK15I", "tenant_id": str(tenant_id)},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match"] is None
    assert [c["plate"] for c in body["candidates"]] == ["KJEK15I"]

    assert len(fake_db.executed_statements) == 2
    pool_sql = str(
        fake_db.executed_statements[1].compile(compile_kwargs={"literal_binds": True})
    )
    assert "service_orders.tenant_id = " in pool_sql
    assert tenant_id.hex in pool_sql.replace("-", "")


def test_no_exact_match_and_nothing_similar_returns_empty_candidates():
    unrelated = make_active_order(plate="ZZZ999Q")
    fake_db = FakeResolvePlateSession(exact_match=None, pool=[unrelated])

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "JEK15I"},
            headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match"] is None
    assert body["candidates"] == []


def test_missing_sonia_secret_returns_401():
    fake_db = FakeResolvePlateSession(exact_match=None, pool=[])

    with make_test_client(current_user=None, fake_db_session=fake_db) as client:
        resp = client.get(
            "/api/v1/orders/resolve/plate",
            params={"plate": "ABC12D"},
        )

    assert resp.status_code == 401
    assert fake_db.executed_statements == []
