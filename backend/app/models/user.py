import uuid
import enum
from sqlalchemy import Column, String, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base

class Role(enum.Enum):
    superadmin = "superadmin"
    jefe_taller = "jefe_taller"
    technician = "technician"
    client = "client"
    parts_dealer = "parts_dealer"
    proveedor = "proveedor"

class UserStatus(enum.Enum):
    pending = "pending"
    active = "active"
    rejected = "rejected"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True) # superadmins no tienen tenant
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=True) # Para autenticación web (híbrido)
    telegram_id = Column(String(50), unique=True, nullable=True)
    phone = Column(String(50), nullable=True)
    role = Column(Enum(Role), nullable=False)
    status = Column(Enum(UserStatus), nullable=False, default=UserStatus.pending)
    service_center_name = Column(String(255), nullable=True)

    tenant = relationship("Tenant", back_populates="users")
    
    # Órdenes creadas / Técnicos asignados
    created_parts_orders = relationship("PartsOrder", back_populates="creator")
