"""
Tests for the backorder-reconciliation service (Phase 3-4 of the
backorder-packing-list-reconciliation change): `reconcile_backorder_packing_list`
and `confirm_backorder_reconciliation` in `app.services.imports_service`.

This is a separate, additive flow: it compares a remainder packing list
against `Backorder.qty_pending` (never `SparePartItem.qty_ordered`) and, on
confirm, ADDS to `SparePartItem.qty_received` instead of overwriting it.
`reconcile_lot_packing_list`/`confirm_reconciliation` (the legacy flow) are
untouched and out of scope here — see
test_reconcile_lot_packing_list_regression.py for that flow's coverage.

Follows this repo's established test pattern (tests/imports/conftest.py):
exercise the REAL service functions against a `FakeAsyncSession`, no live
database, no HTTP server. Excel fixtures are built with real `openpyxl`.
"""
import hashlib
import uuid

from app.services.imports_service import (
    reconcile_backorder_packing_list,
    confirm_backorder_reconciliation,
    precheck_backorder_upload,
)
from app.models.imports import BackorderReconciliation, BackorderReconciliationResult
from tests.imports.conftest import (
    build_packing_list_xlsx,
    build_invoice_xlsx,
    build_malformed_xlsx,
    make_lot,
    make_spare_part_item,
    make_backorder,
    make_backorder_reconciliation,
    make_actor,
    FakeAsyncSession,
)


def _upload_session(
    open_backorders=None,
    models_rows=None,
    prior_batches=None,
    items=None,
) -> FakeAsyncSession:
    """
    Builds a FakeAsyncSession with the execute() queue in the exact order
    `reconcile_backorder_packing_list` issues them:
      1. select(Backorder).join(SparePartItem)...   (open_backorders guard)
      2. select(VehicleModel.model_name)             (via _load_models_map)
      3. select(BackorderReconciliation)...           (prior_batches, lot scope)
      4. select(SparePartItem).where(id.in_(...))     (items behind open backorders)

    NOTE: when `open_backorders` is empty, the function returns immediately
    after query #1 — build the session with `execute_queue=[[]]` only.
    """
    return FakeAsyncSession(execute_queue=[
        open_backorders if open_backorders is not None else [],
        models_rows if models_rows is not None else [],
        prior_batches if prior_batches is not None else [],
        items if items is not None else [],
    ])


class TestNoOpenBackorders:

    async def test_lot_without_open_backorders_returns_error_before_parsing(self):
        lot = make_lot()
        db = FakeAsyncSession(execute_queue=[[]])  # only the guard query runs

        result = await reconcile_backorder_packing_list(
            db, lot, build_malformed_xlsx(), "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        assert result == {"error": "NO_OPEN_BACKORDERS"}
        assert db.added == []
        assert db.deleted == []
        assert db.flush_count == 0


class TestCompleteMatch:

    async def test_remainder_matches_pending_exactly_is_complete(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        db = _upload_session(open_backorders=[bo], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
        ])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        assert result["counts"] == {"complete": 1, "partial": 0, "missing": 0, "extra": 0}
        assert result["warnings"] == []
        lines = db.added_of_type(BackorderReconciliationResult)
        assert len(lines) == 1
        assert lines[0].result == "COMPLETE"
        assert lines[0].backorder_id == bo.id
        assert lines[0].qty_pending_snapshot == 5
        assert lines[0].qty_in_packing == 5
        assert lines[0].qty_applied == 5

        batches = db.added_of_type(BackorderReconciliation)
        assert len(batches) == 1
        assert batches[0].status == "PENDING"
        assert str(batches[0].id) == result["batch_id"]


class TestPartialMatch:

    async def test_remainder_less_than_pending_is_partial(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        db = _upload_session(open_backorders=[bo], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 3},
        ])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        assert result["counts"]["partial"] == 1
        line = db.added_of_type(BackorderReconciliationResult)[0]
        assert line.result == "PARTIAL"
        assert line.qty_applied == 3

    async def test_remainder_more_than_pending_is_still_complete_capped_at_pending(self):
        """Per design: qty_in_pl >= pending -> COMPLETE with applied = pending (capped)."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        db = _upload_session(open_backorders=[bo], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 8},
        ])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        line = db.added_of_type(BackorderReconciliationResult)[0]
        assert line.result == "COMPLETE"
        assert line.qty_applied == 5
        assert result["counts"]["complete"] == 1


class TestMissingItem:

    async def test_remainder_omits_pending_part_number_is_missing(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        db = _upload_session(open_backorders=[bo], items=[item])

        # Remainder PL only mentions an unrelated part.
        file_bytes = build_packing_list_xlsx([
            {"part_number": "ZZZ-999", "description": "unrelated", "qty": 1},
        ])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        assert result["counts"]["missing"] == 1
        assert result["counts"]["extra"] == 1  # ZZZ-999 has no matching open backorder
        lines = db.added_of_type(BackorderReconciliationResult)
        missing_line = next(l for l in lines if l.result == "MISSING")
        assert missing_line.part_number == "ABC-001"
        assert missing_line.backorder_id == bo.id
        assert missing_line.qty_in_packing == 0
        assert missing_line.qty_applied == 0


class TestExtraItem:

    async def test_remainder_reports_part_without_open_backorder_is_extra(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        db = _upload_session(open_backorders=[bo], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
            {"part_number": "ZZZ-999", "description": "unrelated", "qty": 2},
        ])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        assert result["counts"]["extra"] == 1
        extra_line = next(l for l in db.added_of_type(BackorderReconciliationResult) if l.result == "EXTRA")
        assert extra_line.part_number == "ZZZ-999"
        assert extra_line.backorder_id is None
        assert extra_line.spare_part_item_id is None


class TestReuploadBeforeConfirm:

    async def test_second_upload_replaces_prior_pending_batch(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        prior_pending = make_backorder_reconciliation(lot.id, file_name="first.xlsx", content_hash="old-hash")
        db = _upload_session(open_backorders=[bo], prior_batches=[prior_pending], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
        ])

        await reconcile_backorder_packing_list(
            db, lot, file_bytes, "second.xlsx", "minio/second.xlsx", make_actor()
        )

        assert prior_pending in db.deleted
        new_batches = db.added_of_type(BackorderReconciliation)
        assert len(new_batches) == 1
        assert new_batches[0].file_name == "second.xlsx"

    async def test_confirmed_batch_is_never_replaced_or_deleted(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        confirmed = make_backorder_reconciliation(
            lot.id, file_name="first.xlsx", content_hash="old-hash", status="CONFIRMED"
        )
        db = _upload_session(open_backorders=[bo], prior_batches=[confirmed], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
        ])

        await reconcile_backorder_packing_list(
            db, lot, file_bytes, "second.xlsx", "minio/second.xlsx", make_actor()
        )

        assert confirmed not in db.deleted


class TestDuplicateDetection:

    async def test_same_content_hash_as_prior_batch_warns_duplicate_content(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
        ])
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        prior = make_backorder_reconciliation(
            lot.id, file_name="different_name.xlsx", content_hash=content_hash, status="CONFIRMED"
        )
        db = _upload_session(open_backorders=[bo], prior_batches=[prior], items=[item])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        assert result["warnings"] == ["duplicate_content"]

    async def test_same_filename_different_hash_warns_duplicate_filename(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)

        prior = make_backorder_reconciliation(
            lot.id, file_name="remainder.xlsx", content_hash="totally-different-hash", status="CONFIRMED"
        )
        db = _upload_session(open_backorders=[bo], prior_batches=[prior], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
        ])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        assert result["warnings"] == ["duplicate_filename"]

    async def test_distinct_file_has_no_warnings(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)

        prior = make_backorder_reconciliation(
            lot.id, file_name="unrelated.xlsx", content_hash="unrelated-hash", status="CONFIRMED"
        )
        db = _upload_session(open_backorders=[bo], prior_batches=[prior], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
        ])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "brand_new.xlsx", "minio/brand_new.xlsx", make_actor()
        )

        assert result["warnings"] == []


def _batch_with_line(lot, item, bo, result_code, qty_applied, qty_pending_snapshot):
    """Builds a PENDING `BackorderReconciliation` header + a single matching
    `BackorderReconciliationResult` line, for `confirm_backorder_reconciliation` tests."""
    batch = make_backorder_reconciliation(lot.id)
    line = BackorderReconciliationResult(
        id=uuid.uuid4(),
        reconciliation_id=batch.id,
        backorder_id=bo.id,
        spare_part_item_id=item.id,
        part_number=item.part_number,
        qty_pending_snapshot=qty_pending_snapshot,
        qty_in_packing=qty_applied,
        qty_applied=qty_applied,
        result=result_code,
    )
    return batch, line


class TestConfirmBackorderReconciliation:

    async def test_confirm_complete_line_adds_to_qty_received_and_resolves_backorder(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        item.qty_received = 5  # remainder scenario: 5 already received previously
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        batch, line = _batch_with_line(lot, item, bo, "COMPLETE", qty_applied=5, qty_pending_snapshot=5)

        db = FakeAsyncSession(execute_queue=[[batch.id], [line]], get_objects=[item, bo])

        result = await confirm_backorder_reconciliation(db, batch, make_actor())

        assert result["confirmed"] is True
        assert result["qty_applied"] == 5
        assert result["backorders_resolved"] == 1
        assert result["backorders_updated"] == 1
        assert item.qty_received == 10  # additive: 5 + 5, never overwritten
        assert item.qty_pending == 0
        assert item.status == "RECEIVED"
        assert bo.qty_pending == 0
        assert bo.resolved is True
        assert bo.resolved_at is not None
        assert batch.status == "CONFIRMED"
        assert batch.confirmed_at is not None

    async def test_confirm_partial_line_leaves_backorder_open(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        item.qty_received = 0
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        batch, line = _batch_with_line(lot, item, bo, "PARTIAL", qty_applied=3, qty_pending_snapshot=5)

        db = FakeAsyncSession(execute_queue=[[batch.id], [line]], get_objects=[item, bo])

        result = await confirm_backorder_reconciliation(db, batch, make_actor())

        assert item.qty_received == 3
        assert bo.qty_pending == 2
        assert bo.resolved is False
        assert result["backorders_resolved"] == 0
        assert result["qty_applied"] == 3

    async def test_confirm_missing_line_does_not_change_item_or_backorder(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        item.qty_received = 0
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        batch, line = _batch_with_line(lot, item, bo, "MISSING", qty_applied=0, qty_pending_snapshot=5)

        db = FakeAsyncSession(execute_queue=[[batch.id], [line]], get_objects=[item, bo])

        result = await confirm_backorder_reconciliation(db, batch, make_actor())

        assert item.qty_received == 0
        assert bo.qty_pending == 5
        assert bo.resolved is False
        assert result["qty_applied"] == 0
        assert result["backorders_updated"] == 0

    async def test_confirm_already_confirmed_batch_returns_error_without_changes(self):
        lot = make_lot()
        batch = make_backorder_reconciliation(lot.id, status="CONFIRMED")
        db = FakeAsyncSession(execute_queue=[])  # no query should even run

        result = await confirm_backorder_reconciliation(db, batch, make_actor())

        assert result == {"error": "ALREADY_CONFIRMED"}
        assert db.added == []

    async def test_confirm_extra_line_is_skipped_without_side_effects(self):
        """EXTRA lines have no `backorder_id` — nothing to apply, but the
        batch still gets confirmed and the line doesn't count as updated."""
        lot = make_lot()
        batch = make_backorder_reconciliation(lot.id)
        extra_line = BackorderReconciliationResult(
            id=uuid.uuid4(), reconciliation_id=batch.id, backorder_id=None, spare_part_item_id=None,
            part_number="ZZZ-999", qty_pending_snapshot=None, qty_in_packing=2, qty_applied=0, result="EXTRA",
        )
        db = FakeAsyncSession(execute_queue=[[batch.id], [extra_line]])

        result = await confirm_backorder_reconciliation(db, batch, make_actor())

        assert result["confirmed"] is True
        assert result["qty_applied"] == 0
        assert result["backorders_updated"] == 0
        assert result["backorders_resolved"] == 0
        assert batch.status == "CONFIRMED"

    async def test_confirm_line_with_missing_item_or_backorder_logs_warning_and_is_skipped(self, caplog):
        """If the referenced SparePartItem/Backorder was deleted between
        upload and confirm, the line must be skipped safely — logged, not
        silently swallowed with zero trace."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        batch, line = _batch_with_line(lot, item, bo, "COMPLETE", qty_applied=5, qty_pending_snapshot=5)

        db = FakeAsyncSession(execute_queue=[[batch.id], [line]], get_objects=[])  # item/bo ya no existen

        with caplog.at_level("WARNING"):
            result = await confirm_backorder_reconciliation(db, batch, make_actor())

        assert result["qty_applied"] == 0
        assert result["backorders_updated"] == 0
        assert result["backorders_resolved"] == 0
        assert batch.status == "CONFIRMED"
        assert "inexistente" in caplog.text


class TestConfirmConcurrencyGuard:

    async def test_lost_race_against_concurrent_confirm_returns_already_confirmed(self):
        """Two requests confirming the same batch: the second one's atomic
        claim (`UPDATE ... WHERE status = 'PENDING'`) affects 0 rows because
        the first already flipped it to CONFIRMED — must not double-apply."""
        lot = make_lot()
        batch = make_backorder_reconciliation(lot.id, status="PENDING")
        db = FakeAsyncSession(execute_queue=[[]])  # claim UPDATE affects 0 rows

        result = await confirm_backorder_reconciliation(db, batch, make_actor())

        assert result == {"error": "ALREADY_CONFIRMED"}
        assert batch.status == "PENDING"  # no lo pisamos localmente si perdimos la carrera
        assert db.added == []


class TestDuplicateBackordersSameKey:

    async def test_two_open_backorders_same_part_and_model_are_both_preserved(self):
        """Regression test: `_index_open_backorders` used to collapse two
        open backorders sharing (part_number, model) into one dict entry,
        silently dropping the other from matching. Both must now be
        represented in the result — the oldest (FIFO) gets matched against
        the packing list line, the other correctly reported MISSING."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, model_applicable="XR150")
        bo_old = make_backorder(item.id, "ABC-001", "PI-001", qty_pending=3)
        bo_new = make_backorder(item.id, "ABC-001", "PI-002", qty_pending=4)
        db = _upload_session(open_backorders=[bo_old, bo_new], models_rows=["XR150"], items=[item])

        file_bytes = build_invoice_xlsx([
            {"part_number": "ABC-001", "model": "XR150", "description": "Brake pad",
             "description_es": "Pastilla", "qty": 3, "unit_price": 4.5, "amount": 13.5},
        ])

        result = await reconcile_backorder_packing_list(
            db, lot, file_bytes, "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        lines = db.added_of_type(BackorderReconciliationResult)
        assert len(lines) == 2  # ninguno de los dos backorders desaparece
        bo_old_line = next(l for l in lines if l.backorder_id == bo_old.id)
        bo_new_line = next(l for l in lines if l.backorder_id == bo_new.id)

        assert bo_old_line.result == "COMPLETE"
        assert bo_old_line.qty_applied == 3
        assert bo_new_line.result == "MISSING"
        assert bo_new_line.qty_applied == 0
        assert result["counts"] == {"complete": 1, "partial": 0, "missing": 1, "extra": 0}


class TestInvalidPackingListWithOpenBackorders:

    async def test_malformed_file_with_open_backorders_returns_parse_error_not_swallowed(self):
        """Distinct from TestNoOpenBackorders: here the lot HAS open
        backorders, so parsing actually runs and must surface its error —
        this path used to be untested (only reachable when backorders exist)."""
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        db = FakeAsyncSession(execute_queue=[[bo], []])  # 1: guard passes, 2: models_map

        result = await reconcile_backorder_packing_list(
            db, lot, build_malformed_xlsx(), "remainder.xlsx", "minio/remainder.xlsx", make_actor()
        )

        assert "error" in result
        assert result["error"] != "NO_OPEN_BACKORDERS"
        assert db.added == []


class TestPrecheckBackorderUpload:
    """`precheck_backorder_upload` runs BEFORE the file is uploaded to MinIO
    (see `upload_lot_backorder_packing_list`), so a failed validation never
    leaves an orphaned blob behind."""

    async def test_returns_no_open_backorders_code(self):
        lot = make_lot()
        db = FakeAsyncSession(execute_queue=[[]])

        error = await precheck_backorder_upload(db, lot, build_malformed_xlsx())

        assert error == "NO_OPEN_BACKORDERS"

    async def test_returns_parse_error_when_backorders_open_but_file_malformed(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        db = FakeAsyncSession(execute_queue=[[bo], []])

        error = await precheck_backorder_upload(db, lot, build_malformed_xlsx())

        assert error is not None

    async def test_returns_none_for_a_valid_upload(self):
        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        db = FakeAsyncSession(execute_queue=[[bo], []])
        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
        ])

        error = await precheck_backorder_upload(db, lot, file_bytes)

        assert error is None


class TestReplacePendingBatchStorageCleanup:

    async def test_replacing_pending_batch_removes_old_minio_blob(self, monkeypatch):
        """Regression test: re-uploading used to delete the PENDING batch's
        DB row but leave its file orphaned in MinIO forever."""
        from app.services import storage_service

        removed_calls = []
        monkeypatch.setattr(
            storage_service.minio_client,
            "remove_object",
            lambda bucket, object_name: removed_calls.append((bucket, object_name)),
        )

        lot = make_lot()
        item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10)
        bo = make_backorder(item.id, "ABC-001", lot.lot_identifier, qty_pending=5)
        prior_pending = make_backorder_reconciliation(lot.id, file_name="first.xlsx", content_hash="old-hash")
        db = _upload_session(open_backorders=[bo], prior_batches=[prior_pending], items=[item])

        file_bytes = build_packing_list_xlsx([
            {"part_number": "ABC-001", "description": "Brake pad", "qty": 5},
        ])

        await reconcile_backorder_packing_list(
            db, lot, file_bytes, "second.xlsx", "minio/second.xlsx", make_actor()
        )

        assert removed_calls == [(storage_service.IMPORTS_BUCKET, prior_pending.minio_object_name)]
