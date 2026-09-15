"""
Phase 3 "Models/Schemas/Services" — shared test plumbing
(sdd/motored-pedidos-cimientos).

Mirrors the project's established fake-session convention
(`tests/imports/conftest.py`'s `FakeAsyncSession`/`_ExecuteResult`): no live
database anywhere in this suite, matching `tests/conftest.py`'s own stated
approach ("pure unit tests using MagicMock/AsyncMock — no live database
required"). This is a Motored-local copy, deliberately not importing the
`tests/imports` version, since the two domains have nothing in common and
this module must stay independently readable.
"""
import uuid
from typing import Any, List, Optional


class _ScalarsResult:
    def __init__(self, items: list):
        self._items = items

    def all(self) -> list:
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None

    def one_or_none(self):
        if len(self._items) > 1:
            raise AssertionError("one_or_none() expects 0 or 1 queued rows")
        return self._items[0] if self._items else None


class _ExecuteResult:
    def __init__(self, items: list):
        self._items = items

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._items)

    def all(self) -> list:
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class FakeAsyncSession:
    """Minimal stand-in for `AsyncSession`. `execute_queue` is a list of
    lists: each `await db.execute(stmt)` call pops the next queued list of
    rows, in the exact order the service under test issues its queries."""

    def __init__(self, execute_queue: Optional[List[list]] = None):
        self._execute_queue = list(execute_queue or [])
        self.added: List[Any] = []
        self.committed = False
        self.rolled_back = False
        self.executed_statements: List[Any] = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if not self._execute_queue:
            raise AssertionError(
                "FakeAsyncSession.execute() called more times than expected "
                "— update the test's execute_queue."
            )
        return _ExecuteResult(self._execute_queue.pop(0))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def flush(self):
        pass

    async def refresh(self, obj, attribute_names=None):
        pass

    def added_of_type(self, cls) -> list:
        return [obj for obj in self.added if isinstance(obj, cls)]
