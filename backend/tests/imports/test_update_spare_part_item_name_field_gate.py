"""
Field-level superadmin gate for the part's Spanish name on
`PATCH /api/v1/imports/spare-part-items/{item_id}` (`update_spare_part_item`,
`imports.py:1108`) — `sdd/parts-description-source-of-truth` PR2 (design
D8/D9/D10, spec's "Field-Level Permission Split on Repuestos/Reconciliación
Endpoints" requirement).

Name fields for `SparePartItemUpdate` = `{"description", "description_es"}`.
Only `description_es` is delegated to the shared write path
(`parts_description_service.set_description_es`); `description` (the
English text from the PI) stays gated but is still applied via the normal
`setattr` loop — it has no unified-name write path of its own.

Covers:
  - A payload that ONLY touches a name field, submitted by a non-superadmin
    `is_imports_editor`, is rejected 403 `NAME_EDIT_FORBIDDEN` and nothing
    on the item changes.
  - A payload that touches ONLY a non-name field (e.g. `unit_price`) by a
    non-superadmin still succeeds (200) — the endpoint is not locked to
    superadmin-only as a whole.
  - A MIXED payload (name field + non-name field) by a non-superadmin is
    rejected WHOLE (403) — no partial write (D9), unlike a silent field
    drop.
  - A superadmin editing `description_es` delegates to
    `set_description_es`, keyed by the item's `part_number`, and the
    write path's own 409 `PART_NOT_IN_CATALOG` propagates unmodified when
    no matching `PartsReference` exists.
  - Repuestos-tab confirmed-lot exception (spec, no change): editing
    `description_es` as superadmin succeeds even when the item's lot has
    already been confirmed — G4's snapshot-fields freeze does not include
    `description`/`description_es`.
"""
import uuid
from datetime import datetime

import pytest

from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_spare_part_item


def _item_and_db(**item_kwargs):
    item = make_spare_part_item(
        lot_id=uuid.uuid4(), part_number="PN-001", qty_ordered=10, **item_kwargs
    )
    # `SparePartItemRead` requires a non-null `created_at` — the factory
    # doesn't set it (mirrors the existing pattern in
    # `test_update_spare_part_item_guard_regression.py`).
    item.created_at = datetime.utcnow()
    return item


class TestNameFieldOnlyPayloadNonSuperadminRejected:

    @pytest.mark.parametrize("field,value", [("description_es", "Nueva descripcion"), ("description", "New description")])
    def test_403_nothing_mutated(self, field, value):
        """`proveedor` is `is_imports_editor` (passes the outer guard) but
        NOT `is_superadmin`/`is_administrativo` -- still blocked by
        `assert_name_editor` after the 2026-08-24 widening (see
        `TestAdministrativoNowPassesNameGate` below for the role that
        changed)."""
        item = _item_and_db()
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[item])

        with make_test_client(current_user=make_imports_editor(role="proveedor"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={field: value},
            )

        assert response.status_code == 403
        body = response.json()["detail"]
        assert body["code"] == "NAME_EDIT_FORBIDDEN"
        assert getattr(item, field) != value


class TestAdministrativoNowPassesNameGate:
    """2026-08-24 business decision: `assert_name_editor` (shared by
    Maestro de Partes' confirm/dismiss-suggestion endpoints AND this
    Repuestos-tab field-level name gate) now also admits administrativo,
    matching superadmin -- an accepted side effect of widening the shared
    gate, not a Repuestos-tab-specific change."""

    def test_description_es_edit_succeeds(self):
        item = _item_and_db()
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
            get_objects=[item],
        )

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 200
        assert ref.description_es_manual == "Nueva descripcion"


class TestNonNameFieldPayloadNonSuperadminStillAllowed:

    def test_qty_field_still_200(self):
        item = _item_and_db()
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[item])

        with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"unit_price": 12.5},
            )

        assert response.status_code == 200
        assert float(item.unit_price) == 12.5


class TestMixedPayloadNonSuperadminRejectedWhole:

    def test_403_nothing_mutated_including_the_allowed_field(self):
        item = _item_and_db()
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[item])

        with make_test_client(current_user=make_imports_editor(role="proveedor"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"unit_price": 12.5, "description_es": "Nueva descripcion"},
            )

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "NAME_EDIT_FORBIDDEN"
        assert item.unit_price is None
        assert item.description_es is None


class TestSuperadminDescriptionEsDelegatesToSharedWritePath:

    def test_delegates_and_succeeds(self):
        item = _item_and_db()
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
            get_objects=[item],
        )

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 200
        assert ref.description_es_manual == "Nueva descripcion"

    def test_english_description_only_applies_via_normal_setattr_no_write_path_call(self):
        item = _item_and_db()
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[item])

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"description": "New description"},
            )

        assert response.status_code == 200
        assert item.description == "New description"

    def test_part_not_in_catalog_propagates_409(self):
        item = _item_and_db()
        fake_db = FakeAsyncSession(
            execute_queue=[[], [], []],  # _find_reference_for_part_number's 3 lookup attempts, all miss
            get_objects=[item],
        )

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "PART_NOT_IN_CATALOG"


class TestRepuestosTabStaysEditableAfterLotConfirmed:
    """Regression (spec's 'Repuestos-Tab Confirmed-Lot Exception (No Change)'
    requirement): this change must NOT extend Reconciliación's confirmed-lot
    freeze to the Repuestos tab. `description`/`description_es` are not in
    G4's `snapshot_fields`, so a confirmed lot never blocks this edit."""

    def test_superadmin_edit_succeeds_on_confirmed_lot_item(self):
        item = _item_and_db()
        from app.models.parts_manual import PartsReference
        ref = PartsReference(
            factory_part_number="PN-001",
            um_part_number="PN-001",
            description="Original",
            description_es_manual="Old",
            prev_codes=[],
        )
        # No `lot_has_confirmed_reconciliation` query is queued because G4
        # never fires for a description-only payload — this queue only
        # covers `set_description_es`'s two `db.execute` calls.
        fake_db = FakeAsyncSession(execute_queue=[[ref], []], get_objects=[item])

        with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
            response = client.patch(
                f"/api/v1/imports/spare-part-items/{item.id}",
                json={"description_es": "Nueva descripcion"},
            )

        assert response.status_code == 200
        assert ref.description_es_manual == "Nueva descripcion"
