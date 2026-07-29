"""
Distributor Vehicle Delivery — the transactional service backing
`POST /distributor/deliveries`.

`parts_dealer` (Distribuidor) or superadmin registration of a new
motorcycle sale/delivery: a client `User` (lookup-or-create by cédula) and
a `Vehicle` (lookup-or-create by plate, via `register_or_update_vehicle`
AS-IS) created/reused in ONE transaction, with a single `commit()` at the
very end -- same "Technical Approach" shape as `historical_order_service.
create_historical_order`.

Reuses `vehicle_service.register_or_update_vehicle` AS-IS (Design Decision
4) -- see `tests/distributor_deliveries/test_shared_service_contract.py`
for the contract lock (project memory bug #7: never change a shared
contract without checking every caller). `delivery_date`/`engine_number`/
`delivery_act_url` are deliberately NOT part of `VehicleCreate` -- they are
set directly on the returned ORM instance instead (Decision 4's whole
point: a client-controlled `VehicleCreate.delivery_date` would let
`POST /vehicles/` hard-block reception for that bike).

Only `_log_audit` (`imports_service.py`, a pure "build a row and `db.add`
it" helper) is reused for the audit trail, mirroring the same
read-only-import pattern `historical_order_service` already established.
"""
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser
from app.models.user import Role, User, UserStatus
from app.models.vehicle import Vehicle
from app.schemas.distributor_delivery import DeliveryCreate, DeliveryEditIn, DeliveryListItemOut
from app.schemas.vehicle import VehicleCreate
from app.services.imports_service import _log_audit
from app.services.pdf_service import upload_file_to_minio
from app.services.vehicle_service import vehicle_service

logger = logging.getLogger(__name__)

AUDIT_ACTION = "DISTRIBUTOR_VEHICLE_DELIVERY"

# Distributor delivery acts are a different document than a workshop's
# damage-reception photos -- they're commonly scanned/signed as PDF, so PDF
# is accepted alongside images (user decision, 2026-07-29).
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# The system only ever sells UM motorcycles (`vehicle_service.py`'s own
# docstring: "en este sistema la marca siempre es UM"). `DeliveryVehicleIn`
# has no `brand` field at all -- default it the same way
# `historical_order_service.py` does, so `Vehicle.brand` (NOT NULL) never
# receives a bare `None`.
DEFAULT_VEHICLE_BRAND = "UM"


# ---------------------------------------------------------------------------
# Pre-write validation (both run BEFORE any lookup-or-create, zero writes
# on rejection)
# ---------------------------------------------------------------------------

def _require_photo_or_superadmin(actor: CurrentUser, photo: Optional[UploadFile]) -> None:
    """Distribuidor MUST always attach the signed delivery-act photo -- no
    exception, a genuine new sale always has one. Superadmin MAY omit it,
    to support manually re-registering a pre-existing motorcycle that
    predates this system and has no physical signed act. Decided by ROLE,
    never by a client-supplied flag, and checked BEFORE any DB write
    (Design ADR 17/18)."""
    if photo is None and not actor.is_superadmin:
        raise HTTPException(
            status_code=422,
            detail="El acta de entrega firmada es obligatoria.",
        )


def _reject_future_delivery_date(delivery_date: date) -> None:
    """A typo'd FUTURE delivery date would hard-block `POST /orders/` for
    that bike (the warranty lower-bound check has no client-supplied date
    at that path -- its effective date is always "now"). `utcnow().date()`
    is deliberately the reference, not a local/Bogotá date: UTC is always
    equal to or AHEAD of Bogotá (UTC-5), so this can never falsely reject a
    delivery genuinely submitted "today" in Bogotá -- same reasoning as
    `warranty_validation.ensure_order_date_after_delivery`."""
    if delivery_date > datetime.utcnow().date():
        raise HTTPException(
            status_code=422,
            detail="La fecha de entrega no puede ser una fecha futura.",
        )


# ---------------------------------------------------------------------------
# Step 1 — Client lookup-or-create (cédula, global, Design ADR 11)
# ---------------------------------------------------------------------------

async def _lookup_or_create_client(
    db: AsyncSession, payload: DeliveryCreate, actor: CurrentUser
) -> User:
    identification = payload.client.identification.strip()
    stmt = select(User).where(
        User.role == Role.client,
        User.identification == identification,
    )
    client = (await db.execute(stmt)).scalars().first()
    if client:
        # Most-recent-submission wins (user decision, 2026-07-28): a
        # re-delivery for an existing cedula refreshes the stored client's
        # data rather than keeping the first-ever values -- this is the
        # exact mechanism the manual legacy-vehicle backfill flow relies on.
        client.name = payload.client.name
        client.phone = payload.client.phone
        client.email = payload.client.email
        client.birth_date = payload.client.birth_date
        client.city = payload.client.city
        client.department = payload.client.department
        client.address = payload.client.address
        return client

    client = User(
        tenant_id=actor.tenant_id,
        name=payload.client.name,
        phone=payload.client.phone,
        email=payload.client.email,
        role=Role.client,
        status=UserStatus.active,
        telegram_id=None,
        identification=identification,
        birth_date=payload.client.birth_date,
        city=payload.client.city,
        department=payload.client.department,
        address=payload.client.address,
    )
    db.add(client)
    await db.flush()
    return client


# ---------------------------------------------------------------------------
# Step 2 — Vehicle lookup-or-create (AS-IS call into vehicle_service)
# ---------------------------------------------------------------------------

async def _register_vehicle(db: AsyncSession, payload: DeliveryCreate) -> Vehicle:
    # `engine_number` is deliberately excluded -- it is NOT a `VehicleCreate`
    # field (Design Decision 4); `_apply_delivery_fields` sets it directly
    # on the returned ORM instance instead.
    vehicle_fields = payload.vehicle.model_dump(exclude_unset=True, exclude={"engine_number"})
    if not vehicle_fields.get("brand"):
        vehicle_fields["brand"] = DEFAULT_VEHICLE_BRAND

    vehicle_in = VehicleCreate(**vehicle_fields)
    return await vehicle_service.register_or_update_vehicle(db, vehicle_in)


# ---------------------------------------------------------------------------
# Step 3 — delivery_date / engine_number / client_id, set directly on the
# ORM instance (Design Decision 4/5)
# ---------------------------------------------------------------------------

def _apply_delivery_fields(
    vehicle: Vehicle, payload: DeliveryCreate, client: User, actor: CurrentUser
) -> None:
    vehicle.delivery_date = payload.delivery_date
    if payload.vehicle.engine_number:
        vehicle.engine_number = payload.vehicle.engine_number
    vehicle.client_id = client.id
    # Which Distribuidora registered THIS record -- the actor's own tenant,
    # set once at creation and never changed afterward (follow-up feature,
    # migration `c9d0e1f2a3b4`). `actor.tenant_id` is `None` for a
    # Distribuidor with no tenant assigned yet, or for a superadmin manual
    # legacy-vehicle backfill -- both expected, not bugs: the record simply
    # isn't "owned" by any Distribuidora and only shows up in superadmin's
    # unfiltered view of `GET /distributor/deliveries`.
    vehicle.registered_by_tenant_id = actor.tenant_id


# ---------------------------------------------------------------------------
# Step 4 — delivery-act photo (inline, optional -- ADR 18)
# ---------------------------------------------------------------------------

async def _attach_photo(vehicle: Vehicle, photo: Optional[UploadFile]) -> None:
    if photo is None:
        return
    if photo.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de archivo no permitido: {photo.content_type}. Solo se aceptan imágenes o PDF.",
        )
    contents = await photo.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo '{photo.filename}' supera el límite de 10 MB.",
        )
    file_url = await upload_file_to_minio(
        file_bytes=contents, file_name=photo.filename, content_type=photo.content_type
    )
    vehicle.delivery_act_url = file_url


# ---------------------------------------------------------------------------
# ImportAuditLog payload (JSON-safe -- no identification/birth_date/address)
# ---------------------------------------------------------------------------

def _build_audit_payload(
    payload: DeliveryCreate, client: User, vehicle: Vehicle, photo_provided: bool
) -> dict:
    return {
        "client_id": str(client.id),
        "vehicle_id": str(vehicle.id),
        "plate": vehicle.plate,
        "delivery_date": payload.delivery_date.isoformat(),
        "photo_provided": bool(photo_provided),
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def create_delivery(
    db: AsyncSession,
    payload: DeliveryCreate,
    photo: Optional[UploadFile],
    actor: CurrentUser,
) -> Vehicle:
    try:
        # Pure/no-DB validation FIRST -- both reject with ZERO writes,
        # before the client/vehicle is ever looked-up-or-created.
        _require_photo_or_superadmin(actor, photo)
        _reject_future_delivery_date(payload.delivery_date)

        client = await _lookup_or_create_client(db, payload, actor)
        vehicle = await _register_vehicle(db, payload)
        _apply_delivery_fields(vehicle, payload, client, actor)
        await _attach_photo(vehicle, photo)

        _log_audit(
            db,
            actor,
            AUDIT_ACTION,
            "Vehicle",
            str(vehicle.id),
            _build_audit_payload(payload, client, vehicle, photo is not None),
        )

        await db.commit()
        return vehicle

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        logger.exception("Integrity error creating distributor delivery")
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible registrar la entrega: conflicto de datos.",
        )
    except Exception:
        logger.exception("Unexpected error creating distributor delivery")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Error interno al registrar la entrega.",
        )


# ---------------------------------------------------------------------------
# Act-photo retry/replace path (Design ADR 6) -- reused by the standalone
# `POST /distributor/deliveries/{vehicle_id}/act-photo` endpoint.
# ---------------------------------------------------------------------------

async def attach_act_photo(db: AsyncSession, vehicle: Vehicle, photo: UploadFile) -> Vehicle:
    try:
        await _attach_photo(vehicle, photo)
        await db.commit()
        return vehicle
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        logger.exception("Integrity error attaching delivery-act photo")
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible adjuntar el acta: conflicto de datos.",
        )
    except Exception:
        logger.exception("Unexpected error attaching delivery-act photo")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Error interno al adjuntar el acta de entrega.",
        )


# ---------------------------------------------------------------------------
# `GET /distributor/deliveries` -- the list of registrations already made
# (follow-up feature, migration `c9d0e1f2a3b4`).
# ---------------------------------------------------------------------------

async def list_deliveries(db: AsyncSession, actor: CurrentUser) -> list[DeliveryListItemOut]:
    """Tenant-scoped list of delivery records. Superadmin sees every
    Distribuidora's rows (network-wide); a Distribuidor sees only rows
    `registered_by_tenant_id == actor.tenant_id` -- shared across every
    user at the SAME Distribuidora, not just the one who typed it in.

    IMPORTANT deviation from a literal "let SQL do it naturally" reading:
    SQLAlchemy's ORM `Column == None` compiles to `IS NULL`, NOT the raw-SQL
    `= NULL` footgun that never matches anything. If `actor.tenant_id` is
    `None` (Distribuidor with no tenant assigned yet) and this were left
    unguarded, `Vehicle.registered_by_tenant_id == actor.tenant_id` would
    compile to `registered_by_tenant_id IS NULL` and WOULD match every
    other NULL-tenant row -- every superadmin backfill and every other
    tenant-less Distribuidor's rows, a real data leak, not an empty list.
    The explicit early-return below is required to make the actual
    documented requirement ("empty list, never someone else's data") true;
    it also means zero DB reads happen in that case, same discipline as
    `forbid_distribuidor`.
    """
    if not actor.is_superadmin and actor.tenant_id is None:
        return []

    stmt = (
        select(Vehicle)
        .where(Vehicle.delivery_date.isnot(None))
        .options(selectinload(Vehicle.client), selectinload(Vehicle.registered_by_tenant))
        .order_by(Vehicle.delivery_date.desc())
    )
    if not actor.is_superadmin:
        stmt = stmt.where(Vehicle.registered_by_tenant_id == actor.tenant_id)

    vehicles = (await db.execute(stmt)).scalars().all()

    items = []
    for vehicle in vehicles:
        items.append(
            DeliveryListItemOut(
                id=vehicle.id,
                plate=vehicle.plate,
                vin=vehicle.vin,
                model=vehicle.model,
                delivery_date=vehicle.delivery_date,
                client_name=vehicle.client.name if vehicle.client else None,
                registered_by_tenant_name=(
                    vehicle.registered_by_tenant.name
                    if actor.is_superadmin and vehicle.registered_by_tenant
                    else None
                ),
            )
        )
    return items


# ---------------------------------------------------------------------------
# `PATCH /distributor/deliveries/{vehicle_id}` -- superadmin-only edit of a
# delivery record's basic info (router enforces the superadmin-only guard,
# NOT this function -- same "guard in the router, business logic in the
# service" split as `create_delivery`/`require_distribuidor`).
# ---------------------------------------------------------------------------

async def edit_delivery(
    db: AsyncSession, vehicle_id, payload: DeliveryEditIn
) -> Vehicle:
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.delivery_date is None:
        raise HTTPException(status_code=404, detail="Registro de entrega no encontrado")

    fields = payload.model_dump(exclude_unset=True)

    # Validate FIRST -- zero mutations happen before a 422 is raised
    # (Design ADR pattern reused verbatim from `_reject_future_delivery_date`,
    # same module, no duplication needed).
    if fields.get("delivery_date") is not None:
        _reject_future_delivery_date(fields["delivery_date"])

    try:
        if fields.get("plate") is not None:
            vehicle.plate = fields["plate"]
        if "vin" in fields:
            vehicle.vin = fields["vin"]
        if fields.get("delivery_date") is not None:
            vehicle.delivery_date = fields["delivery_date"]

        # `client_name`/`client_phone` are silently no-op'd when the vehicle
        # has no linked client -- not every historical row is guaranteed to
        # have one (task requirement, not an oversight).
        wants_client_edit = "client_name" in fields or "client_phone" in fields
        if wants_client_edit and vehicle.client_id is not None:
            client = await db.get(User, vehicle.client_id)
            if client is not None:
                if fields.get("client_name") is not None:
                    client.name = fields["client_name"]
                if "client_phone" in fields:
                    client.phone = fields["client_phone"]

        await db.commit()
        return vehicle
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        logger.exception("Integrity error editing distributor delivery")
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No fue posible editar la entrega: conflicto de datos.",
        )
    except Exception:
        logger.exception("Unexpected error editing distributor delivery")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Error interno al editar la entrega.",
        )
