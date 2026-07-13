"""
RED regression tests for `list_spare_part_lots`
(`GET /api/v1/imports/spare-part-lots`) capturing CURRENT (pre-refactor)
behavior — Phase 1 of `sdd/imports-oversized-functions-refactor-tier1`.

These exercise the endpoint via the HTTP harness (`make_test_client`) +
`FakeAsyncSession` and MUST keep passing unchanged after the extraction
(task 1.3 delegates to `_apply_lot_filters`/`_build_rotation_map`/
`_build_lot_summary`) — same file, same assertions, only the endpoint's
internals change.

Filter tests inspect `FakeAsyncSession.executed_statements` (compiled SQL +
bound params) rather than DB rows, since the fake ignores WHERE clauses when
deciding what to return — this is the only way to lock in filter semantics
without a live database.
"""
import uuid
from types import SimpleNamespace

from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_actor,
    make_imports_editor,
    make_lot,
    make_spare_part_item,
)


def test_non_editor_role_gets_403():
    """`make_actor()` (role=jefe_taller) is not an imports editor -> 403, no DB call."""
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/spare-part-lots")

    assert response.status_code == 403
    assert response.json()["detail"] == "Sin permisos para el módulo de importaciones"
    assert fake_db.executed_statements == []


def test_lot_summary_fields_computed_from_items():
    """
    One lot with a confirmed-price item, a fob_pi-only (estimate) item, and a
    CANCELLED item — locks in items_count, total_qty_ordered, pct_received,
    models, fob_value/fob_value_is_estimate, pl_value, and rotation_pct
    (including the `sin_clasificar` bucket) exactly as computed today.
    """
    lot = make_lot(packing_list_received=True)
    item_a = make_spare_part_item(
        lot.id, "PN-A", qty_ordered=5, qty_received=3, status="RECEIVED",
        unit_price=10, model_applicable="M1",
    )
    item_b = make_spare_part_item(
        lot.id, "PN-B", qty_ordered=2, qty_received=0, status="PENDING",
        fob_pi=8, model_applicable="M2",
    )
    item_c = make_spare_part_item(
        lot.id, "PN-C", qty_ordered=100, qty_received=50, status="CANCELLED",
        unit_price=999,
    )
    lot.items = [item_a, item_b, item_c]

    fake_db = FakeAsyncSession(execute_queue=[
        [lot],
        [SimpleNamespace(factory_part_number="PN-A", rotation_class="FAST")],
        [],  # _build_confirmed_lot_ids: no confirmed ReconciliationResult for this lot
    ])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/spare-part-lots")

    assert response.status_code == 200
    body = response.json()[0]
    assert body["items_count"] == 3
    assert body["total_qty_ordered"] == 107
    assert body["pct_received"] == 49.5
    assert body["models"] == ["M1", "M2"]
    assert body["fob_value"] == 66.0
    assert body["fob_value_is_estimate"] is True
    assert body["pl_value"] == 30.0
    assert body["rotation_pct"] == {"FAST": 33.3, "sin_clasificar": 66.7}
    assert body["reconciliation_confirmed"] is False


def test_lot_with_no_items_keeps_schema_defaults():
    """`lot.items == []` -> no rotation-map query, all computed fields stay at schema defaults."""
    lot = make_lot()
    lot.items = []
    fake_db = FakeAsyncSession(execute_queue=[
        [lot],
        [],  # _build_confirmed_lot_ids: still queried even with zero items (queries by lot_id, not lot.items)
    ])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/spare-part-lots")

    assert response.status_code == 200
    body = response.json()[0]
    assert body["items_count"] == 0
    assert body["total_qty_ordered"] == 0
    assert body["pct_received"] == 0.0
    assert body["models"] == []
    assert body["fob_value"] is None
    assert body["fob_value_is_estimate"] is False
    assert body["pl_value"] is None
    assert body["rotation_pct"] == {}
    assert body["reconciliation_confirmed"] is False


def test_shipment_order_id_filter_binds_the_uuid_param():
    sid = uuid.uuid4()
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get(
            "/api/v1/imports/spare-part-lots", params={"shipment_order_id": str(sid)}
        )

    assert response.status_code == 200
    compiled = fake_db.executed_statements[0].compile()
    assert sid in compiled.params.values()


def test_detail_loaded_true_filter_binds_boolean_param():
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get(
            "/api/v1/imports/spare-part-lots", params={"detail_loaded": "true"}
        )

    assert response.status_code == 200
    compiled = fake_db.executed_statements[0].compile()
    assert True in compiled.params.values()


def test_detail_loaded_false_filter_binds_boolean_param():
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get(
            "/api/v1/imports/spare-part-lots", params={"detail_loaded": "false"}
        )

    assert response.status_code == 200
    compiled = fake_db.executed_statements[0].compile()
    assert False in compiled.params.values()


def test_has_bl_true_filter_requires_non_placeholder_bl_container():
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/spare-part-lots", params={"has_bl": "true"})

    assert response.status_code == 200
    compiled = fake_db.executed_statements[0].compile()
    sql = str(compiled)
    assert "shipment_orders" in sql
    assert "IS NOT NULL" in sql
    assert "IS NULL" not in sql
    assert set(compiled.params.values()) == {"", "PENDING", "TBD"}


def test_has_bl_false_filter_matches_placeholder_bl_container():
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/spare-part-lots", params={"has_bl": "false"})

    assert response.status_code == 200
    compiled = fake_db.executed_statements[0].compile()
    sql = str(compiled)
    assert "shipment_orders" in sql
    assert "IS NULL" in sql
    assert "IS NOT NULL" not in sql
    assert set(compiled.params.values()) == {"", "PENDING", "TBD"}


class TestReconciliationConfirmedSignal:
    """Regression tests for the G6-adjacent `reconciliation_confirmed`
    field (see sdd/packing-list-reupload-requires-rollback, Phase 6): the
    batched `_build_confirmed_lot_ids` helper, wired into
    `_build_lot_summary`/`list_spare_part_lots`, replaces the frontend's
    previous (wrong) use of `packing_list_received` as the confirmed
    signal."""

    def test_each_lot_gets_its_own_correct_flag_via_a_single_batched_query(self):
        """Two lots, only one confirmed — proves per-lot correctness AND
        that the check is a single batched query, not one-per-lot (N+1):
        with zero items on both lots, `_build_rotation_map` never executes
        (early-returns on an empty part-number set), so exactly 2
        `db.execute()` calls total are expected: the lots query and ONE
        confirmed-lot-ids query covering both lots."""
        lot_a = make_lot(lot_identifier="LOT-A")
        lot_a.items = []
        lot_b = make_lot(lot_identifier="LOT-B")
        lot_b.items = []
        fake_db = FakeAsyncSession(execute_queue=[
            [lot_a, lot_b],
            [lot_b.id],  # only lot_b has a confirmed ReconciliationResult
        ])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get("/api/v1/imports/spare-part-lots")

        assert response.status_code == 200
        body = response.json()
        by_id = {row["id"]: row for row in body}
        assert by_id[str(lot_a.id)]["reconciliation_confirmed"] is False
        assert by_id[str(lot_b.id)]["reconciliation_confirmed"] is True
        assert len(fake_db.executed_statements) == 2

    def test_no_lots_skips_the_confirmed_lot_ids_query_entirely(self):
        """Zero-cost when inapplicable — mirrors G4's field-scoped guard
        pattern: an empty lot list must not issue the confirmed-lot-ids
        query at all."""
        fake_db = FakeAsyncSession(execute_queue=[[]])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.get("/api/v1/imports/spare-part-lots")

        assert response.status_code == 200
        assert response.json() == []
        assert len(fake_db.executed_statements) == 1
