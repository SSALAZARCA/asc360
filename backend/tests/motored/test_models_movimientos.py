"""
Phase 3 "Movement Schema + Shared Infra" (sdd/motored-pedidos-ingesta) —
model-structure tests, mirroring `test_models_ingesta.py`'s established
convention: models are schema, not behavior. No live DB, no service logic.

Covers the 6 new movement tables from design doc §Schema: `venta_mensual`,
`inventario_snapshot`, `backorder_linea`, `factura_proveedor_linea`,
`ingreso_factura`, `demanda_perdida` (migration `fase2_movimientos`).
"""
from sqlalchemy import UniqueConstraint

from app.motored.database import MotoredBase
from app.motored.models import (
    BackorderLinea,
    DemandaPerdida,
    FacturaProveedorLinea,
    IngresoFactura,
    InventarioSnapshot,
    VentaMensual,
)

_MOVEMENT_MODELS = (
    VentaMensual,
    InventarioSnapshot,
    BackorderLinea,
    FacturaProveedorLinea,
    IngresoFactura,
    DemandaPerdida,
)


def test_six_movement_tables_are_registered_on_motored_base():
    expected = {
        "venta_mensual",
        "inventario_snapshot",
        "backorder_linea",
        "factura_proveedor_linea",
        "ingreso_factura",
        "demanda_perdida",
    }
    assert expected.issubset(set(MotoredBase.metadata.tables.keys()))


def test_movement_models_do_not_use_asc360_base():
    from app.database import Base as Asc360Base

    for model in _MOVEMENT_MODELS:
        assert model.metadata is MotoredBase.metadata
        assert model.metadata is not Asc360Base.metadata


def test_every_movement_table_carries_carga_id():
    # design §Schema, closing note: "Every movement table carries `carga_id`."
    for model in _MOVEMENT_MODELS:
        assert "carga_id" in model.__table__.c
        assert model.__table__.c.carga_id.nullable is False


# ---------------------------------------------------------------------------
# venta_mensual (ADR-4)
# ---------------------------------------------------------------------------


def test_venta_mensual_has_unique_sucursal_referencia_anio_mes_origen():
    constraints = [c for c in VentaMensual.__table__.constraints if isinstance(c, UniqueConstraint)]
    match = [
        c for c in constraints
        if {col.name for col in c.columns} == {"sucursal_id", "referencia_id", "anio", "mes", "origen"}
    ]
    assert len(match) == 1


def test_venta_mensual_has_index_referencia_anio_mes():
    indexes = VentaMensual.__table__.indexes
    match = [ix for ix in indexes if {c.name for c in ix.columns} == {"referencia_id", "anio", "mes"}]
    assert len(match) == 1


def test_venta_mensual_unidades_is_signed_numeric():
    from sqlalchemy import Numeric

    col = VentaMensual.__table__.c.unidades
    assert isinstance(col.type, Numeric)
    assert col.nullable is False


# ---------------------------------------------------------------------------
# inventario_snapshot (ADR-3)
# ---------------------------------------------------------------------------


def test_inventario_snapshot_has_unique_fecha_corte_sucursal_referencia():
    constraints = [
        c for c in InventarioSnapshot.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    match = [
        c for c in constraints
        if {col.name for col in c.columns} == {"fecha_corte", "sucursal_id", "referencia_id"}
    ]
    assert len(match) == 1


def test_inventario_snapshot_has_index_fecha_corte():
    indexes = InventarioSnapshot.__table__.indexes
    match = [ix for ix in indexes if {c.name for c in ix.columns} == {"fecha_corte"}]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# backorder_linea
# ---------------------------------------------------------------------------


def test_backorder_linea_has_unique_fecha_corte_sucursal_referencia_pedido():
    constraints = [
        c for c in BackorderLinea.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    match = [
        c for c in constraints
        if {col.name for col in c.columns}
        == {"fecha_corte", "sucursal_id", "referencia_id", "numero_pedido"}
    ]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# factura_proveedor_linea / ingreso_factura (H3 — numero_rh is bigint)
# ---------------------------------------------------------------------------


def test_numero_rh_is_bigint_never_fixed_width_text():
    from sqlalchemy import BigInteger

    for model in (FacturaProveedorLinea, IngresoFactura):
        assert isinstance(model.__table__.c.numero_rh.type, BigInteger)


def test_factura_proveedor_linea_has_unique_rh_sucursal_referencia():
    constraints = [
        c for c in FacturaProveedorLinea.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    match = [
        c for c in constraints
        if {col.name for col in c.columns}
        == {"prefijo_rh", "numero_rh", "sucursal_id", "referencia_id"}
    ]
    assert len(match) == 1


def test_factura_proveedor_linea_has_index_prefijo_rh_numero_rh():
    indexes = FacturaProveedorLinea.__table__.indexes
    match = [ix for ix in indexes if {c.name for c in ix.columns} == {"prefijo_rh", "numero_rh"}]
    assert len(match) == 1


def test_factura_proveedor_linea_has_index_ingresada_transito_vencido():
    indexes = FacturaProveedorLinea.__table__.indexes
    match = [ix for ix in indexes if {c.name for c in ix.columns} == {"ingresada", "transito_vencido"}]
    assert len(match) == 1


def test_ingreso_factura_has_unique_prefijo_rh_numero_rh():
    # Phase 8 (migration `3956c0ebd69c`): document-level identity, not
    # line-level — the real file has no Sucursal/Parte columns at all.
    constraints = [
        c for c in IngresoFactura.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    match = [
        c for c in constraints if {col.name for col in c.columns} == {"prefijo_rh", "numero_rh"}
    ]
    assert len(match) == 1


def test_ingreso_factura_sucursal_referencia_are_nullable():
    # Phase 8: the source file carries no sucursal/parte dimension to
    # resolve — unlike NOT NULL on facturas_pedidos' line-level table.
    assert IngresoFactura.__table__.c.sucursal_id.nullable is True
    assert IngresoFactura.__table__.c.referencia_id.nullable is True


def test_ingreso_factura_has_valor_neto_not_cantidad():
    # Phase 8: this table is a financial document register (Valornetolocal),
    # not a parts register — `cantidad` was renamed to `valor_neto`.
    assert "valor_neto" in IngresoFactura.__table__.c
    assert "cantidad" not in IngresoFactura.__table__.c


def test_factura_proveedor_linea_has_valor_total_alongside_cantidad():
    # Phase 8: the tránsito cruce's ingreso_parcial_sospechoso needs a
    # comparable monetary figure — `cantidad` alone (units) isn't one.
    assert "cantidad" in FacturaProveedorLinea.__table__.c
    assert "valor_total" in FacturaProveedorLinea.__table__.c


def test_ingreso_factura_has_no_transito_flags():
    # Those three booleans live only on the factura side of the cruce.
    for name in ("transito_vencido", "ingreso_parcial_sospechoso", "ingresada"):
        assert name not in IngresoFactura.__table__.c


# ---------------------------------------------------------------------------
# demanda_perdida
# ---------------------------------------------------------------------------


def test_demanda_perdida_has_unique_fecha_sucursal_referencia_origen():
    # Widened by sdd/motored-ventas-perdidas-bot (design D2): BOT-origin rows
    # need their own key so they never collide with the EXCEL-origin row for
    # the same (fecha, sucursal_id, referencia_id).
    constraints = [
        c for c in DemandaPerdida.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    match = [
        c for c in constraints
        if {col.name for col in c.columns} == {"fecha", "sucursal_id", "referencia_id", "origen"}
    ]
    assert len(match) == 1
