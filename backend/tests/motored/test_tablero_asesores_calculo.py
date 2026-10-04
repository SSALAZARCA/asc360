"""
Tablero de asesores (feature motored-tablero-asesores, T4): calculos PUROS.

Aqui no hay base de datos: se arman a mano las filas agregadas que devuelve la
consulta (cubo por mes/linea/banderas, facturas, clientes, personas) y se
comprueba cada indicador contra valores calculados a mano. La consulta SQL real
se prueba en `pg_real/test_tablero_asesores_pg.py`.
"""
from decimal import Decimal as D

import pytest

from app.motored.services import tablero_asesores as t
from app.motored.services.tablero_asesores import (
    FilaCubo,
    FilaClientes,
    FilaFacturas,
    FilaPersona,
)


# --- Linea comercial -------------------------------------------------------------------------


@pytest.mark.parametrize("crudo, esperado", [
    ("REPUESTOS", "REPUESTOS"),
    ("  repuestos ", "REPUESTOS"),
    ("Baterías", "BATERIAS"),
    ("Cascos", "CASCOS"),
    ("NO APLICA", None),
    ("MOTOS", None),
    ("", None),
    (None, None),
])
def test_normalizar_linea_solo_acepta_las_7_lineas(crudo, esperado):
    assert t.normalizar_linea(crudo) == esperado


def test_son_exactamente_siete_lineas():
    assert t.LINEAS == ("REPUESTOS", "ACCESORIOS", "LLANTAS", "LUBRICANTES", "BATERIAS", "GPS", "CASCOS")


# --- Grupo de la fila ------------------------------------------------------------------------


@pytest.mark.parametrize("cargo, esperado", [
    ("ASESOR DE REPUESTOS", t.TIPO_PERSONA),
    ("ASESOR DE REPUESTOS SUPERNUMERARIO", t.TIPO_PERSONA),
    ("ASESOR COMERCIAL DE SERVICIO POSVENTA", t.GRUPO_COMERCIALES),
    ("JEFE DE TALLER", t.GRUPO_OTROS),
    ("", t.GRUPO_OTROS),
])
def test_grupo_de_un_cargo_registrado(cargo, esperado):
    assert t.grupo_de_cargo(cargo) == esperado


def test_el_mapa_cargo_grupo_vive_en_una_sola_constante():
    assert set(t.GRUPO_POR_CARGO.values()) == {t.TIPO_PERSONA, t.GRUPO_COMERCIALES}


def test_clave_de_persona_lleva_el_id():
    assert t.clave_persona("abc") == "P:abc"
    assert t.es_clave_persona("P:abc") and not t.es_clave_persona(t.GRUPO_RESTO)


# --- Rango de meses --------------------------------------------------------------------------


def test_meses_del_rango_cruza_el_fin_de_anio():
    assert t.meses_del_rango("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_rango_valido_de_un_mes_y_de_doce():
    assert t.validar_rango("2026-03", "2026-03") == ["2026-03"]
    assert len(t.validar_rango("2025-10", "2026-09")) == 12


@pytest.mark.parametrize("desde, hasta", [("2026-05", "2026-04"), ("2025-09", "2026-09")])
def test_rango_invertido_o_mayor_a_12_meses_se_rechaza(desde, hasta):
    with pytest.raises(ValueError):
        t.validar_rango(desde, hasta)


def test_fin_exclusivo_es_el_primer_dia_del_mes_siguiente():
    import datetime
    assert t.limites_de_fecha("2026-12", "2026-12") == (datetime.date(2026, 12, 1), datetime.date(2027, 1, 1))


# --- Razones y tendencia ---------------------------------------------------------------------


def test_ratio_con_denominador_cero_o_nulo_es_none():
    assert t.ratio(D(5), D(0)) is None
    assert t.ratio(D(5), None) is None
    assert t.ratio(D(1), D(4)) == 0.25
    assert t.ratio(D(0), D(4)) == 0.0


def test_var_3m_necesita_al_menos_seis_meses():
    meses = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    assert t.variacion_3m({m: D(100) for m in meses}, meses) == t.TENDENCIA_VACIA


def test_var_3m_compara_los_ultimos_3_contra_los_3_anteriores():
    meses = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
    venta = {"2026-01": D(9999), "2026-02": D(100), "2026-03": D(100), "2026-04": D(100),
             "2026-05": D(150), "2026-06": D(150), "2026-07": D(150)}

    r = t.variacion_3m(venta, meses)

    assert r == {"ultimos_3m": 450.0, "previos_3m": 300.0, "diferencia": 150.0, "pct": 0.5}


def test_var_3m_con_meses_sin_venta_cuenta_cero_y_previos_cero_da_pct_none():
    meses = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

    r = t.variacion_3m({"2026-05": D(10), "2026-06": D(20)}, meses)

    assert r == {"ultimos_3m": 30.0, "previos_3m": 0.0, "diferencia": 30.0, "pct": None}


# --- Ranking ---------------------------------------------------------------------------------


def test_rankear_empates_comparten_posicion_y_el_siguiente_salta():
    r = t.rankear({"a": D(10), "b": D(30), "c": D(30), "d": D(5)})

    assert r == {"b": 1, "c": 1, "a": 3, "d": 4}


# --- Tablero completo ------------------------------------------------------------------------

MESES = ["2026-08", "2026-09"]
A, B = t.clave_persona("a"), t.clave_persona("b")


def _f(clave, mes, linea, venta, bruto, desc, cant, lineas, costo, hmcl=False, tec=False, mostr=False, con_costo=True):
    return FilaCubo(clave, mes, linea, hmcl, tec, mostr, con_costo, D(venta), D(bruto), D(desc), D(cant), lineas, D(costo))


CUBO = [
    _f(A, "2026-08", "REPUESTOS", 1000, 1100, 100, 5, 4, 600, mostr=True),
    _f(A, "2026-09", "REPUESTOS", 2000, 2300, 300, 6, 3, 1200, hmcl=True),
    _f(A, "2026-09", "LLANTAS", 500, 500, 0, 1, 1, 0, tec=True, con_costo=False),
    _f(A, "2026-09", None, 700, 700, 0, 1, 1, 0, con_costo=False),  # linea no reconocida: se excluye
    _f(B, "2026-08", "ACCESORIOS", 3000, 3000, 0, 10, 5, 2000, mostr=True),
    _f(B, "2026-09", "REPUESTOS", 1500, 1600, 100, 1, 1, 900, mostr=True),
    _f(t.GRUPO_RESTO, "2026-09", "LUBRICANTES", 400, 400, 0, 2, 2, 100),
]
FACTURAS = [
    FilaFacturas(A, 4, 1, (3, 0, 1, 0, 0, 0, 0)),
    FilaFacturas(t.CLAVE_TOTAL, 9, 3, (5, 4, 1, 1, 0, 0, 0)),
]
CLIENTES = [FilaClientes(A, 3, D(3000)), FilaClientes(t.CLAVE_TOTAL, 8, D(7000))]
PERSONAS = [
    FilaPersona(A, 1, "Ana Pérez", "ASESOR DE REPUESTOS", "CALI NORTE", ("ASESOR DE REPUESTOS",)),
    FilaPersona(B, 1, "Beto Ruiz", "ASESOR DE REPUESTOS SUPERNUMERARIO", "BOGOTA"),
    FilaPersona(t.GRUPO_RESTO, 3, None, None, None),
]


@pytest.fixture(scope="module")
def tablero():
    return t.construir_tablero(CUBO, FACTURAS, CLIENTES, PERSONAS, MESES)


def _fila(tablero, clave):
    return next(f for f in tablero["filas"] if f["clave"] == clave)


def test_las_personas_van_primero_ordenadas_por_punto_de_venta_y_luego_los_grupos(tablero):
    assert [f["clave"] for f in tablero["filas"]] == [B, A, t.GRUPO_RESTO]
    assert [f["tipo"] for f in tablero["filas"]] == ["PERSONA", "PERSONA", "GRUPO"]
    assert tablero["total"]["tipo"] == "TOTAL" and tablero["total"]["nombre"] == "TOTAL"


def test_la_persona_trae_nombre_cargo_y_punto_de_venta(tablero):
    a = _fila(tablero, A)
    assert (a["nombre"], a["cargo"], a["punto_venta"]) == ("Ana Pérez", "ASESOR DE REPUESTOS", "CALI NORTE")


def test_el_grupo_resto_cuenta_vendedores_en_el_nombre(tablero):
    assert _fila(tablero, t.GRUPO_RESTO)["nombre"] == "RESTO COMPAÑÍA (3 vendedores)"


def test_nombres_de_los_grupos_consolidados():
    assert t.nombre_de_grupo(t.GRUPO_COMERCIALES, 5) == "ASESORES COMERCIALES DE SERVICIO POSVENTA (5 personas)"
    assert t.nombre_de_grupo(t.GRUPO_OTROS, 1) == "OTROS ROLES POSVENTA (1 persona)"
    assert t.nombre_de_grupo(t.GRUPO_RESTO, 1) == "RESTO COMPAÑÍA (1 vendedor)"


def test_venta_hmcl_mensual_y_por_linea(tablero):
    v = _fila(tablero, A)["venta"]
    assert v["total"] == 3500.0
    assert v["hmcl"] == 2000.0 and v["sin_hmcl"] == 1500.0
    assert v["pct_hmcl"] == pytest.approx(2000 / 3500)
    assert v["por_mes"] == {"2026-08": 1000.0, "2026-09": 2500.0}
    assert v["por_linea"]["REPUESTOS"] == 3000.0 and v["por_linea"]["LLANTAS"] == 500.0
    assert v["por_linea"]["GPS"] == 0.0
    assert v["mix"]["REPUESTOS"] == pytest.approx(3000 / 3500)


def test_costo_utilidad_y_margen_solo_sobre_las_lineas_con_costo(tablero):
    c = _fila(tablero, A)["costo"]
    assert c["costo_venta"] == 1800.0
    assert c["venta_con_costo"] == 3000.0
    assert c["utilidad_bruta"] == 1200.0
    assert c["pct_margen"] == 0.4
    assert c["pct_venta_con_costo"] == pytest.approx(3000 / 3500)


def test_facturas_ticket_items_y_multilinea(tablero):
    f = _fila(tablero, A)["facturas"]
    assert f["facturas"] == 4
    assert f["ticket_promedio"] == 875.0
    assert f["unidades"] == 12.0
    assert f["items_por_factura"] == 2.0
    assert f["pct_con_linea"]["REPUESTOS"] == 0.75 and f["pct_con_linea"]["LLANTAS"] == 0.25
    assert f["pct_con_linea"]["CASCOS"] == 0.0
    assert f["pct_multilinea"] == 0.25


def test_descuentos_mes_mayor_y_porcentaje(tablero):
    d = _fila(tablero, A)["descuentos"]
    assert d["total"] == 400.0
    assert d["mes_mayor"] == "2026-09"
    assert d["pct_en_mes_mayor"] == 0.75
    assert d["pct_descuento"] == pytest.approx(400 / 3900)


def test_canal_tecnired_y_clientes(tablero):
    c = _fila(tablero, A)["clientes"]
    assert c["pct_mostrador"] == pytest.approx(1000 / 3500)
    assert c["venta_tecnired"] == 500.0 and c["pct_tecnired"] == pytest.approx(500 / 3500)
    assert c["clientes_unicos"] == 3
    assert c["pct_top5"] == pytest.approx(3000 / 3500)


def test_una_fila_sin_facturas_ni_clientes_da_none_y_no_divide_por_cero(tablero):
    b = _fila(tablero, B)
    assert b["facturas"]["facturas"] == 0
    assert b["facturas"]["ticket_promedio"] is None
    assert b["facturas"]["pct_multilinea"] is None
    assert b["clientes"]["clientes_unicos"] == 0 and b["clientes"]["pct_top5"] is None


def test_una_fila_sin_descuento_no_tiene_mes_mayor(tablero):
    d = _fila(tablero, B)["descuentos"]
    assert d["total"] == 100.0 and d["mes_mayor"] == "2026-09" and d["pct_en_mes_mayor"] == 1.0
    sin = _fila(tablero, t.GRUPO_RESTO)["descuentos"]
    assert sin["total"] == 0.0 and sin["mes_mayor"] is None and sin["pct_en_mes_mayor"] is None


def test_el_total_suma_todo_menos_la_venta_sin_linea(tablero):
    total = tablero["total"]
    assert total["venta"]["total"] == 8400.0
    assert total["facturas"]["facturas"] == 9
    assert total["clientes"]["clientes_unicos"] == 8
    assert total["ranking"] is None


def test_la_venta_sin_linea_reconocida_se_informa_aparte(tablero):
    assert tablero["venta_sin_linea"] == 700.0
    assert tablero["pct_venta_sin_linea"] == pytest.approx(700 / 9100)


def test_ranking_solo_entre_personas(tablero):
    a, b = _fila(tablero, A)["ranking"], _fila(tablero, B)["ranking"]
    assert a["indice_vs_promedio"] == pytest.approx(3500 / 4000)
    assert b["indice_vs_promedio"] == pytest.approx(4500 / 4000)
    assert (a["rank_total"], b["rank_total"]) == (2, 1)
    assert (a["rank_repuestos"], b["rank_repuestos"]) == (1, 2)
    assert (a["rank_accesorios"], b["rank_accesorios"]) == (2, 1)
    assert (a["rank_lubricantes"], b["rank_lubricantes"]) == (1, 1)
    assert _fila(tablero, t.GRUPO_RESTO)["ranking"] is None


def test_tablero_vacio_no_revienta():
    r = t.construir_tablero([], [], [], [], MESES)

    assert r["filas"] == [] and r["total"]["venta"]["total"] == 0.0
    assert r["total"]["venta"]["pct_hmcl"] is None
    assert r["venta_sin_linea"] == 0.0 and r["pct_venta_sin_linea"] is None


# --- Una persona con varios nombres del ERP (misma cedula) -----------------------------------


def _v(clave, identidad, nombre, cargo, punto, venta):
    return t.FilaVendedorVenta(clave, identidad, nombre, cargo, punto, D(venta))


def test_la_identidad_de_una_persona_con_cedula_es_la_cedula_y_sin_ella_el_vendedor():
    assert t.identidad_de_vendedor("55", "vend-1") == "55"
    assert t.identidad_de_vendedor("  55 ", "vend-1") == "55"
    assert t.identidad_de_vendedor(None, "vend-1") == "vend-1"
    assert t.identidad_de_vendedor("   ", "vend-1") == "vend-1"


def test_personas_dos_nombres_de_una_cedula_son_una_fila_con_el_nombre_de_mas_ventas():
    clave = t.clave_persona("55")
    personas = t.construir_personas([
        _v(clave, "55", "MORA DIANA PATRICIA", "ASESOR DE REPUESTOS", "CALI", 1400),
        _v(clave, "55", "MORA BUSTOS DIANA PATRICIA", "ASESOR DE REPUESTOS SUPERNUMERARIO", "BOGOTA", 2800),
    ])

    [fila] = personas
    assert fila.clave == clave and fila.personas == 1
    assert fila.nombre == "MORA BUSTOS DIANA PATRICIA"
    # Cargo y punto de venta salen de ESA misma fila, no de la otra.
    assert (fila.cargo, fila.punto_venta) == ("ASESOR DE REPUESTOS SUPERNUMERARIO", "BOGOTA")
    assert fila.cargos == ("ASESOR DE REPUESTOS", "ASESOR DE REPUESTOS SUPERNUMERARIO")


def test_personas_empate_de_ventas_se_resuelve_por_nombre_alfabetico():
    clave = t.clave_persona("55")

    [fila] = t.construir_personas([
        _v(clave, "55", "ZETA", "X", "A", 100), _v(clave, "55", "ALFA", "X", "B", 100)])

    assert (fila.nombre, fila.punto_venta) == ("ALFA", "B")
    assert fila.cargos == ("X",)


def test_personas_un_grupo_cuenta_personas_distintas_no_nombres_del_erp():
    personas = t.construir_personas([
        _v(t.GRUPO_COMERCIALES, "77", "BETO", "ASESOR COMERCIAL DE SERVICIO POSVENTA", None, 10),
        _v(t.GRUPO_COMERCIALES, "77", "BETO ALIAS", "ASESOR COMERCIAL DE SERVICIO POSVENTA", None, 10),
        _v(t.GRUPO_COMERCIALES, "vend-9", "GINA", "ASESOR COMERCIAL DE SERVICIO POSVENTA", None, 10),
        _v(t.GRUPO_RESTO, "EVA", None, None, None, 5),
        _v(t.GRUPO_RESTO, "OTRA", None, None, None, 5),
    ])

    por_clave = {f.clave: f for f in personas}
    assert por_clave[t.GRUPO_COMERCIALES].personas == 2
    assert por_clave[t.GRUPO_RESTO].personas == 2


def test_el_tablero_marca_el_conflicto_de_cargos_de_una_persona():
    clave = t.clave_persona("55")
    cubo = [_f(clave, "2026-08", "REPUESTOS", 100, 100, 0, 1, 1, 0)]
    personas = t.construir_personas([
        _v(clave, "55", "A", "ASESOR DE REPUESTOS", "CALI", 40),
        _v(clave, "55", "B", "ASESOR DE REPUESTOS SUPERNUMERARIO", "CALI", 60),
    ])

    tablero = t.construir_tablero(cubo, [], [], personas, ["2026-08"])

    [fila] = tablero["filas"]
    assert fila["cargo"] == "ASESOR DE REPUESTOS SUPERNUMERARIO"
    assert fila["cargos"] == ["ASESOR DE REPUESTOS", "ASESOR DE REPUESTOS SUPERNUMERARIO"]
    assert fila["cargo_conflicto"] is True


def test_el_tablero_no_marca_conflicto_con_un_solo_cargo(tablero):
    a = _fila(tablero, A)
    assert a["cargo_conflicto"] is False and a["cargos"] == ["ASESOR DE REPUESTOS"]


# --- Reglas de Configuracion -----------------------------------------------------------------


def test_las_reglas_por_defecto_son_las_constantes_historicas():
    r = t.REGLAS_POR_DEFECTO
    assert r.lineas == t.LINEAS and r.hmcl_nits == t.HMCL_NITS
    assert r.grupo_por_cargo == t.GRUPO_POR_CARGO
    assert r.semaforo == {"verde_desde": 90, "ambar_desde": 70}
    assert r.cumplimiento_base == "con_hmcl"


def test_normalizar_linea_usa_la_lista_de_lineas_recibida():
    assert t.normalizar_linea("gps", ("GPS", "CASCOS")) == "GPS"
    assert t.normalizar_linea("repuestos", ("GPS", "CASCOS")) is None


def test_grupo_de_cargo_usa_el_mapa_recibido():
    mapa = {"JEFE DE TALLER": t.TIPO_PERSONA}
    assert t.grupo_de_cargo("JEFE DE TALLER", mapa) == t.TIPO_PERSONA
    assert t.grupo_de_cargo("ASESOR DE REPUESTOS", mapa) == t.GRUPO_OTROS


def test_una_lista_de_lineas_reducida_cambia_los_indicadores():
    reglas = t.Reglas(lineas=("REPUESTOS", "ACCESORIOS"))

    r = t.construir_tablero(CUBO, FACTURAS, CLIENTES, PERSONAS, MESES, reglas)

    a = _fila(r, A)
    assert list(a["venta"]["por_linea"]) == ["REPUESTOS", "ACCESORIOS"]
    assert a["venta"]["total"] == 3000.0  # LLANTAS (500) sale del total de Ana
    assert list(a["facturas"]["pct_con_linea"]) == ["REPUESTOS", "ACCESORIOS"]
    # La venta de LLANTAS y LUBRICANTES, ya fuera de las lineas, se informa aparte.
    assert r["venta_sin_linea"] == 700.0 + 500.0 + 400.0
    # El ranking por LUBRICANTES no revienta cuando la linea no esta configurada.
    assert a["ranking"]["rank_lubricantes"] == 1


def test_sin_reglas_el_resultado_es_el_de_siempre(tablero):
    assert t.construir_tablero(CUBO, FACTURAS, CLIENTES, PERSONAS, MESES, t.REGLAS_POR_DEFECTO) == tablero
