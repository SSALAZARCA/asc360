"""
Motored satisfaction survey (slice T2) -- `encuesta_carga`: one uploaded
customer-base batch (Excel with Nombre, Cedula, Celular, Linea, Placa, SIC,
Centro de servicio and TIPO). Each row becomes an `encuesta_registro`.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class EncuestaCarga(MotoredBase):
    __tablename__ = "encuesta_carga"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre_archivo = Column(String(255), nullable=False)
    total_registros = Column(Integer, nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
