"""
Superadmin Data Editor — Vehículo + Orden quick-fix.

Two self-contained, whitelisted, superadmin-only endpoints that let a
superadmin correct bad intake data (vehicle identifiers, order dates,
mileage/service_type) without SQL access. Mirrors the `app/api/v1/settings.py`
pattern: an internal `APIRouter`, inline Pydantic bodies acting as the
whitelist (no dict is ever passed to a generic update helper), and a
per-route `current_user.is_superadmin` guard.

Phase 1: router registration + both request schemas + guarded route stubs.
Phase 2: Vehicle quick-fix GET/PUT — whitelist diff per field, one audit
row per changed field, 409 on duplicate-plate conflict, no audit row on a
no-op submission.
Phase 3: Order quick-fix — dates only (`created_at`, `delivered_at`). Same
whitelist-diff-audit pattern as Vehicle, plus an unconditional 422 block
when the resulting `delivered_at` would precede the resulting `created_at`
— no exceptions, per the spec's "Delivered-Before-Created Is Blocked
Unconditionally" requirement.
Phase 4: Order quick-fix — `mileage_km` (lives on
`ServiceOrderReception`) and `service_type`, kept in sync with the
vehicle's lifecycle events: the `RECEPCION` event (always exists) resyncs
`km_at_event`/`summary` on any mileage correction; a linked completion
event (`GARANTIA`/`MANTENIMIENTO`, if one already exists) resyncs its `km`
on a mileage correction, or converts in place on a warranty<->km_review
`service_type` correction.
Phase 5 (this batch): the one remaining `service_type` transition —
correcting AWAY from an event-producing type (warranty/km_review) to a
non-event type (regular/quick/pdi) while a completion event already
exists. That transition does not update/convert history, it DELETES it,
so it goes through an explicit confirm-then-delete flow: a first request
without `confirm_delete_event` returns 409 `CONFIRM_DELETE_EVENT` (zero
writes, dry-run), and a second request with `confirm_delete_event: true`
deletes the stale event and applies the field changes in the same
transaction, recording a `lifecycle_event_deleted` audit marker. Mirrors
the `{"detail": ..., "code": ...}` 409 envelope already established in
`imports.py`'s already-confirmed-lot guard family.
"""
import re
from decimal import Decimal
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, Field

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.order import ServiceOrder, ServiceOrderReception, ServiceType
from app.models.vehicle import Vehicle
from app.models.vehicle_lifecycle import VehicleLifecycleEvent, LifecycleEventType
from app.services.imports_service import _log_audit

router = APIRouter(prefix="/superadmin/data", tags=["superadmin_data"])


class VehicleQuickFixUpdate(BaseModel):
    """Whitelisted vehicle fields a superadmin may correct.
    `plate`, `brand`, `model` are NOT NULL in `vehicles` — required here too."""
    plate: str
    brand: str
    model: str
    vin: Optional[str] = None
    color: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = Field(None, ge=0)


class OrderQuickFixUpdate(BaseModel):
    """Whitelisted order fields a superadmin may correct.
    `mileage_km` lives on `ServiceOrderReception`, not `ServiceOrder`.
    `confirm_delete_event` only acknowledges the lifecycle-event deletion
    described in the design's confirm-then-delete flow — it never changes
    a field by itself."""
    created_at: datetime
    delivered_at: Optional[datetime] = None
    mileage_km: Optional[Decimal] = Field(None, ge=0)
    service_type: Optional[ServiceType] = None
    confirm_delete_event: bool = False


def _require_superadmin(current_user: CurrentUser) -> None:
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")


def _log_field_changes(
    db: AsyncSession, current_user: CurrentUser, entity_type: str, entity_id: str, changes: dict
) -> None:
    """One `_log_audit` row per changed field -- shared by both quick-fix
    routes so the "one row per field, skipped entirely on no-op" contract
    lives in a single place."""
    for field_name, change in changes.items():
        _log_audit(
            db, current_user, "SUPERADMIN_DATA_FIX", entity_type, entity_id,
            {field_name: change},
        )


def _serialize_vehicle(vehicle: Vehicle) -> dict:
    return {
        "id": str(vehicle.id),
        "plate": vehicle.plate,
        "vin": vehicle.vin,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "color": vehicle.color,
        "year": vehicle.year,
        "mileage": vehicle.mileage,
    }


@router.get("/vehicles")
async def search_vehicles(
    plate: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Búsqueda de vehículo por placa (global, sin filtro de tenant —
    superadmin opera en toda la red)."""
    _require_superadmin(current_user)
    clean_plate = "".join(str(plate).split()).upper() if plate else None
    vehicle = None
    if clean_plate:
        stmt = select(Vehicle).where(Vehicle.plate == clean_plate)
        vehicle = (await db.execute(stmt)).scalars().first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return _serialize_vehicle(vehicle)


@router.put("/vehicles/{vehicle_id}")
async def update_vehicle(
    vehicle_id: uuid.UUID,
    payload: VehicleQuickFixUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Corrección de datos de vehículo: diff por campo contra la base
    (el schema `VehicleQuickFixUpdate` YA es la whitelist — cualquier otro
    campo enviado se ignora), una fila de auditoría por campo cambiado, sin
    fila de auditoría si la petición es un no-op, y 409 si la placa nueva
    ya está en uso por otro vehículo."""
    _require_superadmin(current_user)
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    # `exclude_unset=True` keeps fields the request body never mentioned out
    # of the dict entirely -- omitting an optional field must leave the DB
    # value untouched, while explicitly sending it as `null` is the one
    # legitimate way to clear it. Required fields (`plate`/`brand`/`model`)
    # have no default, so they are always present here regardless.
    changes: dict = {}
    for field_name, new_value in payload.model_dump(exclude_unset=True).items():
        old_value = getattr(vehicle, field_name)
        if str(old_value) != str(new_value):
            changes[field_name] = {"old": old_value, "new": new_value}
            setattr(vehicle, field_name, new_value)

    _log_field_changes(db, current_user, "Vehicle", str(vehicle.id), changes)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="La placa ya está registrada en otro vehículo",
        )

    await db.refresh(vehicle)
    return _serialize_vehicle(vehicle)


def _serialize_order(order: ServiceOrder, reception: Optional[ServiceOrderReception] = None) -> dict:
    return {
        "id": str(order.id),
        "plate": order.plate,
        "status": order.status.value if order.status else None,
        "service_type": order.service_type.value if order.service_type else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "mileage_km": str(reception.mileage_km) if reception is not None and reception.mileage_km is not None else None,
    }


# Service types whose completion creates a GARANTIA/MANTENIMIENTO lifecycle
# event (mirrors `orders.py` ~L616-639). Used both to detect the warranty<->
# km_review auto-remap (Phase 4) and, in this Phase 5 batch, to detect the
# away-from-event-producing-type transition that requires confirm-then-delete.
_EVENT_PRODUCING_SERVICE_TYPES = {
    ServiceType.warranty: LifecycleEventType.GARANTIA,
    ServiceType.km_review: LifecycleEventType.MANTENIMIENTO,
}


def _garantia_summary(order_id) -> str:
    return f"Garantía aplicada. Orden {str(order_id)[:8]}."


def _mantenimiento_summary(order_id) -> str:
    return f"Mantenimiento por kilometraje realizado. Orden {str(order_id)[:8]}."


def _resync_recepcion_summary(summary: Optional[str], new_mileage) -> Optional[str]:
    """Replace the `KM: <value>` token embedded in the RECEPCION event's
    summary (see `orders.py` ~L160: `f"Recepción en taller. KM: {mileage}...."`)
    with the corrected mileage. If the token is absent, the summary is left
    untouched (the caller still updates `km_at_event` regardless)."""
    if not summary:
        return summary
    # `\d+(?:\.\d+)?` (not the greedier `[\d.]+`) so a decimal fraction is
    # consumed but the sentence-ending period after a bare integer (e.g.
    # "KM: 20000. Cliente: ...") is left untouched.
    return re.sub(r"KM:\s*\d+(?:\.\d+)?", f"KM: {new_mileage}", summary)


def _apply_mileage_correction(
    reception: ServiceOrderReception,
    new_mileage: Decimal,
    recepcion_event: Optional[VehicleLifecycleEvent],
    completion_event: Optional[VehicleLifecycleEvent],
) -> Optional[dict]:
    """Applies a `mileage_km` correction to `reception` and resyncs, in
    place, the linked RECEPCION event (always exists) and the MANTENIMIENTO
    completion event (only if one already exists -- GARANTIA never carries
    a `km_at_event`). Returns the audit change dict for `mileage_km`, or
    `None` if the new value equals the current one (no-op, no audit row)."""
    old_mileage = reception.mileage_km
    if str(old_mileage) == str(new_mileage):
        return None

    reception.mileage_km = new_mileage
    synced_event_ids: list = []

    if recepcion_event is not None:
        recepcion_event.km_at_event = new_mileage
        recepcion_event.summary = _resync_recepcion_summary(recepcion_event.summary, new_mileage)
        synced_event_ids.append(str(recepcion_event.id))

    if completion_event is not None and completion_event.event_type == LifecycleEventType.MANTENIMIENTO:
        completion_event.km_at_event = new_mileage
        synced_event_ids.append(str(completion_event.id))

    change = {"old": old_mileage, "new": new_mileage}
    if synced_event_ids:
        change["lifecycle_event_synced"] = synced_event_ids
    return change


def _needs_delete_confirmation(
    old_service_type: ServiceType,
    new_service_type: Optional[ServiceType],
    completion_event: Optional[VehicleLifecycleEvent],
) -> bool:
    """`True` only for the one `service_type` transition that DELETES
    history instead of updating/converting it in place: correcting AWAY
    from an event-producing type (warranty/km_review) to a non-event type
    (regular/quick/pdi) while a completion event (GARANTIA/MANTENIMIENTO)
    still exists for this order. `False` for: no `service_type` change
    requested, no completion event to begin with (nothing to delete), or
    the warranty<->km_review auto-remap (a valid target event type exists,
    so it converts in place -- see `_apply_service_type_correction`)."""
    if new_service_type is None or completion_event is None:
        return False
    return (
        old_service_type in _EVENT_PRODUCING_SERVICE_TYPES
        and new_service_type not in _EVENT_PRODUCING_SERVICE_TYPES
    )


def _confirm_delete_event_message(event: VehicleLifecycleEvent, plate: Optional[str]) -> str:
    """Describes exactly what the confirm-then-delete flow would delete --
    event type, id, and the vehicle it belongs to -- per the spec's
    "naming the event's id/type and the vehicle it belongs to" requirement.
    Mirrors the wording style of `imports.py`'s `_confirmed_lot_message`."""
    vehicle_ref = plate or "sin placa registrada"
    return (
        f"Esta corrección eliminará el evento {event.event_type.value} "
        f"(id {event.id}) del historial del vehículo {vehicle_ref}. "
        "Envíe confirm_delete_event=true para continuar."
    )


async def _handle_delete_confirmation(
    db: AsyncSession,
    order: ServiceOrder,
    new_service_type: Optional[ServiceType],
    completion_event: Optional[VehicleLifecycleEvent],
    confirm_delete_event: bool,
) -> Optional[dict]:
    """Gate + side effect for the one `service_type` transition that DELETES
    history instead of updating it in place. READ-ONLY (raises, no writes)
    when confirmation is needed but `confirm_delete_event` wasn't sent --
    the whole request is rejected wholesale, before any other field is
    touched. When confirmed, snapshots and deletes the stale completion
    event (in the SAME transaction the caller commits later) and returns
    that snapshot for the audit row. Returns `None` whenever no deletion is
    needed or performed (including the "event already gone" race case,
    since a fresh `completion_event=None` here means nothing to delete)."""
    if not _needs_delete_confirmation(order.service_type, new_service_type, completion_event):
        return None
    if not confirm_delete_event:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": _confirm_delete_event_message(completion_event, order.plate),
                "code": "CONFIRM_DELETE_EVENT",
            },
        )
    # Snapshot the full event BEFORE deleting it -- the only durable
    # recovery trail for an irreversible history removal.
    snapshot = {
        "id": str(completion_event.id),
        "event_type": completion_event.event_type.value,
        "summary": completion_event.summary,
    }
    await db.delete(completion_event)
    return snapshot


def _apply_service_type_correction(
    order: ServiceOrder,
    new_service_type: ServiceType,
    reception: Optional[ServiceOrderReception],
    completion_event: Optional[VehicleLifecycleEvent],
) -> Optional[dict]:
    """Applies a `service_type` correction to `order`. ONLY the warranty<->
    km_review auto-remap converts the linked completion event in place (a
    valid target event type always exists, so no confirmation is needed).
    Any other transition needs no in-place conversion here: the away-from-
    event-producing-type case has ALREADY had its completion event deleted
    (and `completion_event` reset to `None`) by the caller before this runs
    -- see `update_order`'s confirm-then-delete branch -- and the case with
    no completion event at all simply has nothing to sync. Returns the
    audit change dict for `service_type`, or `None` if the new value equals
    the current one (no-op, no audit row).

    Callers MUST apply any `mileage_km` correction to `reception` BEFORE
    calling this -- the MANTENIMIENTO conversion reads `reception.mileage_km`
    as the effective (already-corrected, if applicable) value for the new
    event's `km_at_event`."""
    old_service_type = order.service_type
    if str(old_service_type) == str(new_service_type):
        return None

    change = {"old": old_service_type, "new": new_service_type}
    order.service_type = new_service_type

    old_event_type = _EVENT_PRODUCING_SERVICE_TYPES.get(old_service_type)
    new_event_type = _EVENT_PRODUCING_SERVICE_TYPES.get(new_service_type)

    if old_event_type is not None and new_event_type is not None and completion_event is not None:
        completion_event.event_type = new_event_type
        if new_event_type == LifecycleEventType.MANTENIMIENTO:
            completion_event.km_at_event = reception.mileage_km if reception is not None else None
            completion_event.summary = _mantenimiento_summary(order.id)
        else:
            completion_event.km_at_event = None
            completion_event.summary = _garantia_summary(order.id)
        change["lifecycle_event_synced"] = [str(completion_event.id)]

    return change


@router.get("/orders")
async def search_orders(
    plate: Optional[str] = None,
    order_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Búsqueda de orden por id (prioridad) o por placa (más reciente,
    global — sin filtro de tenant ni de estado, ya que un superadmin debe
    poder corregir órdenes históricas en cualquier estado)."""
    _require_superadmin(current_user)
    order = None
    if order_id:
        order = await db.get(ServiceOrder, order_id)
    elif plate:
        clean_plate = "".join(str(plate).split()).upper()
        stmt = (
            select(ServiceOrder)
            .join(Vehicle, ServiceOrder.vehicle_id == Vehicle.id)
            .where(Vehicle.plate == clean_plate)
            .order_by(ServiceOrder.created_at.desc())
            .limit(1)
        )
        order = (await db.execute(stmt)).scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return _serialize_order(order)


# Plain order date fields diffed the same simple way as Phase 2's Vehicle
# fields. `mileage_km`/`service_type` need reception/lifecycle-event lookups
# and are handled separately below (Phase 4).
_ORDER_DATE_FIELDS = ("created_at", "delivered_at")


def _ensure_delivered_after_created(provided: dict, order: ServiceOrder) -> None:
    """Unconditional 422 block: the resulting `delivered_at` (merged with
    the DB value when omitted from the request) must never precede the
    resulting `created_at` -- no exceptions."""
    effective_created_at = provided.get("created_at", order.created_at)
    effective_delivered_at = (
        provided["delivered_at"] if "delivered_at" in provided else order.delivered_at
    )
    if effective_delivered_at is not None and effective_delivered_at < effective_created_at:
        raise HTTPException(
            status_code=422,
            detail="La fecha de entrega no puede ser anterior a la fecha de creación",
        )


async def _load_lifecycle_correction_context(
    db: AsyncSession, order: ServiceOrder, new_mileage, new_service_type
) -> tuple:
    """Fetches `order`'s `ServiceOrderReception` and linked lifecycle events
    -- ONLY when a `mileage_km`/`service_type` correction is actually being
    requested, to avoid the extra queries on plain date edits. Returns
    `(reception, recepcion_event, completion_event)`; all `None`/empty when
    neither field is being corrected or no such rows exist."""
    if new_mileage is None and new_service_type is None:
        return None, None, None

    reception = (
        await db.execute(select(ServiceOrderReception).where(ServiceOrderReception.order_id == order.id))
    ).scalars().first()
    lifecycle_events = (
        await db.execute(select(VehicleLifecycleEvent).where(VehicleLifecycleEvent.linked_order_id == order.id))
    ).scalars().all()

    recepcion_event = next((e for e in lifecycle_events if e.event_type == LifecycleEventType.RECEPCION), None)
    completion_event = next(
        (e for e in lifecycle_events if e.event_type in (LifecycleEventType.GARANTIA, LifecycleEventType.MANTENIMIENTO)),
        None,
    )
    return reception, recepcion_event, completion_event


def _diff_date_fields(order: ServiceOrder, provided: dict) -> dict:
    """Diffs `_ORDER_DATE_FIELDS` (only the keys actually present in
    `provided`, per the `exclude_unset` field-presence contract) against
    `order`, applying and returning changes for the ones that differ."""
    changes: dict = {}
    for field_name in _ORDER_DATE_FIELDS:
        if field_name not in provided:
            continue
        new_value = provided[field_name]
        old_value = getattr(order, field_name)
        if str(old_value) != str(new_value):
            changes[field_name] = {"old": old_value, "new": new_value}
            setattr(order, field_name, new_value)
    return changes


@router.put("/orders/{order_id}")
async def update_order(
    order_id: uuid.UUID,
    payload: OrderQuickFixUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Corrección de orden: fechas (`created_at`/`delivered_at`), kilometraje
    (`mileage_km`, vive en `ServiceOrderReception`) y `service_type` — diff
    por campo contra la base, una fila de auditoría por campo cambiado, sin
    fila de auditoría si la petición es un no-op, y bloqueo incondicional
    (422) si la fecha de entrega resultante quedara antes que la fecha de
    creación resultante — sin excepciones.
    Una corrección de `mileage_km` resincroniza, en la misma transacción,
    el evento RECEPCION (siempre existe) y el evento de finalización
    MANTENIMIENTO (si ya existe). Una corrección de `service_type` que
    alterna entre `warranty` y `km_review` convierte el evento de
    finalización existente in place (GARANTIA<->MANTENIMIENTO) sin pedir
    confirmación. El caso de corregir `service_type` ALEJÁNDOSE de un tipo
    que genera evento (warranty/km_review) hacia uno que no (regular/quick/
    pdi) mientras un evento de finalización ya existe requiere confirmación
    explícita: sin `confirm_delete_event`, responde 409 `CONFIRM_DELETE_EVENT`
    sin aplicar ningún cambio; con `confirm_delete_event=true`, elimina el
    evento obsoleto y aplica los cambios en la misma transacción, dejando
    una marca `lifecycle_event_deleted` en la auditoría."""
    _require_superadmin(current_user)
    order = await db.get(ServiceOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    # `exclude_unset=True` distinguishes "key absent from the request body"
    # from "key explicitly sent as null". A field the caller never mentioned
    # must not be diffed/applied at all -- the DB value is the effective
    # value for that field. `created_at` is required (no default) so it is
    # always present here; `delivered_at` may legitimately be absent.
    provided = payload.model_dump(exclude_unset=True)
    _ensure_delivered_after_created(provided, order)

    # `mileage_km`/`service_type` are NOT NULL at the DB level (unlike
    # `delivered_at`) -- there is no legitimate "clear it" use case, so an
    # explicit `null` is treated the same as "field omitted": only a real
    # value triggers a correction and the reception/lifecycle-events lookup.
    new_mileage = provided.get("mileage_km")
    new_service_type = provided.get("service_type")
    reception, recepcion_event, completion_event = await _load_lifecycle_correction_context(
        db, order, new_mileage, new_service_type
    )

    # Detection+delete is READ-ONLY until confirmed, and MUST run before any
    # setattr below -- a request that needs confirmation is rejected
    # wholesale (zero writes, not even to unrelated date fields in the same
    # request), per the spec's dry-run requirement.
    deleted_event_snapshot = await _handle_delete_confirmation(
        db, order, new_service_type, completion_event, payload.confirm_delete_event
    )
    if deleted_event_snapshot is not None:
        completion_event = None

    changes = _diff_date_fields(order, provided)

    # Mileage MUST be applied before service_type: the warranty->km_review
    # conversion below reads `reception.mileage_km` as the effective value
    # for the (new) MANTENIMIENTO event's `km_at_event`.
    if reception is not None and new_mileage is not None:
        mileage_change = _apply_mileage_correction(reception, new_mileage, recepcion_event, completion_event)
        if mileage_change is not None:
            changes["mileage_km"] = mileage_change

    if new_service_type is not None:
        service_type_change = _apply_service_type_correction(order, new_service_type, reception, completion_event)
        if service_type_change is not None:
            if deleted_event_snapshot is not None:
                service_type_change["lifecycle_event_deleted"] = deleted_event_snapshot
            changes["service_type"] = service_type_change

    _log_field_changes(db, current_user, "ServiceOrder", str(order.id), changes)

    # Single commit boundary for the WHOLE correction (dates + mileage +
    # service_type + any lifecycle-event sync/deletion) -- a failure here
    # rolls back everything atomically, mirroring `update_vehicle`'s
    # IntegrityError->409 handling instead of leaking a raw 500.
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible guardar la corrección por un conflicto de datos",
        )

    await db.refresh(order)
    return _serialize_order(order, reception)
