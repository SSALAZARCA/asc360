"""
tests/superadmin_data/test_vehicle_quick_fix.py — Phase 2 (Vehicle
quick-fix) for `app/api/v1/superadmin_data.py`.

Covers: GET search (200/404), PUT happy path (whitelist diff + per-field
audit, extra unknown fields ignored), PUT duplicate-plate 409 (no audit,
no commit), PUT no-op (200, no audit row).
"""
import uuid

from tests.conftest import make_test_client
from tests.superadmin_data.conftest import FakeVehicleSession, make_vehicle


def make_superadmin() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


# ---------------------------------------------------------------------------
# 2.1 — GET /superadmin/data/vehicles?plate=
# ---------------------------------------------------------------------------

def test_search_vehicle_by_plate_found_returns_200():
    vehicle = make_vehicle(plate="ABC123")
    fake_db = FakeVehicleSession(search_result=[vehicle])

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.get("/api/v1/superadmin/data/vehicles", params={"plate": "ABC123"})

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == str(vehicle.id)
    assert body["plate"] == "ABC123"
    assert body["mileage"] == 1000


def test_search_vehicle_by_plate_miss_returns_404():
    fake_db = FakeVehicleSession(search_result=[])

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.get("/api/v1/superadmin/data/vehicles", params={"plate": "ZZZ999"})

    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 2.2 — PUT happy path: whitelist diff + per-field audit
# ---------------------------------------------------------------------------

def test_update_vehicle_happy_path_changes_only_diff_fields_and_audits_each():
    vehicle = make_vehicle(plate="ABC123", mileage=1000, brand="UM", model="DSR")
    fake_db = FakeVehicleSession(get_object=vehicle)

    payload = {
        "plate": "XYZ999",
        "brand": "UM",
        "model": "DSR",
        "vin": vehicle.vin,
        "color": vehicle.color,
        "year": vehicle.year,
        "mileage": 1500,
        # Not part of the whitelist schema at all -- must be silently
        # ignored, never reach the model.
        "tenant_id": str(uuid.uuid4()),
        "status": "eliminado",
    }

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/vehicles/{vehicle.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["plate"] == "XYZ999"
    assert body["mileage"] == 1500

    assert fake_db.committed is True
    audit_payloads = [a.payload for a in fake_db.added]
    assert len(audit_payloads) == 2
    changed_fields = {list(p.keys())[0] for p in audit_payloads}
    assert changed_fields == {"plate", "mileage"}
    plate_row = next(p for p in audit_payloads if "plate" in p)
    assert plate_row["plate"] == {"old": "ABC123", "new": "XYZ999"}
    mileage_row = next(p for p in audit_payloads if "mileage" in p)
    assert mileage_row["mileage"] == {"old": 1000, "new": 1500}

    for row in fake_db.added:
        assert row.action == "SUPERADMIN_DATA_FIX"
        assert row.entity_type == "Vehicle"
        assert row.entity_id == str(vehicle.id)
        assert row.shipment_order_id is None


def test_update_vehicle_missing_id_returns_404():
    fake_db = FakeVehicleSession(get_object=None)
    payload = {
        "plate": "ABC123", "brand": "UM", "model": "DSR",
        "vin": None, "color": None, "year": None, "mileage": None,
    }

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/vehicles/{uuid.uuid4()}", json=payload)

    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 2.3 — Duplicate plate -> 409, no commit, no audit persisted
# ---------------------------------------------------------------------------

def test_update_vehicle_duplicate_plate_returns_409_with_no_audit():
    vehicle = make_vehicle(plate="ABC123", mileage=1000)
    fake_db = FakeVehicleSession(get_object=vehicle, raise_integrity_error=True)

    payload = {
        "plate": "DUP001", "brand": vehicle.brand, "model": vehicle.model,
        "vin": vehicle.vin, "color": vehicle.color, "year": vehicle.year,
        "mileage": vehicle.mileage,
    }

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/vehicles/{vehicle.id}", json=payload)

    assert res.status_code == 409
    assert fake_db.committed is False
    assert fake_db.rolled_back is True
    assert fake_db.added == []


# ---------------------------------------------------------------------------
# 2.4 — No-op PUT -> 200, no audit row written
# ---------------------------------------------------------------------------

def test_update_vehicle_no_op_returns_200_with_no_audit_row():
    vehicle = make_vehicle(
        plate="ABC123", brand="UM", model="DSR", vin="VIN0001",
        color="Rojo", year=2024, mileage=1000,
    )
    fake_db = FakeVehicleSession(get_object=vehicle)

    payload = {
        "plate": "ABC123", "brand": "UM", "model": "DSR", "vin": "VIN0001",
        "color": "Rojo", "year": 2024, "mileage": 1000,
    }

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/vehicles/{vehicle.id}", json=payload)

    assert res.status_code == 200
    assert fake_db.added == []
    assert fake_db.committed is True


# ---------------------------------------------------------------------------
# Corrective batch — field-presence-aware partial updates.
#
# `Optional[X] = None` fields must NOT be diffed/nulled just because the
# caller's JSON body omits the key entirely. Pydantic v2's
# `model_dump(exclude_unset=True)` (already the codebase's established
# pattern -- see `app/repositories/base_repository.py`,
# `app/api/v1/imports.py`, `app/api/v1/endpoints/users.py`) distinguishes
# "key absent" from "key explicitly sent as null".
# ---------------------------------------------------------------------------

def test_update_vehicle_omitted_optional_field_leaves_db_value_untouched_no_audit():
    vehicle = make_vehicle(
        plate="ABC123", brand="UM", model="DSR", vin="VIN0001",
        color="Rojo", year=2024, mileage=1000,
    )
    fake_db = FakeVehicleSession(get_object=vehicle)

    # `color` key is entirely ABSENT from the request body -- must be left
    # untouched, not silently nulled by the schema's `Optional[str] = None`
    # default. Only `mileage` actually changes.
    payload = {
        "plate": "ABC123", "brand": "UM", "model": "DSR", "vin": "VIN0001",
        "year": 2024, "mileage": 1500,
    }

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/vehicles/{vehicle.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["color"] == "Rojo"
    assert vehicle.color == "Rojo"

    audit_payloads = [a.payload for a in fake_db.added]
    changed_fields = {list(p.keys())[0] for p in audit_payloads}
    assert changed_fields == {"mileage"}
    assert "color" not in changed_fields


def test_update_vehicle_explicit_null_optional_field_clears_it_and_audits():
    vehicle = make_vehicle(
        plate="ABC123", brand="UM", model="DSR", vin="VIN0001",
        color="Rojo", year=2024, mileage=1000,
    )
    fake_db = FakeVehicleSession(get_object=vehicle)

    # `color` key IS present, explicitly `null` -- this is the one legitimate
    # way to clear an optional field, and it must be diffed/applied/audited.
    payload = {
        "plate": "ABC123", "brand": "UM", "model": "DSR", "vin": "VIN0001",
        "color": None, "year": 2024, "mileage": 1000,
    }

    with make_test_client(make_superadmin(), fake_db) as client:
        res = client.put(f"/api/v1/superadmin/data/vehicles/{vehicle.id}", json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["color"] is None
    assert vehicle.color is None

    audit_payloads = [a.payload for a in fake_db.added]
    assert len(audit_payloads) == 1
    assert audit_payloads[0]["color"] == {"old": "Rojo", "new": None}
