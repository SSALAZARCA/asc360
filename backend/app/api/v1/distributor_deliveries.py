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
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.vehicle import Vehicle
from app.schemas.distributor_delivery import DeliveryCreate, DeliveryOut
from app.services.distributor_delivery_service import create_delivery, attach_act_photo

router = APIRouter(prefix="/distributor", tags=["distributor_deliveries"])


def require_distribuidor(current_user: CurrentUser) -> None:
    if not (current_user.is_distribuidor or current_user.is_superadmin):
        raise HTTPException(status_code=403, detail="Solo Distribuidor o superadmin")


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
