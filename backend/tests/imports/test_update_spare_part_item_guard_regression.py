"""
Regression tests for the G4 guard on `update_spare_part_item`
(`PATCH /api/v1/imports/spare-part-items/{item_id}`, `imports.py`).

Bug prevented: editing a packing-list-DECLARED snapshot field
(`part_number`, `qty_ordered`, `qty_received`, `status`) on a
`SparePartItem` whose lot has already been confirmed silently desyncs the
confirmed reconciliation snapshot — the same corruption class G1/G2/G3
close for re-uploads and `ReconciliationResult` edits. The guard is
FIELD-SCOPED: it must NOT block `qty_physical` (later stage, own
`packing_list_received` gate) or pricing/cosmetic fields (`unit_price`,
`notes`), because `SparePartItem` has no `confirmed_at` of its own — the
guard queries `imports_service.lot_has_confirmed_reconciliation(db,
item.lot_id)` only when a snapshot field is present in the payload.

Covers (per spec's "Inline Edit of a SparePartItem Rejected (Field-Scoped)
When Its Lot Is Already Confirmed" requirement):
  - Each snapshot field (`part_number`, `qty_ordered`, `qty_received`,
    `status`) is rejected 409 on an item whose lot is confirmed, for a
    superadmin (directive rollback message) and a non-superadmin editor
    (contact-an-administrator message).
  - `qty_physical`-only and pricing/cosmetic (`unit_price`, `notes`)
    payloads on a confirmed-lot item are NOT blocked by G4 — no
    `lot_has_confirmed_reconciliation` query even runs (field-scoped,
    zero-cost when inapplicable).
  - A payload mixing a snapshot field with `qty_physical` is rejected
    whole (409), nothing applied.
  - Any field is applied normally on an item whose lot is unconfirmed
    (today's behavior, unaffected) — including the `qty_ordered`
    propagation onto a linked `ReconciliationResult`.
  - A missing item still 404s (guard does not mask ITEM_NOT_FOUND).
  - Editing a snapshot field succeeds again on an item whose lot was
    rebuilt after rollback (fresh confirmed_at=None reconciliation —
    mirrors G1/G2's post-rollback coverage).
"""
import uuid
from datetime import datetime

import pytest

from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_lot, make_spare_part_item


# Each snapshot field, its new value, and the ORIGINAL value the item must
# still hold after a rejected request (proves nothing was mutated).
_SNAPSHOT_FIELD_CASES = [
    ("part_number", "PN-999", "PN-001"),
    ("qty_ordered", 20, 10),
    ("qty_received", 5, 0),
    ("status", "CANCELLED", "PENDING"),
]


def _confirmed_item():
    item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10)
    # execute_queue[0] backs `lot_has_confirmed_reconciliation`'s
    # `.scalars().first()` — a non-empty row means "confirmed".
    fake_db = FakeAsyncSession(execute_queue=[[uuid.uuid4()]], get_objects=[item])
    return item, fake_db


class TestSnapshotFieldEditRejectedOnConfirmedLotSuperadmin:

    @pytest.mark.parametrize("field,new_value,original_value", _SNAPSHOT_FIELD_CASES)
    def test_each_snapshot_field_409_directive_message(self, field, new_value, original_value):
        item, fake_db = _confirmed_item()

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={field: new_value},
            )

        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["code"] == "ITEM_LOT_CONFIRMED"
        assert "rollback" in body["detail"].lower()
        assert getattr(item, field) == original_value


class TestSnapshotFieldEditRejectedOnConfirmedLotNonSuperadmin:

    @pytest.mark.parametrize("field,new_value,original_value", _SNAPSHOT_FIELD_CASES)
    def test_each_snapshot_field_409_points_to_administrator(self, field, new_value, original_value):
        item, fake_db = _confirmed_item()

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={field: new_value},
            )

        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["code"] == "ITEM_LOT_CONFIRMED"
        assert "administrador" in body["detail"].lower()
        assert "rollback-lot" not in body["detail"]
        assert getattr(item, field) == original_value


class TestNonSnapshotFieldsNotBlockedByG4:
    """Proves G4's field-scoping: qty_physical and pricing/cosmetic payloads
    must never be intercepted by the 409, even on a confirmed-lot item —
    and must never even query `lot_has_confirmed_reconciliation` (empty
    execute_queue proves zero db.execute() calls happen)."""

    def test_qty_physical_only_hits_downstream_gate_not_g4(self):
        lot = make_lot(packing_list_received=False)
        item = make_spare_part_item(lot_id=lot.id, part_number="PN-001", qty_ordered=10)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[item, lot])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"qty_physical": 5},
            )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "RECONCILIATION_NOT_CONFIRMED"

    def test_pricing_and_cosmetic_fields_allowed_on_confirmed_lot_item(self):
        item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10)
        item.created_at = datetime.utcnow()
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[item])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"unit_price": 12.5, "notes": "revisado"},
            )

        assert response.status_code == 200
        assert float(item.unit_price) == 12.5
        assert item.notes == "revisado"


class TestMixedSnapshotAndQtyPhysicalPayloadRejectedWhole:

    def test_mixed_payload_409_nothing_applied(self):
        item, fake_db = _confirmed_item()

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"part_number": "PN-999", "qty_physical": 5},
            )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ITEM_LOT_CONFIRMED"
        assert item.part_number == "PN-001"
        assert item.qty_physical is None


class TestSnapshotFieldEditAllowedOnUnconfirmedLot:

    def test_qty_ordered_applies_and_propagates_to_linked_result(self):
        item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10)
        item.created_at = datetime.utcnow()
        from app.models.imports import ReconciliationResult
        rr = ReconciliationResult(
            id=uuid.uuid4(),
            lot_id=item.lot_id,
            packing_list_id=uuid.uuid4(),
            spare_part_item_id=item.id,
            part_number="PN-001",
            qty_ordered=10,
            qty_in_packing=10,
            qty_physical=None,
            result="COMPLETE",
            confirmed_at=None,
        )
        fake_db = FakeAsyncSession(
            execute_queue=[
                [],       # G4 lot_has_confirmed_reconciliation: not confirmed
                [rr],     # propagate_fields lookup: linked ReconciliationResult
            ],
            get_objects=[item],
        )

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"qty_ordered": 20},
            )

        assert response.status_code == 200
        assert item.qty_ordered == 20
        assert rr.qty_ordered == 20


class TestMissingItemStill404s:

    def test_missing_item_returns_404_not_masked_by_guard(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{uuid.uuid4()}",
                json={"part_number": "PN-999"},
            )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "ITEM_NOT_FOUND"


class TestSnapshotFieldEditAllowedAgainAfterRollback:

    def test_item_on_rebuilt_unconfirmed_lot_edit_proceeds(self):
        """Mirrors G1/G2's post-rollback coverage: once `POST
        /spare-parts/rollback-lot` clears the lot's confirmed state, the
        item's lot has no confirmed `ReconciliationResult` — the same
        observable shape as an item whose lot was never confirmed, so G4
        does not trigger."""
        item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10)
        item.created_at = datetime.utcnow()
        fake_db = FakeAsyncSession(execute_queue=[[]], get_objects=[item])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"status": "COMPLETE"},
            )

        assert response.status_code == 200
        assert item.status == "COMPLETE"
