from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
import uuid
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.vehicle_lifecycle import VehicleLifecycleEvent, LifecycleEventType
from app.models.vehicle import Vehicle
from pydantic import BaseModel

router = APIRouter(prefix="/vehicles", tags=["Vehicle Lifecycle"])


# ─── Schemas Pydantic ────────────────────────────────────────────────────────

class LifecycleEventCreate(BaseModel):
    event_type: str
    summary: str
    km_at_event: Optional[float] = None
    details: Optional[str] = None
    linked_order_id: Optional[str] = None
    created_by_telegram_id: Optional[str] = None

class LifecycleEventRead(BaseModel):
    id: str
    vehicle_id: str
    event_type: str
    event_date: datetime
    km_at_event: Optional[float] = None
    summary: str
    details: Optional[str] = None
    linked_order_id: Optional[str] = None
    is_automatic: str

    class Config:
        from_attributes = True


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{vehicle_id}/lifecycle", response_model=List[LifecycleEventRead])
async def get_vehicle_lifecycle(vehicle_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Retorna la hoja de vida completa (línea de tiempo de eventos) de un vehículo.
    """
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    stmt = (
        select(VehicleLifecycleEvent)
        .where(VehicleLifecycleEvent.vehicle_id == vehicle_id)
        .order_by(desc(VehicleLifecycleEvent.event_date))
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    return [
        LifecycleEventRead(
            id=str(e.id),
            vehicle_id=str(e.vehicle_id),
            event_type=e.event_type.value,
            event_date=e.event_date,
            km_at_event=float(e.km_at_event) if e.km_at_event else None,
            summary=e.summary,
            details=e.details,
            linked_order_id=str(e.linked_order_id) if e.linked_order_id else None,
            is_automatic=e.is_automatic
        )
        for e in events
    ]


@router.post("/{vehicle_id}/lifecycle", response_model=LifecycleEventRead, status_code=201)
async def add_lifecycle_event(
    vehicle_id: uuid.UUID,
    event_in: LifecycleEventCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Agrega un evento manual a la hoja de vida del vehículo.
    (Usado para accidentes, cambios de propietario, notas técnicas, etc.)
    """
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    try:
        event_type_enum = LifecycleEventType[event_in.event_type]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Tipo de evento inválido: {event_in.event_type}. Válidos: {[e.value for e in LifecycleEventType]}")

    new_event = VehicleLifecycleEvent(
        vehicle_id=vehicle_id,
        event_type=event_type_enum,
        summary=event_in.summary,
        km_at_event=event_in.km_at_event,
        details=event_in.details,
        linked_order_id=uuid.UUID(event_in.linked_order_id) if event_in.linked_order_id else None,
        created_by_telegram_id=event_in.created_by_telegram_id,
        is_automatic="manual"
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)

    return LifecycleEventRead(
        id=str(new_event.id),
        vehicle_id=str(new_event.vehicle_id),
        event_type=new_event.event_type.value,
        event_date=new_event.event_date,
        km_at_event=float(new_event.km_at_event) if new_event.km_at_event else None,
        summary=new_event.summary,
        details=new_event.details,
        linked_order_id=str(new_event.linked_order_id) if new_event.linked_order_id else None,
        is_automatic=new_event.is_automatic
    )
