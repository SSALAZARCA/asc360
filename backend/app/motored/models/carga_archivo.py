"""
Motored Pedidos — modelo `carga_archivo` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 1 "Staging Schema"; design §Schema, ADR-1/1b/9).

Una fila por archivo subido, de CUALQUIER `tipo` (masters o movimientos):
`tipo` empieza NULL hasta que la detección server-side lo resuelve (ADR-9).
`estado` es `varchar`, no un enum de Postgres, para poder agregar
`APLICANDO` sin una migración de tipo (§Schema). `latido_en` es el
heartbeat de ADR-1b -- reemplaza a un `job_id` de cola de trabajos que este
diseño explícitamente NO tiene (no hay worker separado, ADR-1 Opción B).

`periodo_desde`/`periodo_hasta` son DECLARADOS por el usuario y autoritativos
(ADR-9) -- nunca inferidos del contenido salvo para los dos tipos sin
período declarable (`FACTURAS_PEDIDOS`/`INGRESOS_FACTURAS`, fuera de
alcance de esta fase). `log` guarda, entre otras cosas, `periodo_detectado`
y `filas_por_periodo` (el histograma usado por el veredicto de ADR-9).

`origen` (sdd/motored-ventas-perdidas-bot, Phase 1 "Schema", design D1/D2)
distingue filas subidas por Excel de filas nacidas de un registro del bot
"Lore". Las filas `BOT` no traen archivo real -- por eso las 4 columnas de
archivo se vuelven nullable, con `ck_carga_archivo_archivo_por_origen`
garantizando en la base de datos que una fila `EXCEL` siga exigiendo las 4
tan estricta como antes. `ck_carga_archivo_bot_tipo` limita el origen `BOT`
a `tipo='DEMANDA_PERDIDA'` (única superficie que el bot escribe en v1).
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
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase


class CargaArchivo(MotoredBase):
    __tablename__ = "carga_archivo"
    __table_args__ = (
        Index("ix_carga_archivo_tipo_estado_created_at", "tipo", "estado", "created_at"),
        Index("ix_carga_archivo_hash_sha256", "hash_sha256", unique=False),
        Index(
            "ix_carga_archivo_estado_latido_en",
            "estado",
            "latido_en",
            postgresql_where=text("latido_en IS NOT NULL"),
        ),
        Index(
            "ix_carga_archivo_origen_tipo_created_at", "origen", "tipo", "created_at",
        ),
        CheckConstraint("origen IN ('EXCEL', 'BOT')", name="ck_carga_archivo_origen"),
        CheckConstraint(
            "origen = 'BOT' OR (nombre_archivo IS NOT NULL AND hash_sha256 IS NOT NULL "
            "AND ruta_objeto IS NOT NULL AND bytes IS NOT NULL)",
            name="ck_carga_archivo_archivo_por_origen",
        ),
        CheckConstraint(
            "origen = 'EXCEL' OR tipo = 'DEMANDA_PERDIDA'", name="ck_carga_archivo_bot_tipo",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(String(32), nullable=True)
    origen = Column(String(8), nullable=False, default="EXCEL")
    nombre_archivo = Column(String(255), nullable=True)
    hash_sha256 = Column(String(64), nullable=True)
    ruta_objeto = Column(String(500), nullable=True)
    bytes = Column(Integer, nullable=True)
    estado = Column(String(16), nullable=False, default="PENDIENTE")

    filas_leidas = Column(Integer, nullable=False, default=0)
    filas_validas = Column(Integer, nullable=False, default=0)
    filas_rechazadas = Column(Integer, nullable=False, default=0)

    periodo_desde = Column(Date, nullable=True)
    periodo_hasta = Column(Date, nullable=True)

    lotes_staged = Column(Integer, nullable=False, default=0)
    ultimo_lote_aplicado = Column(Integer, nullable=False, default=0)

    latido_en = Column(DateTime(timezone=True), nullable=True)
    log = Column(JSONB, nullable=True)

    subido_por = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
    aplicado_en = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
