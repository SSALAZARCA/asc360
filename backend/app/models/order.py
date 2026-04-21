import uuid
import enum
from sqlalchemy import Column, String, Integer, Enum, ForeignKey, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base

class ServiceStatus(enum.Enum):
    pending_signature = "pending_signature"
    received = "received"
    scheduled = "scheduled"
    in_progress = "in_progress"
    on_hold_parts = "on_hold_parts"
    rescheduled = "rescheduled"
    on_hold_client = "on_hold_client"
    external_work = "external_work"
    completed = "completed"
    delivered = "delivered"
    cancelled = "cancelled"

class ServiceType(enum.Enum):
    regular = "regular"
    warranty = "warranty"
    km_review = "km_review"
    quick = "quick"
    pdi = "pdi"

class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True) # User con rol client
    technician_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True) # User con rol technician
    
    status = Column(Enum(ServiceStatus), default=ServiceStatus.received, nullable=False)
    service_type = Column(Enum(ServiceType), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True) # Cuándo se le entrega físicamente al cliente

    tenant = relationship("Tenant", back_populates="service_orders")
    vehicle = relationship("Vehicle", back_populates="service_orders")
    client = relationship("User", foreign_keys=[client_id])
    technician = relationship("User", foreign_keys=[technician_id])
    history = relationship("OrderHistory", back_populates="order", cascade="all, delete-orphan")
    reception = relationship("ServiceOrderReception", back_populates="order", uselist=False, cascade="all, delete-orphan")
    work_logs = relationship("OrderWorkLog", back_populates="order", cascade="all, delete-orphan")
    parts = relationship("OrderPart", back_populates="order", cascade="all, delete-orphan")

    @hybrid_property
    def plate(self) -> str | None:
        return self.vehicle.plate if self.vehicle else None

class OrderHistory(Base):
    __tablename__ = "order_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=False)
    
    from_status = Column(Enum(ServiceStatus), nullable=True)
    to_status = Column(Enum(ServiceStatus), nullable=False)
    
    changed_at = Column(DateTime, default=datetime.utcnow)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    duration_minutes = Column(Numeric(10, 2), nullable=True)
    comments = Column(String(500), nullable=True)

    order = relationship("ServiceOrder", back_populates="history")

class OrderWorkLog(Base):
    """
    Registro de trabajo/diagnóstico por cambio de estado.
    Se crea cuando el técnico informa qué encontró en la moto.
    """
    __tablename__ = "order_work_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=False)
    history_id = Column(UUID(as_uuid=True), ForeignKey("order_history.id"), nullable=True)

    diagnosis = Column(String(2000), nullable=False)
    media_urls = Column(JSONB, nullable=True, default=[])

    recorded_by_telegram_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("ServiceOrder", back_populates="work_logs")


class OrderPartType(enum.Enum):
    warranty = "warranty"
    paid = "paid"
    quote = "quote"


class OrderPartStatus(enum.Enum):
    pending = "pending"
    available = "available"
    applied = "applied"


class OrderPart(Base):
    """
    Repuesto individual requerido o utilizado en una orden.
    """
    __tablename__ = "order_parts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=False)

    reference = Column(String(100), nullable=False)
    qty = Column(Integer, default=1, nullable=False)
    part_type = Column(Enum(OrderPartType), default=OrderPartType.paid, nullable=False)
    status = Column(Enum(OrderPartStatus), default=OrderPartStatus.pending, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("ServiceOrder", back_populates="parts")


class ServiceOrderReception(Base):
    __tablename__ = "service_order_receptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=False, unique=True)
    
    # Datos recolectados por Sonia (GPT-4o)
    mileage_km = Column(Numeric(10, 2), nullable=False)
    gas_level = Column(String(50), nullable=True) # Full, Half, Quarter, Reserve
    customer_notes = Column(String(1000), nullable=True) # Motivos de ingreso concatenados
    
    # Soft Warnings de las garantías para que queden perpetuas en la DB
    warranty_warnings = Column(String(2000), nullable=True) 

    # URLs a MinIO (Fotos subidas en telegram)
    damage_photos_urls = Column(JSONB, nullable=True, default=[])
    
    # URL al PDF generado por WeasyPrint (Acta finalizada)
    reception_pdf_url = Column(String(500), nullable=True)
    
    # Cliente (dueño) debió firmar a través del equipo del técnico
    signature_url = Column(String(500), nullable=True)

    # Aceptación via OTP
    accepted_at = Column(DateTime, nullable=True)
    accepted_phone = Column(String(20), nullable=True)  # Enmascarado: ***1234

    # Autorización manual sin OTP (solo jefe_taller / superadmin)
    bypass_at = Column(DateTime, nullable=True)
    bypass_by_id = Column(UUID(as_uuid=True), nullable=True)
    bypass_by_name = Column(String(200), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("ServiceOrder", back_populates="reception")


class OrderOTP(Base):
    """OTP de aceptación del acta de recepción por parte del cliente."""
    __tablename__ = "order_otps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=False)
    phone = Column(String(20), nullable=False)
    code = Column(String(6), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
