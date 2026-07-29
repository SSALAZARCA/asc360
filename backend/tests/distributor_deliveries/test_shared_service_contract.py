"""
tests/distributor_deliveries/test_shared_service_contract.py — Phase 4, task
4.9. Contract lock for `vehicle_service.register_or_update_vehicle` and
`VinLookupResult`, re-asserted from THIS module's perspective since
`distributor_delivery_service` is a second caller of the same shared
function (project memory bug #7 — never change a shared contract without
checking every caller).

Mirrors `tests/historical_orders/test_shared_service_contract.py` verbatim
— that test MUST also stay green, unmodified, after this change.
"""
import inspect
from dataclasses import fields

from app.services.vin_master_service import vin_master_service, VinLookupResult
from app.services.vehicle_service import vehicle_service


def test_register_or_update_vehicle_signature_is_locked():
    sig = inspect.signature(vehicle_service.register_or_update_vehicle)
    assert list(sig.parameters.keys()) == ["db", "vehicle_in"]


def test_query_vin_signature_is_locked():
    sig = inspect.signature(vin_master_service.query_vin)
    assert list(sig.parameters.keys()) == ["db", "vin"]
    assert sig.parameters["vin"].annotation is str


def test_vin_lookup_result_field_tuple_is_locked():
    field_names = tuple(f.name for f in fields(VinLookupResult))
    assert field_names == ("id", "vin", "engine_number", "model", "year", "color")
