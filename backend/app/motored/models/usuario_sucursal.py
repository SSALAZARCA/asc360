"""
Motored Pedidos — tabla M2M `usuario_sucursal` (sdd/motored-pedidos-
cimientos, Fase 3, ADR-6 design open question resolved as M2M). Permite que
un usuario `SUCURSAL` cubra más de una sucursal; `services/auth.py` la usa
para poblar `MotoredUser.sucursal_ids`.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.motored.database import MotoredBase


class UsuarioSucursal(MotoredBase):
    __tablename__ = "usuario_sucursal"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="sucursales")
