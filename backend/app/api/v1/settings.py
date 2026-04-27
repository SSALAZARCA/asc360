from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.system_config import SystemConfig

router = APIRouter(prefix="/settings", tags=["settings"])

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


class SimilarityThresholdPayload(BaseModel):
    threshold: float


@router.get("/parts-similarity-threshold")
async def get_parts_similarity_threshold(db: AsyncSession = Depends(get_db)):
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
