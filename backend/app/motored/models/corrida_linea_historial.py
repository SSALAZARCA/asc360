"""
Motored Pedidos — modelo `corrida_linea_historial` (sdd/motored-pedidos-ui,
Fase 4, B1; design ADR-2, ADR-3).

Auditoria de solo insercion de cada cambio de `corrida_linea.pedido_final`:
quien, cuando, el valor anterior y el nuevo, y el motivo (`MANUAL` para la
edicion de un usuario, `RECORTE_PRESUPUESTO` para un recorte aplicado; en este
ultimo `detalle` guarda el tope usado). Las filas son inmutables, sobreviven
al reabrir y al volver a cerrar, y se borran en cascada con la corrida o la
linea. Nada las escribe todavia: llega con la edicion de lineas (B2).
"""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase

MOTIVOS_EDICION = ("MANUAL", "RECORTE_PRESUPUESTO")


class CorridaLineaHistorial(MotoredBase):
    __tablename__ = "corrida_linea_historial"
    __table_args__ = (
        CheckConstraint(
            "campo IN ('pedido_final')",
            name="ck_corrida_linea_historial_campo",
        ),
        CheckConstraint(
            "motivo IN ('MANUAL', 'RECORTE_PRESUPUESTO')",
            name="ck_corrida_linea_historial_motivo",
        ),
        Index(
            "ix_corrida_linea_historial_linea_creado",
            "linea_id", text("creado_en DESC"),
        ),
        Index(
            "ix_corrida_linea_historial_corrida_sucursal",
            "corrida_id", "sucursal_id",
        ),
    )

    id = Column(BigInteger, Identity(), primary_key=True)
    corrida_id = Column(
        UUID(as_uuid=True),
        ForeignKey("corrida.id", ondelete="CASCADE"),
        nullable=False,
    )
    linea_id = Column(
        BigInteger,
        ForeignKey("corrida_linea.id", ondelete="CASCADE"),
        nullable=False,
    )
    sucursal_id = Column(UUID(as_uuid=True), nullable=False)
    campo = Column(
        String(30), nullable=False, default="pedido_final",
        server_default="pedido_final",
    )
    valor_anterior = Column(Numeric(14, 2), nullable=False)
    valor_nuevo = Column(Numeric(14, 2), nullable=False)
    motivo = Column(String(24), nullable=False)
    detalle = Column(JSONB, nullable=True)
    usuario_id = Column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False,
    )
    creado_en = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
