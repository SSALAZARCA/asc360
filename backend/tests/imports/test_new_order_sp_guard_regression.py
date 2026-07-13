"""
Regression tests for the G6 guard on `create_sp_order_from_excel`
(`imports_service.py`, called by `POST /api/v1/imports/new-order-sp`).

Bug prevented: re-importing an order-detail Excel under a reference that
already resolves to a confirmed lot deletes every non-backorder item
(orphaning their confirmed `ReconciliationResult` via FK) and mutates
backorder-item `qty_ordered` in place — the same corruption class G1
closes for packing-list re-uploads. Unlike G5, the lot is resolved INSIDE
the service (by `reference`, not by `lot_id` path param), so the guard
lives in the service, right after lot resolution, before the
delete-and-rebuild block. It raises `HTTPException` directly (not the
`{"error": ...}` dict pattern G3 uses) because the caller endpoint's
`except ValueError` does not swallow `HTTPException` — the 409 propagates
to the client untouched.

Covers (per spec's "New Order-SP Import Rejected When Reused Reference's
Lot Is Already Confirmed" requirement):
  - A brand-new reference (no existing order) always proceeds — a fresh
    lot can never already be confirmed.
  - Reusing a reference whose lot is unconfirmed proceeds (today's
    behavior, unaffected).
  - Reusing a reference whose lot IS confirmed is rejected 409 for a
    superadmin (directive rollback message) and a non-superadmin editor
    (contact-an-administrator message), via the real HTTP endpoint — this
    specifically proves the 409 is NOT swallowed by the endpoint's
    `except ValueError`.
  - On the 409 path, the old-items delete/update block never runs.
"""
import io
import uuid

import openpyxl

from app.services import imports_service
from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_lot, make_shipment_order


def _order_excel_bytes() -> bytes:
    """Header-only sheet: enough columns for `_find_header_row` to match
    (>= 3 of `SP_ORDER_COLS`), zero data rows — the per-row insert/update
    loop is not this guard's concern (already exercised by whatever other
    coverage exists for the happy path); this test only cares about what
    happens BEFORE that loop."""
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["Codigo Parte", "Nombre", "Cantidad", "Moto Aplica"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _order_excel_file():
    return {"file": ("orden.xlsx", _order_excel_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


class TestNewReferenceAlwaysProceeds:

    async def test_no_existing_order_proceeds_without_confirmed_check_blocking(self):
        fake_db = FakeAsyncSession(execute_queue=[
            [],  # _load_models_map
            [],  # existing_order lookup -> not found
            [],  # G6 check on the freshly created lot -> never confirmed
            [],  # old_items load on the freshly created lot -> empty
        ])

        result = await imports_service.create_sp_order_from_excel(
            fake_db, "E0001111-SP", _order_excel_bytes(), make_imports_editor()
        )

        assert result["inserted"] == 0
        assert result["reference"] == "E0001111-SP"


class TestReusedReferenceUnconfirmedLotProceeds:

    async def test_unconfirmed_lot_reuse_proceeds(self):
        order = make_shipment_order(pi_number="E0000573-SP", is_spare_part=True)
        lot = make_lot(lot_identifier="E0000573-SP", shipment_order_id=order.id)
        fake_db = FakeAsyncSession(execute_queue=[
            [],       # _load_models_map
            [order],  # existing_order lookup -> found
            [lot],    # lot lookup -> found
            [],       # G6 check -> not confirmed
            [],       # old_items load -> empty
        ])

        result = await imports_service.create_sp_order_from_excel(
            fake_db, "e0000573-sp", _order_excel_bytes(), make_imports_editor()
        )

        assert result["order_id"] == str(order.id)
        assert result["lot_id"] == str(lot.id)


class TestReusedReferenceConfirmedLotRejected:

    def _confirmed_fake_db(self, order, lot):
        return FakeAsyncSession(execute_queue=[
            [],                   # _load_models_map
            [order],              # existing_order lookup -> found
            [lot],                # lot lookup -> found
            [uuid.uuid4()],       # G6 check -> confirmed (truthy row)
        ])

    def test_confirmed_lot_409_directive_message_via_endpoint_superadmin(self):
        order = make_shipment_order(pi_number="E0000999-SP", is_spare_part=True)
        lot = make_lot(lot_identifier="E0000999-SP", shipment_order_id=order.id)
        fake_db = self._confirmed_fake_db(order, lot)

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.post(
                "/api/v1/imports/new-order-sp",
                params={"reference": "E0000999-SP"},
                files=_order_excel_file(),
            )

        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["code"] == "LOT_ALREADY_CONFIRMED"
        assert "rollback" in body["detail"].lower()
        assert "E0000999-SP" in body["detail"]
        assert fake_db.deleted == []

    def test_confirmed_lot_409_points_to_administrator_for_editor_role(self):
        order = make_shipment_order(pi_number="E0000999-SP", is_spare_part=True)
        lot = make_lot(lot_identifier="E0000999-SP", shipment_order_id=order.id)
        fake_db = self._confirmed_fake_db(order, lot)

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.post(
                "/api/v1/imports/new-order-sp",
                params={"reference": "E0000999-SP"},
                files=_order_excel_file(),
            )

        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["code"] == "LOT_ALREADY_CONFIRMED"
        assert "administrador" in body["detail"].lower()
        assert "rollback-lot" not in body["detail"]
        assert fake_db.deleted == []
