"""
tests/superadmin_data/test_order_quick_fix_dates.py — Phase 3 (Order
quick-fix — dates) for `app/api/v1/superadmin_data.py`.

Scope for this batch is ONLY `created_at`/`delivered_at`: search (200/404),
PUT happy path (diff + per-field audit, `status` untouched), and the
unconditional 422 block when the resulting `delivered_at` would precede the
resulting `created_at` (no exceptions, per the spec's "Delivered-Before-
Created Is Blocked Unconditionally" requirement). `mileage_km`/`service_type`
and the confirm-then-delete lifecycle sync are out of scope — Phase 4/5.
"""
import uuid
from datetime import datetime

from tests.conftest import make_test_client
from tests.superadmin_data.conftest import FakeOrderSession, make_order, make_vehicle


def make_superadmin() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def base_payload(created_at: str, delivered_at=None) -> dict:
    return {
        "created_at": created_at,
        "delivered_at": delivered_at,
        "mileage_km": None,
        "service_type": None,
        "confirm_delete_event": False,
    }


# ---------------------------------------------------------------------------
# 3.1 — GET /superadmin/data/orders?plate=&order_id= (join Vehicle)
# ---------------------------------------------------------------------------

def test_search_order_by_order_id_found_returns_200():
    vehicle = make_vehicle(plate="ABC123")
    order = make_order(vehicle=vehicle, created_at=datetime(2026, 7, 1))
    fake_db = FakeOrderSession(get_object=order)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.get("/api/v1/superadmin/data/orders", params={"order_id": str(order.id)})

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == str(order.id)
    assert body["plate"] == "ABC123"
    assert body["created_at"].startswith("2026-07-01")


def test_search_order_by_short_id_prefix_found_returns_200():
    """The app only ever shows the first 8 chars of an order's id to the
    user (PDF filenames, lifecycle summaries, the N.° Orden columns/cards
    added 2026-07-24) — searching with that same short prefix must resolve
    an order, not require pasting the full UUID nobody can see."""
    vehicle = make_vehicle(plate="ABC123")
    order = make_order(vehicle=vehicle, created_at=datetime(2026, 7, 1))
    fake_db = FakeOrderSession(search_result=[order])
    short_id = str(order.id)[:8]

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.get("/api/v1/superadmin/data/orders", params={"order_id": short_id})

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == str(order.id)


def test_search_order_by_short_id_too_short_returns_422():
    fake_db = FakeOrderSession(search_result=[])

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.get("/api/v1/superadmin/data/orders", params={"order_id": "abc"})

    assert res.status_code == 422


def test_search_order_by_plate_found_returns_200():
    vehicle = make_vehicle(plate="ABC123")
    order = make_order(vehicle=vehicle, created_at=datetime(2026, 7, 1))
    fake_db = FakeOrderSession(search_result=[order])

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.get("/api/v1/superadmin/data/orders", params={"plate": "ABC123"})

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == str(order.id)
    assert body["plate"] == "ABC123"


def test_search_order_by_plate_with_multiple_orders_returns_match_list():
    """A plate can have several historical orders (visits). Silently
    correcting the MOST RECENT one when the superadmin meant an older
    visit is a real data-corruption risk — the endpoint must surface all
    matches and let the caller pick, instead of guessing."""
    vehicle = make_vehicle(plate="ABC123")
    older = make_order(vehicle=vehicle, created_at=datetime(2026, 1, 1))
    newer = make_order(vehicle=vehicle, created_at=datetime(2026, 7, 1))
    fake_db = FakeOrderSession(search_result=[newer, older])

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.get("/api/v1/superadmin/data/orders", params={"plate": "ABC123"})

    assert res.status_code == 200
    body = res.json()
    assert body["multiple_matches"] is True
    ids = {m["id"] for m in body["matches"]}
    assert ids == {str(older.id), str(newer.id)}


def test_search_order_miss_returns_404():
    fake_db = FakeOrderSession(search_result=[], get_object=None)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.get("/api/v1/superadmin/data/orders", params={"plate": "ZZZ999"})

    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 3.2 — PUT dates happy path: diff + per-field audit, status untouched
# ---------------------------------------------------------------------------

def test_update_order_dates_happy_path_diffs_and_audits_each_changed_field():
    from app.models.order import ServiceStatus

    order = make_order(
        created_at=datetime(2026, 7, 1),
        delivered_at=datetime(2026, 7, 3),
        status=ServiceStatus.completed,
    )
    fake_db = FakeOrderSession(get_object=order)

    payload = base_payload("2026-07-05T00:00:00", "2026-07-06T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["created_at"].startswith("2026-07-05")
    assert body["delivered_at"].startswith("2026-07-06")

    assert order.status == ServiceStatus.completed  # untouched
    assert fake_db.committed is True

    audit_payloads = [a.payload for a in fake_db.added]
    assert len(audit_payloads) == 2
    changed_fields = {list(p.keys())[0] for p in audit_payloads}
    assert changed_fields == {"created_at", "delivered_at"}
    for row in fake_db.added:
        assert row.action == "SUPERADMIN_DATA_FIX"
        assert row.entity_type == "ServiceOrder"
        assert row.entity_id == str(order.id)
        assert row.shipment_order_id is None


def test_update_order_missing_id_returns_404():
    fake_db = FakeOrderSession(get_object=None)
    payload = base_payload("2026-07-05T00:00:00", None)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{uuid.uuid4()}", json=payload)

    assert res.status_code == 404


def test_update_order_no_op_returns_200_with_no_audit_row():
    order = make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
    fake_db = FakeOrderSession(get_object=order)

    payload = base_payload("2026-07-01T00:00:00", "2026-07-03T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert fake_db.added == []
    assert fake_db.committed is True


# ---------------------------------------------------------------------------
# 3.3 — Unconditional 422 block: delivered_at < created_at, no exceptions
# ---------------------------------------------------------------------------

def test_update_order_new_delivered_at_precedes_existing_created_at_returns_422():
    order = make_order(created_at=datetime(2026, 7, 10), delivered_at=None)
    fake_db = FakeOrderSession(get_object=order)

    # created_at left "unchanged" (resent as-is), delivered_at moved earlier.
    payload = base_payload("2026-07-10T00:00:00", "2026-07-05T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 422
    assert fake_db.added == []
    assert fake_db.committed is False
    assert order.created_at == datetime(2026, 7, 10)
    assert order.delivered_at is None


def test_update_order_new_created_at_moved_after_existing_delivered_at_returns_422():
    order = make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 5))
    fake_db = FakeOrderSession(get_object=order)

    # delivered_at left "unchanged" (resent as-is), created_at moved later.
    payload = base_payload("2026-07-10T00:00:00", "2026-07-05T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 422
    assert fake_db.added == []
    assert fake_db.committed is False
    assert order.created_at == datetime(2026, 7, 1)
    assert order.delivered_at == datetime(2026, 7, 5)


def test_update_order_both_dates_changed_but_order_preserved_returns_200():
    order = make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
    fake_db = FakeOrderSession(get_object=order)

    payload = base_payload("2026-07-05T00:00:00", "2026-07-06T00:00:00")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["created_at"].startswith("2026-07-05")
    assert body["delivered_at"].startswith("2026-07-06")


# ---------------------------------------------------------------------------
# Corrective batch — field-presence-aware partial updates + 422 check must
# compare EFFECTIVE (merged with DB) values, not raw request values.
#
# `delivered_at: Optional[datetime] = None` must NOT be nulled just because
# the request omits the key entirely -- only an explicit `null` clears it.
# ---------------------------------------------------------------------------

def test_update_order_omitted_delivered_at_leaves_db_value_untouched_no_audit():
    order = make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
    fake_db = FakeOrderSession(get_object=order)

    # `delivered_at` key entirely ABSENT -- only `created_at` (required) is
    # sent, unchanged. Must be a true no-op: DB's `delivered_at` untouched,
    # no audit row at all.
    payload = {"created_at": "2026-07-01T00:00:00"}

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["delivered_at"].startswith("2026-07-03")
    assert order.delivered_at == datetime(2026, 7, 3)
    assert fake_db.added == []


def test_update_order_explicit_null_delivered_at_clears_it_and_audits():
    order = make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
    fake_db = FakeOrderSession(get_object=order)

    # `delivered_at` key IS present, explicitly `null` -- the one legitimate
    # way to clear it (e.g. un-deliver a mistakenly-marked order).
    payload = {"created_at": "2026-07-01T00:00:00", "delivered_at": None}

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["delivered_at"] is None
    assert order.delivered_at is None

    audit_payloads = [a.payload for a in fake_db.added]
    assert len(audit_payloads) == 1
    assert audit_payloads[0]["delivered_at"] == {"old": datetime(2026, 7, 3), "new": None}


def test_update_order_created_at_moved_after_existing_delivered_at_returns_422_even_when_delivered_at_omitted():
    # `delivered_at` is NOT part of this request at all -- the 422 check
    # must use the order's EXISTING `delivered_at` from the DB (the
    # "effective" value), not `None`/skip the check just because the
    # request happens to omit that key.
    order = make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 5))
    fake_db = FakeOrderSession(get_object=order)

    payload = {"created_at": "2026-07-10T00:00:00"}

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 422
    assert fake_db.added == []
    assert fake_db.committed is False
    assert order.created_at == datetime(2026, 7, 1)
    assert order.delivered_at == datetime(2026, 7, 5)
