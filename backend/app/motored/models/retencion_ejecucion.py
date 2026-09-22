"""
Motored Pedidos — modelo `retencion_ejecucion` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 1 "Staging Schema"; design §Schema, ADR-3).

Ledger Y ancla del scheduler de la purga de retención (ADR-3): cada corrida
de `services/retencion.py` (Fase 12, fuera de alcance de esta fase) escribe
una fila acá. Anclar el "¿cuándo corrió por última vez?" en Postgres -- no
en un `SETNX` de Redis ni en memoria de proceso -- es lo que permite que un
reinicio no duplique ni salte un día de purga.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class RetencionEjecucion(MotoredBase):
    __tablename__ = "retencion_ejecucion"
    __table_args__ = (Index("ix_retencion_ejecucion_tabla_ejecutado_en", "tabla", "ejecutado_en"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tabla = Column(String(64), nullable=False)
    ejecutado_en = Column(DateTime, nullable=False, default=datetime.utcnow)
    fecha_limite = Column(Date, nullable=False)
    filas_eliminadas = Column(Integer, nullable=False, default=0)
    duracion_ms = Column(Integer, nullable=False, default=0)
