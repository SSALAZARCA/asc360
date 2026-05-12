import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.imports import ColorRuntMapping, ShipmentMotoUnit
from app.schemas.imports import ColorRuntMappingCreate, ColorRuntMappingUpdate, ColorRuntMappingRead

router = APIRouter(prefix="/color-runt-mappings", tags=["color-runt-mappings"])


def _require_superadmin(user: CurrentUser):
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Se requiere rol superadmin")


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', str(s).upper().strip().replace('/', ' '))


def _sql_norm_color(col):
    """Replica en SQL la misma normalización de _norm para poder comparar color_key."""
    return func.regexp_replace(
        func.upper(func.trim(func.replace(col, '/', ' '))),
        r'\s+', ' ', 'g',
    )


async def _sync_moto_units(db: AsyncSession, color_key: str, nombre_runt: str | None) -> None:
    """Actualiza color_runt en todas las motos cuyo color normalizado coincide con color_key."""
    await db.execute(
        sa_update(ShipmentMotoUnit)
        .where(
            ShipmentMotoUnit.color.isnot(None),
            _sql_norm_color(ShipmentMotoUnit.color) == color_key,
        )
        .values(color_runt=nombre_runt)
        .execution_options(synchronize_session=False)
    )


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
    await _sync_moto_units(db, color_key, payload.nombre_runt)
    await db.commit()
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

    old_color_key = record.color_key
    old_nombre_runt = record.nombre_runt

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

    # Propagar cambios a las motos afectadas
    if old_color_key != record.color_key:
        # El color del packing list cambió: limpiar motos con el key viejo y resolver las del nuevo
        await _sync_moto_units(db, old_color_key, None)
        await _sync_moto_units(db, record.color_key, record.nombre_runt)
    elif old_nombre_runt != record.nombre_runt:
        # Solo cambió el nombre RUNT: actualizar motos que matchean este color_key
        await _sync_moto_units(db, record.color_key, record.nombre_runt)
    await db.commit()

    return ColorRuntMappingRead.model_validate(record).model_dump()


@router.post("/resync-all", status_code=200)
async def resync_all_moto_units(
    solo_pendientes: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    base_where = [ShipmentMotoUnit.color.isnot(None)]
    if solo_pendientes:
        base_where.append(ShipmentMotoUnit.certificado_generado.is_(False))

    await db.execute(
        sa_update(ShipmentMotoUnit)
        .where(*base_where)
        .values(color_runt=None)
        .execution_options(synchronize_session=False)
    )
    mappings = (await db.execute(select(ColorRuntMapping))).scalars().all()
    motos_actualizadas = 0
    for mapping in mappings:
        result = await db.execute(
            sa_update(ShipmentMotoUnit)
            .where(*base_where, _sql_norm_color(ShipmentMotoUnit.color) == mapping.color_key)
            .values(color_runt=mapping.nombre_runt)
            .execution_options(synchronize_session=False)
        )
        motos_actualizadas += result.rowcount

    sin_mapeo_result = await db.execute(
        select(ShipmentMotoUnit.color)
        .where(*base_where, ShipmentMotoUnit.color_runt.is_(None))
        .distinct()
    )
    sin_mapeo = [r[0] for r in sin_mapeo_result.fetchall() if r[0]]

    await db.commit()
    scope = "sin empadronamiento" if solo_pendientes else "en total"
    msg = f"Sincronización completada. {motos_actualizadas} motos actualizadas ({scope})."
    if sin_mapeo:
        msg += f" Colores sin mapeo: {', '.join(sin_mapeo)}."
    return {"detail": msg}


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
