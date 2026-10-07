"""
Motored -- ledger of the daily asesor report messages
(odd/motored-reporte-diario-asesor, T3b).

One row per attempt to send an asesor the Lore message with their personal
report link, for one `fecha_datos` (the last sales date the report covers):

- `estado`: 'enviado' (Telegram accepted it), 'fallido' (any other error;
  the daily loop retries it, up to 3 attempts per date) or 'bloqueado'
  (403: the asesor blocked the bot; never retried for that date).
- `reenvio`: an ADMIN "Reenviar a todos" row, with `solicitado_por`.
- `uq_reporte_asesor_envio_diario`: at most ONE automatic 'enviado' row per
  usuario and `fecha_datos`, so a reload or a second worker never sends the
  automatic message twice. Resends and failures are not limited.

`detalle` is a short reason ("Telegram 403"). It never holds the token, the
URL or the message text.
"""
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index,
    String, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase

INDICE_DIARIO = "uq_reporte_asesor_envio_diario"
ESTADOS = ("enviado", "fallido", "bloqueado")


class ReporteAsesorEnvio(MotoredBase):
    __tablename__ = "reporte_asesor_envio"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('enviado', 'fallido', 'bloqueado')",
            name="ck_reporte_asesor_envio_estado"),
        Index(
            INDICE_DIARIO, "usuario_id", "fecha_datos", unique=True,
            postgresql_where=text("NOT reenvio AND estado = 'enviado'"),
        ),
        Index("ix_reporte_asesor_envio_fecha", "fecha_datos"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
    )
    cedula = Column(String(20), nullable=False)
    fecha_datos = Column(Date, nullable=False)
    enviado_en = Column(DateTime(timezone=True), nullable=False)
    estado = Column(String(12), nullable=False)
    detalle = Column(String(80), nullable=True)
    reenvio = Column(
        Boolean, nullable=False, default=False,
        server_default=text("false"))
    solicitado_por = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
    )
