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
from sqlalchemy.exc import IntegrityError

from app.models.order import OrderHistory, ServiceOrder, ServiceOrderReception, ServiceStatus, ServiceType
from app.models.vehicle import Vehicle


def make_claim_order(
    order_id: Optional[uuid.UUID] = None,
    tenant_id: Optional[uuid.UUID] = None,
    status: ServiceStatus = ServiceStatus.received,
    technician_id: Optional[uuid.UUID] = None,
) -> ServiceOrder:
    """
    Real `ServiceOrder` ORM instance, unattached to any session — enough
    surface for `classify_claim_outcome`'s disambiguation read (`.tenant_id`,
    `.status`, `.technician_id`).
    """
    return ServiceOrder(
        id=order_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        status=status,
        technician_id=technician_id,
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
        raise_integrity_error: bool = False,
    ):
        self._claim_rowcount = claim_rowcount
        self._disambiguation_order = disambiguation_order
        self._prior_history = prior_history
        self._raise_integrity_error = raise_integrity_error
        self.added: list = []
        self.committed = False
        self.rolled_back = False
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if isinstance(stmt, Update):
            if self._raise_integrity_error:
                raise IntegrityError("UPDATE service_orders", {}, Exception("fk violation"))
            return _ClaimUpdateResult(self._claim_rowcount)

        entity = stmt.column_descriptions[0]["entity"]
        if entity is OrderHistory:
            return _ClaimSelectResult(self._prior_history)
        return _ClaimSelectResult(self._disambiguation_order)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def make_active_order(
    order_id: Optional[uuid.UUID] = None,
    tenant_id: Optional[uuid.UUID] = None,
    status: ServiceStatus = ServiceStatus.in_progress,
    technician_id: Optional[uuid.UUID] = None,
    plate: str = "ABC12D",
    created_at: Optional[datetime] = None,
) -> ServiceOrder:
    """
    Real `ServiceOrder` ORM instance (unattached to any session, same
    convention as `make_claim_order` above), with a `vehicle` relationship
    populated so `OrderRead.model_validate`'s `plate` hybrid property
    (`ServiceOrder.plate` -> `self.vehicle.plate`) resolves without a lazy
    load. Scoped to `GET /orders/active/plate/{plate}`
    (`sdd/order-claim-plate-atomic` PR2 fix cycle).
    """
    vehicle_id = uuid.uuid4()
    order = ServiceOrder(
        id=order_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        vehicle_id=vehicle_id,
        status=status,
        technician_id=technician_id,
        service_type=ServiceType.regular,
        created_at=created_at or datetime.utcnow(),
    )
    order.vehicle = Vehicle(
        id=vehicle_id,
        tenant_id=order.tenant_id,
        plate=plate.upper(),
        brand="UM",
        model="TEST",
    )
    order.reception = None
    order.work_logs = []
    order.parts = []
    return order


def attach_text_only_damage_reception(order: ServiceOrder, desc: str = "Ninguna") -> None:
    """
    Attaches a `ServiceOrderReception` whose `damage_photos_urls` holds a
    text-only entry (`{"type": "text", "desc": ...}`), the shape
    `app/api/v1/endpoints/uploads.py` intentionally writes for damage
    observations reported without a photo. Reproduces the
    `ResponseValidationError` seen in production on `GET
    /orders/active/plate/{plate}` before `ReceptionBase.damage_photos_urls`
    was widened to accept both legacy plain-string URLs and these objects.
    """
    order.reception = ServiceOrderReception(
        id=uuid.uuid4(),
        order_id=order.id,
        mileage_km=1000,
        damage_photos_urls=[{"type": "text", "desc": desc}],
        created_at=datetime.utcnow(),
    )


class FakeActivePlateSession:
    """
    Minimal fake for `GET /orders/active/plate/{plate}` — a single `SELECT`
    (`ServiceOrder JOIN Vehicle`) whose result is read via
    `.scalar_one_or_none()`. Distinct from `FakeAsyncSession` above (that one
    is scoped to the claim endpoint's UPDATE + SELECT sequence); this
    endpoint issues exactly one read, no writes.
    """

    def __init__(self, order: Optional[ServiceOrder] = None):
        self._order = order
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _ClaimSelectResult(self._order)
