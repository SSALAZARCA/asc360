"""
Motored Pedidos — modelo `corrida_sucursal` (sdd/motored-pedidos-motor,
Fase 3 "Motor", S4a; design ADR-3, ADR-5).

Checkpoint por sucursal dentro de una corrida: progreso, estado, atributos
congelados de la sucursal (apertura, divisor, días) y advertencias por
sucursal omitida o fallida. PK compuesta `(corrida_id, sucursal_id)`; el
supervisor reanuda saltando las sucursales ya terminadas.

`estado`: PENDIENTE | OK | OMITIDA (decisión #14, sin historia) | FALLIDA.
`buckets_operados` es un bitmask de los seis meses cerrados en que la
sucursal estaba abierta; `divisor` es la suma de pesos de esos meses.
"""
from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase


class CorridaSucursal(MotoredBase):
    __tablename__ = "corrida_sucursal"
    __table_args__ = (
        Index("ix_corrida_sucursal_corrida_estado", "corrida_id", "estado"),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'OK', 'OMITIDA', 'FALLIDA')",
            name="ck_corrida_sucursal_estado",
        ),
    )

    corrida_id = Column(
        UUID(as_uuid=True),
        ForeignKey("corrida.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), primary_key=True,
    )
    orden = Column(Integer, nullable=False)
    estado = Column(
        String(12), nullable=False, default="PENDIENTE",
        server_default="PENDIENTE",
    )
    codigo = Column(String(20), nullable=True)
    mensaje = Column(Text, nullable=True)

    fecha_apertura = Column(Date, nullable=True)
    divisor = Column(SmallInteger, nullable=True)
    buckets_operados = Column(SmallInteger, nullable=True)
    dias_empaque = Column(Numeric(6, 2), nullable=True)
    dias_transito = Column(Numeric(6, 2), nullable=True)
    dias_seguridad = Column(Numeric(6, 2), nullable=True)
    dias_entre_pedidos = Column(Numeric(6, 2), nullable=True)
    parametros = Column(JSONB, nullable=True)
    coberturas = Column(JSONB, nullable=True)

    lineas = Column(
        Integer, nullable=False, default=0, server_default="0",
    )
    excluidas = Column(
        Integer, nullable=False, default=0, server_default="0",
    )
    unidades = Column(Numeric(14, 2), nullable=True)
    valor = Column(Numeric(16, 2), nullable=True)

    intentos = Column(
        Integer, nullable=False, default=0, server_default="0",
    )
    iniciado_en = Column(DateTime(timezone=True), nullable=True)
    terminado_en = Column(DateTime(timezone=True), nullable=True)
