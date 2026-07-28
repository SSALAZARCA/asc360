"""
tests/historical_orders/test_shared_service_contract.py — contract lock
for the three shared functions the (not-yet-built, PR2) transactional
service is REQUIRED to call AS-IS: `vin_master_service.query_vin`,
`vehicle_service.register_or_update_vehicle`, `vehicle_service.
get_vehicle_by_plate`, plus the `VinLookupResult` field tuple they return.

Mitigates design failure mode #6: any accidental future change to these
signatures/fields must fail THIS test immediately, before it silently
breaks historical-order creation (or any other caller). Written first,
before any production code for this change exists — it locks the CURRENT
(correct) shape of functions that already exist elsewhere in the codebase,
so it must pass with zero source changes.
"""
import inspect
from dataclasses import fields

from app.services.vin_master_service import vin_master_service, VinLookupResult
from app.services.vehicle_service import vehicle_service


def test_query_vin_signature_is_locked():
    sig = inspect.signature(vin_master_service.query_vin)
    assert list(sig.parameters.keys()) == ["db", "vin"]
    assert sig.parameters["vin"].annotation is str


def test_register_or_update_vehicle_signature_is_locked():
    # sdd/vehicle-tenant-checkin-release PR2: `tenant_id` DELIBERATELY
    # dropped from this signature -- it was the live tenant-theft bug's
    # mechanism (`vehicle_in.tenant_id = tenant_id` silently rewrote a
    # vehicle's owning taller on every update). `register_or_update_
    # vehicle` is now a pure lookup-or-upsert with ZERO tenant semantics
    # (Design Decision 1); the conflict check moved to order creation.
    # Updated in the same commit as all its callers (project memory bug
    # #7 -- never change a shared contract without checking every caller).
    sig = inspect.signature(vehicle_service.register_or_update_vehicle)
    assert list(sig.parameters.keys()) == ["db", "vehicle_in"]


def test_get_vehicle_by_plate_signature_is_locked():
    sig = inspect.signature(vehicle_service.get_vehicle_by_plate)
    assert list(sig.parameters.keys()) == ["db", "plate", "tenant_id"]
    assert sig.parameters["tenant_id"].default is None


def test_vin_lookup_result_field_tuple_is_locked():
    field_names = tuple(f.name for f in fields(VinLookupResult))
    assert field_names == ("id", "vin", "engine_number", "model", "year", "color")
