"""
Motored inventory counts -- one referencia sent to reconteo
(odd/motored-conteos-inventario, WU3; design §4.6, §5.2, ADR-4).

`uq_conteo_reconteo_codigo_activo` allows one live reconteo per code and
count (cancelled ones are history). An ASIGNADO or TERMINADO reconteo has
its assignee session; the leader's "same pair" override always carries
its reason. `diferencia_ronda1`/`valor_ronda1` are leader-only.
"""
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Numeric,
    String, Text, func, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase
from app.motored.models.conteo import lista_sql

ESTADOS = ("PENDIENTE", "ASIGNADO", "TERMINADO", "CANCELADO")
ORIGENES = ("UMBRAL", "LIDER")
INDICE_ACTIVO = "uq_conteo_reconteo_codigo_activo"


class ConteoReconteo(MotoredBase):
    __tablename__ = "conteo_reconteo"
    __table_args__ = (
        CheckConstraint(
            f"estado IN {lista_sql(ESTADOS)}",
            name="ck_conteo_reconteo_estado"),
        CheckConstraint(
            f"origen IN {lista_sql(ORIGENES)}",
            name="ck_conteo_reconteo_origen"),
        CheckConstraint(
            "estado NOT IN ('ASIGNADO', 'TERMINADO') "
            "OR sesion_id IS NOT NULL",
            name="ck_conteo_reconteo_sesion_si_asignado"),
        CheckConstraint(
            "NOT misma_pareja_autorizada "
            "OR motivo_autorizacion IS NOT NULL",
            name="ck_conteo_reconteo_motivo_si_autorizada"),
        Index(
            INDICE_ACTIVO, "conteo_id", "codigo", unique=True,
            postgresql_where=text("estado <> 'CANCELADO'"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conteo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conteo.id", ondelete="CASCADE"),
        nullable=False,
    )
    referencia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("referencia.id", ondelete="RESTRICT"),
        nullable=True,
    )
    codigo = Column(String(100), nullable=False)
    estado = Column(String(10), nullable=False, default="PENDIENTE")
    origen = Column(String(8), nullable=False)
    diferencia_ronda1 = Column(Numeric(14, 2), nullable=True)
    valor_ronda1 = Column(Numeric(18, 2), nullable=True)
    sesion_id = Column(
        UUID(as_uuid=True), ForeignKey("conteo_sesion.id"), nullable=True)
    asignado_por = Column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
    misma_pareja_autorizada = Column(
        Boolean, nullable=False, default=False,
        server_default=text("false"))
    motivo_autorizacion = Column(Text, nullable=True)
    asignado_en = Column(DateTime(timezone=True), nullable=True)
    terminado_en = Column(DateTime(timezone=True), nullable=True)
    cancelado_en = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
