"""
Motored -- precomputed KPI summary tables (odd/motored-kpis-resumenes, R1).

The KPI's tabs would otherwise scan `venta_detalle` (~1M rows) several times per
request. These tables hold the same aggregates at a coarser grain, rebuilt by
`services/kpi_resumen.py`. They only store dimensions that do NOT depend on
Configuracion (`vendedor_norm`, `linea_norm`, `nit_especial`); Configuracion
(lines, HMCL NITs, groups, semaforo) is applied when reading.

- `kpi_venta_mes`: one row per month, store, vendedor, line, special NIT,
  mostrador flag and with-cost flag, with the sale measures.
- `kpi_factura_firma`: invoices counted by their "line signature" (the sorted
  distinct lines the invoice carries), so the invoice percentages stay exact.
- `kpi_cliente_mes`: sale per client and line, to count distinct clients.
- `kpi_costo_referencia` / `kpi_inventario_corte`: unit cost per referencia and
  inventory at cost per store, from the latest inventory cut. A referencia with no
  positive inventory cost falls back to `referencia.precio_normal` (> 0), tagged
  `fuente = 'maestro'`; `costo_estimado` isolates that part of the sales cost.
- `kpi_resumen_estado`: the single bookkeeping row (dirty flag, timestamps).

Nullable key parts (`linea_norm`, `nit_especial`) are made unique with
`COALESCE(col, '')` expression indexes (a plain UNIQUE treats NULLs as distinct);
a real value is never the empty string (lines and NITs are non-empty by rule).
The leading (`anio_mes`, `sucursal_id`) of each unique index also serves the
period-and-store reads and the per-period refresh.

The tables are derived data: they are fully rebuildable from the raw tables.
"""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Identity, Index, Integer, Numeric,
    String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.motored.database import MotoredBase


class KpiVentaMes(MotoredBase):
    __tablename__ = "kpi_venta_mes"
    __table_args__ = (CheckConstraint("EXTRACT(DAY FROM anio_mes) = 1", name="ck_kpi_venta_mes_dia_1"),)

    id = Column(BigInteger, Identity(), primary_key=True)
    anio_mes = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id", ondelete="CASCADE"), nullable=False)
    vendedor_norm = Column(String(255), nullable=False)
    linea_norm = Column(Text, nullable=True)  # NULL = not a recognized line
    nit_especial = Column(Text, nullable=True)  # NULL = neither an HMCL NIT nor a Tecnired client
    es_mostrador = Column(Boolean, nullable=False)
    con_costo = Column(Boolean, nullable=False)
    venta = Column(Numeric(20, 2), nullable=False)
    bruto = Column(Numeric(20, 2), nullable=False)
    descuentos = Column(Numeric(20, 2), nullable=False)
    cantidad = Column(Numeric(20, 2), nullable=False)
    lineas = Column(Integer, nullable=False)
    costo = Column(Numeric(24, 6), nullable=False)
    costo_estimado = Column(Numeric(24, 6), nullable=False)  # the part of `costo` priced from the master


Index(
    "uq_kpi_venta_mes_llave", KpiVentaMes.anio_mes, KpiVentaMes.sucursal_id, KpiVentaMes.vendedor_norm,
    func.coalesce(KpiVentaMes.linea_norm, text("''")), func.coalesce(KpiVentaMes.nit_especial, text("''")),
    KpiVentaMes.es_mostrador, KpiVentaMes.con_costo, unique=True)


class KpiFacturaFirma(MotoredBase):
    __tablename__ = "kpi_factura_firma"
    __table_args__ = (CheckConstraint("EXTRACT(DAY FROM anio_mes) = 1", name="ck_kpi_factura_firma_dia_1"),)

    id = Column(BigInteger, Identity(), primary_key=True)
    anio_mes = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id", ondelete="CASCADE"), nullable=False)
    vendedor_norm = Column(String(255), nullable=False)
    nit_especial = Column(Text, nullable=True)
    firma = Column(ARRAY(Text), nullable=False)  # sorted distinct lines; empty = no recognized line
    n_facturas = Column(Integer, nullable=False)


Index(
    "uq_kpi_factura_firma_llave", KpiFacturaFirma.anio_mes, KpiFacturaFirma.sucursal_id,
    KpiFacturaFirma.vendedor_norm, func.coalesce(KpiFacturaFirma.nit_especial, text("''")),
    KpiFacturaFirma.firma, unique=True)


class KpiClienteMes(MotoredBase):
    __tablename__ = "kpi_cliente_mes"
    __table_args__ = (
        UniqueConstraint(
            "anio_mes", "sucursal_id", "vendedor_norm", "cliente_norm", "linea_norm",
            name="uq_kpi_cliente_mes_llave"),
        CheckConstraint("EXTRACT(DAY FROM anio_mes) = 1", name="ck_kpi_cliente_mes_dia_1"),
    )

    id = Column(BigInteger, Identity(), primary_key=True)
    anio_mes = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id", ondelete="CASCADE"), nullable=False)
    vendedor_norm = Column(String(255), nullable=False)
    cliente_norm = Column(Text, nullable=False)
    linea_norm = Column(Text, nullable=False)  # only recognized lines are stored
    venta = Column(Numeric(20, 2), nullable=False)


class KpiCostoReferencia(MotoredBase):
    __tablename__ = "kpi_costo_referencia"
    __table_args__ = (
        CheckConstraint("fuente IN ('inventario', 'maestro')", name="ck_kpi_costo_referencia_fuente"),)

    fecha_corte = Column(Date, primary_key=True)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id", ondelete="CASCADE"), primary_key=True)
    costo_unitario = Column(Numeric(18, 4), nullable=False)
    fuente = Column(Text, nullable=False)  # 'inventario' (median of the cut) | 'maestro' (precio_normal fallback)


class KpiInventarioCorte(MotoredBase):
    __tablename__ = "kpi_inventario_corte"

    fecha_corte = Column(Date, primary_key=True)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id", ondelete="CASCADE"), primary_key=True)
    valor = Column(Numeric(24, 4), nullable=False)
    lineas_sin_costo = Column(Integer, nullable=False)  # no cost from either source
    lineas_costo_maestro = Column(Integer, nullable=False)  # priced with precio_normal


class KpiResumenEstado(MotoredBase):
    __tablename__ = "kpi_resumen_estado"
    __table_args__ = (CheckConstraint("id = 1", name="ck_kpi_resumen_estado_fila_unica"),)

    id = Column(Integer, primary_key=True, default=1)
    sucio = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    reconstruyendo = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    actualizado_en = Column(DateTime(timezone=True), nullable=True)
    ultima_reconstruccion_total = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=0, server_default=text("0"))
