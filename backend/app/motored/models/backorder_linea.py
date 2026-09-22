"""
Motored Pedidos — modelo `backorder_linea` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"; design §Schema,
ADR-9).

Solo cuentan las líneas con `cantidad_pendiente > 0` filtradas por
`estados_backorder_vigentes` (default `['BACKORDER']`, spec "BACKORDER
pending-quantity filter") -- ese filtro lo aplica `services/ingesta/
backorder.py` (Fase 7) al escribir, no una constraint acá. `estado` es
`varchar`, no un enum de Postgres, mismo criterio que `carga_archivo.estado`.
`fecha_corte` es el período DECLARADO (ADR-9, single-`fecha_corte`).
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class BackorderLinea(MotoredBase):
    __tablename__ = "backorder_linea"
    __table_args__ = (
        UniqueConstraint(
            "fecha_corte", "sucursal_id", "referencia_id", "numero_pedido",
            name="uq_backorder_linea_fecha_corte_sucursal_referencia_pedido",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fecha_corte = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    numero_pedido = Column(String(50), nullable=False)
    estado = Column(String(32), nullable=False)
    cantidad_pendiente = Column(Numeric(14, 2), nullable=False)

    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
