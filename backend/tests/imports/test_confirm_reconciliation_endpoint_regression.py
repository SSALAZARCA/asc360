"""
Regression tests for `confirm_lot_reconciliation`
(`POST /api/v1/imports/spare-part-lots/{lot_id}/reconciliation/confirm`,
`imports.py`) and the `confirm_reconciliation` service it calls.

Bug fixed: nothing on the server recorded that a lot's reconciliation had
already been confirmed. `ReconciliationResult.confirmed_by`/`confirmed_at`
existed on the model and were already returned by the API, but
`confirm_reconciliation` never actually set them -- so the frontend's
"already confirmed" button state was pure client-side state that reset on
every reopen/reload, and the endpoint itself would silently re-apply the
whole confirmation (overwriting any manual adjustment made afterwards) if
called a second time.

Covers:
  - A first confirm stamps `confirmed_by`/`confirmed_at` on every result row,
    including a pure "extra" row with no linked SparePartItem (which the
    main per-item loop skips over).
  - A second confirm on already-confirmed results is rejected with 409
    ALREADY_CONFIRMED and does not touch anything further (no second
    `SparePartItem` fetch, no backorder queries).
"""
import uuid
from datetime import datetime

from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_imports_editor,
    make_lot,
    make_reconciliation_result,
    make_spare_part_item,
)


def _confirm(lot, fake_db):
    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        return client.post(f"/api/v1/imports/spare-part-lots/{lot.id}/reconciliation/confirm")


def test_first_confirm_stamps_confirmed_by_and_at_on_every_result_including_pure_extra():
    lot = make_lot()
    item = make_spare_part_item(lot_id=lot.id, part_number="ABC123", qty_ordered=5, qty_received=0, status="PENDING")
    complete_rr = make_reconciliation_result(
        lot_id=lot.id, part_number="ABC123", result="COMPLETE",
        spare_part_item_id=item.id, qty_ordered=5, qty_in_packing=5,
    )
    # Pure extra: no linked SparePartItem, no surplus to cross against backorders
    # (qty_in_packing left None) -- exercises both "continue" branches in
    # confirm_reconciliation without needing extra queued Backorder queries.
    extra_rr = make_reconciliation_result(
        lot_id=lot.id, part_number="ZZZ999", result="EXTRA",
        spare_part_item_id=None, qty_in_packing=None,
    )

    fake_db = FakeAsyncSession(
        execute_queue=[[complete_rr, extra_rr]],
        get_objects=[lot, item],
    )

    resp = _confirm(lot, fake_db)

    assert resp.status_code == 200
    assert complete_rr.confirmed_at is not None
    assert extra_rr.confirmed_at is not None
    assert complete_rr.confirmed_by is not None
    assert isinstance(complete_rr.confirmed_at, datetime)
    # Item fields were still applied normally.
    assert item.qty_received == 5
    assert item.status == "DECLARED"


def test_second_confirm_on_already_confirmed_lot_is_rejected_and_changes_nothing():
    lot = make_lot()
    item = make_spare_part_item(lot_id=lot.id, part_number="ABC123", qty_ordered=5, qty_received=5, status="DECLARED")
    already_confirmed_rr = make_reconciliation_result(
        lot_id=lot.id, part_number="ABC123", result="COMPLETE",
        spare_part_item_id=item.id, qty_ordered=5, qty_in_packing=5,
    )
    already_confirmed_rr.confirmed_by = uuid.uuid4()
    already_confirmed_rr.confirmed_at = datetime(2026, 7, 9, 12, 0, 0)

    # Only the initial ReconciliationResult select should ever run -- the
    # guard must return before any SparePartItem/Backorder lookups, so a
    # single-entry queue is enough; a second execute() call would raise.
    fake_db = FakeAsyncSession(
        execute_queue=[[already_confirmed_rr]],
        get_objects=[lot, item],
    )

    resp = _confirm(lot, fake_db)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "ALREADY_CONFIRMED"
    # Untouched: still the original confirmation, not overwritten.
    assert already_confirmed_rr.confirmed_at == datetime(2026, 7, 9, 12, 0, 0)
    assert item.qty_received == 5
