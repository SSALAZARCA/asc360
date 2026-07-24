"""
tests/superadmin_data/test_order_service_type_confirm_delete.py — Phase 5
(confirm-then-delete flow) for `app/api/v1/superadmin_data.py`.

Scope: the ONE remaining `service_type` transition -- correcting AWAY from
an event-producing type (warranty/km_review) to a non-event type (regular/
quick/pdi), on an order whose completion event (GARANTIA/MANTENIMIENTO)
already exists. Unlike the warranty<->km_review auto-remap (Phase 4, no
confirmation needed), this transition DELETES history, so it must go
through an explicit two-step confirm-then-delete flow:
1. First request without `confirm_delete_event` -> 409 `CONFIRM_DELETE_EVENT`,
   zero writes (dry-run), no audit row.
2. Second request with `confirm_delete_event: true` -> 200, the stale event
   is deleted AND the field changes are applied in the SAME transaction,
   with an audit row carrying a `lifecycle_event_deleted` marker.
"""
import uuid
from decimal import Decimal
from datetime import datetime

from tests.conftest import make_test_client
from tests.superadmin_data.conftest import (
    FakeOrderSession,
    make_order,
    make_vehicle,
    make_reception,
    make_lifecycle_event,
)


def make_superadmin() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def order_payload(
    created_at: str = "2026-07-01T00:00:00",
    delivered_at=None,
    mileage_km=None,
    service_type=None,
    confirm_delete_event: bool = False,
) -> dict:
    return {
        "created_at": created_at,
        "delivered_at": delivered_at,
        "mileage_km": mileage_km,
        "service_type": service_type,
        "confirm_delete_event": confirm_delete_event,
    }


# ---------------------------------------------------------------------------
# 5.1 — away-from-event-type WITHOUT confirm_delete_event -> 409, zero writes
# ---------------------------------------------------------------------------

def test_away_from_event_type_without_confirmation_returns_409_and_applies_nothing():
    from app.models.order import ServiceStatus, ServiceType
    from app.models.vehicle_lifecycle import LifecycleEventType

    vehicle = make_vehicle(plate="XYZ789")
    order = make_order(
        vehicle=vehicle,
        created_at=datetime(2026, 7, 1),
        status=ServiceStatus.completed,
        service_type=ServiceType.km_review,
    )
    reception = make_reception(order_id=order.id, mileage_km=15000)
    mantenimiento_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.MANTENIMIENTO,
        km_at_event=Decimal("15000"),
        summary=f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(
        get_object=order, reception=reception, lifecycle_events=[mantenimiento_event]
    )

    payload = order_payload(service_type="regular")  # confirm_delete_event omitted -> False

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 409
    body = res.json()["detail"]
    assert body["code"] == "CONFIRM_DELETE_EVENT"
    assert "MANTENIMIENTO" in body["detail"]
    assert str(mantenimiento_event.id) in body["detail"]
    assert "XYZ789" in body["detail"]

    # Zero side effects: not even the order's service_type, not the event.
    assert order.service_type == ServiceType.km_review
    assert mantenimiento_event.event_type == LifecycleEventType.MANTENIMIENTO
    assert fake_db.added == []
    assert fake_db.deleted == []
    assert fake_db.committed is False


def test_away_from_event_type_without_confirmation_rejects_whole_request_including_dates():
    """The 409 rejects the WHOLE request -- an unrelated `created_at` change
    bundled in the same payload must NOT be applied either (no partial
    apply, per spec's intent)."""
    from app.models.order import ServiceStatus, ServiceType
    from app.models.vehicle_lifecycle import LifecycleEventType

    vehicle = make_vehicle(plate="ABC999")
    order = make_order(
        vehicle=vehicle,
        created_at=datetime(2026, 7, 1),
        status=ServiceStatus.completed,
        service_type=ServiceType.warranty,
    )
    reception = make_reception(order_id=order.id, mileage_km=8000)
    garantia_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.GARANTIA,
        km_at_event=None,
        summary=f"Garantía aplicada. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(
        get_object=order, reception=reception, lifecycle_events=[garantia_event]
    )

    payload = order_payload(created_at="2026-07-02T00:00:00", service_type="quick")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 409
    assert order.created_at == datetime(2026, 7, 1)  # untouched despite being in the payload
    assert order.service_type == ServiceType.warranty
    assert fake_db.added == []


# ---------------------------------------------------------------------------
# 5.2 — away-from-event-type WITH confirm_delete_event=true -> 200, deletes
# the event, applies field changes, single transaction, audits the deletion
# ---------------------------------------------------------------------------

def test_away_from_event_type_with_confirmation_deletes_event_and_applies_change():
    from app.models.order import ServiceStatus, ServiceType
    from app.models.vehicle_lifecycle import LifecycleEventType

    vehicle = make_vehicle(plate="XYZ789")
    order = make_order(
        vehicle=vehicle,
        created_at=datetime(2026, 7, 1),
        status=ServiceStatus.completed,
        service_type=ServiceType.km_review,
    )
    reception = make_reception(order_id=order.id, mileage_km=15000)
    mantenimiento_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.MANTENIMIENTO,
        km_at_event=Decimal("15000"),
        summary=f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(
        get_object=order, reception=reception, lifecycle_events=[mantenimiento_event]
    )

    payload = order_payload(service_type="regular", confirm_delete_event=True)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["service_type"] == "regular"

    assert order.service_type == ServiceType.regular
    assert fake_db.deleted == [mantenimiento_event]
    assert fake_db.committed is True

    audit = next(a.payload["service_type"] for a in fake_db.added if "service_type" in a.payload)
    # Plain enum members aren't JSON-serializable -- ImportAuditLog.payload
    # is a real JSONB column, so the audit dict must hold `.value` strings,
    # not the enum objects themselves (this crashed with a 500 in
    # production against a real DB; the fakes here never serialize
    # anything, so this assertion is the only thing that catches it).
    assert audit["old"] == "km_review"
    assert audit["new"] == "regular"
    assert audit["lifecycle_event_deleted"] == {
        "id": str(mantenimiento_event.id),
        "event_type": "MANTENIMIENTO",
        "summary": f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}.",
    }
    assert "lifecycle_event_synced" not in audit


def test_away_from_event_type_with_confirmation_garantia_variant_also_deletes():
    from app.models.order import ServiceStatus, ServiceType
    from app.models.vehicle_lifecycle import LifecycleEventType

    vehicle = make_vehicle(plate="GAR001")
    order = make_order(
        vehicle=vehicle,
        created_at=datetime(2026, 7, 1),
        status=ServiceStatus.completed,
        service_type=ServiceType.warranty,
    )
    reception = make_reception(order_id=order.id, mileage_km=9000)
    garantia_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.GARANTIA,
        km_at_event=None,
        summary=f"Garantía aplicada. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(
        get_object=order, reception=reception, lifecycle_events=[garantia_event]
    )

    payload = order_payload(service_type="pdi", confirm_delete_event=True)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert order.service_type == ServiceType.pdi
    assert fake_db.deleted == [garantia_event]

    audit = next(a.payload["service_type"] for a in fake_db.added if "service_type" in a.payload)
    assert audit["lifecycle_event_deleted"]["event_type"] == "GARANTIA"


# ---------------------------------------------------------------------------
# 5.3 — confirmed request, event already gone (race) -> fields applied,
# no delete marker written
# ---------------------------------------------------------------------------

def test_confirmed_request_when_event_already_gone_applies_fields_without_delete_marker():
    from app.models.order import ServiceStatus, ServiceType

    order = make_order(
        created_at=datetime(2026, 7, 1),
        status=ServiceStatus.completed,
        service_type=ServiceType.km_review,
    )
    reception = make_reception(order_id=order.id, mileage_km=15000)
    # No lifecycle events at all -- simulates the completion event having
    # already been deleted (e.g. a concurrent request) by the time THIS
    # request's fresh lookup runs.
    fake_db = FakeOrderSession(get_object=order, reception=reception, lifecycle_events=[])

    payload = order_payload(service_type="regular", confirm_delete_event=True)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert order.service_type == ServiceType.regular
    assert fake_db.deleted == []  # nothing to delete
    assert fake_db.committed is True

    audit = next(a.payload["service_type"] for a in fake_db.added if "service_type" in a.payload)
    assert "lifecycle_event_deleted" not in audit
    assert "lifecycle_event_synced" not in audit


# ---------------------------------------------------------------------------
# 5.4 — forced DB error rolls back field change AND event delete/sync
# (atomicity: single commit boundary covers everything)
# ---------------------------------------------------------------------------

def test_forced_db_error_leaves_nothing_committed_field_and_event_change_together():
    from app.models.order import ServiceStatus, ServiceType
    from app.models.vehicle_lifecycle import LifecycleEventType

    vehicle = make_vehicle(plate="ATOM01")
    order = make_order(
        vehicle=vehicle,
        created_at=datetime(2026, 7, 1),
        status=ServiceStatus.completed,
        service_type=ServiceType.km_review,
    )
    reception = make_reception(order_id=order.id, mileage_km=15000)
    mantenimiento_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.MANTENIMIENTO,
        km_at_event=Decimal("15000"),
        summary=f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(
        get_object=order,
        reception=reception,
        lifecycle_events=[mantenimiento_event],
        raise_integrity_error=True,
    )

    # Bundles a mileage_km change (would resync RECEPCION/completion km) with
    # the service_type deletion in ONE request -- both must be undone
    # together if the single `db.commit()` at the end fails.
    payload = order_payload(mileage_km=15500, service_type="regular", confirm_delete_event=True)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    # The route catches IntegrityError around its single commit() call --
    # covering dates + mileage + service_type + event delete -- and rolls
    # back atomically instead of leaking a raw 500, mirroring
    # `update_vehicle`'s existing IntegrityError->409 handling.
    assert res.status_code == 409
    assert fake_db.committed is False
    assert fake_db.rolled_back is True
