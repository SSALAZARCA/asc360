"""
tests/orders/ — HTTP + unit test fixtures for `POST /orders/{order_id}/claim`
(`sdd/order-claim-plate-atomic`, PR 1: backend).

`FakeAsyncSession` here is a NEW, minimal fake — NOT
`tests.imports.conftest.FakeAsyncSession` — because that one's
`_ExecuteResult` has no concept of `.rowcount` (imports flows never issue a
bulk `UPDATE`) and its docstring/queue-positional-coupling is deliberately
tied to `reconcile_lot_packing_list`'s exact call sequence. The claim
endpoint's sequence is simpler and different in kind:
  1. One conditional `UPDATE ... WHERE id AND status='received' AND
     tenant_id=:t` — the caller only reads `.rowcount` off the result.
  2. ONLY on loss (`rowcount == 0`), one id-only disambiguation
     `SELECT ServiceOrder WHERE id` — the caller reads `.scalar_one_or_none()`.
"""
import uuid
from datetime import datetime
from typing import Optional

from app.models.order import ServiceOrder, ServiceStatus, ServiceType


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
    """Fakes `.scalar_one_or_none()` for the post-loss disambiguation SELECT."""

    def __init__(self, order: Optional[ServiceOrder]):
        self._order = order

    def scalar_one_or_none(self):
        return self._order


class FakeAsyncSession:
    """
    Minimal fake standing in for `AsyncSession`, scoped to
    `POST /orders/{order_id}/claim`'s exact 1-or-2-query shape:
      1. Conditional `UPDATE` — this fake returns `.rowcount` fixed at
         construction (`claim_rowcount`).
      2. IF (and only if) rowcount == 0, the endpoint issues a
         disambiguation `SELECT ServiceOrder WHERE id` — this fake returns
         `disambiguation_order` (or `None`) via `.scalar_one_or_none()`.

    Statement content is NOT inspected (unlike `tests.imports.conftest.
    FakeAsyncSession.executed_statements`) — the claim endpoint's query
    order is fixed and small enough that positional dispatch is sufficient.
    """

    def __init__(
        self,
        claim_rowcount: int,
        disambiguation_order: Optional[ServiceOrder] = None,
    ):
        self._claim_rowcount = claim_rowcount
        self._disambiguation_order = disambiguation_order
        self._update_consumed = False
        self.added: list = []
        self.committed = False

    async def execute(self, stmt):
        if not self._update_consumed:
            self._update_consumed = True
            return _ClaimUpdateResult(self._claim_rowcount)
        return _ClaimSelectResult(self._disambiguation_order)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True
