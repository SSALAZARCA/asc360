import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, get_optional_user, CurrentUser
from app.config import settings
from app.core.security import verify_sonia_secret
from app.schemas.vehicle import VehicleOut, VehicleCreate
from app.schemas.vin_master import VinMasterOut
from app.services.vehicle_service import vehicle_service
from app.services.vin_master_service import vin_master_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/vin/{vin}", response_model=VinMasterOut)
async def get_vin_master(
    vin: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """Consulta la base maestra de VINs. Acepta X-Sonia-Secret (bot) o JWT
    (staff autenticado, ej. el formulario de recepción)."""
    is_bot = verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET)
    if not is_bot and current_user is None:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")
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
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """Consulta una moto por placa. Acepta X-Sonia-Secret o JWT Bearer."""
    is_bot = verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET)
    if not is_bot and current_user is None:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")

    tenant_uuid: Optional[UUID] = None
    if x_tenant_id:
        try:
            tenant_uuid = UUID(x_tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="X-Tenant-Id inválido.")

    vehicle = await vehicle_service.get_vehicle_by_plate(db, plate, tenant_uuid)
    if not vehicle:
        # sdd/vehicle-tenant-checkin-release PR2: reworded -- a vehicle
        # held by another taller's open order now ALSO surfaces as
        # not-found from this tenant's perspective (claim semantics).
        raise HTTPException(
            status_code=404,
            detail="Vehículo no encontrado o en servicio en otro taller.",
        )
    return vehicle


@router.post("/", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def create_or_update_vehicle(
    vehicle_in: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """Registra una moto en el Taller. Acepta X-Sonia-Secret o JWT (admin/superadmin)."""
    is_bot = verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET)
    if not is_bot and (current_user is None or not current_user.is_admin):
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")
    try:
        # sdd/vehicle-tenant-checkin-release PR2: no longer forwards a
        # client-controlled `tenant_id` from the request body -- that was
        # a mass-assignment / OWASP API1 BOLA gap (any caller could set
        # `tenant_id` on the POST body). `register_or_update_vehicle` now
        # has zero tenant semantics.
        vehicle = await vehicle_service.register_or_update_vehicle(db, vehicle_in)
        return vehicle
    except HTTPException:
        raise
    except IntegrityError:
        # Sanitized 409 -- the previous `except Exception as e: raise
        # HTTPException(400, str(e))` leaked raw DB text to the client
        # (verbose error message / information disclosure).
        logger.exception("Error de integridad al registrar/actualizar vehículo")
        raise HTTPException(status_code=409, detail="Ya existe un vehículo con esa placa.")
