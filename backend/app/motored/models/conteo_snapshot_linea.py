"""
Motored inventory counts -- the frozen system side of a count
(odd/motored-conteos-inventario, WU2; design §4.2, §4.10, ADR-1).

Iniciar COPIES the store's latest inventory carga here, so later Maestros
uploads never change a running count. Owner override: the count is per
STORE, so there is ONE line per (conteo, referencia):

- `existencia` is the store's TOTAL system quantity (all of its own
  bodegas summed; can be negative, kept as exported);
- `existencia_por_bodega` is informative only (`{bodega_codigo: qty}`,
  for the adjustment Excel's columns);
- `costo_unitario` is the frozen unit cost used to value differences, and
  `costo_fuente` says where it came from (fallback chain in §4.10).
"""
import uuid

from sqlalchemy import (
    CheckConstraint, Column, ForeignKey, Numeric, String, UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase
from app.motored.models.conteo import lista_sql

COSTO_FUENTES = ("BODEGA", "REFERENCIA", "MEDIANA", "PRECIO", "SIN_COSTO")


class ConteoSnapshotLinea(MotoredBase):
    __tablename__ = "conteo_snapshot_linea"
    __table_args__ = (
        UniqueConstraint(
            "conteo_id", "referencia_id",
            name="uq_conteo_snapshot_linea_referencia"),
        CheckConstraint(
            f"costo_fuente IN {lista_sql(COSTO_FUENTES)}",
            name="ck_conteo_snapshot_linea_costo_fuente"),
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
        nullable=False,
    )
    existencia = Column(Numeric(14, 2), nullable=False)
    existencia_por_bodega = Column(
        JSONB, nullable=False, default=dict,
        server_default=text("'{}'::jsonb"))
    costo_unitario = Column(Numeric(16, 2), nullable=True)
    costo_fuente = Column(String(12), nullable=False)
