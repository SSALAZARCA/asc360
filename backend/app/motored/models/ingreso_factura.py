"""
Motored Pedidos — modelo `ingreso_factura` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"; design §Schema,
spec "Tránsito cruce by RH document identity").

Lado "ingreso" del cruce contra `factura_proveedor_linea` -- misma forma de
clave/índice (`(prefijo_rh, numero_rh)`, `numero_rh bigint`, H3), sin las
tres columnas booleanas de tránsito (esas viven del lado factura, que es
el que el cruce actualiza).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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


class IngresoFactura(MotoredBase):
    __tablename__ = "ingreso_factura"
    __table_args__ = (
        UniqueConstraint(
            "prefijo_rh", "numero_rh", "sucursal_id", "referencia_id",
            name="uq_ingreso_factura_rh_sucursal_referencia",
        ),
        Index("ix_ingreso_factura_prefijo_rh_numero_rh", "prefijo_rh", "numero_rh"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prefijo_rh = Column(String(2), nullable=False)
    numero_rh = Column(BigInteger, nullable=False)
    fecha_ingreso = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    cantidad = Column(Numeric(14, 2), nullable=False)

    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
