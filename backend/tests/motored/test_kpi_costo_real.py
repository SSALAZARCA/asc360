"""
KPI per-row cost rule with the real ERP sale cost (`venta_detalle.costo`).

The rule is one SQL expression shared by every margin / cost reader
(`tablero_asesores_consultas._expr_costo_fila`). It is evaluated here on
SQLite with literal operands so each branch is checked without Postgres:

- qty != 0 and costo not NULL and != 0 -> sign(qty) * |costo| (defensive sign);
- qty != 0 and costo NULL or 0 -> qty * unit fallback (negative for returns);
- qty == 0 -> costo as-is when present, else 0.
A row "has a cost" when it has a real cost or a unit fallback; the estimated
part is the cost of the rows priced by the fallback from `precio_normal`.
"""
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, literal_column, select

from app.motored.services import tablero_asesores_consultas as q


def _lit(valor):
    return literal_column("NULL" if valor is None else repr(valor))


@pytest.fixture(scope="module")
def motor():
    return create_engine("sqlite://")


def _evaluar(motor, expr_fabrica, cantidad, costo, unitario, fuente="inventario"):
    expr = expr_fabrica(_lit(cantidad), _lit(costo), _lit(unitario), literal_column(repr(fuente)))
    with motor.connect() as conexion:
        valor = conexion.execute(select(expr)).scalar_one()
    if valor is None or isinstance(valor, bool):
        return valor
    return Decimal(str(valor))


def _costo(motor, cantidad, costo, unitario):
    return _evaluar(
        motor, lambda c, k, u, f: q._expr_costo_fila(c, k, u), cantidad, costo, unitario)


@pytest.mark.parametrize("cantidad, costo, unitario, esperado", [
    # real cost wins; the sign always follows the quantity
    (2, 100.0, 7.0, 100),
    (-2, 100.0, 7.0, -100),      # return with a positive cost -> negative
    (2, -100.0, 7.0, 100),       # sale with a negative cost -> positive
    (-2, -100.0, 7.0, -100),
    # no real cost -> quantity x unit fallback (negative for returns)
    (3, None, 7.0, 21),
    (3, 0, 7.0, 21),
    (-3, None, 7.0, -21),
    (-3, 0, 7.0, -21),
    (3, None, None, 0),          # no fallback either: the line costs 0
    (-3, 0, None, 0),
    # qty == 0: the cost as-is when present, else 0
    (0, 55.0, 7.0, 55),
    (0, -55.0, 7.0, -55),
    (0, 0, 7.0, 0),
    (0, None, 7.0, 0),
])
def test_regla_de_costo_por_fila(motor, cantidad, costo, unitario, esperado):
    assert _costo(motor, cantidad, costo, unitario) == Decimal(esperado)


def test_los_pares_mas_menos_cero_se_netean(motor):
    venta = _costo(motor, 2, 100.0, 7.0)
    devolucion = _costo(motor, -2, 100.0, 7.0)
    anulada = _costo(motor, 0, 0, 7.0)

    assert venta + devolucion + anulada == 0
    assert _costo(motor, 3, None, 7.0) + _costo(motor, -3, None, 7.0) == 0


@pytest.mark.parametrize("cantidad, costo, unitario, esperado", [
    (2, 100.0, None, True),      # real cost, no fallback
    (2, None, 7.0, True),        # fallback only
    (2, None, None, False),      # neither: excluded from the margin
    (2, 0, None, False),
    (0, None, 7.0, True),
])
def test_una_linea_tiene_costo_si_trae_el_real_o_hay_respaldo(motor, cantidad, costo, unitario, esperado):
    valor = _evaluar(
        motor, lambda c, k, u, f: q._expr_con_costo(k, u), cantidad, costo, unitario)

    assert valor is esperado


@pytest.mark.parametrize("cantidad, costo, unitario, fuente, esperado", [
    (2, None, 7.0, "maestro", 14),       # fallback priced from precio_normal
    (-2, 0, 7.0, "maestro", -14),
    (2, None, 7.0, "inventario", 0),     # median inventory is not the estimate
    (2, 100.0, 7.0, "maestro", 0),       # real cost: never estimated
    (0, None, 7.0, "maestro", 0),
])
def test_el_costo_estimado_es_la_parte_valorada_con_precio_normal(
        motor, cantidad, costo, unitario, fuente, esperado):
    valor = _evaluar(
        motor, lambda c, k, u, f: q._expr_costo_estimado_fila(c, k, u, f),
        cantidad, costo, unitario, fuente)

    assert valor == Decimal(esperado)


# --- migration ---------------------------------------------------------------


def test_la_migracion_marca_los_resumenes_como_sucios():
    import importlib.util
    from pathlib import Path
    from unittest import mock

    ruta = (Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
            / "e5c9b3d8f024_kpi_costo_real_sucio.py")
    spec = importlib.util.spec_from_file_location("mig_costo_sucio", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    assert (modulo.revision, modulo.down_revision) == ("e5c9b3d8f024", "d2b7a94e5c61")
    with mock.patch.object(modulo, "op") as op_mock:
        modulo.upgrade()
    (llamada,) = op_mock.execute.call_args_list
    assert llamada.args[0] == "UPDATE kpi_resumen_estado SET sucio = true WHERE id = 1"
