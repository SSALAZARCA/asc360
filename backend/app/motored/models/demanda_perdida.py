"""
Motored Pedidos — modelo `demanda_perdida` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"; design §Schema,
ADR-9, spec "DEMANDA_PERDIDA silent discard of incomplete rows").

`fecha` viene del período DECLARADO (ADR-9) -- el archivo de este tipo no
trae ninguna columna de fecha (§5.7, verificado). Filas sin referencia
resoluble o con `cantidad_solicitada <= 0` se descartan en silencio, SIN
`carga_error` (única excepción documentada a la tolerancia por-fila) --
esa regla la aplica `services/ingesta/demanda_perdida.py` (Fase 7) al
escribir, no una constraint acá.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class DemandaPerdida(MotoredBase):
    __tablename__ = "demanda_perdida"
    __table_args__ = (
        UniqueConstraint(
            "fecha", "sucursal_id", "referencia_id",
            name="uq_demanda_perdida_fecha_sucursal_referencia",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fecha = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    cantidad_solicitada = Column(Numeric(14, 2), nullable=False)

    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
