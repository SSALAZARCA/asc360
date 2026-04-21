import uuid
import enum
from sqlalchemy import Column, String, Enum, Integer, Boolean, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base

class TenantType(enum.Enum):
    service_center = "service_center"
    parts_dealer = "parts_dealer"
    distribuidor = "distribuidor"

class EstadoRed(enum.Enum):
    activo = "activo"
    suspendido = "suspendido"
    retirado = "retirado"

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

    # Capacidades de red (determinan el nivel 1S/2S/3S)
    has_sales = Column(Boolean, nullable=False, default=False)   # Venta de motos
    has_parts = Column(Boolean, nullable=False, default=False)   # Venta de repuestos
    has_service = Column(Boolean, nullable=False, default=False) # Servicio de taller

    # Identificación extendida
    representante_legal = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    direccion = Column(String(500), nullable=True)
    zona_geografica = Column(String(100), nullable=True)
    fecha_vinculacion = Column(Date, nullable=True)
    estado_red = Column(Enum(EstadoRed), nullable=False, default=EstadoRed.activo)
    categoria = Column(String(10), nullable=True)  # A, B, C

    # Relaciones que aplican a todos los tenants
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="tenant", cascade="all, delete-orphan")
    service_orders = relationship("ServiceOrder", back_populates="tenant", cascade="all, delete-orphan")
    parts_orders = relationship("PartsOrder", back_populates="tenant", cascade="all, delete-orphan")

    @property
    def nivel_red(self) -> str:
        count = sum([self.has_sales, self.has_parts, self.has_service])
        return f"{count}S" if count > 0 else "Sin capacidades"
