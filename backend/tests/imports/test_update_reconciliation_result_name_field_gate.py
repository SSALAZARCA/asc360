"""
Field-level superadmin gate for the part's Spanish name on
`PATCH /api/v1/imports/reconciliation-results/{result_id}`
(`update_reconciliation_result` + `_apply_item_fields`, `imports.py`) —
`sdd/parts-description-source-of-truth` PR2 (design D8/D9/D10, spec's
"Field-Level Permission Split on Repuestos/Reconciliación Endpoints"
requirement).

Name field for `ReconciliationResultUpdate` = `{"description_es"}` only.

Order note: the pre-existing G2 confirmed-lot freeze
(`declared_snapshot_fields`, `imports.py:1242-1247`) already blocks ANY
role from editing `description_es` once `rr.confirmed_at is not None` —
that guard is evaluated FIRST and is unaffected by this change (see
`test_update_reconciliation_result_guard_regression.py`). The new
superadmin-only name gate only becomes observable on an UNCONFIRMED
result, so every scenario here uses `confirmed_at=None`.

Per design D1/D22: a linked `SparePartItem` (`spare_part_item_id` set)
routes `description_es` through the shared write path
(`set_description_es`, keyed by the item's `part_number`). A pure EXTRA
row (`spare_part_item_id IS NULL`) has no catalog identity and keeps its
existing RR-local `setattr` write — it is NOT routed through the shared
service.
"""
import uuid

import pytest

from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_spare_part_item


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


class TestNameFieldOnlyPayloadNonSuperadminRejected:

    def test_403_nothing_mutated_extra_row(self):
        rr = _make_reconciliation_result(spare_part_item_id=None)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "NAME_EDIT_FORBIDDEN"
        assert rr.description_es is None

    def test_403_nothing_mutated_linked_item(self):
        item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10)
        rr = _make_reconciliation_result(spare_part_item_id=item.id)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr, item])

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "NAME_EDIT_FORBIDDEN"
        assert item.description_es is None


class TestNonNameFieldPayloadNonSuperadminStillAllowed:

    def test_qty_in_packing_still_200(self):
        rr = _make_reconciliation_result(qty_ordered=10)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"qty_in_packing": 10},
            )

        assert response.status_code == 200
        assert rr.qty_in_packing == 10


class TestMixedPayloadNonSuperadminRejectedWhole:

    def test_403_nothing_mutated_including_the_allowed_field(self):
        rr = _make_reconciliation_result(qty_ordered=10)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"qty_in_packing": 5, "description_es": "Nueva descripcion"},
            )

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "NAME_EDIT_FORBIDDEN"
        assert rr.qty_in_packing is None
        assert rr.description_es is None


class TestSuperadminLinkedItemDelegatesToSharedWritePath:

    def test_delegates_and_succeeds(self):
        item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10)
        rr = _make_reconciliation_result(spare_part_item_id=item.id, part_number="PN-001")
        from app.models.parts_manual import PartsReference
        ref = PartsReference(
            factory_part_number="PN-001",
            um_part_number="PN-001",
            description="Original",
            description_es_manual="Old",
            prev_codes=[],
        )
        fake_db = FakeAsyncSession(
            execute_queue=[[ref], []],  # 1) _find_reference_for_part_number hit  2) mirror UPDATE
            get_objects=[rr, item],
        )

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 200
        assert ref.description_es_manual == "Nueva descripcion"

    def test_part_not_in_catalog_propagates_409(self):
        item = make_spare_part_item(lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10)
        rr = _make_reconciliation_result(spare_part_item_id=item.id, part_number="PN-001")
        fake_db = FakeAsyncSession(
            execute_queue=[[], [], []],  # _find_reference_for_part_number's 3 lookup attempts, all miss
            get_objects=[rr, item],
        )

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "PART_NOT_IN_CATALOG"


class TestSuperadminExtraRowKeepsLocalWrite:
    """D1/D22: a pure EXTRA row has no catalog identity, so it must NOT be
    routed through `set_description_es` — no `PartsReference` lookup, no
    409 possible, direct `setattr` as before this change."""

    def test_writes_directly_onto_rr_no_catalog_lookup(self):
        rr = _make_reconciliation_result(spare_part_item_id=None, part_number="PN-EXTRA")
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"description_es": "Desc EXTRA"},
            )

        assert response.status_code == 200
        assert rr.description_es == "Desc EXTRA"


class TestConfirmedResultFreezeTakesPriorityOverNameGate:
    """The pre-existing G2 confirmed-lot freeze fires first, for ANY role
    including superadmin — unaffected by the new name gate."""

    def test_superadmin_still_409_on_confirmed_result(self):
        from datetime import datetime
        rr = _make_reconciliation_result(confirmed_at=datetime.utcnow())
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[rr])

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/reconciliation-results/{rr.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "RESULT_LOT_CONFIRMED"
        assert rr.description_es is None
