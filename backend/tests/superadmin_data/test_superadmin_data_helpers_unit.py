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
import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.v1.superadmin_data import (
    _diff_date_fields,
    _ensure_delivered_after_created,
    _resync_recepcion_summary,
    _needs_delete_confirmation,
)
from app.models.order import ServiceOrder, ServiceStatus, ServiceType
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
        assert changes["created_at"] == {"old": datetime(2026, 7, 1), "new": datetime(2026, 7, 2)}
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
