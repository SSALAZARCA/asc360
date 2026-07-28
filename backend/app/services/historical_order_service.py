"""
Historical Order Entry — the transactional service backing
`POST /superadmin/data/historical-orders`.

Superadmin-only creation of a complete, backdated `ServiceOrder` (client,
vehicle, dates, status, diagnosis, lifecycle events, PDF, audit log) for
paper orders written when Sonia was unavailable. Everything happens on ONE
session with a SINGLE `commit()` at the very end (Design's "Technical
Approach") — every timestamp is written explicitly from the payload, never
from a column default.

Reuses `vehicle_service.register_or_update_vehicle`, `vin_master_service.
query_vin` (transitively) AS-IS — see `tests/historical_orders/
test_shared_service_contract.py` for the contract lock (Decision 5 /
failure mode #6). This module never modifies those signatures.

`POST /orders/`, Sonia's reception flow, and `superadmin_data.py` are never
imported for write access here — only `_log_audit` (a pure "build a row and
`db.add` it" helper, `imports_service.py:3129-3148`) is reused, mirroring
the same read-only-import pattern already established for `_require_
superadmin` (Decision 2).
"""
import logging
import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.models.order import (
    OrderHistory,
    OrderWorkLog,
    ServiceOrder,
    ServiceOrderReception,
    ServiceStatus,
    ServiceType,
)
from app.models.tenant import Tenant
from app.models.user import Role, User, UserStatus
from app.models.vehicle import Vehicle
from app.models.vehicle_lifecycle import LifecycleEventType, VehicleLifecycleEvent
from app.schemas.historical_order import HistoricalOrderCreate
from app.schemas.vehicle import VehicleCreate
from app.services.imports_service import _log_audit
from app.services.pdf_service import generate_and_upload_reception_pdf
from app.services.vehicle_service import vehicle_service

logger = logging.getLogger(__name__)

HISTORICAL_ENTRY_COMMENT = "Ingreso histórico manual"
AUDIT_ACTION = "MANUAL_HISTORICAL_ORDER"

# The system only ever sells UM motorcycles (see `vehicle_service.py`'s own
# docstring: "no incluye marca -- en este sistema la marca siempre es UM").
# `Vehicle.brand` is NOT NULL -- if a caller omits it entirely for a brand
# new vehicle, `BaseRepository.create`'s `obj_in.model_dump()` would send a
# bare `None` and blow up with an `IntegrityError` on a constraint that has
# nothing to do with duplication. Defaulting here keeps that failure mode
# from ever reaching the generic 409 mapping with a misleading cause.
DEFAULT_VEHICLE_BRAND = "UM"


# ---------------------------------------------------------------------------
# Step 1 — Client lookup-or-create
# ---------------------------------------------------------------------------

async def _lookup_or_create_client(db: AsyncSession, payload: HistoricalOrderCreate) -> User:
    phone = (payload.client.phone or "").strip() or None
    client: Optional[User] = None
    if phone:
        stmt = select(User).where(
            User.role == Role.client,
            User.tenant_id == payload.tenant_id,
            User.phone == phone,
        )
        client = (await db.execute(stmt)).scalars().first()
    if client:
        return client

    client = User(
        tenant_id=payload.tenant_id,
        name=payload.client.name,
        phone=payload.client.phone,
        role=Role.client,
        status=UserStatus.active,
        telegram_id=None,
    )
    db.add(client)
    await db.flush()
    return client


# ---------------------------------------------------------------------------
# Step 2 — Vehicle lookup-or-create (AS-IS call into vehicle_service)
# ---------------------------------------------------------------------------

async def _register_vehicle(db: AsyncSession, payload: HistoricalOrderCreate) -> Vehicle:
    # Only the fields the superadmin actually filled -- `exclude_unset`
    # mirrors `register_or_update_vehicle`'s own reliance on
    # `model_dump(exclude_unset=True)` for the UPDATE path so an omitted
    # field never blanks an existing column on an already-registered
    # vehicle.
    # sdd/vehicle-tenant-checkin-release PR2: no `tenant_id` set on the
    # vehicle -- `Vehicle`/`VehicleCreate` no longer carry one (a
    # vehicle's tenant is a derived, temporary claim, not a stored value).
    vehicle_fields = payload.vehicle.model_dump(exclude_unset=True)
    if not vehicle_fields.get("brand"):
        vehicle_fields["brand"] = DEFAULT_VEHICLE_BRAND

    vehicle_in = VehicleCreate(**vehicle_fields)
    return await vehicle_service.register_or_update_vehicle(db, vehicle_in)


# ---------------------------------------------------------------------------
# Step 3 — Duplicate check (plate + date), warn-never-block
# ---------------------------------------------------------------------------

async def _check_duplicate(db: AsyncSession, vehicle: Vehicle, payload: HistoricalOrderCreate) -> None:
    if payload.acknowledge_duplicate:
        return

    stmt = (
        select(ServiceOrder)
        .join(Vehicle, ServiceOrder.vehicle_id == Vehicle.id)
        .where(
            Vehicle.plate == vehicle.plate,
            func.date(ServiceOrder.created_at) == payload.created_at.date(),
        )
    )
    matches = (await db.execute(stmt)).scalars().all()
    if not matches:
        return

    raise HTTPException(
        status_code=409,
        detail={
            "detail": (
                f"Ya existe una orden para la placa {vehicle.plate} en la fecha "
                f"{payload.created_at.date()}."
            ),
            "code": "DUPLICATE_ORDER_WARNING",
            "matches": [
                {
                    "order_id": str(order.id),
                    "plate": vehicle.plate,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "status": order.status.value,
                }
                for order in matches
            ],
        },
    )


# ---------------------------------------------------------------------------
# OrderHistory chain (Decision 9 — no `in_progress` row)
# ---------------------------------------------------------------------------

# Statuses with no dedicated date field on `HistoricalOrderCreate` -- they
# describe an order that's still open (no completion/delivery date yet),
# just parked in a more specific live-tracking state than plain `received`.
# `cancelled` has no closing date either, so it's grouped here too rather
# than inventing a `cancelled_at` field this form doesn't need.
_OPEN_STATUSES = {
    ServiceStatus.received,
    ServiceStatus.pending_signature,
    ServiceStatus.scheduled,
    ServiceStatus.in_progress,
    ServiceStatus.on_hold_parts,
    ServiceStatus.rescheduled,
    ServiceStatus.on_hold_client,
    ServiceStatus.external_work,
    ServiceStatus.cancelled,
}


def _last_computed_status(payload: HistoricalOrderCreate) -> ServiceStatus:
    if payload.delivered_at is not None:
        return ServiceStatus.delivered
    if payload.completed_at is not None:
        return ServiceStatus.completed
    return ServiceStatus.received


def _validate_status_matches_dates(payload: HistoricalOrderCreate) -> None:
    """One-Submission Final State (spec) — `payload.status` MUST agree with
    the closing dates actually provided. Runs BEFORE any row is created so
    a mismatch never leaves a partially-built order to roll back.

    Open statuses (see `_OPEN_STATUSES`) are only valid when neither
    closing date is set -- they have no date of their own to justify. The
    two date-bound terminal statuses (`completed`/`delivered`) still must
    match exactly what the provided dates justify, same as before."""
    if payload.status in _OPEN_STATUSES:
        if payload.completed_at is not None or payload.delivered_at is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"El status '{payload.status.value}' no puede tener fecha de "
                    "finalización ni de entrega -- esos datos corresponden a "
                    "'completed'/'delivered'."
                ),
            )
        return

    expected = _last_computed_status(payload)
    if payload.status != expected:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El status '{payload.status.value}' no coincide con las fechas de cierre "
                f"provistas (se esperaba '{expected.value}')."
            ),
        )


def _history_rows_for_dates(
    order_id: uuid.UUID, payload: HistoricalOrderCreate, changed_by: Optional[uuid.UUID]
) -> list[OrderHistory]:
    """Per the design's table: always `None -> received`; `received ->
    completed` when `completed_at` is set; `completed -> delivered` (or
    `received -> delivered` if never completed) when `delivered_at` is set.
    No `in_progress` row (Decision 9 -- no paper timestamp for it)."""
    rows = [
        OrderHistory(
            order_id=order_id,
            from_status=None,
            to_status=ServiceStatus.received,
            changed_at=payload.created_at,
            changed_by=changed_by,
            comments=HISTORICAL_ENTRY_COMMENT,
        )
    ]

    if payload.completed_at is not None:
        rows.append(
            OrderHistory(
                order_id=order_id,
                from_status=ServiceStatus.received,
                to_status=ServiceStatus.completed,
                changed_at=payload.completed_at,
                changed_by=changed_by,
                comments=HISTORICAL_ENTRY_COMMENT,
            )
        )

    if payload.delivered_at is not None:
        prev_status = ServiceStatus.completed if payload.completed_at is not None else ServiceStatus.received
        rows.append(
            OrderHistory(
                order_id=order_id,
                from_status=prev_status,
                to_status=ServiceStatus.delivered,
                changed_at=payload.delivered_at,
                changed_by=changed_by,
                comments=HISTORICAL_ENTRY_COMMENT,
            )
        )

    return rows


def _backfill_durations(rows: list[OrderHistory]) -> None:
    """Each row's `duration_minutes` is the elapsed time to the NEXT row's
    `changed_at`; the last row keeps `None`. Plain float, matching
    `update_order_status`/`claim_order`'s existing convention (`orders.py
    :569`, `:783`) -- not `Decimal`."""
    for i in range(len(rows) - 1):
        delta = rows[i + 1].changed_at - rows[i].changed_at
        rows[i].duration_minutes = delta.total_seconds() / 60.0


def _build_history_chain(
    order_id: uuid.UUID, payload: HistoricalOrderCreate, actor: CurrentUser
) -> list[OrderHistory]:
    """Builds the OrderHistory rows directly, no Kanban machinery."""
    changed_by = uuid.UUID(actor.user_id) if actor.user_id else None
    rows = _history_rows_for_dates(order_id, payload, changed_by)
    _backfill_durations(rows)
    return rows


# ---------------------------------------------------------------------------
# VehicleLifecycleEvent(s) — event_date is the HISTORICAL date, never "now"
# ---------------------------------------------------------------------------

def _recepcion_event(
    payload: HistoricalOrderCreate, order: ServiceOrder, vehicle: Vehicle, client: User
) -> VehicleLifecycleEvent:
    return VehicleLifecycleEvent(
        vehicle_id=vehicle.id,
        event_type=LifecycleEventType.RECEPCION,
        event_date=payload.created_at,
        km_at_event=payload.mileage_km,
        # Must keep this EXACT shape -- `_resync_recepcion_summary`'s
        # `KM:\s*\d+(?:\.\d+)?` regex (superadmin_data.py) depends on it.
        summary=f"Recepción en taller. KM: {payload.mileage_km}. Cliente: {client.name}.",
        details=payload.customer_notes,
        linked_order_id=order.id,
        is_automatic="manual",
    )


def _service_type_event(
    payload: HistoricalOrderCreate, order: ServiceOrder, vehicle: Vehicle
) -> Optional[VehicleLifecycleEvent]:
    """GARANTIA or MANTENIMIENTO, only once the order is closed
    (`completed_at` set), exclusive on `service_type`."""
    if payload.completed_at is None:
        return None

    order_short_id = str(order.id)[:8]
    if payload.service_type == ServiceType.warranty:
        return VehicleLifecycleEvent(
            vehicle_id=vehicle.id,
            event_type=LifecycleEventType.GARANTIA,
            event_date=payload.completed_at,
            summary=f"Garantía aplicada. Orden {order_short_id}.",
            details=payload.diagnosis,
            linked_order_id=order.id,
            is_automatic="manual",
        )
    if payload.service_type == ServiceType.km_review:
        return VehicleLifecycleEvent(
            vehicle_id=vehicle.id,
            event_type=LifecycleEventType.MANTENIMIENTO,
            event_date=payload.completed_at,
            km_at_event=payload.mileage_km,
            summary=f"Mantenimiento por kilometraje realizado. Orden {order_short_id}.",
            details=payload.diagnosis,
            linked_order_id=order.id,
            is_automatic="manual",
        )
    return None


def _entrega_event(
    payload: HistoricalOrderCreate, order: ServiceOrder, vehicle: Vehicle
) -> Optional[VehicleLifecycleEvent]:
    if payload.delivered_at is None:
        return None
    return VehicleLifecycleEvent(
        vehicle_id=vehicle.id,
        event_type=LifecycleEventType.ENTREGA,
        event_date=payload.delivered_at,
        summary=f"Motocicleta entregada al cliente. Orden {str(order.id)[:8]}.",
        linked_order_id=order.id,
        is_automatic="manual",
    )


def _build_lifecycle_events(
    payload: HistoricalOrderCreate, order: ServiceOrder, vehicle: Vehicle, client: User
) -> list[VehicleLifecycleEvent]:
    events = [_recepcion_event(payload, order, vehicle, client)]
    for event in (
        _service_type_event(payload, order, vehicle),
        _entrega_event(payload, order, vehicle),
    ):
        if event is not None:
            events.append(event)
    return events


# ---------------------------------------------------------------------------
# PDF context dicts (mirrors orders.py:112-144, no "identification" key)
# ---------------------------------------------------------------------------

def _build_pdf_context(
    order: ServiceOrder,
    reception: ServiceOrderReception,
    vehicle: Vehicle,
    client: User,
    tenant: Optional[Tenant],
    payload: HistoricalOrderCreate,
) -> tuple[dict, dict, dict, dict, dict]:
    order_data = {
        "id": str(order.id),
        "service_type": payload.service_type.value,
        "date": payload.created_at.strftime("%Y-%m-%d %H:%M"),
        "bypass_at": reception.bypass_at.strftime("%Y-%m-%d %H:%M") if reception.bypass_at else None,
        "bypass_by_name": reception.bypass_by_name,
    }
    reception_data = {
        "mileage_km": payload.mileage_km,
        "gas_level": None,
        "customer_notes": payload.customer_notes,
        "warranty_warnings": None,
        "intake_answers": [],
        "accessories": [],
        "general_observations": payload.general_observations,
        "damage_photos_urls": [],
    }
    vehicle_data = {
        "model": vehicle.model if vehicle else "Desconocido",
        "plate": vehicle.plate if vehicle else "N/A",
        "vin": vehicle.vin if vehicle else "N/A",
        "motor": getattr(vehicle, "engine_number", None),
        "color": vehicle.color if vehicle else None,
    }
    # Deliberately NO "identification" key (Decision 6) -- the PDF template
    # already falls back to "N/A" for a missing value (`pdf_service.py`:
    # `client_data.get("identification", "N/A")`).
    client_data = {
        "full_name": client.name if client else "Cliente Pendiente",
        "email": client.email if client else None,
        "phone": client.phone if client else None,
    }
    tenant_data = {
        "name": tenant.name if tenant else "UM Colombia",
        "nit": tenant.nit if tenant else "",
        "phone": tenant.phone if tenant else "",
        "city": tenant.ciudad if tenant else "",
    }
    return order_data, reception_data, vehicle_data, client_data, tenant_data


# ---------------------------------------------------------------------------
# ImportAuditLog payload (JSON-safe — no cédula/identification key)
# ---------------------------------------------------------------------------

def _build_audit_payload(
    payload: HistoricalOrderCreate, client: User, vehicle: Vehicle, duplicate_acknowledged: bool
) -> dict:
    return {
        "tenant_id": str(payload.tenant_id),
        "client_id": str(client.id),
        "vehicle_id": str(vehicle.id),
        "duplicate_acknowledged": bool(duplicate_acknowledged),
        "service_type": payload.service_type.value,
        "status": payload.status.value,
        "mileage_km": str(payload.mileage_km),
        "created_at": payload.created_at.isoformat(),
        "completed_at": payload.completed_at.isoformat() if payload.completed_at else None,
        "delivered_at": payload.delivered_at.isoformat() if payload.delivered_at else None,
    }


# ---------------------------------------------------------------------------
# ServiceOrder / ServiceOrderReception / OrderWorkLog row builders
# ---------------------------------------------------------------------------

def _create_order_row(payload: HistoricalOrderCreate, vehicle: Vehicle, client: User) -> ServiceOrder:
    return ServiceOrder(
        tenant_id=payload.tenant_id,
        vehicle_id=vehicle.id,
        client_id=client.id,
        technician_id=payload.technician_id,
        status=payload.status,
        service_type=payload.service_type,
        created_at=payload.created_at,
        completed_at=payload.completed_at,
        delivered_at=payload.delivered_at,
    )


def _create_reception_row(
    payload: HistoricalOrderCreate, order: ServiceOrder, actor: CurrentUser
) -> ServiceOrderReception:
    actor_uuid = uuid.UUID(actor.user_id) if actor.user_id else None
    return ServiceOrderReception(
        order_id=order.id,
        mileage_km=payload.mileage_km,
        customer_notes=payload.customer_notes,
        general_observations=payload.general_observations,
        intake_answers=[],
        accessories=[],
        damage_photos_urls=[],
        warranty_warnings=None,
        created_at=payload.created_at,
        signature_url=None,
        accepted_at=None,
        accepted_phone=None,
        bypass_at=payload.created_at,
        bypass_by_id=actor_uuid,
        bypass_by_name=actor.name or "Superadmin",
    )


def _create_work_log_row(
    payload: HistoricalOrderCreate, order: ServiceOrder, history_rows: list[OrderHistory]
) -> Optional[OrderWorkLog]:
    """Only created when diagnosis text was actually provided (the column is
    NOT NULL). Links to the `completed` history row when one exists, else
    the initial `received` row."""
    if not payload.diagnosis:
        return None

    completed_row = next(
        (row for row in history_rows if row.to_status == ServiceStatus.completed), None
    )
    work_log_history_id = completed_row.id if completed_row is not None else history_rows[0].id
    return OrderWorkLog(
        order_id=order.id,
        history_id=work_log_history_id,
        diagnosis=payload.diagnosis,
        media_urls=[],
        recorded_by_telegram_id=None,
        created_at=payload.completed_at or payload.created_at,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def _persist_child_rows(
    db: AsyncSession,
    order: ServiceOrder,
    vehicle: Vehicle,
    client: User,
    payload: HistoricalOrderCreate,
    actor: CurrentUser,
) -> ServiceOrderReception:
    """Reception, OrderHistory chain, optional work log, and lifecycle
    events -- everything that hangs off `order` besides the PDF/audit
    steps (kept separate since those need the flushed reception row)."""
    reception = _create_reception_row(payload, order, actor)
    db.add(reception)
    await db.flush()

    history_rows = _build_history_chain(order.id, payload, actor)
    for row in history_rows:
        db.add(row)
    await db.flush()

    work_log = _create_work_log_row(payload, order, history_rows)
    if work_log is not None:
        db.add(work_log)

    for event in _build_lifecycle_events(payload, order, vehicle, client):
        db.add(event)

    return reception


async def _attach_pdf_and_audit(
    db: AsyncSession,
    order: ServiceOrder,
    reception: ServiceOrderReception,
    vehicle: Vehicle,
    client: User,
    payload: HistoricalOrderCreate,
    actor: CurrentUser,
) -> None:
    tenant = await db.get(Tenant, payload.tenant_id)
    order_data, reception_data, vehicle_data, client_data, tenant_data = _build_pdf_context(
        order, reception, vehicle, client, tenant, payload
    )
    reception.reception_pdf_url = await generate_and_upload_reception_pdf(
        order_data, reception_data, vehicle_data, client_data, tenant_data
    )

    _log_audit(
        db,
        actor,
        AUDIT_ACTION,
        "ServiceOrder",
        str(order.id),
        _build_audit_payload(payload, client, vehicle, payload.acknowledge_duplicate),
    )


async def create_historical_order(
    db: AsyncSession, payload: HistoricalOrderCreate, actor: CurrentUser
) -> ServiceOrder:
    try:
        # Pure/no-DB validation FIRST -- a status/date mismatch must reject
        # with ZERO writes, not after a client/vehicle has already been
        # looked-up-or-created.
        _validate_status_matches_dates(payload)

        client = await _lookup_or_create_client(db, payload)
        vehicle = await _register_vehicle(db, payload)
        await _check_duplicate(db, vehicle, payload)

        order = _create_order_row(payload, vehicle, client)
        db.add(order)
        await db.flush()

        reception = await _persist_child_rows(db, order, vehicle, client, payload, actor)
        await _attach_pdf_and_audit(db, order, reception, vehicle, client, payload, actor)

        await db.commit()
        return order

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        logger.exception("Integrity error creating historical order")
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible crear la orden histórica: conflicto de datos.",
        )
    except Exception:
        logger.exception("Unexpected error creating historical order")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Error interno al crear la orden histórica.",
        )
