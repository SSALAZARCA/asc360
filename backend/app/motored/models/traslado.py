"""
Motored -- pending transfers between stores (odd/tasks/motored-traslados-
pendientes.md).

`traslado_linea`: one row per line of a TRASLADOS load (the ERP file of the
transfers still alive). Each applied load is a full snapshot: the current one
is the latest non-ANULADO APLICADO TRASLADOS carga; older loads keep their
rows so annulling the latest falls back to the previous snapshot.
`sucursal_entrada_id` is the receiving store (required); the origin store is
optional (an unknown origin bodega keeps the bodega code and description).
`referencia_id` is NULL for a code that is not in the catalog.

`traslado_confirmacion`: ONE shared state per transfer, identified by
`(nro_documento, bodega_salida, bodega_entrada)` (the document number
repeats across origin bodegas and may feed two destinations): 'RECIBIDO' | 'NO_HA_LLEGADO' (no row = not confirmed yet).
`traslado_confirmacion_historial`: append-only log of every change (who,
when, through which channel: the web app or the public link).
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
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class TrasladoLinea(MotoredBase):
    __tablename__ = "traslado_linea"
    __table_args__ = (
        Index("ix_traslado_linea_carga_id", "carga_id"),
        Index("ix_traslado_linea_sucursal_entrada_id", "sucursal_entrada_id"),
        Index("ix_traslado_linea_documento_bodega",
              "nro_documento", "bodega_salida"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(
        UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)
    nro_documento = Column(String(40), nullable=False)
    fecha = Column(Date, nullable=False)
    bodega_salida = Column(String(20), nullable=False)
    descripcion_bodega_salida = Column(String(120), nullable=True)
    sucursal_salida_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=True)
    bodega_entrada = Column(String(20), nullable=False)
    sucursal_entrada_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_codigo = Column(String(60), nullable=False)
    referencia_id = Column(
        UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=True)
    descripcion = Column(String(200), nullable=True)
    unidad = Column(String(20), nullable=True)
    cantidad = Column(Numeric(14, 2), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class TrasladoConfirmacion(MotoredBase):
    __tablename__ = "traslado_confirmacion"
    __table_args__ = (
        UniqueConstraint(
            "nro_documento", "bodega_salida", "bodega_entrada",
            name="uq_traslado_confirmacion_documento_bodega"),
        CheckConstraint(
            "estado IN ('RECIBIDO', 'NO_HA_LLEGADO')",
            name="ck_traslado_confirmacion_estado"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nro_documento = Column(String(40), nullable=False)
    bodega_salida = Column(String(20), nullable=False)
    bodega_entrada = Column(String(20), nullable=False)
    estado = Column(String(16), nullable=False)
    actualizado_por_usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    actualizado_por_nombre = Column(String(200), nullable=False)
    actualizado_por_cedula = Column(String(20), nullable=True)
    actualizado_en = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class TrasladoConfirmacionHistorial(MotoredBase):
    __tablename__ = "traslado_confirmacion_historial"
    __table_args__ = (
        Index("ix_traslado_confirmacion_historial_doc",
              "nro_documento", "bodega_salida", "bodega_entrada"),
        CheckConstraint(
            "estado IN ('RECIBIDO', 'NO_HA_LLEGADO')",
            name="ck_traslado_confirmacion_historial_estado"),
        CheckConstraint(
            "canal IN ('web', 'link')",
            name="ck_traslado_confirmacion_historial_canal"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nro_documento = Column(String(40), nullable=False)
    bodega_salida = Column(String(20), nullable=False)
    bodega_entrada = Column(String(20), nullable=False)
    estado = Column(String(16), nullable=False)
    por_usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    por_nombre = Column(String(200), nullable=False)
    por_cedula = Column(String(20), nullable=True)
    canal = Column(String(8), nullable=False)
    creado_en = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
