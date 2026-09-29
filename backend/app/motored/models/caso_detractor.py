"""
Motored satisfaction survey (slice T2) -- `caso_detractor`: one case per
detractor response (overall satisfaction <= 3), unique `respuesta_id`.

Workflow ABIERTO -> EN_GESTION -> CERRADO. `resultado` is set if and only if
the case is CERRADO (`ck_caso_detractor_resultado_iff_cerrado`), enforced by
the DB. `numero` is the human-friendly sequential case number shown to the
customer, backed by a Postgres identity column. The action history lives in
the append-only `caso_detractor_accion`.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class CasoDetractor(MotoredBase):
    __tablename__ = "caso_detractor"
    __table_args__ = (
        UniqueConstraint("respuesta_id", name="uq_caso_detractor_respuesta_id"),
        UniqueConstraint("numero", name="uq_caso_detractor_numero"),
        CheckConstraint(
            "estado IN ('ABIERTO', 'EN_GESTION', 'CERRADO')",
            name="ck_caso_detractor_estado",
        ),
        CheckConstraint(
            "resultado IN ('RECUPERADO', 'NO_RECUPERADO', 'NO_CONTACTABLE')",
            name="ck_caso_detractor_resultado",
        ),
        CheckConstraint(
            "(estado = 'CERRADO' AND resultado IS NOT NULL) "
            "OR (estado <> 'CERRADO' AND resultado IS NULL)",
            name="ck_caso_detractor_resultado_iff_cerrado",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    respuesta_id = Column(
        UUID(as_uuid=True), ForeignKey("encuesta_respuesta.id"), nullable=False
    )
    numero = Column(Integer, Identity(), nullable=False)
    estado = Column(String(16), nullable=False, default="ABIERTO", server_default="ABIERTO")
    resultado = Column(String(16), nullable=True)
    asignado_a = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cerrado_at = Column(DateTime, nullable=True)
