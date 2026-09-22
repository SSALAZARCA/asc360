"""
Motored Pedidos — modelo `venta_mensual` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"; design §Schema,
ADR-4/ADR-9).

Agregado NETO-firmado por `(sucursal, referencia, anio, mes, origen)`: una
nota de crédito resta directamente sobre el mismo mes/`origen`, sin
clasificación de devolución (ADR-4 -- `Cantidad inv.` se suma tal cual
llega, con signo). `origen` (`MOSTRADOR`/`TALLER`, viene de `Módulo`) es una
COLUMNA de la clave, nunca se colapsa al ingerir (spec "Módulo origin is
queryable separately or combined").

Apply es REPLACE-not-sum (`ON CONFLICT DO UPDATE SET unidades =
EXCLUDED.unidades`, ADR-4) -- el `UNIQUE` de abajo es la clave de ese
upsert. `es_mes_parcial`/`dias_transcurridos` los completa el módulo de
período de la Fase 5 (ADR-9); acá solo existen como columnas nullable/
default, sin lógica todavía (fuera de alcance de esta fase).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class VentaMensual(MotoredBase):
    __tablename__ = "venta_mensual"
    __table_args__ = (
        UniqueConstraint(
            "sucursal_id", "referencia_id", "anio", "mes", "origen",
            name="uq_venta_mensual_sucursal_referencia_anio_mes_origen",
        ),
        Index("ix_venta_mensual_referencia_id_anio_mes", "referencia_id", "anio", "mes"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    anio = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)
    origen = Column(String(12), nullable=False)
    unidades = Column(Numeric(14, 2), nullable=False)

    es_mes_parcial = Column(Boolean, nullable=False, default=False)
    dias_transcurridos = Column(Integer, nullable=True)

    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
