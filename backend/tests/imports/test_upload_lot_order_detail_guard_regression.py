"""
Regression tests for the G5 guard on `upload_lot_order_detail`
(`POST /api/v1/imports/spare-part-lots/{lot_id}/order-detail`, `imports.py`).

Bug prevented: re-uploading an order-detail Excel onto a lot whose
reconciliation was already confirmed silently mutates `qty_ordered`/
`qty_pending` on existing `SparePartItem` rows (`load_order_detail_excel`),
desyncing the confirmed reconciliation snapshot — the same corruption class
G1 closes for packing-list re-uploads. The endpoint must reject the upload
BEFORE any file read, with a role-aware neutral-Spanish HTTP 409. Mirrors
G1's guard exactly: the endpoint already holds the lot before any I/O.

Covers (per spec's "Order-Detail Upload Rejected When Lot Reconciliation Is
Already Confirmed" requirement):
  - First-ever / unconfirmed-lot order-detail upload is allowed.
  - Re-upload on a confirmed lot is rejected 409 for a superadmin, with a
    directive message naming rollback.
  - Re-upload on a confirmed lot is rejected 409 for a non-superadmin editor,
    with a message pointing them to an admin.
  - A missing lot still 404s (the guard does not mask LOT_NOT_FOUND).
  - Upload is allowed again once rollback has cleared the confirmed state.
  - On the 409 path, no bytes are read and `load_order_detail_excel` is
    never invoked.
"""
from app.api.v1 import imports as imports_module
from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_lot


def _od_file():
    return {"file": ("order-detail.xlsx", b"fake xlsx bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def _patch_load_ok(monkeypatch, calls: dict):
    async def _fake_load(db, lot, file_bytes, actor):
        calls["load_called"] = True
        return {"loaded": 1}

    monkeypatch.setattr(imports_module.imports_service, "load_order_detail_excel", _fake_load)


def _patch_load_must_not_be_called(monkeypatch):
    async def _fail(*args, **kwargs):
        raise AssertionError("load_order_detail_excel must NOT be called on a confirmed lot")

    monkeypatch.setattr(imports_module.imports_service, "load_order_detail_excel", _fail)


def _upload(lot, fake_db, current_user):
    with make_test_client(current_user=current_user, fake_db_session=fake_db) as client:
        return client.post(f"/api/v1/imports/spare-part-lots/{lot.id}/order-detail", files=_od_file())


class TestFirstEverOrUnconfirmedUploadAllowed:

    def test_no_confirmed_reconciliation_upload_proceeds(self, monkeypatch):
        lot = make_lot()
        calls: dict = {}
        _patch_load_ok(monkeypatch, calls)
        # Single execute(): the G5 confirmed-existence check, returns no rows.
        fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor())

        assert resp.status_code == 200
        assert calls.get("load_called") is True


class TestUploadRejectedOnConfirmedLotSuperadmin:

    def test_confirmed_lot_409_directive_message_names_rollback(self, monkeypatch):
        lot = make_lot(lot_identifier="E0000999-SP")
        _patch_load_must_not_be_called(monkeypatch)
        # One truthy row = a confirmed ReconciliationResult exists for this lot.
        fake_db = FakeAsyncSession(execute_queue=[["some-confirmed-rr-id"]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor(role="superadmin"))

        assert resp.status_code == 409
        body = resp.json()["detail"]
        assert body["code"] == "LOT_ALREADY_CONFIRMED"
        assert "rollback" in body["detail"].lower()
        assert "E0000999-SP" in body["detail"]


class TestUploadRejectedOnConfirmedLotNonSuperadmin:

    def test_confirmed_lot_409_points_to_administrator_for_editor_role(self, monkeypatch):
        lot = make_lot(lot_identifier="E0000999-SP")
        _patch_load_must_not_be_called(monkeypatch)
        fake_db = FakeAsyncSession(execute_queue=[["some-confirmed-rr-id"]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor(role="administrativo"))

        assert resp.status_code == 409
        body = resp.json()["detail"]
        assert body["code"] == "LOT_ALREADY_CONFIRMED"
        assert "administrador" in body["detail"].lower()
        assert "rollback-lot" not in body["detail"]


class TestMissingLotStill404s:

    def test_missing_lot_returns_404_not_masked_by_guard(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            resp = client.post(
                "/api/v1/imports/spare-part-lots/00000000-0000-0000-0000-000000000000/order-detail",
                files=_od_file(),
            )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "LOT_NOT_FOUND"


class TestUploadAllowedAgainAfterRollback:

    def test_no_confirmed_rows_remain_after_rollback_upload_proceeds(self, monkeypatch):
        lot = make_lot()
        calls: dict = {}
        _patch_load_ok(monkeypatch, calls)
        # Rollback deleted every ReconciliationResult for the lot — same
        # observable shape as a first-ever upload: the confirmed-existence
        # check comes back empty.
        fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[lot])

        resp = _upload(lot, fake_db, make_imports_editor())

        assert resp.status_code == 200
        assert calls.get("load_called") is True
