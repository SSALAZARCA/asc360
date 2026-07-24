"""
tests/superadmin_data/test_superadmin_data_helpers_unit.py — Phase 5 task
5.6: direct unit tests (no HTTP layer, no fake session) for the pure
helper functions in `app/api/v1/superadmin_data.py` that were previously
only exercised indirectly through the integration tests:

- `_diff_date_fields` — diffs only the keys actually present in `provided`.
- `_ensure_delivered_after_created` — effective-value (DB-merged) resolution
  for the unconditional 422 date-order guard.
- `_resync_recepcion_summary` — the `KM: <value>` token regex replace.
- `_needs_delete_confirmation` — truth table for the confirm-then-delete
  gate (Phase 5's new predicate).
"""
import json
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.v1.superadmin_data import (
    _diff_date_fields,
    _ensure_delivered_after_created,
    _resync_recepcion_summary,
    _needs_delete_confirmation,
    _apply_mileage_correction,
    _apply_service_type_correction,
)
from app.models.order import ServiceOrder, ServiceOrderReception, ServiceStatus, ServiceType
from app.models.vehicle_lifecycle import VehicleLifecycleEvent, LifecycleEventType


def _make_order(created_at, delivered_at=None) -> ServiceOrder:
    return ServiceOrder(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        status=ServiceStatus.received,
        service_type=ServiceType.regular,
        created_at=created_at,
        delivered_at=delivered_at,
    )


def _make_reception(mileage_km) -> ServiceOrderReception:
    return ServiceOrderReception(
        id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        mileage_km=Decimal(str(mileage_km)),
        created_at=datetime(2026, 7, 1),
    )


def _make_event(event_type) -> VehicleLifecycleEvent:
    return VehicleLifecycleEvent(
        id=uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        event_type=event_type,
        event_date=datetime(2026, 7, 1),
        km_at_event=None,
        summary="",
        linked_order_id=uuid.uuid4(),
        is_automatic="auto",
    )


# ---------------------------------------------------------------------------
# _diff_date_fields — only keys present in `provided` are diffed/applied
# ---------------------------------------------------------------------------

class TestDiffDateFields:
    def test_diffs_only_changed_present_field(self):
        order = _make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
        changes = _diff_date_fields(order, {"created_at": datetime(2026, 7, 2)})

        assert set(changes.keys()) == {"created_at"}
        # `datetime` objects aren't JSON-serializable -- ImportAuditLog.payload
        # is a real JSONB column, so the audit dict must hold isoformat
        # strings (this crashed with a 500 in production against a real DB).
        # `order.created_at` itself still gets the real datetime (below).
        assert changes["created_at"] == {"old": "2026-07-01T00:00:00", "new": "2026-07-02T00:00:00"}
        assert order.created_at == datetime(2026, 7, 2)
        assert order.delivered_at == datetime(2026, 7, 3)  # untouched -- never in `provided`

    def test_omitted_field_is_not_diffed_or_applied(self):
        order = _make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
        changes = _diff_date_fields(order, {"created_at": datetime(2026, 7, 1)})  # same value

        assert changes == {}
        assert "delivered_at" not in changes
        assert order.delivered_at == datetime(2026, 7, 3)

    def test_equal_value_present_is_a_no_op(self):
        order = _make_order(created_at=datetime(2026, 7, 1))
        changes = _diff_date_fields(order, {"created_at": datetime(2026, 7, 1)})
        assert changes == {}


# ---------------------------------------------------------------------------
# _ensure_delivered_after_created — effective (DB-merged) value resolution
# ---------------------------------------------------------------------------

class TestEnsureDeliveredAfterCreated:
    def test_both_provided_and_valid_does_not_raise(self):
        order = _make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
        _ensure_delivered_after_created(
            {"created_at": datetime(2026, 7, 5), "delivered_at": datetime(2026, 7, 6)}, order
        )  # no raise

    def test_only_created_at_provided_uses_db_delivered_at_as_effective(self):
        """`delivered_at` isn't in `provided` -- the effective value MUST
        fall back to the order's EXISTING DB value, not be treated as
        absent/unbounded."""
        order = _make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
        with pytest.raises(HTTPException) as exc:
            _ensure_delivered_after_created({"created_at": datetime(2026, 7, 10)}, order)
        assert exc.value.status_code == 422

    def test_only_delivered_at_provided_uses_db_created_at_as_effective(self):
        order = _make_order(created_at=datetime(2026, 7, 10))
        with pytest.raises(HTTPException) as exc:
            _ensure_delivered_after_created({"delivered_at": datetime(2026, 7, 5)}, order)
        assert exc.value.status_code == 422

    def test_delivered_at_explicitly_null_in_provided_skips_the_check(self):
        """`provided["delivered_at"] = None` (explicit clear) means the
        effective `delivered_at` IS `None` -- nothing to compare, no 422."""
        order = _make_order(created_at=datetime(2026, 7, 1), delivered_at=datetime(2026, 7, 3))
        _ensure_delivered_after_created(
            {"created_at": datetime(2026, 7, 20), "delivered_at": None}, order
        )  # no raise -- None short-circuits the comparison


# ---------------------------------------------------------------------------
# _resync_recepcion_summary — KM: <value> token regex replace
# ---------------------------------------------------------------------------

class TestResyncRecepcionSummary:
    def test_replaces_integer_km_token_preserving_trailing_period(self):
        result = _resync_recepcion_summary("Recepción en taller. KM: 20000. Cliente: Ana.", 20500)
        assert result == "Recepción en taller. KM: 20500. Cliente: Ana."

    def test_replaces_decimal_km_token(self):
        result = _resync_recepcion_summary("KM: 1000.50 al ingreso", "1500.75")
        assert result == "KM: 1500.75 al ingreso"

    def test_absent_token_leaves_summary_untouched(self):
        result = _resync_recepcion_summary("Recepción sin kilometraje registrado.", 500)
        assert result == "Recepción sin kilometraje registrado."

    def test_empty_or_none_summary_returned_as_is(self):
        assert _resync_recepcion_summary(None, 500) is None
        assert _resync_recepcion_summary("", 500) == ""


# ---------------------------------------------------------------------------
# _needs_delete_confirmation — truth table
# ---------------------------------------------------------------------------

class TestNeedsDeleteConfirmation:
    def test_away_from_warranty_with_garantia_event_needs_confirmation(self):
        event = _make_event(LifecycleEventType.GARANTIA)
        assert _needs_delete_confirmation(ServiceType.warranty, ServiceType.regular, event) is True

    def test_away_from_km_review_with_mantenimiento_event_needs_confirmation(self):
        event = _make_event(LifecycleEventType.MANTENIMIENTO)
        assert _needs_delete_confirmation(ServiceType.km_review, ServiceType.quick, event) is True

    def test_warranty_to_km_review_cross_conversion_does_not_need_confirmation(self):
        event = _make_event(LifecycleEventType.GARANTIA)
        assert _needs_delete_confirmation(ServiceType.warranty, ServiceType.km_review, event) is False

    def test_km_review_to_warranty_cross_conversion_does_not_need_confirmation(self):
        event = _make_event(LifecycleEventType.MANTENIMIENTO)
        assert _needs_delete_confirmation(ServiceType.km_review, ServiceType.warranty, event) is False

    def test_no_completion_event_never_needs_confirmation(self):
        assert _needs_delete_confirmation(ServiceType.warranty, ServiceType.regular, None) is False

    def test_no_service_type_change_requested_never_needs_confirmation(self):
        event = _make_event(LifecycleEventType.GARANTIA)
        assert _needs_delete_confirmation(ServiceType.warranty, None, event) is False

    def test_transition_between_two_non_event_types_never_needs_confirmation(self):
        assert _needs_delete_confirmation(ServiceType.regular, ServiceType.quick, None) is False

    def test_synthesis_direction_into_event_type_with_no_prior_event_does_not_need_confirmation(self):
        """regular/quick/pdi -> warranty/km_review with NO existing event is
        the synthesis case (out of scope, no event created) -- never needs
        confirmation regardless of the (irrelevant) `completion_event`
        argument here since this predicate is only ever called with the
        order's CURRENT completion event, which is `None` in that case."""
        assert _needs_delete_confirmation(ServiceType.regular, ServiceType.warranty, None) is False


# ---------------------------------------------------------------------------
# _apply_mileage_correction — audit payload must be JSON-serializable
# (ImportAuditLog.payload is a real JSONB column; a raw Decimal crashes the
# commit with an unhandled TypeError, seen as a live 500 in production), and
# the no-op check must compare Decimal VALUES, not their string formatting:
# Decimal("6245") vs Decimal("6245.00") are equal but format differently, so
# a str()-based no-op check treated a same-value resubmit as a real change.
# ---------------------------------------------------------------------------

class TestApplyMileageCorrection:
    def test_real_change_returns_json_serializable_str_values(self):
        reception = _make_reception(1000)
        change = _apply_mileage_correction(reception, Decimal("1500"), None, None)

        assert change == {"old": "1000", "new": "1500"}
        assert reception.mileage_km == Decimal("1500")
        json.dumps(change)  # must not raise -- this is the exact production crash

    def test_mathematically_equal_value_with_different_decimal_precision_is_a_no_op(self):
        """The value the frontend round-trips (a plain JSON number, e.g.
        6245) parses to Decimal("6245"), while the DB's Numeric(10,2)
        column holds Decimal("6245.00") -- same value, different string
        precision. A str()-based no-op check treats this as a real change,
        needlessly resyncing lifecycle events and writing an audit row (and,
        before the JSON fix above, crashing outright)."""
        reception = _make_reception("6245.00")
        change = _apply_mileage_correction(reception, Decimal("6245"), None, None)

        assert change is None
        assert reception.mileage_km == Decimal("6245.00")  # untouched

    def test_syncs_recepcion_and_mantenimiento_events_with_json_serializable_change(self):
        recepcion_event = _make_event(LifecycleEventType.RECEPCION)
        recepcion_event.summary = "Recepción en taller. KM: 1000. Cliente: Juan."
        mantenimiento_event = _make_event(LifecycleEventType.MANTENIMIENTO)
        reception = _make_reception(1000)

        change = _apply_mileage_correction(reception, Decimal("1500"), recepcion_event, mantenimiento_event)

        assert recepcion_event.km_at_event == Decimal("1500")
        assert mantenimiento_event.km_at_event == Decimal("1500")
        assert change["lifecycle_event_synced"] == [str(recepcion_event.id), str(mantenimiento_event.id)]
        json.dumps(change)


# ---------------------------------------------------------------------------
# _apply_service_type_correction — same JSON-serializability requirement:
# a raw `ServiceType` enum member in the audit payload crashes the JSONB
# commit the same way a raw Decimal does.
# ---------------------------------------------------------------------------

class TestApplyServiceTypeCorrection:
    def test_real_change_returns_json_serializable_value_strings(self):
        order = _make_order(created_at=datetime(2026, 7, 1))
        order.service_type = ServiceType.regular

        change = _apply_service_type_correction(order, ServiceType.quick, None, None)

        assert change == {"old": "regular", "new": "quick"}
        assert order.service_type == ServiceType.quick
        json.dumps(change)  # must not raise -- this is the exact production crash

    def test_same_value_is_a_no_op(self):
        order = _make_order(created_at=datetime(2026, 7, 1))
        order.service_type = ServiceType.regular

        change = _apply_service_type_correction(order, ServiceType.regular, None, None)

        assert change is None

    def test_warranty_to_km_review_conversion_change_is_json_serializable(self):
        order = _make_order(created_at=datetime(2026, 7, 1))
        order.service_type = ServiceType.warranty
        garantia_event = _make_event(LifecycleEventType.GARANTIA)
        reception = _make_reception(500)

        change = _apply_service_type_correction(order, ServiceType.km_review, reception, garantia_event)

        assert change["old"] == "warranty"
        assert change["new"] == "km_review"
        assert garantia_event.event_type == LifecycleEventType.MANTENIMIENTO
        json.dumps(change)
