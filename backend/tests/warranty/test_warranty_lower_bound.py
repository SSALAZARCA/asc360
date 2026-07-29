"""
tests/warranty/test_warranty_lower_bound.py — `sdd/distributor-vehicle-delivery`
PR1, task 1.1: RED tests for the pure warranty lower-bound helper,
`app.services.warranty_validation.ensure_order_date_after_delivery`.

No DB session, no HTTP layer — this is a plain unit test of a pure function
(Design Decision 1). Matrix per the design's Testing Strategy table:
vehicle=None / order_date=None / vehicle.delivery_date=None -> no-op;
order before delivery_date -> 422 with the date in the message; same-day ->
passes; after -> passes.
"""
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.warranty_validation import ensure_order_date_after_delivery


def _vehicle(delivery_date):
    return SimpleNamespace(delivery_date=delivery_date)


class TestNoOpCases:
    def test_vehicle_none_is_a_no_op(self):
        ensure_order_date_after_delivery(None, datetime(2026, 7, 1))  # no raise

    def test_order_date_none_is_a_no_op(self):
        ensure_order_date_after_delivery(_vehicle(date(2026, 1, 1)), None)  # no raise

    def test_vehicle_without_delivery_date_is_a_no_op(self):
        """Day-1 behaviour: no existing vehicle has a `delivery_date` yet,
        so every pre-existing vehicle must pass through untouched."""
        ensure_order_date_after_delivery(_vehicle(None), datetime(2026, 7, 1))  # no raise


class TestBoundaryComparison:
    def test_order_date_before_delivery_date_raises_422_with_date_in_message(self):
        vehicle = _vehicle(date(2026, 7, 10))
        with pytest.raises(HTTPException) as exc:
            ensure_order_date_after_delivery(vehicle, datetime(2026, 7, 5))
        assert exc.value.status_code == 422
        assert "2026-07-10" in exc.value.detail

    def test_order_date_same_day_as_delivery_date_passes(self):
        vehicle = _vehicle(date(2026, 7, 10))
        ensure_order_date_after_delivery(vehicle, datetime(2026, 7, 10, 23, 59))  # no raise

    def test_order_date_after_delivery_date_passes(self):
        vehicle = _vehicle(date(2026, 7, 10))
        ensure_order_date_after_delivery(vehicle, datetime(2026, 7, 11))  # no raise

    def test_accepts_a_plain_date_object_not_only_datetime(self):
        """`order_date` may be a bare `date` (e.g. superadmin's date-only
        edit path) as well as a `datetime` -- both must compare correctly."""
        vehicle = _vehicle(date(2026, 7, 10))
        with pytest.raises(HTTPException):
            ensure_order_date_after_delivery(vehicle, date(2026, 7, 9))
        ensure_order_date_after_delivery(vehicle, date(2026, 7, 10))  # no raise
