"""
Motored - modelo `aviso_antiguedad_enviado`: ledger de los avisos de
antiguedad ya enviados por Telegram.

La clave unica (dataset, umbral, fecha_vencimiento) es lo que hace el envio
idempotente: quien inserta primero gana el derecho de enviar; un reinicio o
una segunda replica reciben el conflicto y no mandan nada.
"""
import uuid

from sqlalchemy import Column, Date, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class AvisoAntiguedadEnviado(MotoredBase):
    __tablename__ = "aviso_antiguedad_enviado"
    __table_args__ = (
        UniqueConstraint(
            "dataset", "umbral", "fecha_vencimiento",
            name="uq_aviso_antiguedad_dataset_umbral_vence"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset = Column(String(32), nullable=False)
    umbral = Column(String(16), nullable=False)
    fecha_vencimiento = Column(Date, nullable=False)
    enviado_en = Column(DateTime(timezone=True), nullable=False)
