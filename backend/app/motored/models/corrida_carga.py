"""
Motored Pedidos — modelo `corrida_carga` (sdd/motored-pedidos-motor, Fase 3
"Motor", S4a; design ADR-3, ADR-11).

Vínculo entre una corrida y cada carga (origen EXCEL) cuyos datos usó. Es la
fuente de verdad de `cargas_usadas` (la API lo proyecta por `tipo`) y de la
guarda de anulación de cargas (ADR-11). Las cargas de origen BOT no se
registran acá: son ~340 mil cabeceras al año y se revierten en sitio.

Sobrevive a la purga de 90 días de F2 porque las cabeceras de carga no se
purgan nunca. `carga_id` no tiene CASCADE: una carga usada por una corrida
no puede borrarse.
"""
from sqlalchemy import Column, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class CorridaCarga(MotoredBase):
    __tablename__ = "corrida_carga"
    __table_args__ = (
        Index("ix_corrida_carga_carga_id", "carga_id"),
    )

    corrida_id = Column(
        UUID(as_uuid=True),
        ForeignKey("corrida.id", ondelete="CASCADE"),
        primary_key=True,
    )
    carga_id = Column(
        UUID(as_uuid=True), ForeignKey("carga_archivo.id"), primary_key=True,
    )
    tipo = Column(String(32), nullable=False)
