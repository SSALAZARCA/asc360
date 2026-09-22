"""
Motored Pedidos — modelo `carga_error` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 1 "Staging Schema"; design §Schema, ADR-5/7).

Una fila por error de validación de una `carga_archivo`, tanto para el
camino tolerante (movimientos) como para el adaptador de `MAESTRO_*`
(ADR-5 espeja `CargaResultado.errores` acá para que la grilla de errores y
`errores.csv` sean uniformes entre ambas políticas de ejecución).
`ON DELETE CASCADE`: los errores de una carga no tienen sentido sin ella.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class CargaError(MotoredBase):
    __tablename__ = "carga_error"
    __table_args__ = (Index("ix_carga_error_carga_id_codigo_error", "carga_id", "codigo_error"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(
        UUID(as_uuid=True), ForeignKey("carga_archivo.id", ondelete="CASCADE"), nullable=False
    )
    fila = Column(Integer, nullable=False)
    columna = Column(String(100), nullable=True)
    valor = Column(String(500), nullable=True)
    codigo_error = Column(String(32), nullable=False)
    mensaje = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
