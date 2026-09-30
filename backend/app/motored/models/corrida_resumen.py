"""
Motored Pedidos — modelo `corrida_resumen` (sdd/motored-pedidos-motor,
Fase 3 "Motor", S4a; design ADR-3).

Resumen por clase (AF, AM, ..., DS) de cada sucursal de una corrida, el
equivalente de AA1:AE11 del Excel: unidades, referencias con pedido > 0,
valor y peso porcentual. Los totales de red NO se persisten: se suman al
leer. `clase` admite hasta 8 caracteres para no cerrar la puerta a una fila
`TOTAL` por sucursal si la persistencia (S6a) decide guardarla.
"""
from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class CorridaResumen(MotoredBase):
    __tablename__ = "corrida_resumen"

    corrida_id = Column(
        UUID(as_uuid=True),
        ForeignKey("corrida.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), primary_key=True,
    )
    clase = Column(String(8), primary_key=True)

    unidades = Column(
        Numeric(14, 2), nullable=False, default=0, server_default="0",
    )
    referencias = Column(
        Integer, nullable=False, default=0, server_default="0",
    )
    valor = Column(
        Numeric(16, 2), nullable=False, default=0, server_default="0",
    )
    porcentaje_peso = Column(Numeric(12, 6), nullable=True)
