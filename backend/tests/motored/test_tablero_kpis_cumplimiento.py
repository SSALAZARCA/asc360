"""
KPI's (B4): matematica pura del cumplimiento del presupuesto por asesor, tienda y
red. Sin base de datos; la lectura de presupuestos y ventas esta en
`pg_real/test_tablero_kpis_cumplimiento_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal as D

import pytest

from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_kpis as k
from app.motored.services.presupuestos import LineaPresupuesto
from app.motored.services.tablero_asesores import FilaCubo

S1, S2 = uuid.uuid4(), uuid.uuid4()
SUCURSALES = {str(S1): ("Norte", None), str(S2): ("Sur", None)}


def _venta(cedula, mes, monto, *, hmcl=False, linea="REPUESTOS", clave=None):
    return FilaCubo(
        clave or f"P:{cedula}", mes, linea, hmcl, False, False, True, D(monto), D(monto), D(0), D(1), 1, D(0))


def _pres(mes, cedula, tienda, monto):
    return (mes, cedula), LineaPresupuesto(tienda, monto)


def _calcular(cubo, lineas_presupuesto, reglas=t.REGLAS_POR_DEFECTO, **extra):
    return k.construir_cumplimiento(cubo, dict(lineas_presupuesto), reglas, sucursales=SUCURSALES, **extra)


def _asesor(resultado, cedula):
    return next(f for f in resultado["asesores"] if f["cedula"] == cedula)


# --- Semaforo ---------------------------------------------------------------------------------


@pytest.mark.parametrize("venta, esperado", [
    (90, k.VERDE), (89.99, k.AMBAR), (70, k.AMBAR), (69.99, k.VIOLETA), (0, k.VIOLETA), (150, k.VERDE),
])
def test_el_semaforo_usa_los_cortes_por_defecto_inclusivos(venta, esperado):
    assert k.semaforo_de(D(str(venta)), 100, t.SEMAFORO_POR_DEFECTO) == esperado


def test_el_semaforo_sigue_los_cortes_de_configuracion():
    cortes = {"verde_desde": 95, "ambar_desde": 60}

    assert [k.semaforo_de(D(v), 100, cortes) for v in (95, 94, 60, 59)] == [k.VERDE, k.AMBAR, k.AMBAR, k.VIOLETA]


def test_el_semaforo_no_cae_en_errores_de_coma_flotante():
    # 29 / 100 * 100 is 28.999999999999996 in floating point.
    assert k.semaforo_de(D(29), 100, {"verde_desde": 29, "ambar_desde": 10}) == k.VERDE


def test_sin_presupuesto_no_hay_semaforo():
    assert k.semaforo_de(D(500), 0, t.SEMAFORO_POR_DEFECTO) is None


# --- Asesores ---------------------------------------------------------------------------------


def test_solo_cuentan_los_meses_con_presupuesto_del_asesor():
    cubo = [_venta("100", "2026-01", 500), _venta("100", "2026-02", 400), _venta("100", "2026-03", 9999)]
    presupuestos = [_pres("2026-01", "100", S1, 600), _pres("2026-02", "100", S1, 400)]

    ana = _asesor(_calcular(cubo, presupuestos), "100")

    assert (ana["presupuesto"], ana["venta_cumplimiento"], ana["meses_con_presupuesto"]) == (1000, 900.0, 2)
    assert ana["cumplimiento_pct"] == pytest.approx(0.9)
    assert (ana["semaforo"], ana["estado"], ana["cumple"]) == (k.VERDE, k.CUMPLE, True)


def test_un_asesor_con_presupuesto_y_sin_ventas_aparece_con_cero():
    r = _calcular([], [_pres("2026-01", "300", S2, 500)], nombres={"300": "Cami Pérez"})

    cami = _asesor(r, "300")

    assert (cami["nombre"], cami["venta_cumplimiento"], cami["cumplimiento_pct"]) == ("Cami Pérez", 0.0, 0.0)
    assert (cami["semaforo"], cami["estado"], cami["cumple"]) == (k.VIOLETA, k.ATRASADO, False)
    assert cami["clave"] == "P:300" and cami["sucursal_id"] == str(S2)


def test_quien_vendio_sin_presupuesto_queda_sin_presupuesto_y_no_cumple():
    r = _calcular([_venta("400", "2026-01", 50)], [_pres("2026-01", "100", S1, 100)])

    eli = _asesor(r, "400")

    assert (eli["estado"], eli["semaforo"]) == (k.SIN_PRESUPUESTO, None)
    assert (eli["cumplimiento_pct"], eli["cumple"]) == (None, False)
    assert (eli["presupuesto"], eli["meses_con_presupuesto"], eli["sucursal_id"]) == (0, 0, None)
    assert r["conteos"]["asesores"] == {k.VERDE: 0, k.AMBAR: 0, k.VIOLETA: 1, k.SIN_PRESUPUESTO: 1}


def test_las_personas_sin_cedula_valida_no_cruzan_y_se_cuentan_en_las_advertencias():
    cubo = [
        _venta("", "2026-01", 70, clave="P:7f3c9a10-aaaa-bbbb-cccc-000000000001"),
        _venta("", "2026-02", 30, clave="P:7f3c9a10-aaaa-bbbb-cccc-000000000001"),
        _venta("", "2026-01", 5, clave="P:JUAN SIN CEDULA"),
        _venta("100", "2026-01", 10),
    ]

    r = _calcular(cubo, [_pres("2026-01", "100", S1, 100)], nombres_por_clave={"P:JUAN SIN CEDULA": "Juan"})

    assert r["advertencias"] == {"personas_sin_cedula": 2, "venta_sin_cedula": 105.0}
    sin = [f for f in r["asesores"] if f["cedula"] is None]
    assert {f["estado"] for f in sin} == {k.SIN_PRESUPUESTO} and len(sin) == 2
    assert next(f["nombre"] for f in sin if f["clave"] == "P:JUAN SIN CEDULA") == "Juan"


def test_la_cedula_con_puntos_o_decimal_cruza_con_el_presupuesto():
    cubo = [_venta("1.130.123.456", "2026-01", 80), _venta("200.0", "2026-01", 40)]
    presupuestos = [_pres("2026-01", "1130123456", S1, 100), _pres("2026-01", "200", S1, 100)]

    r = _calcular(cubo, presupuestos)

    assert _asesor(r, "1130123456")["venta_cumplimiento"] == 80.0
    assert _asesor(r, "200")["venta_cumplimiento"] == 40.0
    assert _asesor(r, "200")["clave"] == "P:200.0"  # the row of the tablero keeps its own key
    assert r["advertencias"]["personas_sin_cedula"] == 0


def test_dos_claves_con_la_misma_cedula_limpia_se_suman():
    cubo = [_venta("200", "2026-01", 30), _venta("200.0", "2026-01", 20)]

    r = _calcular(cubo, [_pres("2026-01", "200", S1, 100)])

    assert _asesor(r, "200")["venta_cumplimiento"] == 50.0 and len([f for f in r["asesores"]]) == 1


def test_con_base_sin_hmcl_se_descuenta_la_venta_a_clientes_hmcl():
    cubo = [_venta("100", "2026-01", 600), _venta("100", "2026-01", 400, hmcl=True)]
    presupuestos = [_pres("2026-01", "100", S1, 1000)]

    con = _asesor(_calcular(cubo, presupuestos), "100")
    sin = _asesor(_calcular(cubo, presupuestos, t.Reglas(cumplimiento_base=t.CUMPLIMIENTO_SIN_HMCL)), "100")

    assert (con["venta_cumplimiento"], con["semaforo"]) == (1000.0, k.VERDE)
    assert (sin["venta_cumplimiento"], sin["semaforo"]) == (600.0, k.VIOLETA)


def test_los_cortes_del_semaforo_salen_de_las_reglas():
    cubo = [_venta("100", "2026-01", 92)]
    presupuestos = [_pres("2026-01", "100", S1, 100)]

    exigente = _asesor(_calcular(cubo, presupuestos, t.Reglas(semaforo={"verde_desde": 95, "ambar_desde": 60})), "100")

    assert (exigente["semaforo"], exigente["cumple"]) == (k.AMBAR, False)


def test_solo_cuentan_las_personas_y_las_lineas_comerciales():
    cubo = [
        _venta("100", "2026-01", 10),
        _venta("100", "2026-01", 999, linea=None),
        _venta("100", "2026-01", 999, linea="MOTOS"),
        _venta("", "2026-01", 999, clave=t.GRUPO_COMERCIALES),
        _venta("", "2026-01", 999, clave=t.GRUPO_RESTO),
    ]

    r = _calcular(cubo, [_pres("2026-01", "100", S1, 100)])

    assert _asesor(r, "100")["venta_cumplimiento"] == 10.0 and r["advertencias"]["personas_sin_cedula"] == 0


# --- Tiendas y red ----------------------------------------------------------------------------


def test_la_venta_de_un_asesor_reasignado_cuenta_para_la_tienda_de_cada_mes():
    cubo = [
        _venta("100", "2026-01", 300), _venta("100", "2026-02", 500),
        _venta("200", "2026-01", 100),
    ]
    presupuestos = [
        _pres("2026-01", "100", S1, 400), _pres("2026-02", "100", S2, 500),  # Ana moves from Norte to Sur
        _pres("2026-01", "200", S1, 100),
    ]

    r = _calcular(cubo, presupuestos)

    norte, sur = r["tiendas"]
    assert (norte["nombre"], norte["presupuesto"], norte["venta_cumplimiento"]) == ("Norte", 500, 400.0)
    assert (sur["nombre"], sur["presupuesto"], sur["venta_cumplimiento"]) == ("Sur", 500, 500.0)
    assert norte["cumplimiento_pct"] == pytest.approx(0.8) and norte["semaforo"] == k.AMBAR
    assert sur["cumplimiento_pct"] == pytest.approx(1.0) and sur["cumple"] is True
    assert norte["asesores_con_presupuesto"] == 2 and sur["asesores_con_presupuesto"] == 1
    assert _asesor(r, "100")["sucursal_id"] == str(S2)  # the store of its latest budget month


def test_la_red_suma_las_tiendas_y_los_conteos_por_semaforo():
    cubo = [_venta("100", "2026-01", 100), _venta("200", "2026-01", 10), _venta("300", "2026-01", 75)]
    presupuestos = [
        _pres("2026-01", "100", S1, 100), _pres("2026-01", "200", S2, 100), _pres("2026-01", "300", S2, 100),
    ]

    r = _calcular(cubo, presupuestos)

    assert (r["red"]["presupuesto"], r["red"]["venta_cumplimiento"]) == (300, 185.0)
    assert r["red"]["cumplimiento_pct"] == pytest.approx(185 / 300) and r["red"]["semaforo"] == k.VIOLETA
    assert r["conteos"]["tiendas"] == {k.VERDE: 1, k.AMBAR: 0, k.VIOLETA: 1}
    assert r["conteos"]["asesores"] == {k.VERDE: 1, k.AMBAR: 1, k.VIOLETA: 1, k.SIN_PRESUPUESTO: 0}


def test_sin_presupuestos_no_hay_red_con_cumplimiento():
    r = _calcular([_venta("100", "2026-01", 100)], [])

    assert r["tiendas"] == [] and r["red"]["estado"] == k.SIN_PRESUPUESTO and r["red"]["cumplimiento_pct"] is None


# --- Lectura de presupuestos ---------------------------------------------------------------------


def test_los_presupuestos_se_filtran_a_los_meses_elegidos_y_a_las_tiendas():
    crudos = {
        (datetime.date(2026, 1, 1), "100"): LineaPresupuesto(S1, 10),
        (datetime.date(2026, 2, 1), "100"): LineaPresupuesto(S1, 20),   # month in between, not selected
        (datetime.date(2026, 3, 1), "100.0"): LineaPresupuesto(S1, 30),  # dirty cedula is cleaned
        (datetime.date(2026, 3, 1), "200"): LineaPresupuesto(S2, 40),
    }

    todos = k.presupuestos_del_rango(crudos, ["2026-01", "2026-03"])
    solo_s2 = k.presupuestos_del_rango(crudos, ["2026-01", "2026-03"], [S2])
    como_texto = k.presupuestos_del_rango(crudos, ["2026-01", "2026-03"], [str(S2)])

    assert set(todos) == {("2026-01", "100"), ("2026-03", "100"), ("2026-03", "200")}
    assert set(solo_s2) == set(como_texto) == {("2026-03", "200")}


def test_una_linea_de_una_tienda_asociada_cuenta_en_su_principal():
    crudos = {
        (datetime.date(2026, 1, 1), "100"): LineaPresupuesto(S1, 10),
        (datetime.date(2026, 1, 1), "200"): LineaPresupuesto(S2, 40),  # S2 is associated to S1
    }
    principales = {S1: S1, S2: S1}

    todas = k.presupuestos_del_rango(crudos, ["2026-01"], None, principales)
    solo_s1 = k.presupuestos_del_rango(crudos, ["2026-01"], [S1], principales)
    solo_s2 = k.presupuestos_del_rango(crudos, ["2026-01"], [S2], principales)

    assert {linea.sucursal_id for linea in todas.values()} == {S1}
    assert set(solo_s1) == {("2026-01", "100"), ("2026-01", "200")}
    assert solo_s2 == {}  # the UI only offers principals; the stale id of an associate selects nothing here


# --- Compania (Ventas gauge) --------------------------------------------------------------------


def _compania(cubo, lineas_presupuesto, reglas=t.REGLAS_POR_DEFECTO):
    resultado = _calcular(cubo, lineas_presupuesto, reglas, cubo_compania=cubo)
    return resultado["compania"]


def _cubo_compania():
    return [
        _venta("100", "2026-01", 1000), _venta("100", "2026-01", 500, hmcl=True),
        _venta("200", "2026-01", 100),  # asesor without budget
        _venta("100", "2026-02", 800),
        _venta("100", "2026-03", 9999),  # month without any budget
        _venta("", "2026-01", 70, clave="RESTO"), _venta("", "2026-02", 30, clave="COMERCIALES"),
        _venta("", "2026-01", 20, clave="OTROS"),
        _venta("", "2026-01", 7, linea=None, clave="RESTO"),  # unrecognised line: out, like the network venta
    ]


PRESUPUESTOS_COMPANIA = [_pres("2026-01", "100", S1, 1200), _pres("2026-02", "100", S1, 1000)]


def test_la_compania_compara_toda_la_venta_con_toda_la_suma_de_presupuestos():
    c = _compania(_cubo_compania(), PRESUPUESTOS_COMPANIA)

    # Jan: 1000+500+100+70+20, Feb: 800+30; March has no budget so it is out of both sides.
    assert c["venta"] == 2520.0 and c["presupuesto"] == 2200
    assert c["pct"] == pytest.approx(2520 / 2200) and c["semaforo"] == k.VERDE
    assert c["meses_con_presupuesto"] == 2


def test_la_compania_incluye_resto_y_asesores_sin_presupuesto_aunque_el_asesor_no_los_cuente():
    resultado = _calcular(_cubo_compania(), PRESUPUESTOS_COMPANIA, cubo_compania=_cubo_compania())

    assert resultado["red"]["venta_cumplimiento"] == 2300.0  # asesores with budget only
    assert resultado["compania"]["venta"] == 2520.0


def test_la_compania_con_base_sin_hmcl_descuenta_la_venta_hmcl():
    reglas = t.REGLAS_POR_DEFECTO._replace(cumplimiento_base=t.CUMPLIMIENTO_SIN_HMCL)

    assert _compania(_cubo_compania(), PRESUPUESTOS_COMPANIA, reglas)["venta"] == 2020.0


def test_la_compania_reparte_la_venta_en_los_cuatro_grupos_y_suman_el_medidor():
    c = _compania(_cubo_compania(), PRESUPUESTOS_COMPANIA)

    assert [g["grupo"] for g in c["por_grupo"]] == [
        "Asesores de repuestos", "Comerciales", "Otros roles de posventa", "Resto de compañía"]
    assert [g["venta"] for g in c["por_grupo"]] == [2400.0, 30.0, 20.0, 70.0]
    assert sum(g["venta"] for g in c["por_grupo"]) == c["venta"]
    assert c["por_grupo"][0]["pct"] == pytest.approx(2400 / 2520)
    assert sum(g["pct"] for g in c["por_grupo"]) == pytest.approx(1)


def test_la_compania_trae_el_cumplimiento_propio_de_los_asesores():
    c = _compania(_cubo_compania(), PRESUPUESTOS_COMPANIA)

    assert c["asesores"]["presupuesto"] == 2200 and c["asesores"]["venta_cumplimiento"] == 2300.0
    assert c["asesores"]["cumplimiento_pct"] == pytest.approx(2300 / 2200) and c["asesores"]["semaforo"] == k.VERDE


def test_la_compania_sin_presupuesto_no_tiene_pct_ni_semaforo():
    c = _compania(_cubo_compania(), [])

    assert (c["venta"], c["presupuesto"], c["pct"], c["semaforo"], c["meses_con_presupuesto"]) == (0.0, 0, None, None, 0)
    assert all(g["pct"] is None for g in c["por_grupo"])


def test_sin_cubo_de_compania_el_bloque_no_existe():
    assert "compania" not in _calcular(_cubo_compania(), PRESUPUESTOS_COMPANIA)


# --- Tiendas con venta total ------------------------------------------------------------------


def _cubo_tiendas():
    norte, sur = str(S1), str(S2)
    return [
        _venta("", "2026-01", 1000, clave=norte), _venta("", "2026-01", 500, hmcl=True, clave=norte),
        _venta("", "2026-02", 700, clave=norte),  # Norte has no budget in February: out
        _venta("", "2026-01", 300, clave=sur), _venta("", "2026-02", 100, clave=sur),
        _venta("", "2026-01", 40, linea=None, clave=sur),  # unrecognised line: out
        _venta("", "2026-01", 999, clave=str(uuid.uuid4())),  # store without budget: no row
    ]


PRESUPUESTOS_TIENDAS = [
    _pres("2026-01", "100", S1, 1200), _pres("2026-01", "200", S1, 300),
    _pres("2026-01", "300", S2, 400), _pres("2026-02", "300", S2, 100),
]


def _tiendas_total(reglas=t.REGLAS_POR_DEFECTO):
    r = _calcular(_cubo_tiendas(), PRESUPUESTOS_TIENDAS, reglas, cubo_sucursal=_cubo_tiendas())
    return r, {f["sucursal_id"]: f for f in r["tiendas"]}


def test_la_tienda_se_mide_con_su_venta_total_contra_la_suma_de_sus_presupuestos():
    _, por_tienda = _tiendas_total()

    norte, sur = por_tienda[str(S1)], por_tienda[str(S2)]
    assert (norte["venta_cumplimiento"], norte["presupuesto"]) == (1500.0, 1500)
    assert norte["cumplimiento_pct"] == pytest.approx(1.0) and norte["semaforo"] == k.VERDE
    assert (sur["venta_cumplimiento"], sur["presupuesto"]) == (400.0, 500)
    assert sur["cumplimiento_pct"] == pytest.approx(0.8) and sur["estado"] == k.EN_CAMINO
    assert set(por_tienda) == {str(S1), str(S2)}  # the store without budget is not listed


def test_la_tienda_con_base_sin_hmcl_descuenta_la_venta_hmcl():
    reglas = t.REGLAS_POR_DEFECTO._replace(cumplimiento_base=t.CUMPLIMIENTO_SIN_HMCL)

    _, por_tienda = _tiendas_total(reglas)

    assert por_tienda[str(S1)]["venta_cumplimiento"] == 1000.0


def test_los_conteos_de_tiendas_siguen_la_venta_total_y_la_red_sigue_siendo_de_asesores():
    r, _ = _tiendas_total()

    assert r["conteos"]["tiendas"] == {k.VERDE: 1, k.AMBAR: 1, k.VIOLETA: 0}
    assert r["red"]["venta_cumplimiento"] == 0.0  # asesor-based: the cube has no persons


def test_a_venta_row_with_an_unexpected_group_key_does_not_raise():
    cubo = [_venta("1", "2026-08", 100, clave="GRUPO_RARO"), _venta("2", "2026-08", 50, clave="P:2")]
    pres = dict([_pres("2026-08", "2", S1, 1000)])
    compania = k.construir_compania(cubo, pres, t.REGLAS_POR_DEFECTO, _RED)
    assert compania["venta"] == 150.0
    por_grupo = {g["grupo"]: g["venta"] for g in compania["por_grupo"]}
    assert por_grupo["Otros roles de posventa"] == 100.0 and sum(por_grupo.values()) == 150.0


_RED = {"presupuesto": 0, "venta_cumplimiento": 0, "cumplimiento_pct": None, "semaforo": None}
