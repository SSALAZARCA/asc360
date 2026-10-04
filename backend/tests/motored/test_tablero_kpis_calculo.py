"""
KPI's (B3): calculos puros por tienda: acumuladores por mes y linea, Tecnired,
crecimiento 3M con meses de calendario y filas de tienda. Sin base de datos; las
consultas se prueban en `pg_real/test_tablero_kpis_pg.py`.
"""
import datetime
from decimal import Decimal as D

import pytest

from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_kpis as k
from app.motored.services.tablero_asesores_consultas import FilaVentana
from app.motored.services.tablero_asesores import FilaCubo, FilaFacturas, FilaClientes


def _cubo(clave, mes, linea, venta, *, tecnired=False, hmcl=False, costo=0, cant=1):
    return FilaCubo(clave, mes, linea, hmcl, tecnired, False, True, D(venta), D(venta), D(0), D(cant), 1, D(costo))


# --- Acumuladores por mes y linea ----------------------------------------------------------


def test_la_venta_por_mes_y_linea_cruza_los_dos_ejes():
    cubo = [
        _cubo("a", "2026-01", "REPUESTOS", 100), _cubo("a", "2026-01", "REPUESTOS", 50),
        _cubo("a", "2026-01", "GPS", 30), _cubo("a", "2026-03", "REPUESTOS", 7),
    ]
    acum, _ = t.acumular_cubo(cubo)

    venta = t.indicadores(acum["a"], None, None, ["2026-01", "2026-02", "2026-03"])["venta"]

    assert venta["por_mes_linea"]["2026-01"]["REPUESTOS"] == 150.0
    assert venta["por_mes_linea"]["2026-01"]["GPS"] == 30.0
    assert venta["por_mes_linea"]["2026-02"] == {linea: 0.0 for linea in t.LINEAS}  # a month without sales
    assert venta["por_mes_linea"]["2026-03"]["REPUESTOS"] == 7.0
    enero = venta["por_mes_linea"]["2026-01"]
    assert enero["GPS"] + enero["REPUESTOS"] == venta["por_mes"]["2026-01"]


def test_tecnired_se_acumula_por_mes_y_por_linea_sin_contar_a_los_demas():
    cubo = [
        _cubo("a", "2026-01", "REPUESTOS", 100, tecnired=True),
        _cubo("a", "2026-01", "GPS", 40),
        _cubo("a", "2026-02", "REPUESTOS", 10, tecnired=True),
        _cubo("a", "2026-02", "LLANTAS", 5, tecnired=True),
    ]
    acum, _ = t.acumular_cubo(cubo)

    c = t.indicadores(acum["a"], None, None, ["2026-01", "2026-02"])["clientes"]

    assert c["tecnired_por_mes"] == {"2026-01": 100.0, "2026-02": 15.0}
    assert c["tecnired_por_linea"]["REPUESTOS"] == 110.0 and c["tecnired_por_linea"]["LLANTAS"] == 5.0
    assert c["tecnired_por_linea"]["GPS"] == 0.0
    assert c["venta_tecnired"] == 115.0


def test_el_acumulado_total_suma_todas_las_claves_y_la_venta_sin_linea_se_aparta():
    cubo = [_cubo("a", "2026-01", "GPS", 10), _cubo("b", "2026-01", "GPS", 5), _cubo("b", "2026-01", None, 99)]

    acum, sin_linea = t.acumular_cubo(cubo)

    assert acum[t.CLAVE_TOTAL].venta == D(15) and sin_linea == D(99)
    assert set(acum) == {t.CLAVE_TOTAL, "a", "b"}


# --- Meses de calendario y crecimiento -------------------------------------------------------


@pytest.mark.parametrize("mes, n, esperado", [
    ("2026-03", -2, "2026-01"), ("2026-01", -1, "2025-12"), ("2026-01", -5, "2025-08"),
    ("2026-12", 1, "2027-01"), ("2026-06", 0, "2026-06"),
])
def test_mes_desplazado_cruza_el_cambio_de_anio(mes, n, esperado):
    assert t.mes_desplazado(mes, n) == esperado


def test_el_crecimiento_usa_meses_de_calendario_y_no_las_posiciones_de_la_seleccion():
    # Selection could be only 2026-06; the window still covers 2026-01..06.
    venta = {"2026-01": D(100), "2026-02": D(100), "2026-03": D(100),
             "2026-04": D(200), "2026-05": D(0), "2026-06": D(100)}

    c = t.crecimiento_3m(venta, "2026-06")

    assert (c["ultimos_3m"], c["previos_3m"], c["diferencia"]) == (300.0, 300.0, 0.0)
    assert c["pct"] == 0.0 and c["clasificacion"] == t.CAE  # equal = cae (<= 0)


def test_el_crecimiento_cruza_el_anio():
    venta = {"2025-10": D(100), "2025-11": D(100), "2025-12": D(100), "2026-01": D(300), "2026-02": D(0), "2026-03": D(0)}

    c = t.crecimiento_3m(venta, "2026-03")

    assert (c["ultimos_3m"], c["previos_3m"]) == (300.0, 300.0)
    c = t.crecimiento_3m({**venta, "2026-03": D(1)}, "2026-03")
    assert c["clasificacion"] == t.CRECE and c["pct"] == pytest.approx(301 / 300 - 1)


def test_meses_fuera_de_la_ventana_no_cuentan():
    venta = {"2025-12": D(9999), "2026-01": D(10), "2026-04": D(20), "2026-07": D(9999)}

    c = t.crecimiento_3m(venta, "2026-06")

    assert (c["ultimos_3m"], c["previos_3m"]) == (20.0, 10.0)


def test_una_tienda_sin_ventas_en_los_3_primeros_meses_es_nueva():
    c = t.crecimiento_3m({"2026-05": D(10), "2026-06": D(20)}, "2026-06")

    assert c["clasificacion"] == t.NUEVA and c["pct"] is None


def test_una_tienda_que_abrio_dentro_de_la_ventana_es_nueva_aunque_tenga_ventas_previas():
    venta = {"2026-01": D(10), "2026-04": D(50)}

    abierta = t.crecimiento_3m(venta, "2026-06", datetime.date(2026, 1, 1))  # first day of the window
    antes = t.crecimiento_3m(venta, "2026-06", datetime.date(2025, 12, 31))  # one day before
    sin_fecha = t.crecimiento_3m(venta, "2026-06", None)

    assert abierta["clasificacion"] == t.NUEVA
    assert antes["clasificacion"] == sin_fecha["clasificacion"] == t.CRECE


def test_una_tienda_sin_ninguna_venta_en_la_ventana_es_nueva():
    assert t.crecimiento_3m({}, "2026-06")["clasificacion"] == t.NUEVA


# --- Ventana y filas de tienda ----------------------------------------------------------------


def test_el_filtro_de_ventana_cubre_seis_meses_de_calendario_y_conserva_los_demas_filtros():
    filtro = t.filtro_de_meses(["2026-01", "2026-04"], t.HMCL_SOLO, {"s1"})

    ventana = k.filtro_de_ventana(filtro)

    assert ventana.rangos == ((datetime.date(2025, 11, 1), datetime.date(2026, 5, 1)),)
    assert (ventana.modo_hmcl, ventana.sucursal_ids, ventana.meses) == (t.HMCL_SOLO, frozenset({"s1"}), filtro.meses)


def test_la_ventana_aplica_el_modo_hmcl_en_python():
    filas = [
        _v("s1", "2026-01", False, 10), _v("s1", "2026-01", True, 90), _v("s1", "2026-02", False, 5),
    ]
    assert k.ventana_por_clave(filas, t.HMCL_INCLUIR)["s1"] == {"2026-01": D(100), "2026-02": D(5)}
    assert k.ventana_por_clave(filas, t.HMCL_EXCLUIR)["s1"] == {"2026-01": D(10), "2026-02": D(5)}
    assert k.ventana_por_clave(filas, t.HMCL_SOLO)["s1"] == {"2026-01": D(90)}


def _v(clave, mes, hmcl, venta):
    return FilaVentana(clave, mes, hmcl, D(venta))


def test_las_filas_de_tienda_traen_nombre_indicadores_y_crecimiento_ordenadas_por_venta():
    cubo = [
        _cubo("s1", "2026-06", "GPS", 100, costo=60), _cubo("s2", "2026-06", "REPUESTOS", 500),
        _cubo("s2", "2026-06", None, 7),
    ]
    sucursales = {"s1": ("Cali", None), "s2": ("Bogotá", datetime.date(2026, 5, 1))}
    ventana = {"s1": {"2026-01": D(10), "2026-06": D(100)}, "s2": {"2026-06": D(500)}}

    filas, sin_linea = k.construir_filas_sucursal(
        cubo, [FilaFacturas("s1", 4, 1, (0,) * 7)], [FilaClientes("s1", 3, D(80))], ventana, sucursales, ["2026-06"])

    assert [f["nombre"] for f in filas] == ["Bogotá", "Cali"] and sin_linea == D(7)
    cali = filas[1]
    assert cali["sucursal_id"] == "s1" and cali["venta"]["total"] == 100.0
    assert cali["costo"]["pct_margen"] == pytest.approx(0.4)
    assert cali["facturas"]["ticket_promedio"] == 25.0 and cali["clientes"]["clientes_unicos"] == 3
    assert "ranking" not in cali and "tendencia" not in cali
    assert cali["crecimiento"]["clasificacion"] == t.CRECE
    assert filas[0]["crecimiento"]["clasificacion"] == t.NUEVA  # opened inside the window
    assert k.resumen_crecimiento(filas) == {t.CRECE: 1, t.CAE: 0, t.NUEVA: 1}


def test_una_tienda_sin_nombre_conocido_usa_su_id():
    filas, _ = k.construir_filas_sucursal([_cubo("zzz", "2026-06", "GPS", 1)], [], [], {}, {}, ["2026-06"])

    assert filas[0]["nombre"] == "zzz"
