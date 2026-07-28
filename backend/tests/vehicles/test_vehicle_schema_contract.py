"""
tests/vehicles/test_vehicle_schema_contract.py -- static introspection
locking Design File Change #2 (`schemas/vehicle.py`) and Decision 2
(`Vehicle` model column removal, PR1). A vehicle's tenant is now a DERIVED
claim, never a stored/serialized column -- these tests fail loudly if
either surface regresses back to a stored `tenant_id`.
"""
import uuid

from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleOut


def test_vehicle_model_has_no_tenant_id_column():
    """Locks PR1's result -- guards against a future re-add."""
    assert "tenant_id" not in Vehicle.__table__.columns.keys()


def test_vehicle_create_has_no_tenant_id_field():
    assert "tenant_id" not in VehicleCreate.model_fields


def test_vehicle_update_has_no_tenant_id_field():
    assert "tenant_id" not in VehicleUpdate.model_fields


def test_vehicle_out_renames_tenant_id_to_claimed_by_fields():
    fields = VehicleOut.model_fields
    assert "tenant_id" not in fields
    assert "claimed_by_tenant_id" in fields
    assert fields["claimed_by_tenant_id"].is_required() is False
    assert "claimed_by_tenant_name" in fields
    assert fields["claimed_by_tenant_name"].is_required() is False


def test_unclaimed_vehicle_serializes_without_a_claim_value():
    """Requirement 'Vehicle Schema Serializes Unclaimed Vehicles' (spec) --
    an unclaimed vehicle (no claim fields set) must round-trip cleanly."""
    out = VehicleOut(id=uuid.uuid4(), plate="ABC123")
    assert out.claimed_by_tenant_id is None
    assert out.claimed_by_tenant_name is None
