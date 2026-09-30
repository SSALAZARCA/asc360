"""
Motored Pedidos — modelo `parametro_metodologia` (sdd/motored-pedidos-
cimientos, Fase 3, §6.10).

SOLO estructura en Fase 1 -- ningún motor la lee todavía. Versionado por
INSERCIÓN: un cambio SIEMPRE crea una fila nueva con un nuevo
`vigente_desde`; la fila anterior queda intacta, nunca se hace UPDATE en
sitio (spec "parametro_metodologia versioning"). Por eso esta tabla NO
lleva `updated_at` -- ninguna fila se actualiza jamás después de creada.

`sucursal_id` (sdd/motored-pedidos-motor, S4a, ADR-7): alcance por sucursal,
NULL = alcance global. Todas las filas existentes son globales, así que la
columna nullable no cambia ninguna lectura actual. La resolución cae de
sucursal a global a default codificado; ese lector llega en S4b.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase


class ParametroMetodologia(MotoredBase):
    __tablename__ = "parametro_metodologia"
    __table_args__ = (
        Index(
            "ix_parametro_metodologia_clave_sucursal_vigente",
            "clave", "sucursal_id", "vigente_desde",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clave = Column(String(100), nullable=False)
    valor = Column(JSONB, nullable=False)
    vigente_desde = Column(Date, nullable=False, default=date.today)
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
