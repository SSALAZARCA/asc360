"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S2-1) — clasificación
ABC/FMS, estado de quiebre y resumen por clase.

Mapa spec -> tests: ABC (cortes 80/95, orden obligatorio, empates, filas D,
denominador por sucursal, suma N <= 0) TestAbc*; FMS (umbrales, mes negativo,
demanda perdida) TestFms; estado_quiebre (tabla, precedencia, inventario
muerto) TestQuiebre; resumen por clase (bloque AA1:AE11 del Excel)
TestResumen.

Regla del Excel (ADR-2, gana sobre el texto del spec 6.5.1): el denominador
del peso es la suma de N sobre TODAS las filas del universo, incluidas las
de N <= 0, y el acumulado incluye la fila actual.
"""
from datetime import date
from fractions import Fraction

import pytest

from app.motored.services.motor.clasificacion import (
    clasificar_abc,
    clase_fms,
    meses_con_venta,
    ventas_efectivas,
)
from app.motored.services.motor.puntos import (
    BAJO_MINIMO,
    INVENTARIO_MUERTO,
    NORMAL,
    QUIEBRE_PISO,
    QUIEBRE_TOTAL,
    SIN_MOVIMIENTO,
    SOBRESTOCK,
    estado_quiebre,
)
from app.motored.services.motor.resumen import CLASES_RESUMEN, resumir
from app.motored.services.motor.ventana import construir_ventana
from tests.motored.fixtures.motor.constructores import (
    entrada,
    parametros_legacy,
)

F = Fraction
SEIS_CEROS = (F(0),) * 6


def _abc(demandas, **kwargs):
    params = kwargs.pop("params", None) or parametros_legacy()
    return clasificar_abc(
        {c: F(n) for c, n in demandas.items()}, params, **kwargs
    )


def _clases(resultado):
    return {c: item.clase for c, item in resultado.items.items()}


class TestAbcCortes:
    def test_cortes_exactos_80_y_95(self):
        resultado = _abc({"a": 50, "b": 30, "c": 10, "d": 5, "e": 5})
        assert _clases(resultado) == {
            "a": "A", "b": "A", "c": "B", "d": "B", "e": "B",
        }
        assert [resultado.items[c].acumulado for c in "abcde"] == [
            F(1, 2), F(4, 5), F(9, 10), F(19, 20), F(1),
        ]
        assert resultado.items["a"].peso == F(1, 2)

    def test_cortes_configurables_desde_los_parametros(self):
        params = parametros_legacy(corte_abc_a=F(1, 2), corte_abc_b=F(9, 10))
        resultado = _abc(
            {"a": 50, "b": 30, "c": 10, "d": 5, "e": 5}, params=params
        )
        assert _clases(resultado) == {
            "a": "A", "b": "B", "c": "B", "d": "C", "e": "C",
        }

    def test_el_orden_es_el_de_n_descendente_desde_uno(self):
        resultado = _abc({"a": 50, "b": 30, "c": 10, "d": 5, "e": 5})
        assert [resultado.items[c].orden for c in "abcde"] == [1, 2, 3, 4, 5]

    def test_el_orden_de_entrada_no_cambia_nada(self):
        directo = _abc({"a": 50, "b": 30, "c": 10, "d": 5, "e": 5})
        invertido = _abc({"e": 5, "d": 5, "c": 10, "b": 30, "a": 50})
        assert directo.items == invertido.items

    def test_los_pesos_son_exactos_sin_error_binario(self):
        resultado = _abc({str(i): 1 for i in range(10)})
        clases = [resultado.items[str(i)].clase for i in range(10)]
        assert clases == ["A"] * 10  # un solo grupo: clase de la posición 1
        assert resultado.items["7"].acumulado == F(4, 5)
        distintos = _abc({str(i): i + 1 for i in range(10)})
        assert distintos.items["0"].clase == "C"
        assert distintos.items["9"].acumulado == F(10, 55)


class TestAbcDesempate:
    DEMANDAS = {"x": 50, "y": 15, "z": 15, "w": 20}

    def test_empate_en_frontera_da_la_misma_clase_al_grupo(self):
        resultado = _abc(self.DEMANDAS)
        assert _clases(resultado) == {"x": "A", "w": "A", "y": "B", "z": "B"}
        assert resultado.items["y"].orden == 3
        assert resultado.items["z"].orden == 4

    def test_el_grupo_toma_la_clase_de_su_primera_posicion(self):
        resultado = _abc({"a": 70, "b": 10, "c": 10, "d": 10})
        assert _clases(resultado) == {
            "a": "A", "b": "A", "c": "A", "d": "A",
        }
        abierto = _abc({"a": 75, "b": 10, "c": 10, "d": 5})
        assert _clases(abierto)["b"] == _clases(abierto)["c"] == "B"

    def test_peso_y_acumulado_siguen_siendo_por_fila(self):
        resultado = _abc(self.DEMANDAS)
        assert resultado.items["y"].acumulado == F(17, 20)
        assert resultado.items["z"].acumulado == F(1)
        assert resultado.items["y"].peso == resultado.items["z"].peso

    def test_empate_es_independiente_del_orden_de_entrada(self):
        invertido = dict(reversed(list(self.DEMANDAS.items())))
        assert _abc(invertido).items == _abc(self.DEMANDAS).items

    def test_orden_explicito_solo_mueve_el_orden_no_la_clase(self):
        rango = {"z": 0, "y": 1}
        resultado = _abc(self.DEMANDAS, desempate=rango)
        assert resultado.items["z"].orden == 3
        assert resultado.items["y"].orden == 4
        assert resultado.items["z"].clase == "B"
        assert resultado.items["y"].clase == "B"
        assert resultado.items["z"].acumulado == F(17, 20)

    def test_empates_como_excel_clasifica_fila_por_fila(self):
        rango = {"z": 0, "y": 1}
        resultado = _abc(
            self.DEMANDAS, desempate=rango, empates_como_excel=True
        )
        assert resultado.items["z"].clase == "B"
        assert resultado.items["y"].clase == "C"

    def test_solo_empata_con_n_exactamente_igual(self):
        resultado = _abc({"a": 50, "b": 30, "c": 10, "d": 5, "e": 5})
        assert _clases(resultado)["d"] == _clases(resultado)["e"] == "B"
        casi = clasificar_abc(
            {"d": F(5), "e": F(5) + F(1, 1000), "f": F(90)},
            parametros_legacy(),
        )
        assert casi.items["e"].orden == 2 and casi.items["d"].orden == 3

    def test_empate_de_filas_d_sigue_siendo_d(self):
        resultado = _abc({"a": 70, "b": 0, "c": 0, "d": 30})
        assert _clases(resultado) == {
            "a": "A", "b": "D", "c": "D", "d": "C",
        }


class TestAbcFilasD:
    def test_el_denominador_incluye_las_filas_con_n_no_positiva(self):
        resultado = _abc({"a": 50, "b": 30, "c": -20})
        assert resultado.items["a"].acumulado == F(5, 6)
        assert _clases(resultado) == {"a": "B", "b": "C", "c": "D"}

    def test_fila_d_conserva_peso_y_acumulado_del_excel(self):
        resultado = _abc({"a": 60, "b": 40, "c": 0, "d": -20})
        assert _clases(resultado) == {"a": "A", "b": "C", "c": "D", "d": "D"}
        assert resultado.items["c"].peso == F(0)
        assert resultado.items["d"].peso == F(-1, 4)
        assert resultado.items["d"].acumulado == F(1)
        assert resultado.items["d"].orden == 4

    def test_n_cero_es_d(self):
        resultado = _abc({"a": 70, "b": 30, "c": 0})
        assert _clases(resultado) == {"a": "A", "b": "C", "c": "D"}

    def test_cada_sucursal_usa_su_propio_total(self):
        una = _abc({"ref": 50, "otra": 10})
        otra = _abc({"ref": 50, "otra": 30, "extra": 30})
        assert una.items["ref"].clase == "B"
        assert otra.items["ref"].clase == "A"

    def test_suma_no_positiva_deja_c_sin_pesos_y_avisa(self):
        resultado = _abc({"a": 10, "b": -30, "c": -5})
        assert resultado.suma_no_positiva is True
        assert _clases(resultado) == {"a": "C", "b": "D", "c": "D"}
        assert all(
            i.peso is None and i.acumulado is None
            for i in resultado.items.values()
        )
        assert resultado.items["a"].orden == 1

    def test_suma_positiva_no_avisa(self):
        assert _abc({"a": 10, "b": -5}).suma_no_positiva is False

    def test_sin_filas_no_avisa(self):
        resultado = _abc({})
        assert resultado.items == {}
        assert resultado.suma_no_positiva is False


class TestFms:
    @pytest.mark.parametrize(
        "meses,letra", [(6, "F"), (2, "F"), (1, "M"), (0, "S")]
    )
    def test_umbrales_por_defecto(self, meses, letra):
        assert clase_fms(meses, parametros_legacy()) == letra

    def test_umbrales_configurables(self):
        params = parametros_legacy(umbral_f=3, umbral_m=2)
        assert [clase_fms(m, params) for m in (3, 2, 1)] == ["F", "M", "S"]

    def test_cuenta_los_meses_con_venta_positiva(self):
        assert meses_con_venta((F(5), F(0), F(3), F(0), F(0), F(1))) == 3
        assert meses_con_venta(SEIS_CEROS) == 0

    def test_un_mes_negativo_no_es_mes_de_venta(self):
        meses = meses_con_venta((F(5), F(-2), F(0), F(0), F(0), F(0)))
        assert meses == 1
        assert clase_fms(meses, parametros_legacy()) == "M"

    def test_la_demanda_perdida_no_cuenta_como_venta(self):
        fila = entrada((0, 0, 0, 0, 0, 4), (0, 0, 0, 9, 9, 9))
        ventana = construir_ventana(date(2026, 9, 29), None)
        efectivas = ventas_efectivas(fila, ventana)
        assert meses_con_venta(efectivas) == 1

    def test_meses_no_operados_no_cuentan(self):
        fila = entrada((10,) * 6)
        ventana = construir_ventana(date(2026, 9, 15), date(2026, 6, 1))
        efectivas = ventas_efectivas(fila, ventana)
        assert efectivas == (F(0), F(0), F(0), F(10), F(10), F(10))
        assert meses_con_venta(efectivas) == 3
        assert clase_fms(3, parametros_legacy()) == "F"


def _quiebre(*, n=10, v=0, w=0, x=0, minimo=10, maximo=20,
             ventas=(0, 0, 0, 0, 0, 5), params=None):
    return estado_quiebre(
        n=F(n), inventario=F(v), transito=F(w), backorder=F(x),
        punto_minimo=F(minimo), punto_maximo=F(maximo),
        ventas=tuple(F(m) for m in ventas),
        params=params or parametros_legacy(),
    )


class TestQuiebre:
    def test_sin_movimiento(self):
        assert _quiebre(n=0, v=0) == SIN_MOVIMIENTO
        assert _quiebre(n=-4, v=0) == SIN_MOVIMIENTO

    def test_inventario_muerto_sin_ventas_en_los_ultimos_meses(self):
        estado = _quiebre(n=0, v=5, ventas=(0,) * 6)
        assert estado == INVENTARIO_MUERTO

    def test_sobrestock_si_hubo_venta_en_la_ventana_de_muerto(self):
        estado = _quiebre(n=0, v=5, ventas=(0, 0, 0, 0, 0, 3))
        assert estado == SOBRESTOCK

    def test_ventana_de_inventario_muerto_configurable(self):
        params = parametros_legacy(meses_inventario_muerto=2)
        venta_vieja = _quiebre(
            n=0, v=5, ventas=(7, 0, 0, 0, 0, 0), params=params
        )
        venta_reciente = _quiebre(
            n=0, v=5, ventas=(0, 0, 0, 0, 0, 7), params=params
        )
        assert venta_vieja == INVENTARIO_MUERTO
        assert venta_reciente == SOBRESTOCK

    def test_quiebre_total_gana_sobre_bajo_minimo(self):
        assert _quiebre(n=10, v=0, w=0, x=0) == QUIEBRE_TOTAL

    def test_quiebre_piso_con_transito_o_backorder(self):
        assert _quiebre(n=10, v=0, w=5) == QUIEBRE_PISO
        assert _quiebre(n=10, v=0, x=2) == QUIEBRE_PISO

    def test_quiebre_piso_gana_sobre_bajo_minimo(self):
        assert _quiebre(n=10, v=0, w=3, minimo=10) == QUIEBRE_PISO

    def test_bajo_minimo_es_estricto(self):
        assert _quiebre(v=9, minimo=10) == BAJO_MINIMO
        assert _quiebre(v=10, minimo=10) == NORMAL

    def test_sobrestock_con_tolerancia_estricta(self):
        assert _quiebre(v=25, maximo=20) == NORMAL
        assert _quiebre(v=26, maximo=20) == SOBRESTOCK

    def test_tolerancia_configurable(self):
        params = parametros_legacy(tolerancia_sobrestock=F(0))
        assert _quiebre(v=21, maximo=20, params=params) == SOBRESTOCK

    def test_normal_entre_minimo_y_maximo(self):
        assert _quiebre(v=15) == NORMAL

    def test_v_y_efectivo_suman_transito_y_backorder(self):
        assert _quiebre(v=5, w=3, x=2, minimo=10) == NORMAL
        assert _quiebre(v=4, w=3, x=2, minimo=10) == BAJO_MINIMO


class TestResumen:
    LINEAS = [
        ("AF", F(50), F(46075, 2)),
        ("AF", F(10), F(100)),
        ("AM", F(0), F(0)),
        ("BS", F(5), F(50)),
    ]

    def test_bloque_de_diez_clases_en_el_orden_del_excel(self):
        resumen = resumir(self.LINEAS)
        assert CLASES_RESUMEN == (
            "AF", "AM", "AS", "BF", "BM", "BS", "CF", "CM", "CS", "DS",
        )
        assert tuple(f.clase for f in resumen.filas) == CLASES_RESUMEN

    def test_suma_unidades_cuenta_referencias_y_suma_valor(self):
        fila = {f.clase: f for f in resumir(self.LINEAS).filas}["AF"]
        assert fila.unidades == F(60)
        assert fila.referencias == 2
        assert fila.valor == F(46075, 2) + 100

    def test_referencias_cuenta_solo_pedido_positivo(self):
        fila = {f.clase: f for f in resumir(self.LINEAS).filas}["AM"]
        assert (fila.unidades, fila.referencias, fila.valor) == (0, 0, 0)

    def test_peso_es_la_fraccion_de_unidades_sobre_el_total(self):
        resumen = resumir(self.LINEAS)
        pesos = {f.clase: f.porcentaje_peso for f in resumen.filas}
        assert pesos["AF"] == F(60, 65)
        assert pesos["BS"] == F(5, 65)
        assert sum(pesos.values()) == 1
        assert resumen.total.porcentaje_peso == 1

    def test_totales_suman_las_clases(self):
        total = resumir(self.LINEAS).total
        assert total.clase == "TOTAL"
        assert total.unidades == F(65)
        assert total.referencias == 3
        assert total.valor == F(46075, 2) + 150

    def test_total_cero_da_pesos_cero(self):
        resumen = resumir([("AF", F(0), F(0)), ("CM", F(0), F(0))])
        assert all(f.porcentaje_peso == 0 for f in resumen.filas)
        assert resumen.total.porcentaje_peso == 0

    def test_sin_lineas_devuelve_el_bloque_en_ceros(self):
        resumen = resumir([])
        assert len(resumen.filas) == 10
        assert resumen.total.unidades == 0

    def test_clase_fuera_del_bloque_se_agrega_y_entra_al_total(self):
        resumen = resumir([("AF", F(10), F(10)), ("DM", F(4), F(8))])
        clases = tuple(f.clase for f in resumen.filas)
        assert clases == CLASES_RESUMEN + ("DM",)
        assert resumen.filas[-1].unidades == 4
        assert resumen.total.unidades == 14
        assert resumen.total.valor == 18
        assert sum(f.porcentaje_peso for f in resumen.filas) == 1
