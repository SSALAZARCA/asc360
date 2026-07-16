from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from typing import Optional, List, Union, Dict, Any
from datetime import datetime
from app.models.order import ServiceStatus, ServiceType, OrderPartType, OrderPartStatus

class PartCreate(BaseModel):
    reference: str = Field(..., min_length=1, max_length=100)
    qty: int = Field(default=1, ge=1)
    part_type: OrderPartType = Field(default=OrderPartType.paid)


class PartRead(PartCreate):
    id: UUID
    order_id: UUID
    status: OrderPartStatus
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WorkLogCreate(BaseModel):
    diagnosis: str = Field(..., min_length=1, max_length=2000)
    media_urls: Optional[List[str]] = Field(default=[])
    recorded_by_telegram_id: Optional[str] = None


class WorkLogRead(WorkLogCreate):
    id: UUID
    order_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReceptionBase(BaseModel):
    mileage_km: float = Field(..., ge=0, description="Kilometraje actual del vehículo")
    gas_level: Optional[str] = Field(None, max_length=50, description="Lleno, Medio, 1/4, Reserva")
    customer_notes: Optional[str] = Field(None, max_length=1000, description="Motivos de ingreso combinados")
    warranty_warnings: Optional[str] = Field(None, max_length=2000, description="Soft warnings generados por Sonia")
    damage_photos_urls: Optional[List[Union[str, Dict[str, Any]]]] = Field(
        default=[],
        description=(
            "Evidencia de daños: URLs de MinIO (legacy, string plano) u objetos "
            "{'url','desc'} para foto / {'type':'text','desc'} para observación sin foto "
            "(ver app/api/v1/endpoints/uploads.py)"
        ),
    )
    intake_answers: Optional[List[dict]] = Field(default=[], description="Respuestas a preguntas según tipo de servicio")
    accessories: Optional[List[str]] = Field(default=[], description="Accesorios u objetos que el cliente deja con la moto")
    general_observations: Optional[str] = Field(None, max_length=2000, description="Observaciones generales o acuerdos del asesor")

class OrderCreate(BaseModel):
    tenant_id: UUID = Field(..., description="ID del taller")
    vehicle_id: UUID = Field(..., description="ID del vehículo ingresando")
    client_id: Optional[UUID] = Field(None, description="ID del dueño del vehículo")
    client_phone: Optional[str] = Field(None, description="Teléfono del dueño recolectado al momento de ingreso")
    technician_id: Optional[UUID] = Field(None, description="Técnico al que se le auto-asigna si fue él quien la creó")
    service_type: ServiceType = Field(default=ServiceType.regular, description="Tipo de servicio")
    reception: ReceptionBase

class ReceptionRead(ReceptionBase):
    id: UUID
    reception_pdf_url: Optional[str] = None
    signature_url: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class OrderRead(BaseModel):
    id: UUID
    tenant_id: UUID
    vehicle_id: UUID
    client_id: Optional[UUID]
    technician_id: Optional[UUID]
    status: ServiceStatus
    service_type: ServiceType
    created_at: datetime
    completed_at: Optional[datetime]
    plate: Optional[str] = None
    reception: Optional[ReceptionRead] = None
    work_logs: Optional[List[WorkLogRead]] = []
    parts: Optional[List[PartRead]] = []

    model_config = ConfigDict(from_attributes=True)


class OrderStatusUpdate(BaseModel):
    status: ServiceStatus
    technician_id: Optional[UUID] = None
    diagnosis: Optional[str] = Field(None, max_length=2000, description="Diagnóstico del técnico — crea OrderWorkLog")
    parts: Optional[List[PartCreate]] = Field(None, description="Repuestos requeridos — crea OrderPart(s)")
    recorded_by_telegram_id: Optional[str] = None


class OrderClaimRequest(BaseModel):
    """
    Body de `POST /orders/{order_id}/claim`. Sonia (único caller hoy, vía
    X-Sonia-Secret) no mantiene sesión JWT del técnico, por lo que
    `technician_id`/`tenant_id` viajan explícitos en el body — mismo patrón
    ya usado por `OrderCreate.technician_id` y `OrderStatusUpdate.technician_id`
    para escrituras iniciadas por el bot.
    """
    technician_id: UUID
    tenant_id: UUID
