from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.user import User, Role
from app.models.warranty_policies import VehicleLimitedWarranty, MandatoryMaintenanceSchedule
from app.schemas.warranty_policies import (
    VehicleLimitedWarrantyCreate, VehicleLimitedWarrantyRead,
    MandatoryMaintenanceScheduleCreate, MandatoryMaintenanceScheduleRead
)

router = APIRouter(prefix="/warranty-policies", tags=["Warranty Policies"])

# MOCK temporal hasta integrar el módulo real de OAuth de Tenant.
def require_admin() -> User:
    # Usamos un ID dummy pero con rol ADMIN para pasar la restricción
    return User(id="123e4567-e89b-12d3-a456-426614174000", role=Role.admin)

# --- LIMITED WARRANTIES ---
@router.post("/limited-warranties", response_model=VehicleLimitedWarrantyRead, status_code=status.HTTP_201_CREATED)
async def create_limited_warranty(
    data: VehicleLimitedWarrantyCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    db_obj = VehicleLimitedWarranty(**data.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.get("/limited-warranties", response_model=List[VehicleLimitedWarrantyRead])
async def list_limited_warranties(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(VehicleLimitedWarranty))
    return result.scalars().all()

@router.delete("/limited-warranties/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_limited_warranty(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    obj = await db.get(VehicleLimitedWarranty, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Garantía Limitada no encontrada")
    await db.delete(obj)
    await db.commit()

# --- MANDATORY MAINTENANCE SCHEDULES ---
@router.post("/mandatory-maintenances", response_model=MandatoryMaintenanceScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_maintenance_schedule(
    data: MandatoryMaintenanceScheduleCreate,
    db: AsyncSession = Depends(get_db)
):
    db_obj = MandatoryMaintenanceSchedule(**data.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.get("/mandatory-maintenances", response_model=List[MandatoryMaintenanceScheduleRead])
async def list_maintenance_schedules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MandatoryMaintenanceSchedule))
    return result.scalars().all()

@router.delete("/mandatory-maintenances/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance_schedule(
    item_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    obj = await db.get(MandatoryMaintenanceSchedule, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Agenda de mantenimiento obligatorio no encontrada")
    await db.delete(obj)
    await db.commit()
