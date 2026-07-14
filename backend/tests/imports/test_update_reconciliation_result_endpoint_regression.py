"""
Approval/regression tests for `update_reconciliation_result`
(`PATCH /api/v1/imports/reconciliation-results/{result_id}`, `imports.py:1076`),
written BEFORE its Phase 3 extraction
(`sdd/imports-oversized-functions-refactor-tier2`).

Covers the endpoint's three branches exactly as they exist today:
  - `qty_in_packing`: recomputes `rr.result` via `_compute_reconciliation_result`
    and, when linked to a `SparePartItem`, mirrors the quantity onto it.
  - `qty_physical`: 400s with `RECONCILIATION_NOT_CONFIRMED` unless the lot's
    packing list has been confirmed (`lot.packing_list_received`).
  - `item_fields` (`part_number`, `description_es`, `model_applicable`):
    written onto the linked `SparePartItem` when one exists, otherwise
    directly onto the `ReconciliationResult` (EXTRA row), with `part_number`
    always mirrored onto `rr` regardless of branch.

Run FIRST against pre-refactor `imports.py` to capture baseline behavior,
then again after Phase 3's extraction into `_apply_qty_in_packing`,
`_apply_qty_physical`, `_apply_item_fields` to confirm byte-for-byte
identical responses/status codes/error strings (spec's Behavior-Preserving
Refactor requirement).

The `qty_physical` branch resolves the linked `SparePartItem` via
`rr.spare_part_item_id` before delegating to `apply_physical_inspection`
(fixed by `sdd/reconciliation-result-qty-physical-fix`): for a MATCHED row,
`apply_physical_inspection` runs against the linked item; for a pure EXTRA
row (`spare_part_item_id IS NULL`), the value is stored on `rr.qty_physical`
directly and no item sync is attempted.
"""
import uuid
from unittest.mock import AsyncMock

from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_imports_editor,
    make_lot,
    make_spare_part_item,
)
from app.services import imports_service


def _make_reconciliation_result(**kwargs):
    from app.models.imports import ReconciliationResult
    defaults = dict(
        id=uuid.uuid4(),
        lot_id=uuid.uuid4(),
        packing_list_id=uuid.uuid4(),
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


# ---------------------------------------------------------------------------
# qty_in_packing branch
# ---------------------------------------------------------------------------

def test_qty_in_packing_extra_row_recomputes_result_only():
    """No linked SparePartItem (EXTRA row): only `rr` fields change."""
    rr = _make_reconciliation_result(qty_ordered=10, spare_part_item_id=None)
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={"qty_in_packing": 10},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["qty_in_packing"] == 10
    assert body["result"] == "COMPLETE"  # _compute_reconciliation_result(10, 10)


def test_qty_in_packing_linked_item_mirrors_qty_onto_item():
    """Linked SparePartItem: qty mirrored, qty_pending recomputed on the item."""
    item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10, qty_received=0)
    rr = _make_reconciliation_result(qty_ordered=10, spare_part_item_id=item.id)
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, item])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={"qty_in_packing": 6},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["qty_in_packing"] == 6
    assert body["result"] == "PARTIAL"  # _compute_reconciliation_result(10, 6)
    assert item.qty_received == 6
    assert item.qty_pending == 4  # max(0, 10 - 6)


# ---------------------------------------------------------------------------
# qty_physical branch
# ---------------------------------------------------------------------------

def test_qty_physical_400_when_lot_missing():
    rr = _make_reconciliation_result(lot_id=uuid.uuid4())
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])  # no matching lot

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={"qty_physical": 5},
        )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "detail": "El inventario físico solo puede registrarse después de confirmar el cruce",
            "code": "RECONCILIATION_NOT_CONFIRMED",
        }
    }


def test_qty_physical_400_when_lot_not_confirmed():
    lot = make_lot(packing_list_received=False)
    rr = _make_reconciliation_result(lot_id=lot.id)
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, lot])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={"qty_physical": 5},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RECONCILIATION_NOT_CONFIRMED"


def test_qty_physical_confirmed_lot_linked_item_propagates(monkeypatch):
    """MATCHED row: qty_physical propagates to the linked SparePartItem,
    never to the ReconciliationResult itself."""
    lot = make_lot(packing_list_received=True)
    item = make_spare_part_item(lot_id=lot.id, part_number="PN-001", qty_ordered=10, qty_received=6)
    rr = _make_reconciliation_result(lot_id=lot.id, spare_part_item_id=item.id)
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, lot, item])
    mock_apply = AsyncMock()
    monkeypatch.setattr(imports_service, "apply_physical_inspection", mock_apply)

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={"qty_physical": 5},
        )

    assert response.status_code == 200
    assert rr.qty_physical == 5
    mock_apply.assert_called_once_with(fake_db, item, 5)


def test_qty_physical_confirmed_lot_extra_row_stores_no_item_sync(monkeypatch):
    """Pure EXTRA row (no linked SparePartItem): qty_physical is stored on
    `rr` directly and no item lookup/sync is attempted."""
    lot = make_lot(packing_list_received=True)
    rr = _make_reconciliation_result(lot_id=lot.id, spare_part_item_id=None)
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, lot])
    mock_apply = AsyncMock()
    monkeypatch.setattr(imports_service, "apply_physical_inspection", mock_apply)

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={"qty_physical": 5},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["qty_physical"] == 5
    assert rr.qty_physical == 5
    mock_apply.assert_not_called()


# ---------------------------------------------------------------------------
# item_fields branch
# ---------------------------------------------------------------------------

def test_item_fields_linked_item_writes_onto_item_and_mirrors_part_number():
    item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-OLD", qty_ordered=10)
    rr = _make_reconciliation_result(spare_part_item_id=item.id, part_number="PN-OLD")
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, item])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={
                "part_number": "PN-999",
                "description_es": "Nueva descripcion",
                "model_applicable": "MODEL-X",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["part_number"] == "PN-999"
    assert item.part_number == "PN-999"
    assert item.description_es == "Nueva descripcion"
    assert item.model_applicable == "MODEL-X"


def test_item_fields_extra_row_writes_directly_onto_reconciliation_result():
    rr = _make_reconciliation_result(spare_part_item_id=None, part_number="PN-OLD")
    fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.patch(
            f"/api/v1/imports/reconciliation-results/{rr.id}",
            json={
                "part_number": "PN-EXTRA",
                "description_es": "Desc EXTRA",
                "model_applicable": "MODEL-Y",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["part_number"] == "PN-EXTRA"
    assert rr.description_es == "Desc EXTRA"
    assert rr.model_applicable == "MODEL-Y"
    assert rr.part_number == "PN-EXTRA"
