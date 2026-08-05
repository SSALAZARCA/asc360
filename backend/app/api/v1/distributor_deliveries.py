"""
Distributor Vehicle Delivery — `parts_dealer` (Distribuidor) or superadmin
registration of a new motorcycle sale/delivery: a client `User` and a
`Vehicle` created (or reused) in one transaction, with an authoritative
warranty-start date (`Vehicle.delivery_date`) and a role-conditional signed
delivery-act photo (Design ADR 17/18 — mandatory for Distribuidor, optional
for superadmin's legacy-vehicle backfill).

Phase 4 (this batch): the real transactional service
(`app.services.distributor_delivery_service.create_delivery`) is wired in,
replacing Phase 3's `HTTPException(501, ...)` stub. Thin router: guard,
parse, delegate, no business logic here (mirrors `app/api/v1/
superadmin_historical_orders.py`'s post-PR2 shape).

`require_distribuidor` is a PUBLIC function name (not `_require_...`) on
purpose — the design's future parts-sale router reuses it verbatim, the
same precedent `_require_superadmin` already set for every
superadmin-only router in this codebase.

The create endpoint is multipart (`payload: str = Form(...)` +
`photo: UploadFile | None = File(None)`), per Design ADR 18 — the
role-conditional photo requirement must be checked atomically, in the SAME
request that decides whether to write, so the photo has to be assessable
before any DB write happens.

`POST /deliveries/{vehicle_id}/act-photo` (Design ADR 6) is the retry/
replace path, kept alive alongside the inline photo field for the case
where the inline upload fails or a superadmin decides to attach a photo
after the fact.

Follow-up feature (migration `c9d0e1f2a3b4`): `GET /deliveries` lists
registrations already made -- Distribuidor sees only their own
Distribuidora's rows (shared across colleagues, scoped by TENANT not by the
individual user who typed it in), superadmin sees every Distribuidora's
rows network-wide. `PATCH /deliveries/{vehicle_id}` edits a record's basic
info -- superadmin ONLY, Distribuidor is explicitly excluded even for a
record they created themselves, so it does NOT reuse `require_distribuidor`.
Follow-up bugfix (2026-07-30): `GET /deliveries/{vehicle_id}/act-file` proxies
the signed delivery-act file's bytes through the backend instead of letting
the browser hit `Vehicle.delivery_act_url` directly -- that URL is built by
`pdf_service.upload_file_to_minio` with a hardcoded `localhost:9000` host,
which resolves to the BROWSER's own machine, not the server, in production.
Mirrors the same proxy pattern already established by `orders.py`'s
`download_reception_pdf` and `imports.py`'s `get_dim_pdf_url`.
"""
import io
from datetime import datetime
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.vehicle import Vehicle
from app.schemas.distributor_delivery import (
    DeliveryCreate,
    DeliveryDetailOut,
    DeliveryEditIn,
    DeliveryListItemOut,
    DeliveryOut,
)
from app.services.distributor_delivery_service import (
    attach_act_photo,
    create_delivery,
    edit_delivery,
    export_deliveries,
    get_delivery_act_file,
    get_delivery_detail,
    list_deliveries,
)

router = APIRouter(prefix="/distributor", tags=["distributor_deliveries"])


def require_distribuidor(current_user: CurrentUser) -> None:
    if not (current_user.is_distribuidor or current_user.is_superadmin):
        raise HTTPException(status_code=403, detail="Solo Distribuidor o superadmin")


def _content_disposition(disposition: str, filename: str) -> str:
    """Bugfix (2026-08-06): a raw non-ASCII filename (e.g. an accented
    client name baked into the act's object key) breaks HTTP header
    encoding -- headers must be Latin-1, so a literal 'í'/'á' crashes the
    response with an unhandled 500 AFTER the file was already fetched
    successfully. RFC 5987's `filename*=UTF-8''...` carries the real name
    for modern browsers; the quoted `filename=` stays as an ASCII-only
    fallback for anything that doesn't understand `filename*`."""
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "acta.pdf"
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.post("/deliveries", status_code=201, response_model=DeliveryOut)
async def create_delivery_endpoint(
    payload: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    require_distribuidor(current_user)
    try:
        delivery_in = DeliveryCreate.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    return await create_delivery(db, delivery_in, photo, current_user)


@router.get("/deliveries", response_model=list[DeliveryListItemOut])
async def list_deliveries_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    require_distribuidor(current_user)
    return await list_deliveries(db, current_user)


@router.get("/deliveries/export")
async def export_deliveries_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    # Same audience as the on-screen list -- Distribuidor exports only
    # their own Distribuidora's rows, superadmin exports everything.
    require_distribuidor(current_user)
    buf = await export_deliveries(db, current_user)
    filename = f"entregas_registradas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/deliveries/{vehicle_id}", response_model=DeliveryDetailOut)
async def get_delivery_detail_endpoint(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    # Superadmin-only -- same access boundary as the `PATCH` below, not
    # `require_distribuidor` (which also admits Distribuidor). This endpoint
    # exists specifically to feed the superadmin-only edit modal.
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin puede ver el detalle")

    return await get_delivery_detail(db, vehicle_id)


@router.patch("/deliveries/{vehicle_id}", response_model=DeliveryOut)
async def edit_delivery_endpoint(
    vehicle_id: UUID,
    payload: DeliveryEditIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    # Distribuidor is explicitly EXCLUDED from editing -- even the
    # Distribuidor who created the record -- so this does NOT reuse
    # `require_distribuidor` (which also admits Distribuidor). Only
    # superadmin edits.
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin puede editar")

    return await edit_delivery(db, vehicle_id, payload)


@router.post("/deliveries/{vehicle_id}/act-photo", status_code=200, response_model=DeliveryOut)
async def upload_act_photo_endpoint(
    vehicle_id: UUID,
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    require_distribuidor(current_user)
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    return await attach_act_photo(db, vehicle, photo)


@router.get("/deliveries/{vehicle_id}/act-file")
async def download_act_file_endpoint(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    require_distribuidor(current_user)
    file_bytes, content_type, filename = await get_delivery_act_file(db, vehicle_id, current_user)

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=content_type,
        headers={"Content-Disposition": _content_disposition("inline", filename)},
    )
