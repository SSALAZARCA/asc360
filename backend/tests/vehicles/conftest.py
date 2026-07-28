"""
tests/vehicles/ — fixtures for the vehicle tenant claim primitives
(`sdd/vehicle-tenant-checkin-release`, PR 1: migration + models +
repository claim primitives).

`FakeClaimSession` is scoped to `vehicle_repository.get_open_claim`'s exact
query shape: a single `SELECT (ServiceOrder, Tenant) JOIN ...` read via
`.first()`, returning a 2-tuple row (or `None` when unclaimed). Dispatch by
call order is unambiguous here -- `get_open_claim` issues exactly one
`execute()` -- so no statement-shape dispatch is needed (unlike
`tests.orders.conftest.FakeAsyncSession`, which fakes a multi-statement
sequence).

Mirrors `tests/orders/conftest.py`'s convention: every statement passed to
`.execute()` is recorded on `executed_statements` so tests can compile and
inspect the real SQL.
"""
from typing import Optional


class _ClaimRowResult:
    """Fakes the subset of SQLAlchemy's `Result` surface `get_open_claim`
    reads: `.first()`, returning a `(ServiceOrder, Tenant)`-shaped row (or
    `None`)."""

    def __init__(self, row: Optional[tuple]):
        self._row = row

    def first(self):
        return self._row


class FakeClaimSession:
    """Minimal fake standing in for `AsyncSession`, scoped to
    `get_open_claim`'s single `SELECT ... JOIN Tenant ... LIMIT 1`."""

    def __init__(self, row: Optional[tuple] = None):
        self._row = row
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _ClaimRowResult(self._row)
