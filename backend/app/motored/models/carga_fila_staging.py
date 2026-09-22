"""
Motored Pedidos — modelo `carga_fila_staging` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 1 "Staging Schema"; design §Schema, ADR-2/2b).

Guarda SOLO las filas aplicables de un dry-run (las rechazadas van directo
a `carga_error`), con `sucursal_id`/`referencia_id` ya resueltas cuando la
resolución tuvo éxito y NULL en caso contrario -- así `Aplicar` sólo tiene
que re-resolver los NULL contra los maestros vigentes (ADR-2), sin
re-parsear el archivo. `UNIQUE(carga_id, fila)` es la garantía de
idempotencia por fila dentro de una misma carga; `lote` es lo que permite
reanudar desde `ultimo_lote_aplicado + 1` tras un reinicio (ADR-1b).
Se borra al llegar a `APLICADO`/`ANULADO`.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase


class CargaFilaStaging(MotoredBase):
    __tablename__ = "carga_fila_staging"
    __table_args__ = (
        UniqueConstraint("carga_id", "fila", name="uq_carga_fila_staging_carga_id_fila"),
        Index("ix_carga_fila_staging_carga_id_lote", "carga_id", "lote"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(
        UUID(as_uuid=True), ForeignKey("carga_archivo.id", ondelete="CASCADE"), nullable=False
    )
    fila = Column(Integer, nullable=False)
    lote = Column(Integer, nullable=False)
    payload = Column(JSONB, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=True)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
