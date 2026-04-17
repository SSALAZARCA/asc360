from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
import uuid

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.imports import VehicleModel
from app.schemas.imports import VehicleModelCreate, VehicleModelUpdate, VehicleModelRead

router = APIRouter(prefix="/vehicle-models", tags=["vehicle-models"])


def _require_superadmin(user: CurrentUser):
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Se requiere rol superadmin")


# ---------------------------------------------------------------------------
# GET /vehicle-models — listado global (catálogo compartido, sin filtro de tenant)
# ---------------------------------------------------------------------------

@router.get("", status_code=200)
async def list_vehicle_models(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    stmt = select(VehicleModel).order_by(VehicleModel.model_name.asc())
    records = (await db.execute(stmt)).scalars().all()
    return [VehicleModelRead.model_validate(r).model_dump() for r in records]


# ---------------------------------------------------------------------------
# POST /vehicle-models — crear, solo superadmin
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_vehicle_model(
    payload: VehicleModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    record = VehicleModel(
        model_name=payload.model_name,
        brand=payload.brand,
        cilindrada=payload.cilindrada,
        potencia=payload.potencia,
        peso=payload.peso,
        vueltas_aire=payload.vueltas_aire,
        posicion_cortina=payload.posicion_cortina,
        sistemas_control=payload.sistemas_control,
        fuel_system=payload.fuel_system,
        model_year=payload.model_year,
    )
    db.add(record)
    try:
        await db.commit()
        await db.refresh(record)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe un modelo con ese nombre",
        )

    return VehicleModelRead.model_validate(record).model_dump()


# ---------------------------------------------------------------------------
# PUT /vehicle-models/{model_id} — actualizar, solo superadmin
# ---------------------------------------------------------------------------

@router.put("/{model_id}", status_code=200)
async def update_vehicle_model(
    model_id: uuid.UUID,
    payload: VehicleModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    record = await db.get(VehicleModel, model_id)
    if not record:
        raise HTTPException(status_code=404, detail="Modelo no encontrado")

    update_data = payload.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    await db.commit()
    await db.refresh(record)

    return VehicleModelRead.model_validate(record).model_dump()


# ---------------------------------------------------------------------------
# DELETE /vehicle-models/{model_id} — eliminar, solo superadmin
# ---------------------------------------------------------------------------

@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    record = await db.get(VehicleModel, model_id)
    if not record:
        raise HTTPException(status_code=404, detail="Modelo no encontrado")

    await db.delete(record)
    await db.commit()
