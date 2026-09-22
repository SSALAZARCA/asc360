"""
Motored Pedidos — modelo `sucursal_alias` (sdd/motored-pedidos-cimientos,
Fase 3). Pura data maestra en esta fase: solo debe existir y aceptar filas
(spec "sucursal_alias table exists"). Sin UI ni lógica de resolución todavía
(§7.3 -- eso es de una fase posterior).

Post-Fase-1-de-Ingesta correction (sdd/motored-pedidos-ingesta, migración
`fase2_alias_unique`): `texto_normalizado` gana un UNIQUE + índice. La tabla
salió de Fase 1 sin ninguna restricción ni índice -- verificado contra
código -- y ADR-8 de Fase 2 la convierte en un lookup caliente (cache-first
de resolución) y en destino de escritura (H11 prereq).
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class SucursalAlias(MotoredBase):
    __tablename__ = "sucursal_alias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    texto_normalizado = Column(String(255), nullable=False, unique=True)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
