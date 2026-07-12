"""
Regression tests for `reconcile_lot_packing_list` (Phase 2 of the
backorder-packing-list-reconciliation change).

Purpose: capture TODAY's observable behavior (return dict counts, the
`ReconciliationResult`/`PackingListItem`/`PackingList` rows created, and
which prior rows get deleted on re-upload) BEFORE the parser-extraction
refactor, so the exact same assertions can be re-run AFTER the refactor to
prove the change is byte-for-byte behavior-preserving. Per task 2.1 + 2.3.

These tests exercise the REAL `reconcile_lot_packing_list` function against a
`FakeAsyncSession` (see tests/imports/conftest.py) and real .xlsx bytes built
with openpyxl — no live database, no HTTP server, matching this repo's
established test pattern (tests/remisiones/*, tests/test_parts_manual_catalog.py).
"""
import uuid
from unittest.mock import AsyncMock, patch

from app.services.imports_service import reconcile_lot_packing_list
from app.models.imports import ReconciliationResult, PackingList, PackingListItem
from tests.imports.conftest import (
    build_packing_list_xlsx,
    build_invoice_xlsx,
    build_malformed_xlsx,
    make_lot,
    make_spare_part_item,
    make_actor,
    FakeAsyncSession,
)


def _session(models_rows=None, confirmed_check=None, old_results=None, old_pls=None, lot_items=None) -> FakeAsyncSession:
    """Builds a FakeAsyncSession with the 5-call execute queue in the exact
    order `reconcile_lot_packing_list` issues them today (see the class
    docstring in conftest.py). `confirmed_check` is the G3 defense-in-depth
    existence check — empty for every scenario here (none involves an
    already-confirmed lot)."""
    return FakeAsyncSession(execute_queue=[
        models_rows if models_rows is not None else [],
        confirmed_check if confirmed_check is not None else [],
        old_results if old_results is not None else [],
        old_pls if old_pls is not None else [],
        lot_items if lot_items is not None else [],
    ])


class TestReconcileCompleteMatch:

    async def test_all_items_complete(self):
        lot = make_lot()
        item1 = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        item2 = make_spare_part_item(lot.id, "ABC-002", qty_ordered=5)
        db = _session(lot_items=[item1, item2])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 10},
            {"part_number": "ABC-002", "description": "Oil filter", "qty": 5},
        ])

        result = await reconcile_lot_packing_list(
            db, lot, file_bytes, "pl.xlsx", "minio/pl.xlsx", make_actor()
        )

        assert result["complete"] == 2
        assert result["partial"] == 0
        assert result["missing"] == 0
        assert result["extra"] == 0
        assert result["is_invoice"] is False
        assert result["total_parts_in_pl"] == 2

        rr_rows = db.added_of_type(ReconciliationResult)
        assert len(rr_rows) == 2
        assert {r.result for r in rr_rows} == {"COMPLETE"}
        assert {r.qty_ordered for r in rr_rows} == {10, 5}

        pli_rows = db.added_of_type(PackingListItem)
        assert len(pli_rows) == 2

        pl_rows = db.added_of_type(PackingList)
        assert len(pl_rows) == 1
        assert pl_rows[0].processed is True
        assert lot.packing_list_received is True


class TestReconcilePartialMatch:

    async def test_qty_less_than_ordered_is_partial(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        db = _session(lot_items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 4},
        ])

        result = await reconcile_lot_packing_list(
            db, lot, file_bytes, "pl.xlsx", "minio/pl.xlsx", make_actor()
        )

        assert result["partial"] == 1
        assert result["complete"] == 0
        rr = db.added_of_type(ReconciliationResult)[0]
        assert rr.result == "PARTIAL"
        assert rr.qty_ordered == 10
        assert rr.qty_in_packing == 4
        # PARTIAL is the precondition confirm_reconciliation later uses to
        # create a Backorder for the pending qty (out of scope for this PR —
        # confirm_reconciliation/_upsert_backorder are untouched).


class TestReconcileMissingItem:

    async def test_ordered_item_absent_from_packing_list_is_missing(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        db = _session(lot_items=[item])

        # Packing list mentions an unrelated part only.
        file_bytes = build_packing_list_xlsx([
            {"part_number": "ZZZ-999", "description": "unrelated", "qty": 1},
        ])

        result = await reconcile_lot_packing_list(
            db, lot, file_bytes, "pl.xlsx", "minio/pl.xlsx", make_actor()
        )

        assert result["missing"] == 1
        assert result["extra"] == 1  # ZZZ-999 has no matching SparePartItem
        rr_rows = db.added_of_type(ReconciliationResult)
        missing_row = next(r for r in rr_rows if r.result == "MISSING")
        assert missing_row.part_number == "ABC-001"
        assert missing_row.qty_in_packing == 0
        extra_row = next(r for r in rr_rows if r.result == "EXTRA")
        assert extra_row.part_number == "ZZZ-999"
        assert extra_row.spare_part_item_id is None


class TestReconcileExtraItem:

    async def test_qty_greater_than_ordered_is_extra_on_matched_item(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        db = _session(lot_items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 15},
        ])

        result = await reconcile_lot_packing_list(
            db, lot, file_bytes, "pl.xlsx", "minio/pl.xlsx", make_actor()
        )

        assert result["extra"] == 1
        rr = db.added_of_type(ReconciliationResult)[0]
        assert rr.result == "EXTRA"
        assert rr.spare_part_item_id == item.id  # matched, not a "pure" extra
        assert rr.qty_in_packing == 15


class TestReconcileInvoiceFormat:

    async def test_invoice_updates_prices_description_and_lot_total(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        db = _session(lot_items=[item])

        file_bytes = build_invoice_xlsx([
            {
                "part_number": "ABC-001", "description": "Brake pad EN",
                "description_es": "Pastilla de freno", "qty": 10,
                "unit_price": 4.5, "amount": 45.0,
            },
        ])

        with patch(
            "app.services.pricing_service.recalculate_part_cost",
            new=AsyncMock(),
        ) as mocked_recalc:
            result = await reconcile_lot_packing_list(
                db, lot, file_bytes, "invoice.xlsx", "minio/invoice.xlsx", make_actor()
            )

        assert result["is_invoice"] is True
        assert result["complete"] == 1
        assert item.unit_price == 4.5
        assert item.amount == 45.0
        assert item.description == "Brake pad EN"
        assert item.description_es == "Pastilla de freno"
        assert lot.total_declared_value == 45.0
        mocked_recalc.assert_awaited_once()


class TestReconcileModelBasedMatching:

    async def test_same_part_number_different_models_route_correctly(self):
        lot = make_lot()
        item_xr = make_spare_part_item(lot.id, "ABC-001", qty_ordered=5, model_applicable="XR150")
        item_cb = make_spare_part_item(lot.id, "ABC-001", qty_ordered=3, model_applicable="CB190")
        db = _session(
            models_rows=["XR150", "CB190"],
            lot_items=[item_xr, item_cb],
        )

        file_bytes = build_invoice_xlsx([
            {"part_number": "ABC-001", "model": "XR150", "description": "x", "qty": 5, "unit_price": 1.0, "amount": 5.0},
            {"part_number": "ABC-001", "model": "CB190", "description": "x", "qty": 3, "unit_price": 1.0, "amount": 3.0},
        ])

        with patch("app.services.pricing_service.recalculate_part_cost", new=AsyncMock()):
            result = await reconcile_lot_packing_list(
                db, lot, file_bytes, "invoice.xlsx", "minio/invoice.xlsx", make_actor()
            )

        assert result["complete"] == 2
        rr_rows = db.added_of_type(ReconciliationResult)
        by_item = {r.spare_part_item_id: r for r in rr_rows}
        assert by_item[item_xr.id].qty_in_packing == 5
        assert by_item[item_cb.id].qty_in_packing == 3


class TestReconcileNoValidHeaders:

    async def test_malformed_file_returns_error_without_touching_db(self):
        lot = make_lot()
        db = FakeAsyncSession(execute_queue=[])  # any execute() call is a bug

        result = await reconcile_lot_packing_list(
            db, lot, build_malformed_xlsx(), "bad.xlsx", "minio/bad.xlsx", make_actor()
        )

        assert "error" in result
        assert db.added == []
        assert db.deleted == []
        assert db.flush_count == 0


class TestReconcileReupload:

    async def test_reupload_deletes_previous_results_and_packing_lists(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)

        old_rr = ReconciliationResult(
            id=uuid.uuid4(), lot_id=lot.id, packing_list_id=uuid.uuid4(),
            part_number="ABC-001", result="COMPLETE",
        )
        old_pl = PackingList(
            id=uuid.uuid4(), lot_id=lot.id, file_name="old.xlsx",
            minio_object_name="minio/old.xlsx",
        )
        db = _session(old_results=[old_rr], old_pls=[old_pl], lot_items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 10},
        ])

        await reconcile_lot_packing_list(
            db, lot, file_bytes, "new.xlsx", "minio/new.xlsx", make_actor()
        )

        assert old_rr in db.deleted
        assert old_pl in db.deleted


class TestReconcileAlreadyConfirmedGuard:
    """G3: defense-in-depth check inside `reconcile_lot_packing_list` itself,
    placed immediately before `_replace_lot_packing_list` (after model
    loading and Excel parsing), to minimize the window where a concurrent
    `confirm_reconciliation` commits after the endpoint-level (G1) guard
    passed but before the delete-and-recreate cascade runs."""

    async def test_confirmed_lot_mid_flight_returns_error_and_touches_nothing(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        db = _session(confirmed_check=["some-confirmed-rr-id"], lot_items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 10},
        ])

        result = await reconcile_lot_packing_list(
            db, lot, file_bytes, "pl.xlsx", "minio/pl.xlsx", make_actor()
        )

        assert result == {"error": "ALREADY_CONFIRMED"}
        assert db.added == []
        assert db.deleted == []
        assert db.flush_count == 0
        # Only the model-map + confirmed-check queries ran — the guard fires
        # before old_results/old_pls/lot_items are ever queried.
        assert db.executed_statements == db.executed_statements[:2]
