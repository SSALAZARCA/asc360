"""
Regression tests for the G1 guard on `upload_lot_packing_list`
(`POST /api/v1/imports/spare-part-lots/{lot_id}/packing-list`, `imports.py`).

Bug prevented: re-uploading a packing list onto a lot whose reconciliation
was already confirmed silently desynced the confirmed snapshot (deletes and
recreates `ReconciliationResult`/`PackingList` rows, orphaning anything a
user did after confirming). The endpoint must reject the upload BEFORE any
file read or MinIO write, with a role-aware neutral-Spanish HTTP 409.

Covers (per spec's "Packing List Upload Rejected When Lot Reconciliation Is
Already Confirmed" requirement):
  - First-ever upload (no `ReconciliationResult` rows at all) is allowed.
  - Re-upload while every existing result is still unconfirmed is allowed.
  - Re-upload on a confirmed lot is rejected 409 for a superadmin, with a
    directive message naming rollback.
  - Re-upload on a confirmed lot is rejected 409 for a non-superadmin editor
    (proveedor/administrativo), with a message pointing them to an admin.
  - A missing lot still 404s (the guard does not mask LOT_NOT_FOUND).
  - Upload is allowed again once rollback has cleared the confirmed state
    (i.e. no confirmed `ReconciliationResult` remains for the lot).
  - On the 409 path, no bytes are read, no MinIO object is stored, and
    `reconcile_lot_packing_list` is never invoked.
"""
from app.api.v1 import imports as imports_module
from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_lot


def _pl_file():
    return {"file": ("pl.xlsx", b"fake xlsx bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def _patch_upload_ok(monkeypatch, calls: dict):
    async def _fake_upload_bytes(bucket, name, data, content_type=None):
        calls["upload_bytes"] = True

    monkeypatch.setattr(imports_module.storage_service, "upload_bytes", _fake_upload_bytes)


def _patch_reconcile_ok(monkeypatch, calls: dict):
    async def _fake_reconcile(db, lot, file_bytes, file_name, minio_object_name, actor):
        calls["reconcile_called"] = True
        return {"complete": 1, "partial": 0, "missing": 0, "extra": 0, "is_invoice": False, "total_parts_in_pl": 1, "pl_id": "x"}

    monkeypatch.setattr(imports_module.imports_service, "reconcile_lot_packing_list", _fake_reconcile)


def _patch_reconcile_must_not_be_called(monkeypatch):
    async def _fail(*args, **kwargs):
        raise AssertionError("reconcile_lot_packing_list must NOT be called on a confirmed lot")

    monkeypatch.setattr(imports_module.imports_service, "reconcile_lot_packing_list", _fail)


def _upload(lot, fake_db, current_user):
    with make_test_client(current_user=current_user, fake_db_session=fake_db) as client:
        return client.post(f"/api/v1/imports/spare-part-lots/{lot.id}/packing-list", files=_pl_file())


class TestFirstEverUploadAllowed:

    def test_no_reconciliation_rows_at_all_upload_proceeds(self, monkeypatch):
        lot = make_lot()
        calls: dict = {}
        _patch_upload_ok(monkeypatch, calls)
        _patch_reconcile_ok(monkeypatch, calls)
        # Single execute(): the G1 confirmed-existence check, returns no rows.
        fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor())

        assert resp.status_code == 200
        assert calls.get("upload_bytes") is True
        assert calls.get("reconcile_called") is True


class TestReuploadBeforeConfirmAllowed:

    def test_only_unconfirmed_results_exist_upload_proceeds(self, monkeypatch):
        lot = make_lot()
        calls: dict = {}
        _patch_upload_ok(monkeypatch, calls)
        _patch_reconcile_ok(monkeypatch, calls)
        # The G1 check filters confirmed_at.isnot(None) — unconfirmed rows
        # never appear in this queued result, regardless of how many exist.
        fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor())

        assert resp.status_code == 200
        assert calls.get("reconcile_called") is True


class TestUploadRejectedOnConfirmedLotSuperadmin:

    def test_confirmed_lot_409_directive_message_names_rollback(self, monkeypatch):
        lot = make_lot(lot_identifier="E0000999-SP")
        _patch_reconcile_must_not_be_called(monkeypatch)
        upload_called = {"called": False}

        async def _fail_upload(bucket, name, data, content_type=None):
            upload_called["called"] = True
            raise AssertionError("upload_bytes must NOT be called on a confirmed lot")

        monkeypatch.setattr(imports_module.storage_service, "upload_bytes", _fail_upload)

        # One truthy row = a confirmed ReconciliationResult exists for this lot.
        fake_db = FakeAsyncSession(execute_queue=[["some-confirmed-rr-id"]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor(role="superadmin"))

        assert resp.status_code == 409
        body = resp.json()["detail"]
        assert body["code"] == "LOT_ALREADY_CONFIRMED"
        assert "rollback" in body["detail"].lower()
        assert "E0000999-SP" in body["detail"]
        assert upload_called["called"] is False
        assert fake_db.added == []
        assert fake_db.deleted == []


class TestUploadRejectedOnConfirmedLotNonSuperadmin:

    def test_confirmed_lot_409_points_to_administrator_for_editor_role(self, monkeypatch):
        lot = make_lot(lot_identifier="E0000999-SP")
        _patch_reconcile_must_not_be_called(monkeypatch)

        async def _fail_upload(bucket, name, data, content_type=None):
            raise AssertionError("upload_bytes must NOT be called on a confirmed lot")

        monkeypatch.setattr(imports_module.storage_service, "upload_bytes", _fail_upload)

        fake_db = FakeAsyncSession(execute_queue=[["some-confirmed-rr-id"]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor(role="administrativo"))

        assert resp.status_code == 409
        body = resp.json()["detail"]
        assert body["code"] == "LOT_ALREADY_CONFIRMED"
        assert "administrador" in body["detail"].lower()
        # Non-superadmin message must not itself name the rollback route as a
        # self-service action.
        assert "rollback-lot" not in body["detail"]
        assert fake_db.added == []
        assert fake_db.deleted == []


class TestMissingLotStill404s:

    def test_missing_lot_returns_404_not_masked_by_guard(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            resp = client.post(
                "/api/v1/imports/spare-part-lots/00000000-0000-0000-0000-000000000000/packing-list",
                files=_pl_file(),
            )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "LOT_NOT_FOUND"


class TestUploadAllowedAgainAfterRollback:

    def test_no_confirmed_rows_remain_after_rollback_upload_proceeds(self, monkeypatch):
        lot = make_lot()
        calls: dict = {}
        _patch_upload_ok(monkeypatch, calls)
        _patch_reconcile_ok(monkeypatch, calls)
        # Rollback deleted every ReconciliationResult for the lot — same
        # observable shape as a first-ever upload: the confirmed-existence
        # check comes back empty.
        fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor())

        assert resp.status_code == 200
        assert calls.get("reconcile_called") is True


class TestConcurrentConfirmDuringUploadTranslatesToHttp409:
    """G3's defense-in-depth: the endpoint guard (G1) passed because no
    confirmed rows existed at check time, but by the time the service ran
    its own race-check a concurrent `confirm_reconciliation` had already
    landed. The service returns `{"error": "ALREADY_CONFIRMED"}` instead of
    raising — the endpoint MUST translate that into a real HTTP 409, never
    an HTTP 200 with an error body, and MUST NOT commit."""

    def test_service_already_confirmed_error_becomes_409_not_200(self, monkeypatch):
        lot = make_lot(lot_identifier="E0000777-SP")
        upload_called = {"called": False}

        async def _fake_upload_bytes(bucket, name, data, content_type=None):
            upload_called["called"] = True

        monkeypatch.setattr(imports_module.storage_service, "upload_bytes", _fake_upload_bytes)

        async def _fake_reconcile(db, lot, file_bytes, file_name, minio_object_name, actor):
            return {"error": "ALREADY_CONFIRMED"}

        monkeypatch.setattr(imports_module.imports_service, "reconcile_lot_packing_list", _fake_reconcile)

        # G1 endpoint-level check passes (no confirmed rows at check time) —
        # the race is simulated entirely inside the (mocked) service call.
        fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor(role="superadmin"))

        assert resp.status_code == 409
        body = resp.json()["detail"]
        assert body["code"] == "LOT_ALREADY_CONFIRMED"
        assert "rollback" in body["detail"].lower()
        # upload_bytes DID run before the service race-check (accepted,
        # known limitation — storage-only, no DB row touched), but no DB
        # commit should have occurred as part of this request.
        assert upload_called["called"] is True
