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
"""
import uuid
from datetime import datetime

from sqlalchemy import (
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
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(String(32), nullable=True)
    nombre_archivo = Column(String(255), nullable=False)
    hash_sha256 = Column(String(64), nullable=False)
    ruta_objeto = Column(String(500), nullable=False)
    bytes = Column(Integer, nullable=False)
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
