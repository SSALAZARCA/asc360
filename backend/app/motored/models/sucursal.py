"""
Motored Pedidos — modelo `sucursal` (sdd/motored-pedidos-cimientos, Fase 3).

`nombre` UNIQUE y canónico; el `trim()` obligatorio se aplica en la capa de
servicio (`services/maestros.py`) antes de persistir o comparar (spec:
"Trailing-whitespace sucursal name is normalized"). `sic` faltante es el
ÚNICO defecto BLOQUEANTE del tablero de salud (spec "Sucursal without SIC
is blocking").
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class Sucursal(MotoredBase):
    __tablename__ = "sucursal"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(255), unique=True, nullable=False)
    sic = Column(String(50), nullable=True)
    dias_seguridad = Column(Numeric(5, 2), nullable=False, default=2.5)
    activa = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
