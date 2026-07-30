"""
tests/distributor_deliveries/test_schema_model_contract.py — locks the
model column shape the (not-yet-built, PR4) transactional service plan
depends on. Every attribute name the design's Data Flow / File Changes
sections say the service will `setattr`/construct on each ORM model MUST
exist on that model's `__table__.columns` — written now, before the
service exists, so a column rename/removal on any of these models fails
HERE first instead of surfacing as a silent `AttributeError` once PR4
wires the real service. Mirrors `tests/historical_orders/
test_schema_model_contract.py`.

Also pins Design Decision 4: `VehicleCreate` must NOT carry `delivery_date`
— the delivery service sets it directly on the returned ORM instance
instead, because adding it to `VehicleCreate` would let a client-controlled
value hard-block reception for that bike (mass-assignment class flagged in
`vehicle-tenant-checkin-release`).
"""
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.imports import ImportAuditLog

from app.schemas.vehicle import VehicleCreate
from app.schemas.distributor_delivery import (
    DeliveryClientIn,
    DeliveryVehicleIn,
    DeliveryCreate,
    DeliveryOut,
)


MODEL_ATTRIBUTES_THE_SERVICE_WILL_SET = {
    User: {
        "tenant_id", "name", "phone", "email", "role", "status", "telegram_id",
        "identification", "birth_date", "city", "department", "address",
    },
    Vehicle: {
        "plate", "vin", "brand", "model", "color", "year",
        "delivery_date", "engine_number", "delivery_act_url", "client_id",
    },
    ImportAuditLog: {"actor_id", "actor_role", "action", "entity_type", "entity_id", "payload", "created_at"},
}


def test_every_service_planned_attribute_exists_on_its_model():
    for model, attribute_names in MODEL_ATTRIBUTES_THE_SERVICE_WILL_SET.items():
        column_names = set(model.__table__.columns.keys())
        missing = attribute_names - column_names
        assert not missing, f"{model.__name__} is missing columns the service plan needs: {missing}"


def test_vehicle_create_does_not_carry_delivery_date():
    # Pins Decision 4 — the field is exposed on VehicleOut only, never on
    # the whitelist the delivery service feeds into register_or_update_vehicle.
    schema_fields = set(VehicleCreate.model_fields.keys())
    assert "delivery_date" not in schema_fields
    assert "engine_number" not in schema_fields
    assert "delivery_act_url" not in schema_fields


def test_delivery_create_schema_shape():
    client_fields = set(DeliveryClientIn.model_fields.keys())
    assert client_fields == {
        "name", "identification", "birth_date", "city", "department", "address", "phone", "email",
    }

    vehicle_fields = set(DeliveryVehicleIn.model_fields.keys())
    assert vehicle_fields == {"plate", "vin", "model", "color", "year", "engine_number"}

    create_fields = set(DeliveryCreate.model_fields.keys())
    assert create_fields == {"client", "vehicle", "delivery_date"}

    assert DeliveryClientIn.model_fields["identification"].is_required()
    assert DeliveryVehicleIn.model_fields["plate"].is_required()
    # Follow-up fix (2026-07-30): VIN is now mandatory, no exceptions
    # anywhere in this feature (see `distributor_delivery_service.
    # _require_vin_in_master`).
    assert DeliveryVehicleIn.model_fields["vin"].is_required()
    assert DeliveryCreate.model_fields["delivery_date"].is_required()


def test_delivery_out_schema_exists():
    out_fields = set(DeliveryOut.model_fields.keys())
    assert {"id", "plate", "delivery_date", "client_id"} <= out_fields
