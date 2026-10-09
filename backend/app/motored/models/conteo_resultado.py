"""
Motored inventory counts -- the final line per referencia, written at
close (odd/motored-conteos-inventario, WU3; design §4.8, §7; read by the
adjustment Excel and stage 4).

Owner override: the count is per STORE, so there is ONE line per
(conteo, codigo) and the whole difference goes to the store's PRINCIPAL
bodega, `bodega_ajuste_id`. `sucursal_id` and `cerrado_en` are
denormalized for the history lookups. `valor_diferencia` is NULL when
the cost is SIN_COSTO; `diferencia` is always counted - system.
"""
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Numeric,
    String, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.motored.database import MotoredBase
from app.motored.models.conteo import lista_sql
from app.motored.models.conteo_snapshot_linea import COSTO_FUENTES


class ConteoResultado(MotoredBase):
    __tablename__ = "conteo_resultado"
    __table_args__ = (
        UniqueConstraint(
            "conteo_id", "codigo", name="uq_conteo_resultado_codigo"),
        CheckConstraint(
            f"costo_fuente IN {lista_sql(COSTO_FUENTES)}",
            name="ck_conteo_resultado_costo_fuente"),
        CheckConstraint(
            "diferencia = cantidad_contada - existencia_sistema",
            name="ck_conteo_resultado_diferencia"),
        Index(
            "ix_conteo_resultado_historial",
            "sucursal_id", "referencia_id", text("cerrado_en DESC"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conteo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conteo.id", ondelete="CASCADE"),
        nullable=False,
    )
    sucursal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sucursal.id", ondelete="RESTRICT"),
        nullable=False,
    )
    referencia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("referencia.id", ondelete="RESTRICT"),
        nullable=True,
    )
    codigo = Column(String(100), nullable=False)
    bodega_ajuste_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bodega.id", ondelete="RESTRICT"),
        nullable=False,
    )
    existencia_sistema = Column(Numeric(14, 2), nullable=False)
    cantidad_contada = Column(Numeric(14, 2), nullable=False)
    diferencia = Column(Numeric(14, 2), nullable=False)
    costo_unitario = Column(Numeric(16, 2), nullable=True)
    costo_fuente = Column(String(12), nullable=False)
    valor_diferencia = Column(Numeric(18, 2), nullable=True)
    ubicaciones = Column(
        ARRAY(String(60)), nullable=False, default=list,
        server_default=text("'{}'"))
    con_reconteo = Column(Boolean, nullable=False, default=False)
    critico = Column(Boolean, nullable=False, default=False)
    confirmada = Column(Boolean, nullable=True)
    cerrado_en = Column(DateTime(timezone=True), nullable=False)
