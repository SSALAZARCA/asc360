"""
Regression tests for `search_spare_parts` (`GET /api/v1/imports/spare-parts/search`,
`imports.py`).

Bug fixed: the search only queried `SparePartItem`, so a part number that
arrived as a pure packing-list "extra" (a `ReconciliationResult` row with
`spare_part_item_id=None` — never ordered, so it has no `SparePartItem`)
was invisible to the search in EVERY lot, including its own. A user could
search a reference, get zero results, and wrongly conclude it doesn't
exist anywhere in the system.

Covers:
  - Ordered items still match by `part_number` (existing behavior, unchanged).
  - A pure "extra" reconciliation row now matches too, surfaced under its
    own lot with `status="EXTRA"`, `qty_ordered=0`, `qty_received` taken
    from `qty_in_packing`.
  - Both kinds of matches for the same query are merged under the correct
    lot rather than only one being returned.

`sdd/parts-description-source-of-truth` PR4 (R5, design D11-D14): the
ordered-item branch now issues ONE additional `resolve_names` query
(right after the `SparePartItem` join, before the `ReconciliationResult`
EXTRA join) to live-resolve `description_es` against the catalog's
`description_es_manual` -- see `test_live_read_description_es.py
::TestR5SearchSpareParts` for the dedicated manual-name-wins coverage.
The EXTRA branch is explicitly NOT resolved (no catalog identity, D1/D22),
so `test_pure_extra_reference_is_now_found` is unaffected.
"""
from app.api.v1 import imports as imports_module
from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_imports_editor,
    make_lot,
    make_reconciliation_result,
    make_spare_part_item,
)


def test_ordered_item_match_is_returned():
    lot = make_lot(lot_identifier="S05066")
    item = make_spare_part_item(lot_id=lot.id, part_number="ABC123", qty_ordered=5, qty_received=5, status="RECEIVED")

    fake_db = FakeAsyncSession(execute_queue=[
        [(item, lot)],  # SparePartItem join
        [],             # resolve_names -- no PartsReference match, stored value stays
        [],             # ReconciliationResult EXTRA join
    ])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        resp = client.get("/api/v1/imports/spare-parts/search", params={"q": "ABC123"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["lot_identifier"] == "S05066"
    assert body[0]["items"] == [{
        "part_number": "ABC123",
        "description_es": None,
        "qty_ordered": 5,
        "qty_received": 5,
        "status": "RECEIVED",
    }]


def test_pure_extra_reference_is_now_found():
    lot = make_lot(lot_identifier="S05066")
    rr = make_reconciliation_result(
        lot_id=lot.id,
        part_number="S05066EXTRA",
        result="EXTRA",
        spare_part_item_id=None,
        description_es="Pieza no pedida",
        qty_in_packing=3,
    )

    fake_db = FakeAsyncSession(execute_queue=[
        [],          # SparePartItem join — no ordered item exists for this part
        [(rr, lot)],  # ReconciliationResult EXTRA join
    ])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        resp = client.get("/api/v1/imports/spare-parts/search", params={"q": "S05066EXTRA"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["lot_identifier"] == "S05066"
    assert body[0]["items"] == [{
        "part_number": "S05066EXTRA",
        "description_es": "Pieza no pedida",
        "qty_ordered": 0,
        "qty_received": 3,
        "status": "EXTRA",
    }]


def test_ordered_item_and_extra_in_different_lots_both_returned_separately():
    lot_a = make_lot(lot_identifier="LOTE-A")
    lot_b = make_lot(lot_identifier="LOTE-B")
    item = make_spare_part_item(lot_id=lot_a.id, part_number="XYZ", qty_ordered=2, qty_received=0, status="PENDING")
    rr = make_reconciliation_result(lot_id=lot_b.id, part_number="XYZ", result="EXTRA", qty_in_packing=1)

    fake_db = FakeAsyncSession(execute_queue=[
        [(item, lot_a)],
        [],              # resolve_names -- no PartsReference match
        [(rr, lot_b)],
    ])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        resp = client.get("/api/v1/imports/spare-parts/search", params={"q": "XYZ"})

    assert resp.status_code == 200
    body = resp.json()
    lots_by_id = {b["lot_identifier"]: b for b in body}
    assert set(lots_by_id) == {"LOTE-A", "LOTE-B"}
    assert lots_by_id["LOTE-A"]["items"][0]["status"] == "PENDING"
    assert lots_by_id["LOTE-B"]["items"][0]["status"] == "EXTRA"


def test_query_too_short_returns_422_without_hitting_db():
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        resp = client.get("/api/v1/imports/spare-parts/search", params={"q": "a"})

    assert resp.status_code == 422
    assert fake_db.executed_statements == []
