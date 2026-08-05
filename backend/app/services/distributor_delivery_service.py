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
import mimetypes
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser
from app.models.tenant import Tenant
from app.models.user import Role, User, UserStatus
from app.models.vehicle import Vehicle
from app.schemas.distributor_delivery import (
    DeliveryCreate,
    DeliveryDetailOut,
    DeliveryEditIn,
    DeliveryListItemOut,
)
from app.schemas.vehicle import VehicleCreate
from app.services.divipola_service import resolve_geo
from app.services.imports_service import _log_audit
from app.services.pdf_service import BUCKET_NAME, get_pdf_stream_from_minio, upload_file_to_minio
from app.services.vehicle_service import vehicle_service
from app.services.vin_master_service import vin_master_service

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


VIN_NOT_FOUND_DETAIL = (
    "El VIN no fue encontrado en el maestro de motocicletas. "
    "Verificá que esté bien digitado."
)


async def _require_vin_in_master(db: AsyncSession, vin: Optional[str]) -> None:
    """Follow-up fix (2026-07-30, user decision): the VIN is mandatory AND
    must exist in the VIN master catalog (`vin_master_service.query_vin`,
    which already applies the 17-char VIN rule internally) -- no exception
    anywhere in this feature, including superadmin's manual legacy-vehicle
    backfill (unlike the mandatory-photo rule, which DOES exempt
    superadmin). Checked BEFORE any DB write/mutation, same "validate
    first" discipline as `_reject_future_delivery_date` -- the difference
    is this one needs an async DB lookup, so it must be awaited inside the
    caller, not a bare sync helper like its siblings."""
    if not vin or not vin.strip():
        raise HTTPException(status_code=422, detail=VIN_NOT_FOUND_DETAIL)
    result = await vin_master_service.query_vin(db, vin)
    if result is None:
        raise HTTPException(status_code=422, detail=VIN_NOT_FOUND_DETAIL)


async def _resolve_registered_by_tenant_id(
    db: AsyncSession, payload: DeliveryCreate, actor: CurrentUser
) -> Optional[UUID]:
    """Which Distribuidora gets attributed this sale. A non-superadmin
    actor's OWN tenant is used unconditionally -- `payload.
    registered_by_tenant_id` is never even read in that branch, so a
    Distribuidor can never attribute a sale to a different Distribuidora by
    sending an arbitrary id. Superadmin has no tenant of their own, so they
    MUST explicitly choose a real one."""
    if not actor.is_superadmin:
        return actor.tenant_id
    if payload.registered_by_tenant_id is None:
        raise HTTPException(
            status_code=422,
            detail="Debe seleccionar la tienda que realizó la venta.",
        )
    tenant = await db.get(Tenant, payload.registered_by_tenant_id)
    if tenant is None:
        raise HTTPException(status_code=422, detail="La tienda seleccionada no existe.")
    return tenant.id


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
    city, department = resolve_geo(payload.client.city, payload.client.department)
    if client:
        # Most-recent-submission wins (user decision, 2026-07-28): a
        # re-delivery for an existing cedula refreshes the stored client's
        # data rather than keeping the first-ever values -- this is the
        # exact mechanism the manual legacy-vehicle backfill flow relies on.
        client.name = payload.client.name
        client.phone = payload.client.phone
        client.email = payload.client.email
        client.birth_date = payload.client.birth_date
        client.city = city
        client.department = department
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
        city=city,
        department=department,
        address=payload.client.address,
    )
    db.add(client)
    await db.flush()
    return client


# ---------------------------------------------------------------------------
# Step 1.5 — Vehicle-ownership conflict check. `vehicle_service.
# register_or_update_vehicle` (Step 2, below) finds an existing `Vehicle` by
# plate and silently UPDATES it in place if found -- correct for its other
# callers (e.g. reception, where re-touching a known vehicle is expected),
# but here it means a delivery submitted with a plate/VIN that already
# belongs to a DIFFERENT client would silently steal that vehicle's
# ownership with zero warning (`plate`'s DB `unique=True` constraint never
# even fires, since this is a find-then-update, not a bare insert -- and
# `vin` has no uniqueness constraint at all). This check runs BEFORE
# `_register_vehicle` mutates anything, and only blocks when the matched
# vehicle already has a DIFFERENT client attached -- a vehicle with no
# client yet (`client_id IS NULL`, e.g. legacy-imported data) or the SAME
# client resubmitting (the legitimate re-delivery/backfill case, Design
# ADR 11) must keep working exactly as before.
# ---------------------------------------------------------------------------

async def _reject_if_vehicle_owned_by_another_client(
    db: AsyncSession,
    plate: str,
    vin: Optional[str],
    client_id: Optional[UUID],
    exclude_vehicle_id: Optional[UUID] = None,
) -> None:
    clean_plate = "".join(plate.split()).upper()
    conditions = [Vehicle.plate == clean_plate]
    if vin:
        conditions.append(Vehicle.vin == vin)

    stmt = select(Vehicle).where(or_(*conditions))
    candidates = (await db.execute(stmt)).scalars().all()

    for existing in candidates:
        if exclude_vehicle_id is not None and existing.id == exclude_vehicle_id:
            continue
        if existing.plate != clean_plate and existing.vin != vin:
            continue
        if existing.client_id is not None and existing.client_id != client_id:
            owner = await db.get(User, existing.client_id)
            owner_name = owner.name if owner else "otro cliente"
            raise HTTPException(
                status_code=422,
                detail=(
                    f"La placa o el VIN ya está registrada a nombre de {owner_name}. "
                    "Si esto es un error, corríjalo desde la opción Editar."
                ),
            )


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
    vehicle: Vehicle,
    payload: DeliveryCreate,
    client: User,
    registered_by_tenant_id: Optional[UUID],
) -> None:
    vehicle.delivery_date = payload.delivery_date
    if payload.vehicle.engine_number:
        vehicle.engine_number = payload.vehicle.engine_number
    vehicle.client_id = client.id
    # Which Distribuidora registered THIS record -- resolved by
    # `_resolve_registered_by_tenant_id` (the actor's own tenant for a
    # tenant-scoped actor, or superadmin's explicit selection). `None` only
    # for a Distribuidor with no tenant assigned yet -- expected, not a bug:
    # the record simply isn't "owned" by any Distribuidora and only shows up
    # in superadmin's unfiltered view of `GET /distributor/deliveries`.
    vehicle.registered_by_tenant_id = registered_by_tenant_id


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
        # Validation FIRST -- all three reject with ZERO writes, before the
        # client/vehicle is ever looked-up-or-created.
        _require_photo_or_superadmin(actor, photo)
        _reject_future_delivery_date(payload.delivery_date)
        await _require_vin_in_master(db, payload.vehicle.vin)
        registered_by_tenant_id = await _resolve_registered_by_tenant_id(db, payload, actor)

        client = await _lookup_or_create_client(db, payload, actor)
        await _reject_if_vehicle_owned_by_another_client(
            db, payload.vehicle.plate, payload.vehicle.vin, client.id
        )
        vehicle = await _register_vehicle(db, payload)
        _apply_delivery_fields(vehicle, payload, client, registered_by_tenant_id)
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
                delivery_act_url=vehicle.delivery_act_url,
            )
        )
    return items


# ---------------------------------------------------------------------------
# `PATCH /distributor/deliveries/{vehicle_id}` -- superadmin-only edit of a
# delivery record's basic info (router enforces the superadmin-only guard,
# NOT this function -- same "guard in the router, business logic in the
# service" split as `create_delivery`/`require_distribuidor`).
# ---------------------------------------------------------------------------

def _apply_vehicle_edit_fields(vehicle: Vehicle, fields: dict) -> None:
    if fields.get("plate") is not None:
        vehicle.plate = fields["plate"]
    if "vin" in fields:
        vehicle.vin = fields["vin"]
    if fields.get("delivery_date") is not None:
        vehicle.delivery_date = fields["delivery_date"]
    if fields.get("model") is not None:
        vehicle.model = fields["model"]
    if fields.get("color") is not None:
        vehicle.color = fields["color"]
    if fields.get("year") is not None:
        vehicle.year = fields["year"]
    if fields.get("engine_number") is not None:
        vehicle.engine_number = fields["engine_number"]
    if "registered_by_tenant_id" in fields:
        vehicle.registered_by_tenant_id = fields["registered_by_tenant_id"]


_CLIENT_EDIT_FIELD_KEYS = (
    "client_name", "client_phone", "client_identification",
    "client_birth_date", "client_city", "client_department",
    "client_address", "client_email",
)


async def _apply_client_edit_fields(db: AsyncSession, vehicle: Vehicle, fields: dict) -> None:
    """Silently no-op'd when the vehicle has no linked client -- not every
    historical row is guaranteed to have one (task requirement, not an
    oversight)."""
    wants_client_edit = any(key in fields for key in _CLIENT_EDIT_FIELD_KEYS)
    if not wants_client_edit or vehicle.client_id is None:
        return
    client = await db.get(User, vehicle.client_id)
    if client is None:
        return
    if fields.get("client_name") is not None:
        client.name = fields["client_name"]
    if "client_phone" in fields:
        client.phone = fields["client_phone"]
    if "client_identification" in fields:
        client.identification = fields["client_identification"]
    if "client_birth_date" in fields:
        client.birth_date = fields["client_birth_date"]
    if "client_city" in fields or "client_department" in fields:
        city = fields.get("client_city", client.city)
        department = fields.get("client_department", client.department)
        client.city, client.department = resolve_geo(city, department)
    if "client_address" in fields:
        client.address = fields["client_address"]
    if "client_email" in fields:
        client.email = fields["client_email"]


async def _validate_edit_fields(db: AsyncSession, vehicle: Vehicle, fields: dict) -> None:
    """All pre-mutation edit validation, grouped so `edit_delivery` stays a
    thin orchestrator -- same "validate FIRST, zero mutations happen before
    a 422" discipline as `create_delivery`'s `_require_*`/`_reject_*` calls."""
    if fields.get("delivery_date") is not None:
        _reject_future_delivery_date(fields["delivery_date"])

    # Follow-up fix (2026-07-30): a VIN change is subject to the SAME
    # master-catalog check as create -- no exception anywhere in this
    # feature, including edits. Untouched/no-op VINs (identical to what's
    # already stored) are NOT re-validated -- that would retroactively
    # force every pre-existing record to pass a rule that didn't exist when
    # it was created; only an actual change to the `vin` value triggers the
    # check.
    if "vin" in fields and fields["vin"] != vehicle.vin:
        await _require_vin_in_master(db, fields["vin"])

    # Same ownership-conflict guard as create (see `_reject_if_vehicle_
    # owned_by_another_client`'s docstring) -- only re-checked when the
    # plate or VIN is actually CHANGING to a new value, same "no
    # retroactive re-validation of untouched fields" discipline as the
    # VIN-master check above. The vehicle being edited is excluded from its
    # own conflict check.
    plate_changing = "plate" in fields and fields["plate"] != vehicle.plate
    vin_changing = "vin" in fields and fields["vin"] != vehicle.vin
    if plate_changing or vin_changing:
        await _reject_if_vehicle_owned_by_another_client(
            db,
            fields.get("plate", vehicle.plate),
            fields.get("vin", vehicle.vin),
            vehicle.client_id,
            exclude_vehicle_id=vehicle.id,
        )

    if fields.get("registered_by_tenant_id") is not None:
        tenant = await db.get(Tenant, fields["registered_by_tenant_id"])
        if tenant is None:
            raise HTTPException(status_code=422, detail="La tienda seleccionada no existe.")


async def edit_delivery(
    db: AsyncSession, vehicle_id, payload: DeliveryEditIn
) -> Vehicle:
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.delivery_date is None:
        raise HTTPException(status_code=404, detail="Registro de entrega no encontrado")

    fields = payload.model_dump(exclude_unset=True)
    await _validate_edit_fields(db, vehicle, fields)

    try:
        _apply_vehicle_edit_fields(vehicle, fields)
        await _apply_client_edit_fields(db, vehicle, fields)

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


# ---------------------------------------------------------------------------
# `GET /distributor/deliveries/{vehicle_id}` -- superadmin-only read of a
# single delivery record's FULL detail (bugfix, 2026-07-30): the edit modal
# used to prefill from `DeliveryListItemOut` (the LIST row), which never
# carried most of the fields captured at creation time, so it opened blank.
# Router enforces the superadmin-only guard (same as `PATCH .../{vehicle_id}`
# -- fetch-for-editing shares the exact same access boundary as editing
# itself, no exception), not this function.
# ---------------------------------------------------------------------------

async def get_delivery_detail(db: AsyncSession, vehicle_id: UUID) -> DeliveryDetailOut:
    stmt = (
        select(Vehicle)
        .where(Vehicle.id == vehicle_id)
        .options(selectinload(Vehicle.client), selectinload(Vehicle.registered_by_tenant))
    )
    vehicle = (await db.execute(stmt)).scalars().first()
    if vehicle is None or vehicle.delivery_date is None:
        raise HTTPException(status_code=404, detail="Registro de entrega no encontrado")

    client = vehicle.client
    return DeliveryDetailOut(
        id=vehicle.id,
        plate=vehicle.plate,
        vin=vehicle.vin,
        model=vehicle.model,
        color=vehicle.color,
        year=vehicle.year,
        engine_number=vehicle.engine_number,
        delivery_date=vehicle.delivery_date,
        client_name=client.name if client else None,
        client_identification=client.identification if client else None,
        client_birth_date=client.birth_date if client else None,
        client_city=client.city if client else None,
        client_department=client.department if client else None,
        client_address=client.address if client else None,
        client_phone=client.phone if client else None,
        client_email=client.email if client else None,
        registered_by_tenant_id=vehicle.registered_by_tenant_id,
        registered_by_tenant_name=(
            vehicle.registered_by_tenant.name if vehicle.registered_by_tenant else None
        ),
    )


# ---------------------------------------------------------------------------
# `GET /distributor/deliveries/{vehicle_id}/act-file` -- bugfix (2026-07-30):
# `upload_file_to_minio` hardcodes `http://localhost:9000/...` as the stored
# `Vehicle.delivery_act_url` -- that host resolves to the BROWSER's own
# machine, not the server, so a browser can never fetch it directly in
# production (`ERR_CONNECTION_REFUSED`). This proxy mirrors the SAME
# already-working pattern `orders.py`'s `download_reception_pdf` and
# `imports.py`'s `get_dim_pdf_url` already use: fetch the object's bytes
# internally and stream them back through an authenticated route, so the
# browser never talks to MinIO directly. The router handles the
# `require_distribuidor` role guard (zero DB read, mirrors every other
# endpoint in this file); this function does the rest, in the SAME order
# `download_reception_pdf` uses -- fetch row (404) -> tenant check (403,
# superadmin bypasses) -> file-reference-exists check (404) -> fetch bytes
# (404 if the object itself is missing from storage).
# ---------------------------------------------------------------------------

def _object_name_from_delivery_act_url(url: str) -> str:
    """Mirrors `orders.py`'s `download_reception_pdf` object-name recovery:
    strip a presigned URL's query string, then the bucket-name prefix, to
    recover MinIO's internal object key."""
    url_path_only = url.split("?")[0]
    try:
        return url_path_only.split(f"{BUCKET_NAME}/")[1]
    except IndexError:
        raise HTTPException(status_code=500, detail="Formato de URL en BD corrupto")


async def get_delivery_act_file(
    db: AsyncSession, vehicle_id: UUID, actor: CurrentUser
) -> tuple[bytes, str, str]:
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    # A tenant-less actor must never match a tenant-less vehicle -- `None !=
    # None` is `False` in plain Python, so an unguarded equality check would
    # silently let an unassigned Distribuidor through (same NULL-comparison
    # lesson already learned in `list_deliveries`). Checked as an explicit
    # early rejection, not implicit equality.
    if not actor.is_superadmin and actor.tenant_id is None:
        raise HTTPException(status_code=403, detail="No tiene permiso para acceder a esta acta")
    if not actor.is_superadmin and vehicle.registered_by_tenant_id != actor.tenant_id:
        raise HTTPException(status_code=403, detail="No tiene permiso para acceder a esta acta")

    if not vehicle.delivery_act_url:
        raise HTTPException(status_code=404, detail="Esta entrega no tiene acta cargada")

    object_name = _object_name_from_delivery_act_url(vehicle.delivery_act_url)
    file_bytes = await get_pdf_stream_from_minio(object_name)
    if not file_bytes:
        raise HTTPException(status_code=404, detail="El archivo del acta no existe en almacenamiento")

    content_type, _ = mimetypes.guess_type(object_name)
    filename = object_name.rsplit("/", 1)[-1]
    return file_bytes, content_type or "application/octet-stream", filename
