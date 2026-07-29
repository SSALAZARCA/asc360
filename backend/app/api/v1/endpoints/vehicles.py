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
from app.schemas.vehicle import VehicleOut, VehicleCreate, VehicleClientOut, ClientEditIn
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


@router.patch("/{plate}/client", response_model=VehicleClientOut)
async def update_vehicle_client(
    plate: str,
    client_in: ClientEditIn,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """sdd/distributor-vehicle-delivery PR5 (design-dual-channel ADR 20):
    persiste ediciones del asesor sobre el cliente vinculado a una moto
    que regresa al taller. Endpoint COMPARTIDO por ambos canales de
    recepción (el bot de Telegram, PR6, y la Mini App, PR8) -- ninguno
    tiene su propia implementación.

    Acepta X-Sonia-Secret (bot) o JWT (staff autenticado), mismo patrón
    dual-auth que `GET /{plate}` (`:40-51`). Por ADR 22, esto es una
    verificación de IDENTIDAD DE PROCESO ("esta llamada vino del bot de
    Sonia"), no de asesor individual -- igual que cualquier otra
    escritura originada por el bot en este código.
    """
    is_bot = verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET)
    if not is_bot and current_user is None:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")

    tenant_uuid: Optional[UUID] = None
    if x_tenant_id:
        try:
            tenant_uuid = UUID(x_tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="X-Tenant-Id inválido.")

    # Reaplica la MISMA resolución de placa + visibilidad por tenant que
    # `GET /{plate}` (ADR 20) -- una sola implementación del lookup.
    vehicle = await vehicle_service.get_vehicle_by_plate(db, plate, tenant_uuid)
    if not vehicle:
        raise HTTPException(
            status_code=404,
            detail="Vehículo no encontrado o en servicio en otro taller.",
        )
    if not vehicle.client_id or vehicle.client is None:
        raise HTTPException(status_code=404, detail="El vehículo no tiene un cliente vinculado.")

    for field, value in client_in.model_dump(exclude_unset=True).items():
        setattr(vehicle.client, field, value)

    await db.commit()
    await db.refresh(vehicle.client)
    return vehicle.client


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
