"""
Motored satisfaction survey (slice T2) -- `encuesta_registro`: one customer /
service row to survey, taken from an uploaded `encuesta_carga`.

`cedula` is normalized digits-only text (Excel numeric cells are cast before
storing) and `placa` is stored uppercase; the ingestion service (T3) owns that
normalization. `tipo` stays as data so the sales survey can reuse the table.
A record is unique per (batch, cedula, placa, tipo).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class EncuestaRegistro(MotoredBase):
    __tablename__ = "encuesta_registro"
    __table_args__ = (
        UniqueConstraint(
            "carga_id", "cedula", "placa", "tipo",
            name="uq_encuesta_registro_carga_cedula_placa_tipo",
        ),
        CheckConstraint(
            "tipo IN ('SERVICIO_TALLER', 'VENTA')", name="ck_encuesta_registro_tipo"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(UUID(as_uuid=True), ForeignKey("encuesta_carga.id"), nullable=False)
    tipo = Column(String(16), nullable=False)
    nombre = Column(String(255), nullable=False)
    cedula = Column(String(32), nullable=False, index=True)
    celular = Column(String(32), nullable=True)
    linea = Column(String(100), nullable=True)
    placa = Column(String(16), nullable=False)
    sic = Column(String(32), nullable=True)
    centro_servicio = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
