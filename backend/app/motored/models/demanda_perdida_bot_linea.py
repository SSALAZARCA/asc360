"""
Motored Pedidos — modelo `demanda_perdida_bot_linea` (sdd/motored-ventas-
perdidas-bot, Phase 1 "Schema", design D1/D2).

Ledger por referencia de cada registro que el bot "Lore" escribe. Existe
porque `demanda_perdida.carga_id` sólo guarda el ÚLTIMO header que
contribuyó a esa fila -- insuficiente para saber cuánto aportó una
REGISTRACIÓN puntual cuando el asesor la edita o la cancela el mismo día
(Fase 6). Cada fila de este ledger es la fuente de verdad de "cuánto sumó
este `carga_id` a esta `referencia_id`", independiente de lecturas
posteriores sobre `demanda_perdida`.

`UNIQUE(carga_id, referencia_id)`: una registración nunca repite la misma
referencia dos veces (Fase 6, validación de duplicados en `lineas[]`).
`estado` sigue el mismo patrón varchar+CHECK que `carga_archivo.estado`
(nunca un enum de Postgres, para no requerir una migración de tipo si se
agrega un estado más).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class DemandaPerdidaBotLinea(MotoredBase):
    __tablename__ = "demanda_perdida_bot_linea"
    __table_args__ = (
        UniqueConstraint(
            "carga_id", "referencia_id", name="uq_demanda_perdida_bot_linea_carga_referencia",
        ),
        Index("ix_demanda_perdida_bot_linea_usuario_id_fecha", "usuario_id", "fecha"),
        Index("ix_demanda_perdida_bot_linea_sucursal_id_fecha", "sucursal_id", "fecha"),
        CheckConstraint("cantidad > 0", name="ck_demanda_perdida_bot_linea_cantidad_positiva"),
        CheckConstraint(
            "estado IN ('ACTIVA', 'ANULADA')", name="ck_demanda_perdida_bot_linea_estado",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    cantidad = Column(Numeric(14, 2), nullable=False)
    estado = Column(String(16), nullable=False, default="ACTIVA")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
