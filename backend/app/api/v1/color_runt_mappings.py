import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.imports import ColorRuntMapping
from app.schemas.imports import ColorRuntMappingCreate, ColorRuntMappingUpdate, ColorRuntMappingRead

router = APIRouter(prefix="/color-runt-mappings", tags=["color-runt-mappings"])


def _require_superadmin(user: CurrentUser):
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Se requiere rol superadmin")


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', str(s).upper().strip().replace('/', ' '))


@router.get("", status_code=200)
async def list_color_runt_mappings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    rows = (await db.execute(
        select(ColorRuntMapping).order_by(ColorRuntMapping.color_key.asc())
    )).scalars().all()
    return [ColorRuntMappingRead.model_validate(r).model_dump() for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_color_runt_mapping(
    payload: ColorRuntMappingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    color_key = _norm(payload.color_original)
    record = ColorRuntMapping(
        color_key=color_key,
        color_original=payload.color_original,
        codigo_runt=payload.codigo_runt,
        nombre_runt=payload.nombre_runt,
    )
    db.add(record)
    try:
        await db.commit()
        await db.refresh(record)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un mapeo con la clave normalizada '{color_key}'",
        )
    return ColorRuntMappingRead.model_validate(record).model_dump()


@router.put("/{mapping_id}", status_code=200)
async def update_color_runt_mapping(
    mapping_id: uuid.UUID,
    payload: ColorRuntMappingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    record = await db.get(ColorRuntMapping, mapping_id)
    if not record:
        raise HTTPException(status_code=404, detail="Mapeo no encontrado")

    if payload.color_original is not None:
        record.color_key = _norm(payload.color_original)
        record.color_original = payload.color_original
    if payload.codigo_runt is not None:
        record.codigo_runt = payload.codigo_runt
    if payload.nombre_runt is not None:
        record.nombre_runt = payload.nombre_runt

    try:
        await db.commit()
        await db.refresh(record)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un mapeo con esa clave normalizada")
    return ColorRuntMappingRead.model_validate(record).model_dump()


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_color_runt_mapping(
    mapping_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    record = await db.get(ColorRuntMapping, mapping_id)
    if not record:
        raise HTTPException(status_code=404, detail="Mapeo no encontrado")
    await db.delete(record)
    await db.commit()
