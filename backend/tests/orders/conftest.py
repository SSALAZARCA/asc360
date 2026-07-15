"""
tests/orders/ — HTTP + unit test fixtures for `POST /orders/{order_id}/claim`
(`sdd/order-claim-plate-atomic`, PR 1: backend).

`FakeAsyncSession` here is a NEW, minimal fake — NOT
`tests.imports.conftest.FakeAsyncSession` — because that one's
`_ExecuteResult` has no concept of `.rowcount` (imports flows never issue a
bulk `UPDATE`) and its docstring/queue-positional-coupling is deliberately
tied to `reconcile_lot_packing_list`'s exact call sequence. The claim
endpoint's sequence is:
  1. One conditional `UPDATE ... WHERE id AND status='received' AND
     tenant_id=:t` — the caller only reads `.rowcount` off the result.
  2a. ON WIN (`rowcount == 1`), one `SELECT OrderHistory WHERE order_id
     ORDER BY changed_at DESC LIMIT 1` (the prior-history lookup used to
     backfill `duration_minutes`) — the caller reads `.scalar_one_or_none()`.
  2b. ON LOSS (`rowcount == 0`), one id-only disambiguation
     `SELECT ServiceOrder WHERE id` — the caller reads `.scalar_one_or_none()`.

Dispatch below is by statement entity/type (NOT by call order — 2a and 2b
are mutually exclusive per call, but both are "the 2nd `.execute()` call",
so positional dispatch cannot tell them apart).
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Update

from app.models.order import OrderHistory, ServiceOrder, ServiceStatus, ServiceType


def make_claim_order(
    order_id: Optional[uuid.UUID] = None,
    tenant_id: Optional[uuid.UUID] = None,
    status: ServiceStatus = ServiceStatus.received,
) -> ServiceOrder:
    """
    Real `ServiceOrder` ORM instance, unattached to any session — enough
    surface for `classify_claim_outcome`'s disambiguation read (`.tenant_id`,
    `.status`).
    """
    return ServiceOrder(
        id=order_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        status=status,
        service_type=ServiceType.regular,
        created_at=datetime.utcnow(),
    )


class _ClaimUpdateResult:
    """Fakes the subset of SQLAlchemy's `CursorResult` surface the claim
    endpoint reads off the conditional `UPDATE`'s result: `.rowcount` only."""

    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _ClaimSelectResult:
    """Fakes `.scalar_one_or_none()` for a SELECT result (disambiguation or
    winning-path history lookup — the wrapped object's type varies by
    caller, this fake is generic over both)."""

    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class FakeAsyncSession:
    """
    Minimal fake standing in for `AsyncSession`, scoped to
    `POST /orders/{order_id}/claim`'s exact query shape:
      1. Conditional `UPDATE(ServiceOrder)` — this fake returns `.rowcount`
         fixed at construction (`claim_rowcount`), regardless of dispatch.
      2a. ON WIN (`rowcount == 1`), the endpoint issues a
         `SELECT(OrderHistory)` (the prior-history lookup for the
         `duration_minutes` backfill) — this fake returns `prior_history`
         (or `None`) via `.scalar_one_or_none()`.
      2b. ON LOSS (`rowcount == 0`), the endpoint issues a
         `SELECT(ServiceOrder)` disambiguation query — this fake returns
         `disambiguation_order` (or `None`) via `.scalar_one_or_none()`.

    Dispatch is by the statement's target entity/type — an `Update` always
    returns the fixed `claim_rowcount` result; a `Select` is routed by its
    `column_descriptions[0]["entity"]` to either `prior_history` (entity is
    `OrderHistory`) or `disambiguation_order` (entity is `ServiceOrder`) —
    NOT by call order, since both are "the 2nd `.execute()` call" depending
    on which branch (win vs. loss) the production code takes.

    Mirroring `tests.imports.conftest.FakeAsyncSession.executed_statements`,
    every statement passed to `.execute()` is also recorded on
    `self.executed_statements`, so tests can compile and inspect the real
    SQL (e.g. to assert the atomic UPDATE's WHERE predicates).
    """

    def __init__(
        self,
        claim_rowcount: int,
        disambiguation_order: Optional[ServiceOrder] = None,
        prior_history: Optional[OrderHistory] = None,
    ):
        self._claim_rowcount = claim_rowcount
        self._disambiguation_order = disambiguation_order
        self._prior_history = prior_history
        self.added: list = []
        self.committed = False
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if isinstance(stmt, Update):
            return _ClaimUpdateResult(self._claim_rowcount)

        entity = stmt.column_descriptions[0]["entity"]
        if entity is OrderHistory:
            return _ClaimSelectResult(self._prior_history)
        return _ClaimSelectResult(self._disambiguation_order)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True
