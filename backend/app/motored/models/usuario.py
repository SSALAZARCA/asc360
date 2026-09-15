"""
Motored Pedidos — modelo `usuario` (sdd/motored-pedidos-cimientos, Fase 3).

Tabla de usuarios COMPLETAMENTE independiente de `app.models.user.User` --
sin FK, sin secuencia compartida, sin join posible (motored-isolation,
"Independent user store"). Vive sobre `MotoredBase`, nunca sobre
`app.database.Base`.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.motored.database import MotoredBase


class MotoredRole(enum.Enum):
    ADMIN = "ADMIN"
    COMPRAS = "COMPRAS"
    SUCURSAL = "SUCURSAL"
    CONSULTA = "CONSULTA"


class Usuario(MotoredBase):
    __tablename__ = "usuario"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(MotoredRole, name="motored_role"), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sucursales = relationship(
        "UsuarioSucursal", back_populates="usuario", cascade="all, delete-orphan"
    )
