"""
Regression test for the Phase 2 write-path test harness capability
(`sdd/imports-oversized-functions-refactor-tier2`).

`FakeAsyncSession` previously only simulated read operations (`execute`,
`get`, `add`, `delete`, `flush`) — any endpoint calling `await db.commit()`
or `await db.refresh(obj, ...)` would raise `AttributeError` inside the
fake, since neither method existed on the class at all.

This test exercises a real write endpoint, `PATCH
/api/v1/imports/reconciliation-results/{result_id}`
(`update_reconciliation_result`, `imports.py:1076`), which calls both
`await db.commit()` and `await db.refresh(rr)` (no `attribute_names`) at
its end (`imports.py:1126-1127`). Before task 2.1, this call would blow up
with `AttributeError: 'FakeAsyncSession' object has no attribute 'commit'`
before ever reaching the assertions below.

`update_moto_unit` (Phase 6's own target) calls `db.refresh(unit,
['location', 'observation'])` — the stub's `refresh()` signature accepts an
optional `attribute_names` param for that reason, even though this specific
test only exercises the no-argument form.
"""
import uuid

from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_imports_editor,
)


def _make_reconciliation_result(**kwargs):
    from app.models.imports import ReconciliationResult
    defaults = dict(
        id=uuid.uuid4(),
        lot_id=uuid.uuid4(),
        spare_part_item_id=None,
        part_number="PN-001",
        qty_ordered=10,
        qty_in_packing=None,
        qty_physical=None,
        result="PENDING",
        description_es=None,
        model_applicable=None,
    )
    defaults.update(kwargs)
    return ReconciliationResult(**defaults)


def test_update_reconciliation_result_commit_and_refresh_do_not_raise():
    """Proves an HTTP write-endpoint call runs to completion (200, correct
    body) without `AttributeError` on `db.commit()`/`db.refresh()`, using
    only the new no-op harness stubs — no live database involved."""
    rr = _make_reconciliation_result(qty_ordered=10)

    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={"qty_in_packing": 7},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(rr.id)
    assert body["qty_in_packing"] == 7
    # `_compute_reconciliation_result(10, 7)` -> "PARTIAL" (qty_in_packing < qty_ordered);
    # not the point of this test, only confirms the endpoint completed normally.
    assert body["result"] is not None
