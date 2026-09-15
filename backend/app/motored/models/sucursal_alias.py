"""
Motored Pedidos — modelo `sucursal_alias` (sdd/motored-pedidos-cimientos,
Fase 3). Pura data maestra en esta fase: solo debe existir y aceptar filas
(spec "sucursal_alias table exists"). Sin UI ni lógica de resolución todavía
(§7.3 -- eso es de una fase posterior).
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class SucursalAlias(MotoredBase):
    __tablename__ = "sucursal_alias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    texto_normalizado = Column(String(255), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
