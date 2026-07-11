"""
Regression tests for `get_latest_backorder_reconciliation`
(`GET /api/v1/imports/spare-part-lots/{lot_id}/backorder-reconciliation/latest`,
`imports_service.py`).

Bug fixed: BackorderReconciliationModal.js had no way to know "what did we
already upload/confirm for this lot" -- unlike the main packing-list
reconciliation modal (fixed earlier this session), it started empty on every
open/reopen, and a CONFIRMED batch's "Confirmar recepcion" button showed as
active again since `confirmed` was pure client-side state with nothing to
derive from. There was no GET endpoint at all for this data.

This is a read-only endpoint -- it never mutates anything. For a CONFIRMED
batch, the "confirmed_summary" (qty_applied/backorders_resolved/
backorders_updated) is derived fresh from the stored lines plus the CURRENT
state of the linked Backorder rows (not a stored snapshot), and the missing-
price skip is re-derived using the exact same condition
`_apply_confirmed_lines` used when it actually confirmed (batch.is_invoice
and line.unit_price is None and line.backorder_id is not None and
line.qty_applied > 0) -- no new column needed to remember which lines were
skipped.

Plain `def test_...` + `asyncio.run(...)` for the service-level tests --
matches this project's established convention for exercising async service
code without pytest-asyncio (see `test_backorder_reconciliation_service.py`).
"""
import asyncio
import uuid

from app.services.imports_service import get_latest_backorder_reconciliation
from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_imports_editor,
    make_lot,
    make_backorder_reconciliation,
    make_backorder_reconciliation_result,
)


def test_no_batch_returns_empty_shell():
    lot = make_lot()
    fake_db = FakeAsyncSession(execute_queue=[[]])

    result = asyncio.run(get_latest_backorder_reconciliation(fake_db, lot))

    assert result["batch_id"] is None
    assert result["status"] is None
    assert result["counts"] == {}
    assert result["lines"] == []
    assert result["skipped_missing_price"] == []
    assert result["confirmed_summary"] is None


def test_pending_batch_returns_lines_and_counts_no_confirmed_summary():
    lot = make_lot()
    batch = make_backorder_reconciliation(lot_id=lot.id, status="PENDING")
    bo1_id, bo2_id = uuid.uuid4(), uuid.uuid4()
    line_complete = make_backorder_reconciliation_result(
        reconciliation_id=batch.id, part_number="ABC", result="COMPLETE",
        backorder_id=bo1_id, qty_applied=5,
    )
    line_partial = make_backorder_reconciliation_result(
        reconciliation_id=batch.id, part_number="XYZ", result="PARTIAL",
        backorder_id=bo2_id, qty_applied=2,
    )
    fake_db = FakeAsyncSession(execute_queue=[
        [batch],
        [line_complete, line_partial],
    ])

    result = asyncio.run(get_latest_backorder_reconciliation(fake_db, lot))

    assert result["batch_id"] == batch.id
    assert result["status"] == "PENDING"
    assert result["counts"] == {"complete": 1, "partial": 1, "missing": 0, "extra": 0}
    assert len(result["lines"]) == 2
    assert result["confirmed_summary"] is None
    assert result["skipped_missing_price"] == []


def test_confirmed_batch_computes_summary_from_current_backorder_state():
    lot = make_lot()
    batch = make_backorder_reconciliation(lot_id=lot.id, status="CONFIRMED", is_invoice=False)
    bo1_id, bo2_id = uuid.uuid4(), uuid.uuid4()
    line1 = make_backorder_reconciliation_result(
        reconciliation_id=batch.id, part_number="ABC", result="COMPLETE",
        backorder_id=bo1_id, qty_applied=5,
    )
    line2 = make_backorder_reconciliation_result(
        reconciliation_id=batch.id, part_number="XYZ", result="PARTIAL",
        backorder_id=bo2_id, qty_applied=2,
    )
    fake_db = FakeAsyncSession(execute_queue=[
        [batch],
        [line1, line2],
        [bo1_id],  # only bo1 currently shows as resolved=True
    ])

    result = asyncio.run(get_latest_backorder_reconciliation(fake_db, lot))

    assert result["status"] == "CONFIRMED"
    assert result["confirmed_summary"] == {
        "qty_applied": 7,
        "backorders_resolved": 1,
        "backorders_updated": 2,
    }
    assert result["skipped_missing_price"] == []


def test_confirmed_invoice_batch_missing_price_line_reported_as_skipped():
    lot = make_lot()
    batch = make_backorder_reconciliation(lot_id=lot.id, status="CONFIRMED", is_invoice=True)
    bo1_id, bo2_id = uuid.uuid4(), uuid.uuid4()
    priced_line = make_backorder_reconciliation_result(
        reconciliation_id=batch.id, part_number="ABC", result="COMPLETE",
        backorder_id=bo1_id, qty_applied=5, unit_price=10.0,
    )
    priceless_line = make_backorder_reconciliation_result(
        reconciliation_id=batch.id, part_number="ZZZ", result="COMPLETE",
        backorder_id=bo2_id, qty_applied=3, unit_price=None, qty_in_packing=3,
    )
    fake_db = FakeAsyncSession(execute_queue=[
        [batch],
        [priced_line, priceless_line],
        [bo1_id],
    ])

    result = asyncio.run(get_latest_backorder_reconciliation(fake_db, lot))

    assert result["confirmed_summary"] == {
        "qty_applied": 5,
        "backorders_resolved": 1,
        "backorders_updated": 1,
    }
    assert result["skipped_missing_price"] == [
        {"part_number": "ZZZ", "qty_in_packing": 3},
    ]


def test_confirmed_batch_all_skipped_never_queries_backorder_resolution():
    """No applied lines -> applied_bo_ids stays empty -> the resolved-check
    query must never run (FakeAsyncSession raises if execute() is called
    more times than queued)."""
    lot = make_lot()
    batch = make_backorder_reconciliation(lot_id=lot.id, status="CONFIRMED", is_invoice=True)
    priceless_line = make_backorder_reconciliation_result(
        reconciliation_id=batch.id, part_number="ZZZ", result="COMPLETE",
        backorder_id=uuid.uuid4(), qty_applied=3, unit_price=None,
    )
    fake_db = FakeAsyncSession(execute_queue=[
        [batch],
        [priceless_line],
    ])

    result = asyncio.run(get_latest_backorder_reconciliation(fake_db, lot))

    assert result["confirmed_summary"] == {
        "qty_applied": 0,
        "backorders_resolved": 0,
        "backorders_updated": 0,
    }
    assert len(result["skipped_missing_price"]) == 1


def test_endpoint_returns_404_for_unknown_lot():
    fake_db = FakeAsyncSession(execute_queue=[])
    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        resp = client.get(f"/api/v1/imports/spare-part-lots/{uuid.uuid4()}/backorder-reconciliation/latest")
    assert resp.status_code == 404


def test_endpoint_serializes_empty_shell_for_lot_with_no_batch():
    lot = make_lot()
    fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[lot])
    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        resp = client.get(f"/api/v1/imports/spare-part-lots/{lot.id}/backorder-reconciliation/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["batch_id"] is None
    assert body["status"] is None
    assert body["confirmed_summary"] is None
