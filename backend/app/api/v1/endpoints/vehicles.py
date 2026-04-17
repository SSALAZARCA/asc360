from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.config import settings
from app.schemas.vehicle import VehicleOut, VehicleCreate
from app.schemas.vin_master import VinMasterOut
from app.services.vehicle_service import vehicle_service
from app.services.vin_master_service import vin_master_service

router = APIRouter()


def _verify_sonia_secret(x_sonia_secret: Optional[str]) -> None:
    """Valida el secreto compartido del bot Sonia. Lanza 403 si es inválido."""
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")


@router.get("/vin/{vin}", response_model=VinMasterOut)
async def get_vin_master(
    vin: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
):
    """Consulta la base maestra de VINs. Protegido por X-Sonia-Secret (uso interno del bot)."""
    _verify_sonia_secret(x_sonia_secret)
    vin_data = await vin_master_service.query_vin(db, vin)
    if not vin_data:
        raise HTTPException(status_code=404, detail="VIN no encontrado en el Maestro.")
    return vin_data


@router.get("/{plate}", response_model=VehicleOut)
async def get_vehicle_by_plate(
    plate: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
):
    """Consulta una moto por placa. Protegido por X-Sonia-Secret (uso interno del bot)."""
    _verify_sonia_secret(x_sonia_secret)
    vehicle = await vehicle_service.get_vehicle_by_plate(db, plate, x_tenant_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado en este Taller.")
    return vehicle


@router.post("/", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def create_or_update_vehicle(
    vehicle_in: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
):
    """Registra una moto en el Taller. Protegido por X-Sonia-Secret (uso interno del bot)."""
    _verify_sonia_secret(x_sonia_secret)
    try:
        vehicle = await vehicle_service.register_or_update_vehicle(db, vehicle_in, vehicle_in.tenant_id)
        return vehicle
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
