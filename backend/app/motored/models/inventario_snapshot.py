"""
Motored Pedidos — modelo `inventario_snapshot` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"; design §Schema,
ADR-3/ADR-9).

Consolidación bodega-principal: `services/ingesta/inventario.py` (Fase 6)
resuelve cada bodega secundaria a la sucursal de su bodega principal
(`BA066 -> BA061`, ADR-8) ANTES de escribir acá -- esta tabla ya guarda el
resultado consolidado, nunca una fila por bodega física. `fecha_corte` es
el período DECLARADO (ADR-9, este tipo no tiene columna de fecha en el
archivo). Retención de 90 días (ADR-3) es un purgado externo
(`services/retencion.py`, Fase 12) -- este modelo no la enforza.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class InventarioSnapshot(MotoredBase):
    __tablename__ = "inventario_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "fecha_corte", "sucursal_id", "referencia_id",
            name="uq_inventario_snapshot_fecha_corte_sucursal_referencia",
        ),
        Index("ix_inventario_snapshot_fecha_corte", "fecha_corte"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fecha_corte = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    existencias = Column(Numeric(14, 2), nullable=False)

    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
