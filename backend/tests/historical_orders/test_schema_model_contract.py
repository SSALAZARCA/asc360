"""
tests/historical_orders/test_schema_model_contract.py — locks the model
column shape the (not-yet-built, PR2) transactional service plan depends
on. Every attribute name the design's "Transactional Service Plan" section
says the service will `setattr`/construct on each ORM model MUST exist on
that model's `__table__.columns` — written now, before the service exists,
so a column rename/removal on any of these models fails HERE first instead
of surfacing as a silent `AttributeError` once PR2 wires the real service.

Also locks `HistoricalOrderCreate`'s own field shape (Decision 6 — no
identification/cédula field anywhere; Decision 11 — `tenant_id` required).
"""
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.order import ServiceOrder, ServiceOrderReception, OrderWorkLog, OrderHistory
from app.models.vehicle_lifecycle import VehicleLifecycleEvent
from app.models.imports import ImportAuditLog

from app.schemas.historical_order import (
    HistoricalOrderCreate,
    HistoricalOrderClientIn,
    HistoricalOrderVehicleIn,
    HistoricalOrderOut,
    DuplicateMatch,
)


MODEL_ATTRIBUTES_THE_SERVICE_WILL_SET = {
    User: {"tenant_id", "name", "phone", "role", "status", "telegram_id"},
    # sdd/vehicle-tenant-checkin-release PR2: `tenant_id` removed -- the
    # historical-order service no longer sets it (`_register_vehicle`);
    # `Vehicle.tenant_id` was unmapped from the ORM entirely in PR1.
    Vehicle: {"plate", "vin", "brand", "model", "year", "color"},
    ServiceOrder: {
        "tenant_id", "vehicle_id", "client_id", "technician_id",
        "status", "service_type", "created_at", "completed_at", "delivered_at",
    },
    ServiceOrderReception: {
        "order_id", "mileage_km", "customer_notes", "general_observations",
        "intake_answers", "accessories", "damage_photos_urls", "warranty_warnings",
        "created_at", "signature_url", "accepted_at", "accepted_phone",
        "bypass_at", "bypass_by_id", "bypass_by_name", "reception_pdf_url",
    },
    OrderWorkLog: {"order_id", "history_id", "diagnosis", "media_urls", "recorded_by_telegram_id", "created_at"},
    OrderHistory: {"order_id", "from_status", "to_status", "changed_at", "changed_by", "duration_minutes", "comments"},
    VehicleLifecycleEvent: {
        "vehicle_id", "event_type", "event_date", "km_at_event",
        "summary", "details", "linked_order_id", "is_automatic",
    },
    ImportAuditLog: {"actor_id", "actor_role", "action", "entity_type", "entity_id", "payload", "created_at"},
}


def test_every_service_planned_attribute_exists_on_its_model():
    for model, attribute_names in MODEL_ATTRIBUTES_THE_SERVICE_WILL_SET.items():
        column_names = set(model.__table__.columns.keys())
        missing = attribute_names - column_names
        assert not missing, f"{model.__name__} is missing columns the service plan needs: {missing}"


def test_historical_order_create_has_no_identification_field():
    schema_fields = set(HistoricalOrderCreate.model_fields.keys())
    schema_fields |= set(HistoricalOrderClientIn.model_fields.keys())
    schema_fields |= set(HistoricalOrderVehicleIn.model_fields.keys())
    assert "identification" not in schema_fields
    assert "cedula" not in schema_fields


def test_historical_order_create_requires_tenant_id():
    assert HistoricalOrderCreate.model_fields["tenant_id"].is_required()


def test_historical_order_out_and_duplicate_match_schemas_exist():
    # Locks Phase 1's full schema surface (design's File Changes table) --
    # a bare import + attribute check, no instantiation needed yet.
    assert "id" in HistoricalOrderOut.model_fields
    assert "order_id" in DuplicateMatch.model_fields
