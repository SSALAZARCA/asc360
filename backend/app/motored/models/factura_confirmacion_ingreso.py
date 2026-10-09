"""
Motored -- asesor confirmations of pending invoice ingresos
(odd/tasks/motored-ingresos-pendientes.md).

`factura_confirmacion_ingreso`: ONE shared state per invoice document and
(principal) store: any asesor of the store may set it and correct it later.
`factura_confirmacion_ingreso_historial`: append-only log of every change
(who, when, through which channel: the web app or the public link).
`estado` is 'LLEGO' | 'NO_HA_LLEGADO' (no row = not confirmed yet).
"""
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class FacturaConfirmacionIngreso(MotoredBase):
    __tablename__ = "factura_confirmacion_ingreso"
    __table_args__ = (
        UniqueConstraint(
            "prefijo_rh", "numero_rh", "sucursal_id",
            name="uq_factura_confirmacion_ingreso_doc_sucursal"),
        CheckConstraint(
            "estado IN ('LLEGO', 'NO_HA_LLEGADO')",
            name="ck_factura_confirmacion_ingreso_estado"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prefijo_rh = Column(String(2), nullable=False)
    numero_rh = Column(BigInteger, nullable=False)
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    estado = Column(String(16), nullable=False)
    actualizado_por_usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    actualizado_por_nombre = Column(String(200), nullable=False)
    actualizado_por_cedula = Column(String(20), nullable=True)
    actualizado_en = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())


class FacturaConfirmacionIngresoHistorial(MotoredBase):
    __tablename__ = "factura_confirmacion_ingreso_historial"
    __table_args__ = (
        Index(
            "ix_factura_confirmacion_ingreso_historial_doc",
            "prefijo_rh", "numero_rh", "sucursal_id"),
        CheckConstraint(
            "estado IN ('LLEGO', 'NO_HA_LLEGADO')",
            name="ck_factura_confirmacion_ingreso_historial_estado"),
        CheckConstraint(
            "canal IN ('web', 'link')",
            name="ck_factura_confirmacion_ingreso_historial_canal"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prefijo_rh = Column(String(2), nullable=False)
    numero_rh = Column(BigInteger, nullable=False)
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    estado = Column(String(16), nullable=False)
    por_usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    por_nombre = Column(String(200), nullable=False)
    por_cedula = Column(String(20), nullable=True)
    canal = Column(String(8), nullable=False)
    creado_en = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
