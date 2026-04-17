import uuid
import enum
from sqlalchemy import Column, String, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base

class TenantType(enum.Enum):
    service_center = "service_center"
    parts_dealer = "parts_dealer"

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    subdomain = Column(String(100), unique=True, nullable=False)
    nit = Column(String(50), nullable=True)
    phone = Column(String(50), nullable=True)
    tenant_type = Column(Enum(TenantType), nullable=False)
    ciudad = Column(String(100), nullable=True)
    departamento = Column(String(100), nullable=True)
    capacidad_bahias = Column(Integer, nullable=True)
    numero_tecnicos = Column(Integer, nullable=True)
    tipo_servicio = Column(String(50), nullable=True)  # 'Todos' o 'Revisiones/Express'
    config = Column(JSONB, default={})

    # Relaciones que aplican a todos los tenants
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="tenant", cascade="all, delete-orphan")
    service_orders = relationship("ServiceOrder", back_populates="tenant", cascade="all, delete-orphan")
    parts_orders = relationship("PartsOrder", back_populates="tenant", cascade="all, delete-orphan")
