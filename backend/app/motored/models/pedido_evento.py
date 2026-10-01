"""
Motored Pedidos — modelo `pedido_evento` (sdd/motored-pedidos-ui, Fase 4,
B1; design ADR-1, ADR-2; decision F4-15).

Linea de tiempo de auditoria del pedido de cada (corrida, sucursal): quien
cerro, reabrio o envio, y cuando. `evento`: CERRADO | REABIERTO | ENVIADO |
ENVIO_CORREGIDO. REABIERTO exige un `motivo` no vacio; `detalle` guarda el
tope vigente al cerrar, el numero al enviar o `{antes, despues}` al corregir
el numero. `usuario_id` es NULL solo en los CERRADO `migrado_f3` que M1
inserta para las corridas que F3 dejo CERRADA. Nada la escribe todavia:
llega con el cierre y el envio por tienda (B3a, B3b).
"""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase

EVENTOS_PEDIDO = ("CERRADO", "REABIERTO", "ENVIADO", "ENVIO_CORREGIDO")


class PedidoEvento(MotoredBase):
    __tablename__ = "pedido_evento"
    __table_args__ = (
        CheckConstraint(
            "evento IN ('CERRADO', 'REABIERTO', 'ENVIADO', "
            "'ENVIO_CORREGIDO')",
            name="ck_pedido_evento_evento",
        ),
        CheckConstraint(
            "evento <> 'REABIERTO' OR "
            "(motivo IS NOT NULL AND length(btrim(motivo)) > 0)",
            name="ck_pedido_evento_reabierto_motivo",
        ),
        Index(
            "ix_pedido_evento_corrida_sucursal_creado",
            "corrida_id", "sucursal_id", "creado_en",
        ),
    )

    id = Column(BigInteger, Identity(), primary_key=True)
    corrida_id = Column(
        UUID(as_uuid=True),
        ForeignKey("corrida.id", ondelete="CASCADE"),
        nullable=False,
    )
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False,
    )
    evento = Column(String(20), nullable=False)
    motivo = Column(Text, nullable=True)
    detalle = Column(JSONB, nullable=True)
    usuario_id = Column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True,
    )
    creado_en = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
