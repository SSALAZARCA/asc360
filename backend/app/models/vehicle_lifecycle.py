import uuid
import enum
from sqlalchemy import Column, String, Enum, ForeignKey, Numeric, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class LifecycleEventType(enum.Enum):
    """Tipos de evento en la hoja de vida del vehículo."""
    RECEPCION = "RECEPCION"           # Entrada al taller (automático al crear Orden)
    ENTREGA = "ENTREGA"               # Salida del taller (automático al completar Orden)
    CAMBIO_PROPIETARIO = "CAMBIO_PROPIETARIO"  # El vehículo cambia de dueño
    MANTENIMIENTO = "MANTENIMIENTO"   # Mantenimiento preventivo realizado
    GARANTIA = "GARANTIA"             # Garantía aplicada
    ACCIDENTE = "ACCIDENTE"           # Evento de accidente o daño externo
    ROBO_RECUPERADO = "ROBO_RECUPERADO"  # Fue robado y recuperado
    RESETEO_ODOMETRO = "RESETEO_ODOMETRO"  # Odómetro reiniciado (explicación manual)
    INSPECCION_TECNICA = "INSPECCION_TECNICA"  # Revisión técnico-mecánica externa
    NOTA_TECNICA = "NOTA_TECNICA"        # Nota técnica libre del asesor/técnico


class VehicleLifecycleEvent(Base):
    """
    Hoja de vida unificada del vehículo.
    Registra todos los eventos relevantes en una línea de tiempo plana,
    ya sea generados automáticamente por el sistema o agregados manualmente.
    """
    __tablename__ = "vehicle_lifecycle"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    
    # Tipo de evento
    event_type = Column(Enum(LifecycleEventType), nullable=False)
    
    # Cuándo ocurrió
    event_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # KM al momento del evento (para la trazabilidad del odómetro)
    km_at_event = Column(Numeric(10, 0), nullable=True)
    
    # Descripción del evento (texto libre enriquecido)
    summary = Column(String(500), nullable=False)
    details = Column(Text, nullable=True)  # Texto extendido, puede incluir diagnósticos
    
    # Referencia opcional a la Orden de Servicio que generó este evento
    linked_order_id = Column(UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=True)
    
    # Quién registró el evento
    created_by_telegram_id = Column(String(50), nullable=True)  # ID del asesor en Telegram
    
    # Si fue generado automáticamente por el sistema o manualmente
    is_automatic = Column(String(10), default="auto")  # "auto" | "manual"

    # Relaciones
    vehicle = relationship("Vehicle", back_populates="lifecycle_events")
    linked_order = relationship("ServiceOrder", foreign_keys=[linked_order_id])
