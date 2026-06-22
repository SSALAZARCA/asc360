from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.system_config import SystemConfig

router = APIRouter(prefix="/settings", tags=["settings"])

from sqlalchemy.future import select

LOGO_KEY = "logo_base64"
PARTS_SIM_KEY = "parts_similarity_threshold"


class LogoPayload(BaseModel):
    logo_base64: Optional[str] = None


@router.get("/logo")
async def get_logo(db: AsyncSession = Depends(get_db)):
    """Retorna el logo global de la marca. Accesible sin restricción de taller."""
    record = await db.get(SystemConfig, LOGO_KEY)
    return {"logo_base64": record.value if record else None}


@router.put("/logo")
async def save_logo(
    payload: LogoPayload,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Guarda o elimina el logo global. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin puede modificar el logo")

    record = await db.get(SystemConfig, LOGO_KEY)

    if payload.logo_base64:
        if record:
            record.value = payload.logo_base64
        else:
            record = SystemConfig(key=LOGO_KEY, value=payload.logo_base64)
            db.add(record)
    else:
        if record:
            await db.delete(record)

    await db.commit()
    return {"ok": True}


class PricingFactorsPayload(BaseModel):
    import_factor:      float
    provider_margin:    float
    distributor_margin: float
    iva_rate:           float
    trm:                float


@router.get("/pricing-factors")
async def get_pricing_factors(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Retorna los factores de pricing. Requiere autenticación."""
    if not current_user.is_superadmin and not current_user.is_imports_editor:
        raise HTTPException(status_code=403, detail="Sin permiso para ver factores de pricing")
    from app.services.pricing_service import get_pricing_factors
    return await get_pricing_factors(db)


@router.put("/pricing-factors")
async def save_pricing_factors(
    payload: PricingFactorsPayload,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Actualiza los factores de pricing. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    updates = {
        "pricing.import_factor":      str(round(payload.import_factor, 4)),
        "pricing.provider_margin":    str(round(payload.provider_margin, 4)),
        "pricing.distributor_margin": str(round(payload.distributor_margin, 4)),
        "pricing.iva_rate":           str(round(payload.iva_rate, 4)),
        "pricing.trm":                str(round(payload.trm, 2)),
    }
    for key, value in updates.items():
        record = await db.get(SystemConfig, key)
        if record:
            record.value = value
        else:
            db.add(SystemConfig(key=key, value=value))

    await db.commit()
    return {
        "import_factor":      float(updates["pricing.import_factor"]),
        "provider_margin":    float(updates["pricing.provider_margin"]),
        "distributor_margin": float(updates["pricing.distributor_margin"]),
        "iva_rate":           float(updates["pricing.iva_rate"]),
        "trm":                float(updates["pricing.trm"]),
    }


class SimilarityThresholdPayload(BaseModel):
    threshold: float


@router.get("/parts-similarity-threshold")
async def get_parts_similarity_threshold(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")
    record = await db.get(SystemConfig, PARTS_SIM_KEY)
    return {"threshold": float(record.value) if record else 0.9}


@router.put("/parts-similarity-threshold")
async def save_parts_similarity_threshold(
    payload: SimilarityThresholdPayload,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")
    value = round(max(0.1, min(1.0, payload.threshold)), 2)
    record = await db.get(SystemConfig, PARTS_SIM_KEY)
    if record:
        record.value = str(value)
    else:
        db.add(SystemConfig(key=PARTS_SIM_KEY, value=str(value)))
    await db.commit()
    return {"threshold": value}


@router.post("/backfill-part-costs")
async def backfill_part_costs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Calcula el avg_fob_cost para todas las partes del catálogo usando los
    SparePartItems históricos que ya tienen unit_price cargado.
    Ejecutar una sola vez después de activar la feature de pricing.
    Solo superadmin.
    """
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    from app.models.parts_manual import PartsReference
    from app.services.pricing_service import recalculate_part_cost

    refs = (await db.execute(select(PartsReference.factory_part_number))).scalars().all()

    updated = 0
    skipped = 0
    for fpn in refs:
        await recalculate_part_cost(db, fpn)
        # Verificar si quedó con costo
        ref = await db.get(PartsReference, fpn)
        if ref and ref.avg_fob_cost is not None:
            updated += 1
        else:
            skipped += 1

    await db.commit()
    return {"updated": updated, "skipped": skipped, "total": len(refs)}


SUGERIDO_DEFAULTS = {
    "sugerido.rate_alta":           20.0,
    "sugerido.rate_media":          10.0,
    "sugerido.rate_baja":           1.0,
    "sugerido.pending_moto_factor": 0.5,
}


class SugeridoParamsResponse(BaseModel):
    rate_alta: float
    rate_media: float
    rate_baja: float
    pending_moto_factor: float


class SugeridoParamsUpdate(BaseModel):
    rate_alta: float
    rate_media: float
    rate_baja: float
    pending_moto_factor: float


@router.get("/sugerido-params", response_model=SugeridoParamsResponse)
async def get_sugerido_params(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Retorna los parámetros de cálculo de sugerido de pedido. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    key_to_field = {
        "sugerido.rate_alta":           "rate_alta",
        "sugerido.rate_media":          "rate_media",
        "sugerido.rate_baja":           "rate_baja",
        "sugerido.pending_moto_factor": "pending_moto_factor",
    }

    result = {}
    for key, field in key_to_field.items():
        record = await db.get(SystemConfig, key)
        if record is None:
            record = SystemConfig(key=key, value=str(SUGERIDO_DEFAULTS[key]))
            db.add(record)
        result[field] = float(record.value)

    await db.commit()
    return SugeridoParamsResponse(**result)


@router.put("/sugerido-params", response_model=SugeridoParamsResponse)
async def save_sugerido_params(
    payload: SugeridoParamsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Actualiza los parámetros de cálculo de sugerido de pedido. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    updates = {
        "sugerido.rate_alta":           payload.rate_alta,
        "sugerido.rate_media":          payload.rate_media,
        "sugerido.rate_baja":           payload.rate_baja,
        "sugerido.pending_moto_factor": payload.pending_moto_factor,
    }

    for key, value in updates.items():
        record = await db.get(SystemConfig, key)
        if record:
            record.value = str(value)
        else:
            db.add(SystemConfig(key=key, value=str(value)))

    await db.commit()
    return SugeridoParamsResponse(
        rate_alta=payload.rate_alta,
        rate_media=payload.rate_media,
        rate_baja=payload.rate_baja,
        pending_moto_factor=payload.pending_moto_factor,
    )
