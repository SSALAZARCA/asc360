"""
Motored Pedidos — modelo `bodega` (sdd/motored-pedidos-cimientos, Fase 3).

`codigo` UNIQUE. `bodega_principal` nombra el `codigo` de la bodega de
consolidación (p.ej. `BA066` -> `BA061`, §4.1/§5.2) -- guardado como texto
simple en Fase 1, sin FK propia (la resolución de consolidación es de una
fase posterior). Bodega sin `sucursal_id` es un hallazgo de ADVERTENCIA
(nunca bloqueante) en el tablero de salud.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class Bodega(MotoredBase):
    __tablename__ = "bodega"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo = Column(String(50), unique=True, nullable=False)
    descripcion = Column(String(255), nullable=True)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=True)
    bodega_principal = Column(String(50), nullable=True)
    activa = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
