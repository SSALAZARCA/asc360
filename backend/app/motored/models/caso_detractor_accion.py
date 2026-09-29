"""
Motored satisfaction survey (slice T2) -- `caso_detractor_accion`: APPEND-ONLY
log of everything done on a detractor case (who, when, what). Corrections are
new `CORRECCION` rows, never edits. The migration enforces this at the DB level
with a trigger that rejects UPDATE and DELETE. `usuario_id` NULL means the
system acted (e.g. the automatic `APERTURA` entry).
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class CasoDetractorAccion(MotoredBase):
    __tablename__ = "caso_detractor_accion"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('APERTURA', 'LLAMADA', 'WHATSAPP', 'NOTA', "
            "'CAMBIO_ESTADO', 'COMPENSACION', 'CORRECCION')",
            name="ck_caso_detractor_accion_tipo",
        ),
        Index("ix_caso_detractor_accion_caso_id_created_at", "caso_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    caso_id = Column(UUID(as_uuid=True), ForeignKey("caso_detractor.id"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
    tipo = Column(String(16), nullable=False)
    descripcion = Column(Text, nullable=False)
    estado_anterior = Column(String(16), nullable=True)
    estado_nuevo = Column(String(16), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
