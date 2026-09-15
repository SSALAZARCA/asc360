"""
Motored Pedidos — modelo `proveedor` (sdd/motored-pedidos-cimientos, Fase 3).

`codigo` UNIQUE (proposal §4.1, spec "Master schema fields and constraints").
Nunca se hace hard-delete: eliminar = `activa = false` (owner decision #3).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class Proveedor(MotoredBase):
    __tablename__ = "proveedor"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(255), nullable=False)
    es_principal = Column(Boolean, nullable=False, default=False)
    dias_empaque_default = Column(Integer, nullable=True)
    dias_transito_default = Column(Integer, nullable=True)
    activa = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
