"""
Motored satisfaction survey (slice T2) -- `encuesta_respuesta`: the customer's
answer, at most ONE per `encuesta_registro` (unique `registro_id`).

Mapping to the Google Form "ENCUESTA TALLERES" questions:
- Q1 (required, 1-5)              -> `satisfaccion_general`
- Q2 matrix rows (1-5, NULL=NS/NR), in the form's order:
    1. explicacion y asesoria tecnica   -> `p_explicacion_tecnica`
    2. confianza en la reparacion       -> `p_confianza_reparacion`
    3. servicio en el taller            -> `p_servicio_taller`
    4. calidad del trabajo mecanicos    -> `p_calidad_mecanicos`
    5. claridad de los cobros           -> `p_claridad_cobros`
    6. procedencia/originalidad repuestos -> `p_originalidad_repuestos`
- Q3 (optional free text)         -> `observaciones`
- Q4 (required, Si/No consent)    -> `autoriza_datos`
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase

MATRIX_COLUMNS = (
    "p_explicacion_tecnica",
    "p_confianza_reparacion",
    "p_servicio_taller",
    "p_calidad_mecanicos",
    "p_claridad_cobros",
    "p_originalidad_repuestos",
)


class EncuestaRespuesta(MotoredBase):
    __tablename__ = "encuesta_respuesta"
    __table_args__ = (
        UniqueConstraint("registro_id", name="uq_encuesta_respuesta_registro_id"),
        CheckConstraint(
            "satisfaccion_general BETWEEN 1 AND 5",
            name="ck_encuesta_respuesta_satisfaccion_general",
        ),
        *(
            CheckConstraint(
                f"{col} IS NULL OR {col} BETWEEN 1 AND 5",
                name=f"ck_encuesta_respuesta_{col}",
            )
            for col in MATRIX_COLUMNS
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registro_id = Column(
        UUID(as_uuid=True), ForeignKey("encuesta_registro.id"), nullable=False
    )
    satisfaccion_general = Column(SmallInteger, nullable=False)
    p_explicacion_tecnica = Column(SmallInteger, nullable=True)
    p_confianza_reparacion = Column(SmallInteger, nullable=True)
    p_servicio_taller = Column(SmallInteger, nullable=True)
    p_calidad_mecanicos = Column(SmallInteger, nullable=True)
    p_claridad_cobros = Column(SmallInteger, nullable=True)
    p_originalidad_repuestos = Column(SmallInteger, nullable=True)
    observaciones = Column(Text, nullable=True)
    autoriza_datos = Column(Boolean, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
