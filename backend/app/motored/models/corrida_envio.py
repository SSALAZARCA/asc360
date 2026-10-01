"""
Motored Pedidos — modelo `corrida_envio` (sdd/motored-pedidos-ui, Fase 4,
B1; design ADR-2; decisiones F4-5, F4-13 y F4-15).

Un envio por pedido de tienda enviado: PK `(corrida_id, sucursal_id)`. El
proveedor y la `fecha_corte` se denormalizan para que la UNIQUE
`uq_corrida_envio_corte_sucursal` (`proveedor_id, fecha_corte, sucursal_id`)
sea la regla F4-13 exacta: una tienda no se envia dos veces para el mismo
corte. `ENVIADO <=> existe la fila` (se escriben en la misma transaccion).
El FK a la corrida es RESTRICT: ENVIADO es terminal y una corrida con un
envio no se anula ni se borra. Los hechos del envio son inmutables salvo el
numero de orden, que F4-15 permite corregir (la auditoria queda en
`pedido_evento`). Nada la escribe todavia: llega con el envio (B3b).
"""
from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class CorridaEnvio(MotoredBase):
    __tablename__ = "corrida_envio"
    __table_args__ = (
        UniqueConstraint(
            "proveedor_id", "fecha_corte", "sucursal_id",
            name="uq_corrida_envio_corte_sucursal",
        ),
        CheckConstraint(
            "length(btrim(numero_pedido_proveedor)) > 0",
            name="ck_corrida_envio_numero",
        ),
    )

    corrida_id = Column(
        UUID(as_uuid=True),
        ForeignKey("corrida.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), primary_key=True,
    )
    proveedor_id = Column(
        UUID(as_uuid=True), ForeignKey("proveedor.id"), nullable=False,
    )
    fecha_corte = Column(Date, nullable=False)
    numero_pedido_proveedor = Column(String(50), nullable=False)
    fecha_envio = Column(Date, nullable=False)
    enviada_por = Column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False,
    )
    enviada_en = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
