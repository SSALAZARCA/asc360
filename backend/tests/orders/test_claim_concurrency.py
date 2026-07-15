"""
RED/GREEN tests for `POST /orders/{order_id}/claim` — the atomic anti-race
claim endpoint (`sdd/order-claim-plate-atomic`, PR 1: backend).

Two layers, mirroring `tests/remisiones/test_concurrency.py`:
  1. Unit — `classify_claim_outcome`: pure post-UPDATE classification logic,
     no DB, no HTTP. The real DB race guard is the atomic conditional
     `UPDATE ... WHERE id AND status='received' AND tenant_id=:t`
     (`rowcount`-checked, no pre-SELECT); this only tests what happens to
     the ALREADY-RESOLVED result.
  2. Integration (HTTP) — `POST /orders/{order_id}/claim` via
     `tests.conftest.make_test_client` + this module's rowcount-aware
     `tests.orders.conftest.FakeAsyncSession`, simulating a winning claim
     (rowcount=1) and a losing claim (rowcount=0) on the same order id, plus
     404 not_claimable and 403 cross_tenant.

A true two-transaction DB race needs a live Postgres (out of harness — same
caveat as `test_concurrency.py`'s header). We assert the guard CONTRACT
(rowcount -> outcome), which is what makes the atomic UPDATE race-safe.
"""
import uuid
from types import SimpleNamespace

from app.api.v1.orders import classify_claim_outcome
from app.config import settings
from app.models.order import ServiceStatus

from tests.conftest import make_test_client
from tests.orders.conftest import FakeAsyncSession, make_claim_order


class TestClassifyClaimOutcome:
    """
    Pure logic — no DB, no HTTP. Mirrors `_post_lock_availability_check`'s
    style in `tests/remisiones/test_concurrency.py`.
    """

    def test_rowcount_one_is_claimed(self):
        tenant = uuid.uuid4()
        assert classify_claim_outcome(1, None, tenant) == "claimed"

    def test_rowcount_zero_and_no_order_is_not_found(self):
        tenant = uuid.uuid4()
        assert classify_claim_outcome(0, None, tenant) == "not_found"

    def test_rowcount_zero_and_other_tenant_is_wrong_tenant(self):
        expected_tenant = uuid.uuid4()
        other_tenant = uuid.uuid4()
        order = SimpleNamespace(tenant_id=other_tenant, status=ServiceStatus.received)
        assert classify_claim_outcome(0, order, expected_tenant) == "wrong_tenant"

    def test_rowcount_zero_and_in_progress_same_tenant_is_already_claimed(self):
        tenant = uuid.uuid4()
        order = SimpleNamespace(tenant_id=tenant, status=ServiceStatus.in_progress)
        assert classify_claim_outcome(0, order, tenant) == "already_claimed"

    def test_rowcount_zero_and_advanced_status_same_tenant_is_not_found(self):
        """
        Order exists, same tenant, but its status is neither `received` nor
        `in_progress` (e.g. `completed`) — spec's "Not Claimable / Not
        Found" requirement: such orders were NEVER valid claim targets, so
        this is 404 not_claimable, NOT 409 already_claimed. (Extends the
        tasks.md outline's 4 base cases with this 5th branch for full spec
        compliance — see apply-progress Deviations.)
        """
        tenant = uuid.uuid4()
        order = SimpleNamespace(tenant_id=tenant, status=ServiceStatus.completed)
        assert classify_claim_outcome(0, order, tenant) == "not_found"


class TestClaimEndpointConcurrency:
    """HTTP layer: two claim calls on the same order id -> exactly one 200, one 409."""

    def test_first_caller_wins_second_gets_already_claimed(self):
        order_id = uuid.uuid4()
        winner_technician_id = uuid.uuid4()
        loser_technician_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        winner_db = FakeAsyncSession(claim_rowcount=1)
        with make_test_client(current_user=None, fake_db_session=winner_db) as client:
            resp1 = client.post(
                f"/api/v1/orders/{order_id}/claim",
                json={
                    "technician_id": str(winner_technician_id),
                    "tenant_id": str(tenant_id),
                },
                headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
            )

        already_claimed_order = make_claim_order(
            order_id=order_id, tenant_id=tenant_id, status=ServiceStatus.in_progress,
        )
        loser_db = FakeAsyncSession(claim_rowcount=0, disambiguation_order=already_claimed_order)
        with make_test_client(current_user=None, fake_db_session=loser_db) as client:
            resp2 = client.post(
                f"/api/v1/orders/{order_id}/claim",
                json={
                    "technician_id": str(loser_technician_id),
                    "tenant_id": str(tenant_id),
                },
                headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
            )

        assert resp1.status_code == 200
        body1 = resp1.json()
        assert body1["status"] == "claimed"
        assert body1["new_status"] == "in_progress"
        assert body1["technician_id"] == str(winner_technician_id)
        assert winner_db.committed is True

        assert resp2.status_code == 409
        assert resp2.json()["detail"] == "already_claimed"


class TestClaimEndpointFailureModes:
    def test_order_not_found_returns_404(self):
        order_id = uuid.uuid4()
        fake_db = FakeAsyncSession(claim_rowcount=0, disambiguation_order=None)

        with make_test_client(current_user=None, fake_db_session=fake_db) as client:
            resp = client.post(
                f"/api/v1/orders/{order_id}/claim",
                json={"technician_id": str(uuid.uuid4()), "tenant_id": str(uuid.uuid4())},
                headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "not_claimable"

    def test_cross_tenant_returns_403(self):
        order_id = uuid.uuid4()
        caller_tenant_id = uuid.uuid4()
        actual_tenant_id = uuid.uuid4()
        order = make_claim_order(
            order_id=order_id, tenant_id=actual_tenant_id, status=ServiceStatus.received,
        )
        fake_db = FakeAsyncSession(claim_rowcount=0, disambiguation_order=order)

        with make_test_client(current_user=None, fake_db_session=fake_db) as client:
            resp = client.post(
                f"/api/v1/orders/{order_id}/claim",
                json={"technician_id": str(uuid.uuid4()), "tenant_id": str(caller_tenant_id)},
                headers={"X-Sonia-Secret": settings.SONIA_BOT_SECRET},
            )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "cross_tenant"

    def test_missing_sonia_secret_returns_401(self):
        """Bonus coverage (beyond tasks.md's literal list): mirrors the
        `is_bot_call`/401 guard already used by every other bot-facing
        endpoint in this file (e.g. `create_service_order`)."""
        order_id = uuid.uuid4()
        fake_db = FakeAsyncSession(claim_rowcount=0, disambiguation_order=None)

        with make_test_client(current_user=None, fake_db_session=fake_db) as client:
            resp = client.post(
                f"/api/v1/orders/{order_id}/claim",
                json={"technician_id": str(uuid.uuid4()), "tenant_id": str(uuid.uuid4())},
            )

        assert resp.status_code == 401
