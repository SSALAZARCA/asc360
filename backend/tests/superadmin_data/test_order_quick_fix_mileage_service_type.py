"""
tests/superadmin_data/test_order_quick_fix_mileage_service_type.py — Phase 4
(mileage_km/service_type + RECEPCION/completion lifecycle event sync) for
`app/api/v1/superadmin_data.py`.

Scope for this batch: `mileage_km` (lives on `ServiceOrderReception`) and
`service_type` persist and, when they change, keep the linked lifecycle
events (`RECEPCION`, always; `GARANTIA`/`MANTENIMIENTO`, if a completion
event already exists) in sync -- ONLY the warranty<->km_review auto-remap
case for `service_type`. The away-from-event-producing-type case (which
requires the confirm-then-delete flow) is explicitly out of scope here --
it lands in Phase 5.
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
# 4.1 — mileage_km/service_type persist to reception/order, status unchanged
# ---------------------------------------------------------------------------

def test_update_order_mileage_and_service_type_persist_status_unchanged():
    from app.models.order import ServiceStatus, ServiceType

    order = make_order(
        created_at=datetime(2026, 7, 1),
        status=ServiceStatus.in_progress,
        service_type=ServiceType.regular,
    )
    reception = make_reception(order_id=order.id, mileage_km=1000)
    fake_db = FakeOrderSession(get_object=order, reception=reception, lifecycle_events=[])

    payload = order_payload(mileage_km=1500, service_type="quick")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["mileage_km"] == "1500"
    assert body["service_type"] == "quick"

    assert order.status == ServiceStatus.in_progress  # untouched
    assert reception.mileage_km == Decimal("1500")
    assert order.service_type == ServiceType.quick
    assert fake_db.committed is True

    audit_by_field = {list(a.payload.keys())[0]: a.payload for a in fake_db.added}
    assert set(audit_by_field.keys()) == {"mileage_km", "service_type"}
    assert audit_by_field["mileage_km"]["mileage_km"]["old"] == Decimal("1000")
    assert audit_by_field["mileage_km"]["mileage_km"]["new"] == Decimal("1500")
    assert audit_by_field["service_type"]["service_type"]["old"] == ServiceType.regular
    assert audit_by_field["service_type"]["service_type"]["new"] == ServiceType.quick
    for row in fake_db.added:
        assert row.action == "SUPERADMIN_DATA_FIX"
        assert row.entity_type == "ServiceOrder"


def test_update_order_mileage_no_op_writes_no_audit_row():
    order = make_order(created_at=datetime(2026, 7, 1))
    reception = make_reception(order_id=order.id, mileage_km=1000)
    fake_db = FakeOrderSession(get_object=order, reception=reception, lifecycle_events=[])

    payload = order_payload(mileage_km=1000)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert fake_db.added == []
    assert fake_db.committed is True


def test_update_order_omitted_mileage_and_service_type_leave_them_untouched():
    """Backward-compat guard: `mileage_km`/`service_type` are NOT NULL at the
    DB level (unlike `delivered_at`) -- an explicit `null` (or an omitted
    key) must never attempt to clear them, and must not trigger the
    reception/lifecycle-events queries at all."""
    from app.models.order import ServiceType

    order = make_order(created_at=datetime(2026, 7, 1), service_type=ServiceType.regular)
    fake_db = FakeOrderSession(get_object=order)  # no reception/lifecycle_events configured

    payload = {"created_at": "2026-07-01T00:00:00", "mileage_km": None, "service_type": None}

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert order.service_type == ServiceType.regular
    assert fake_db.added == []


# ---------------------------------------------------------------------------
# 4.2 — RECEPCION km_at_event + summary sync (in-progress AND completed order)
# ---------------------------------------------------------------------------

def test_update_order_mileage_change_syncs_recepcion_event_in_progress_order():
    from app.models.order import ServiceStatus
    from app.models.vehicle_lifecycle import LifecycleEventType

    order = make_order(created_at=datetime(2026, 7, 1), status=ServiceStatus.in_progress)
    reception = make_reception(order_id=order.id, mileage_km=10000)
    recepcion_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.RECEPCION,
        km_at_event=Decimal("10000"),
        summary="Recepción en taller. KM: 10000. Cliente: Juan Pérez.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(get_object=order, reception=reception, lifecycle_events=[recepcion_event])

    payload = order_payload(mileage_km=10500)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert recepcion_event.km_at_event == Decimal("10500")
    assert recepcion_event.summary == "Recepción en taller. KM: 10500. Cliente: Juan Pérez."
    assert fake_db.committed is True

    audit = next(a.payload["mileage_km"] for a in fake_db.added if "mileage_km" in a.payload)
    assert audit["lifecycle_event_synced"] == [str(recepcion_event.id)]


def test_update_order_mileage_change_syncs_recepcion_event_on_completed_order():
    from app.models.order import ServiceStatus
    from app.models.vehicle_lifecycle import LifecycleEventType

    order = make_order(created_at=datetime(2026, 7, 1), status=ServiceStatus.completed)
    reception = make_reception(order_id=order.id, mileage_km=20000)
    recepcion_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.RECEPCION,
        km_at_event=Decimal("20000"),
        summary="Recepción en taller. KM: 20000. Cliente: Ana.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(get_object=order, reception=reception, lifecycle_events=[recepcion_event])

    payload = order_payload(mileage_km=20500)

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert recepcion_event.km_at_event == Decimal("20500")
    assert recepcion_event.summary == "Recepción en taller. KM: 20500. Cliente: Ana."
    assert order.status == ServiceStatus.completed  # untouched


# ---------------------------------------------------------------------------
# 4.3 — completion event (MANTENIMIENTO) km resync when service_type unchanged
# ---------------------------------------------------------------------------

def test_update_order_mileage_change_resyncs_mantenimiento_completion_event_km():
    from app.models.order import ServiceStatus, ServiceType
    from app.models.vehicle_lifecycle import LifecycleEventType

    order = make_order(
        created_at=datetime(2026, 7, 1), status=ServiceStatus.completed, service_type=ServiceType.km_review
    )
    reception = make_reception(order_id=order.id, mileage_km=15000)
    recepcion_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.RECEPCION,
        km_at_event=Decimal("15000"),
        summary="Recepción en taller. KM: 15000. Cliente: Ana.",
        linked_order_id=order.id,
    )
    mantenimiento_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.MANTENIMIENTO,
        km_at_event=Decimal("15000"),
        summary=f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(
        get_object=order, reception=reception, lifecycle_events=[recepcion_event, mantenimiento_event]
    )

    payload = order_payload(mileage_km=15200)  # service_type omitted -> unchanged

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert mantenimiento_event.km_at_event == Decimal("15200")
    assert order.service_type == ServiceType.km_review  # unchanged -> no conversion
    # MANTENIMIENTO summary carries no KM token (unlike RECEPCION) -> unchanged
    assert mantenimiento_event.summary == f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}."

    audit = next(a.payload["mileage_km"] for a in fake_db.added if "mileage_km" in a.payload)
    assert set(audit["lifecycle_event_synced"]) == {str(recepcion_event.id), str(mantenimiento_event.id)}


# ---------------------------------------------------------------------------
# 4.4 — warranty<->km_review cross-conversion remaps event_type/km/summary,
# no confirmation required (a valid target event type always exists)
# ---------------------------------------------------------------------------

def test_update_order_service_type_warranty_to_km_review_converts_event_in_place():
    from app.models.order import ServiceStatus, ServiceType
    from app.models.vehicle_lifecycle import LifecycleEventType

    order = make_order(created_at=datetime(2026, 7, 1), status=ServiceStatus.completed, service_type=ServiceType.warranty)
    reception = make_reception(order_id=order.id, mileage_km=12000)
    garantia_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.GARANTIA,
        km_at_event=None,
        summary=f"Garantía aplicada. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(get_object=order, reception=reception, lifecycle_events=[garantia_event])

    payload = order_payload(service_type="km_review")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert garantia_event.event_type == LifecycleEventType.MANTENIMIENTO
    assert garantia_event.km_at_event == Decimal("12000")
    assert garantia_event.summary == f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}."

    audit = next(a.payload["service_type"] for a in fake_db.added if "service_type" in a.payload)
    assert audit["lifecycle_event_synced"] == [str(garantia_event.id)]


def test_update_order_service_type_km_review_to_warranty_converts_event_and_clears_km():
    from app.models.order import ServiceStatus, ServiceType
    from app.models.vehicle_lifecycle import LifecycleEventType

    order = make_order(created_at=datetime(2026, 7, 1), status=ServiceStatus.completed, service_type=ServiceType.km_review)
    reception = make_reception(order_id=order.id, mileage_km=18000)
    mantenimiento_event = make_lifecycle_event(
        vehicle_id=order.vehicle_id,
        event_type=LifecycleEventType.MANTENIMIENTO,
        km_at_event=Decimal("18000"),
        summary=f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
    )
    fake_db = FakeOrderSession(get_object=order, reception=reception, lifecycle_events=[mantenimiento_event])

    payload = order_payload(service_type="warranty")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert mantenimiento_event.event_type == LifecycleEventType.GARANTIA
    assert mantenimiento_event.km_at_event is None
    assert mantenimiento_event.summary == f"Garantía aplicada. Orden {str(order.id)[:8]}."


# ---------------------------------------------------------------------------
# 4.5 — no completion event exists -> no lifecycle side effect, still audited
# ---------------------------------------------------------------------------

def test_update_order_service_type_change_with_no_completion_event_has_no_lifecycle_side_effect():
    from app.models.order import ServiceStatus, ServiceType

    order = make_order(created_at=datetime(2026, 7, 1), status=ServiceStatus.in_progress, service_type=ServiceType.regular)
    reception = make_reception(order_id=order.id, mileage_km=5000)
    fake_db = FakeOrderSession(get_object=order, reception=reception, lifecycle_events=[])

    payload = order_payload(service_type="warranty")

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/orders/{order.id}", json=payload)

    assert res.status_code == 200
    assert order.service_type == ServiceType.warranty
    assert fake_db.added != []  # still recorded in the audit trail

    audit = next(a.payload["service_type"] for a in fake_db.added if "service_type" in a.payload)
    assert "lifecycle_event_synced" not in audit
    assert all(type(obj).__name__ != "VehicleLifecycleEvent" for obj in fake_db.added)
