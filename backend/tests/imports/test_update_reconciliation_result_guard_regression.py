"""
Regression tests for the G2 guard on `update_reconciliation_result`
(`PATCH /api/v1/imports/reconciliation-results/{result_id}`, `imports.py`).

Bug prevented: editing a packing-list-DECLARED field (`part_number`,
`description_es`, `model_applicable`, `qty_in_packing`) on a
`ReconciliationResult` whose lot has already been confirmed silently
desyncs the confirmed snapshot — the same corruption class G1/G3 close for
re-uploads. The guard is FIELD-SCOPED: it must NOT block `qty_physical`,
because physical inspection is a later stage that happens AFTER
confirmation and has its own `packing_list_received` gate (owned by the
sibling change `reconciliation-result-qty-physical-fix`).

Covers (per spec's "Inline Edit of a ReconciliationResult Rejected
(Field-Scoped) When Its Lot Is Already Confirmed" requirement):
  - Each declared field (`part_number`, `description_es`,
    `model_applicable`, `qty_in_packing`) is rejected 409 on a confirmed
    result for a superadmin (directive rollback message) and for a
    non-superadmin editor (contact-an-administrator message).
  - A `qty_physical`-only payload on a confirmed result is NOT blocked by
    G2 — it reaches the downstream `qty_physical` branch untouched. That
    branch's own correctness (linked-item vs. EXTRA-row handling) is owned
    and covered by the sibling change `reconciliation-result-qty-physical-fix`.
  - A payload mixing a declared field with `qty_physical` is rejected
    whole (409), nothing applied — matches the "simpler is safer" design
    choice, safe because `EditableReconciliationCell` only ever submits
    one field per request.
  - Any field is applied normally on an unconfirmed result (today's
    behavior, unaffected).
  - A missing result still 404s (guard does not mask NOT_FOUND).
  - Editing a declared field succeeds again on a row rebuilt after
    rollback (fresh `confirmed_at=None` row — mirrors G1's post-rollback
    coverage).
"""
import uuid
from datetime import datetime

import pytest

from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_lot, make_spare_part_item


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
        confirmed_at=None,
    )
    defaults.update(kwargs)
    return ReconciliationResult(**defaults)


# Each declared field, its new value, and the ORIGINAL value the row must
# still hold after a rejected request (proves nothing was mutated).
_DECLARED_FIELD_CASES = [
    ("part_number", "PN-999", "PN-001"),
    ("description_es", "Nueva descripcion", None),
    ("model_applicable", "MODEL-X", None),
    ("qty_in_packing", 5, None),
]


class TestDeclaredFieldEditRejectedOnConfirmedResultSuperadmin:

    @pytest.mark.parametrize("field,new_value,original_value", _DECLARED_FIELD_CASES)
    def test_each_declared_field_409_directive_message(self, field, new_value, original_value):
        rr = _make_reconciliation_result(confirmed_at=datetime.utcnow())
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={field: new_value},
            )

        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["code"] == "RESULT_LOT_CONFIRMED"
        assert "rollback" in body["detail"].lower()
        assert getattr(rr, field) == original_value


class TestDeclaredFieldEditRejectedOnConfirmedResultNonSuperadmin:

    @pytest.mark.parametrize("field,new_value,original_value", _DECLARED_FIELD_CASES)
    def test_each_declared_field_409_points_to_administrator(self, field, new_value, original_value):
        rr = _make_reconciliation_result(confirmed_at=datetime.utcnow())
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={field: new_value},
            )

        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["code"] == "RESULT_LOT_CONFIRMED"
        assert "administrador" in body["detail"].lower()
        # Non-superadmin message must not name the rollback route as a
        # self-service action.
        assert "rollback-lot" not in body["detail"]
        assert getattr(rr, field) == original_value


class TestQtyPhysicalOnlyNotBlockedByG2:
    """Proves G2's field-scoping: a qty_physical-only payload must NEVER be
    intercepted by the 409, even on a confirmed result. What happens
    downstream (the qty_physical branch's own gate/bug) is deliberately out
    of scope for this guard."""

    def test_confirmed_result_lot_not_packing_list_received_hits_downstream_400_not_g2(self):
        """`_apply_qty_physical` has its own `packing_list_received` gate.
        If G2 wrongly intercepted qty_physical, this would be a 409 with
        code RESULT_LOT_CONFIRMED instead of the downstream 400."""
        lot = make_lot(packing_list_received=False)
        rr = _make_reconciliation_result(lot_id=lot.id, confirmed_at=datetime.utcnow())
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, lot])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"qty_physical": 5},
            )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "RECONCILIATION_NOT_CONFIRMED"

    def test_confirmed_result_lot_packing_list_received_reaches_downstream_branch_not_g2(self):
        """With `packing_list_received=True`, the request reaches
        `_apply_qty_physical` untouched by G2 (fixed by sibling change
        `reconciliation-result-qty-physical-fix`: this is a pure EXTRA row,
        so the value is stored directly on `rr.qty_physical` with no
        `SparePartItem` sync). This test only proves G2 did NOT add a 409
        in front of it; a 409 would have short-circuited before reaching
        the downstream branch at all."""
        lot = make_lot(packing_list_received=True)
        rr = _make_reconciliation_result(lot_id=lot.id, confirmed_at=datetime.utcnow())
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, lot])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"qty_physical": 5},
            )

        assert response.status_code == 200
        assert rr.qty_physical == 5


class TestMixedDeclaredAndQtyPhysicalPayloadRejectedWhole:

    def test_mixed_payload_409_nothing_applied(self):
        rr = _make_reconciliation_result(confirmed_at=datetime.utcnow())
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"part_number": "PN-999", "qty_physical": 5},
            )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "RESULT_LOT_CONFIRMED"
        assert rr.part_number == "PN-001"
        assert rr.qty_physical is None


class TestDeclaredFieldEditAllowedOnUnconfirmedResult:

    def test_blocked_fields_still_apply_normally_when_not_confirmed(self):
        item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-OLD", qty_ordered=10)
        rr = _make_reconciliation_result(spare_part_item_id=item.id, part_number="PN-OLD", confirmed_at=None)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, item])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"part_number": "PN-999", "description_es": "Nueva", "model_applicable": "MODEL-X"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["part_number"] == "PN-999"
        assert item.part_number == "PN-999"


class TestMissingResultStill404s:

    def test_missing_result_returns_404_not_masked_by_guard(self):
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{uuid.uuid4()}",
                json={"part_number": "PN-999"},
            )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "NOT_FOUND"


class TestDeclaredFieldEditAllowedAgainAfterRollback:

    def test_rebuilt_row_after_rollback_is_unconfirmed_edit_proceeds(self):
        """Mirrors G1's post-rollback coverage: once `POST
        /spare-parts/rollback-lot` clears the lot's confirmed state and it
        is rebuilt via re-import, the new `ReconciliationResult` row has
        `confirmed_at=None` — the same observable shape as a never-confirmed
        row, so G2 does not trigger."""
        rr = _make_reconciliation_result(confirmed_at=None)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"qty_in_packing": 7},
            )

        assert response.status_code == 200
        assert rr.qty_in_packing == 7
