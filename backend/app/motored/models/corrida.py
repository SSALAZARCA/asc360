"""
Motored Pedidos — modelo `corrida` (sdd/motored-pedidos-motor, Fase 3
"Motor", S4a; design ADR-3).

Cabecera de una corrida semanal (o de escenario) del motor de pedidos.
SOLO estructura en S4a -- nada la lee ni la escribe todavía; el ciclo de
vida, el job y la API llegan en S6a/S6b/S7.

`estado` es `varchar` con CHECK (no un enum de Postgres) para poder sumar
estados sin una migración de tipo, igual que `carga_archivo.estado`.
`EN_REVISION` y `ENVIADA` existen en el CHECK pero no son alcanzables en F3.

Los tres JSONB de snapshot (`parametros_snapshot`, `maestro_sustitucion`,
`seleccion_datos`) congelan las entradas de la corrida para que el
reproceso puro no lea tablas de movimiento ni maestros. `seleccion_datos`
lleva, además, el bloque de antigüedad por tipo de dato (decisión #16) y
el bloque `mes_en_curso` (ADR-12). Los números dentro de esos JSON son
strings decimales o fracciones reducidas, nunca floats.

`log` es append-only (eventos de la corrida). `latido_en` +
`reintentar_despues_de` + `intentos` sostienen el heartbeat, el barrido y
el backoff del supervisor propio (ADR-5), separado del de cargas.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase


class Corrida(MotoredBase):
    __tablename__ = "corrida"
    __table_args__ = (
        Index(
            "ix_corrida_proveedor_fecha_corte",
            "proveedor_id",
            text("fecha_corte DESC"),
        ),
        Index("ix_corrida_estado_created_at", "estado", "created_at"),
        Index(
            "ix_corrida_estado_latido_en",
            "estado",
            "latido_en",
            postgresql_where=text("latido_en IS NOT NULL"),
        ),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'CALCULANDO', 'FALLIDA', 'BORRADOR', "
            "'EN_REVISION', 'CERRADA', 'ENVIADA', 'ANULADA')",
            name="ck_corrida_estado",
        ),
        CheckConstraint(
            "alcance IN ('TODAS', 'SELECCION')", name="ck_corrida_alcance",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # PED-{isoYYYY}-S{ww}-{nnn}; los escenarios usan el prefijo ESC-.
    codigo = Column(String(30), nullable=False, unique=True)
    proveedor_id = Column(
        UUID(as_uuid=True), ForeignKey("proveedor.id"), nullable=False,
    )
    fecha_corte = Column(Date, nullable=False)
    estado = Column(
        String(16), nullable=False, default="PENDIENTE",
        server_default="PENDIENTE",
    )
    es_escenario = Column(
        Boolean, nullable=False, default=False, server_default=false(),
    )
    overrides = Column(JSONB, nullable=True)
    alcance = Column(
        String(12), nullable=False, default="TODAS", server_default="TODAS",
    )

    parametros_en_fecha = Column(Date, nullable=True)
    parametros_snapshot = Column(JSONB, nullable=True)
    maestro_sustitucion = Column(JSONB, nullable=True)
    seleccion_datos = Column(JSONB, nullable=True)

    invalidada = Column(
        Boolean, nullable=False, default=False, server_default=false(),
    )
    motivo_invalidacion = Column(JSONB, nullable=True)

    sucursales_total = Column(
        Integer, nullable=False, default=0, server_default="0",
    )
    sucursales_procesadas = Column(
        Integer, nullable=False, default=0, server_default="0",
    )
    latido_en = Column(DateTime(timezone=True), nullable=True)
    intentos = Column(
        Integer, nullable=False, default=0, server_default="0",
    )
    reintentar_despues_de = Column(DateTime(timezone=True), nullable=True)
    log = Column(JSONB, nullable=True)

    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"))
    iniciado_en = Column(DateTime(timezone=True), nullable=True)
    terminado_en = Column(DateTime(timezone=True), nullable=True)
    cerrada_en = Column(DateTime(timezone=True), nullable=True)
    cerrada_por = Column(UUID(as_uuid=True), ForeignKey("usuario.id"))
    anulada_en = Column(DateTime(timezone=True), nullable=True)
    anulada_por = Column(UUID(as_uuid=True), ForeignKey("usuario.id"))
    motivo_anulacion = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
