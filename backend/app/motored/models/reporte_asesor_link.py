"""
Motored -- the asesor's personal report link
(odd/motored-reporte-diario-asesor, T3a).

One secret, PERMANENT token per asesor (no month, no expiry). Lore sends the
URL `<MOTORED_PUBLIC_URL>/motored/informe/<token>`; whoever opens it must
also type the asesor's cédula to see the report. Rules:

- `uq_reporte_asesor_link_activo`: at most ONE active (not revoked) link
  per usuario. "Generar enlace nuevo" revokes the old one first.
- The link is revoked (never deleted) when the usuario is deactivated, its
  cédula changes or loses approval, or its Telegram changes
  (`services/reporte_asesor_link.py::revocar_si_cambio`).
- `intentos_fallidos`/`bloqueado_hasta` back the public endpoint's lock
  after wrong cédulas; `ultimo_acceso_en` is the last successful opening.

The token is a credential: it is never logged, audited or returned by any
ADMIN endpoint.
"""
import uuid

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint,
    func, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase

INDICE_ACTIVO = "uq_reporte_asesor_link_activo"


class ReporteAsesorLink(MotoredBase):
    __tablename__ = "reporte_asesor_link"
    __table_args__ = (
        UniqueConstraint("token", name="uq_reporte_asesor_link_token"),
        Index(
            INDICE_ACTIVO, "usuario_id",
            unique=True, postgresql_where=text("revocado_en IS NULL"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
    )
    cedula = Column(String(20), nullable=False)
    token = Column(String(64), nullable=False)
    creado_en = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    creado_por = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
    )
    revocado_en = Column(DateTime(timezone=True), nullable=True)
    motivo_revocacion = Column(String(40), nullable=True)
    ultimo_acceso_en = Column(DateTime(timezone=True), nullable=True)
    intentos_fallidos = Column(
        Integer, nullable=False, default=0, server_default=text("0"))
    bloqueado_hasta = Column(DateTime(timezone=True), nullable=True)
