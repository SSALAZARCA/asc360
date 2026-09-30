"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S2-2) — motor
ensamblado `calcular_sucursal`, de las entradas de una sucursal a líneas,
resumen y advertencias.

Mapa spec -> tests: [§10.1] fila patrón de punta a punta TestPatronExtremo,
T01/T02/T08/T12 TestUniverso y TestLineasBorde, T15 TestDivisorDinamico,
#14 OMITIDA + A-CORRIDA-102 TestSucursalOmitida, determinismo
TestDeterminismo, [OFF-ID] dias_entre_pedidos = 30 / demanda perdida / mes en
curso TestOffIdentidad, AjustesPrueba (A1) TestAjustesPrueba, rendimiento
TestRendimiento.
"""
import dataclasses
import random
import time
from datetime import date
from fractions import Fraction

import pytest

from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.pedido import ADV_UNIDAD_EMPAQUE_INVALIDA
from app.motored.services.motor.tipos import (
    COD_SUCURSAL_OMITIDA,
    COD_SUMA_NO_POSITIVA,
    ESTADO_OK,
    ESTADO_OMITIDA,
    Advertencia,
    AjustesPrueba,
    MesEnCurso,
)
from tests.motored.fixtures.motor.constructores import (
    atributos,
    entrada,
    fila_patron,
    parametros_legacy,
)

F = Fraction
CODIGO_PATRON = "94109-12000S"


def _calcular(entradas, *, atr=None, params=None, ajustes=None):
    return calcular_sucursal(
        entradas, atr or atributos(), params or parametros_legacy(),
        ajustes_prueba=ajustes,
    )


def _por_codigo(resultado):
    return {linea.entrada.codigo: linea for linea in resultado.lineas}


def _salidas(resultado):
    """Resultado sin los insumos crudos: sólo lo calculado por el motor."""
    return (
        resultado.estado,
        {
            c: dataclasses.replace(linea, entrada=None)
            for c, linea in _por_codigo(resultado).items()
        },
        resultado.resumen,
        resultado.advertencias,
    )


def _relleno(prefijo, cantidad, n):
    return [
        entrada((n,) * 6, codigo=f"{prefijo}-{i:02d}")
        for i in range(cantidad)
    ]


class TestPatronExtremo:
    """[§10.1] la fila patrón con rellenos que fijan el acumulado en 21.6 %."""

    def _resultado(self):
        entradas = (
            [fila_patron(), entrada((100,) * 6, codigo="GRANDE")]
            + _relleno("COLA", 9, "74.78")
        )
        return _calcular(entradas)

    def test_los_ocho_valores_de_la_fila_patron(self):
        linea = _por_codigo(self._resultado())[CODIGO_PATRON]
        assert linea.n == F(598, 7)
        assert linea.clase == "AF"
        assert linea.cobertura == F(7, 4)
        assert linea.stock_objetivo == F(299, 2)
        assert linea.inventario_efectivo == F(97)
        assert linea.pedido == F(50)
        assert linea.valor_pedido == F(46075, 2)
        assert linea.cobertura_final == F(1029, 598)

    def test_acumulado_de_la_fila_patron_es_21_6_por_ciento(self):
        linea = _por_codigo(self._resultado())[CODIGO_PATRON]
        assert abs(float(linea.acumulado) - 0.216) < 0.0005
        assert linea.orden_abc == 2
        assert linea.clase_abc == "A"
        assert linea.clase_fms == "F"
        assert linea.meses_con_venta == 6

    def test_puntos_y_quiebre_de_la_fila_patron(self):
        linea = _por_codigo(self._resultado())[CODIGO_PATRON]
        assert linea.punto_maximo == F(299, 2)
        assert linea.punto_minimo == F(598, 7) * F(15, 2) * 3 / 30
        assert linea.estado_quiebre == "NORMAL"

    def test_lineas_salen_en_orden_abc(self):
        resultado = self._resultado()
        assert resultado.estado == ESTADO_OK
        ordenes = [linea.orden_abc for linea in resultado.lineas]
        assert ordenes == list(range(1, 12))
        assert resultado.lineas[0].entrada.codigo == "GRANDE"

    def test_resumen_incluye_el_pedido_de_la_fila_patron(self):
        resultado = self._resultado()
        af = {f.clase: f for f in resultado.resumen.filas}["AF"]
        assert af.unidades >= 50
        assert af.valor >= F(46075, 2)


class TestUniverso:
    def test_t01_sin_ventas_ni_stock_no_hay_linea(self):
        vacia = entrada((0,) * 6, codigo="VACIA")
        con_venta = entrada((0, 0, 0, 0, 0, 5), codigo="CON-VENTA")
        assert set(_por_codigo(_calcular([vacia, con_venta]))) == {"CON-VENTA"}

    def test_universo_es_solo_ventas_stock_transito_backorder_no_entran(self):
        solo_stock = entrada((0,) * 6, codigo="STOCK", inventario=40)
        solo_transito = entrada((0,) * 6, codigo="TRANSITO", transito=9)
        solo_backorder = entrada((0,) * 6, codigo="BACKORDER", backorder=3)
        con_venta = entrada((5, 0, 0, 0, 0, 0), codigo="VENTA")
        resultado = _calcular(
            [solo_stock, solo_transito, solo_backorder, con_venta]
        )
        assert set(_por_codigo(resultado)) == {"VENTA"}

    def test_un_solo_mes_con_venta_califica_y_es_fms_m(self):
        linea = _por_codigo(_calcular([entrada((0, 0, 5, 0, 0, 0))]))["REF-1"]
        assert linea.clase_fms == "M"
        assert linea.meses_con_venta == 1

    def test_t12_devolucion_neta_el_mes(self):
        linea = _por_codigo(_calcular([entrada((0, 0, 0, 0, 0, 6))]))["REF-1"]
        assert linea.n == F(36, 21)

    def test_neto_negativo_no_es_venta_y_no_califica(self):
        devuelta = entrada((0, 0, 0, 0, 0, -3), codigo="DEVUELTA")
        con_venta = entrada((0, 0, 0, 0, 0, 5), codigo="VENTA")
        assert set(_por_codigo(_calcular([devuelta, con_venta]))) == {"VENTA"}

    def test_codigo_repetido_es_un_error_y_no_se_pisa_en_silencio(self):
        repetidas = [
            entrada((0, 0, 0, 0, 0, 5), codigo="DUP"),
            entrada((0, 0, 0, 0, 0, 9), codigo="DUP"),
        ]
        with pytest.raises(ValueError, match="DUP"):
            _calcular(repetidas)

    def test_solo_mes_en_curso_no_califica(self):
        m0 = entrada((0,) * 6, codigo="SOLO-M0", venta_m0=50)
        con_venta = entrada((0, 0, 0, 0, 0, 5), codigo="VENTA")
        assert set(_por_codigo(_calcular([m0, con_venta]))) == {"VENTA"}

    def test_venta_antes_de_la_apertura_no_califica(self):
        atr = atributos(
            fecha_corte=date(2026, 9, 15), fecha_apertura=date(2026, 6, 1)
        )
        vieja = entrada((9, 9, 9, 0, 0, 0), codigo="VIEJA")
        nueva = entrada((0, 0, 0, 0, 0, 5), codigo="NUEVA")
        resultado = _calcular([vieja, nueva], atr=atr)
        assert set(_por_codigo(resultado)) == {"NUEVA"}


class TestLineasBorde:
    def test_t02_venta_con_stock_cero_es_quiebre_total_con_pedido(self):
        linea = _por_codigo(_calcular([entrada((0, 0, 0, 0, 0, 30))]))["REF-1"]
        assert linea.estado_quiebre == "QUIEBRE_TOTAL"
        assert linea.pedido > 0

    def test_t08_n_cero_es_clase_d_sin_cobertura_ni_pedido(self):
        fila = entrada((6, 0, 0, 0, 0, -1), inventario=8)
        linea = _por_codigo(_calcular([fila]))["REF-1"]
        assert linea.n == 0
        assert linea.clase_abc == "D"
        assert linea.clase == "DM"
        assert linea.cobertura == 0
        assert linea.stock_objetivo == 0
        assert linea.pedido == 0
        assert linea.cobertura_final is None
        assert linea.cobertura_actual is None
        assert linea.punto_minimo == 0
        assert linea.punto_maximo == 0

    def test_unidad_de_empaque_invalida_da_pedido_cero_y_advierte(self):
        fila = entrada((0, 0, 0, 0, 0, 30), unidad_empaque=0)
        linea = _por_codigo(_calcular([fila]))["REF-1"]
        assert linea.pedido == 0
        assert linea.advertencias == (ADV_UNIDAD_EMPAQUE_INVALIDA,)

    def test_unidad_valida_no_advierte(self):
        fila = entrada((0, 0, 0, 0, 0, 30), unidad_empaque=12)
        linea = _por_codigo(_calcular([fila]))["REF-1"]
        assert linea.advertencias == ()
        assert linea.pedido % 12 == 0
        assert linea.pedido > 0

    def test_suma_no_positiva_deja_c_a_las_positivas_y_avisa(self):
        positiva = entrada((0, 0, 0, 0, 0, 10), codigo="POSITIVA")
        negativa = entrada((10, 0, 0, 0, 0, -20), codigo="NEGATIVA")
        resultado = _calcular([positiva, negativa])
        lineas = _por_codigo(resultado)
        assert lineas["POSITIVA"].clase_abc == "C"
        assert lineas["POSITIVA"].peso is None
        assert lineas["NEGATIVA"].clase_abc == "D"
        assert resultado.advertencias == (
            Advertencia(
                COD_SUMA_NO_POSITIVA,
                "La suma de la demanda ponderada no es positiva: "
                "no se puede clasificar ABC",
            ),
        )

    def test_suma_positiva_no_agrega_advertencias(self):
        resultado = _calcular([entrada((0, 0, 0, 0, 0, 10))])
        assert resultado.advertencias == ()


class TestDivisorDinamico:
    def test_t15_sucursal_abierta_hace_tres_meses(self):
        atr = atributos(
            fecha_corte=date(2026, 9, 15), fecha_apertura=date(2026, 6, 1)
        )
        fila = entrada((7, 7, 7, 10, 10, 10))
        resultado = _calcular([fila], atr=atr)
        linea = _por_codigo(resultado)["REF-1"]
        assert resultado.divisor == 15
        assert linea.n == F(10)
        assert linea.clase_fms == "F"
        assert linea.meses_con_venta == 3

    def test_sucursal_antigua_usa_21(self):
        resultado = _calcular([entrada((10,) * 6)])
        assert resultado.divisor == 21
        assert resultado.lineas[0].n == F(10)


class TestSucursalOmitida:
    MENSAJE = (
        "Sucursal SUCURSAL DE PRUEBA abrió hace menos de un mes: "
        "sin historia para calcular el pedido"
    )

    def _omitida(self, apertura, corte):
        atr = atributos(fecha_corte=corte, fecha_apertura=apertura)
        return _calcular([entrada((0, 0, 0, 0, 0, 5))], atr=atr)

    def test_abierta_en_el_ultimo_mes_se_omite(self):
        resultado = self._omitida(date(2026, 8, 2), date(2026, 9, 15))
        assert resultado.estado == ESTADO_OMITIDA
        assert resultado.lineas == ()
        assert resultado.divisor == 0
        assert resultado.advertencias == (
            Advertencia(COD_SUCURSAL_OMITIDA, self.MENSAJE),
        )
        assert COD_SUCURSAL_OMITIDA == "A-CORRIDA-102"

    def test_abierta_en_el_mes_en_curso_se_omite(self):
        resultado = self._omitida(date(2026, 9, 5), date(2026, 9, 15))
        assert resultado.estado == ESTADO_OMITIDA

    def test_abierta_despues_del_corte_se_omite(self):
        resultado = self._omitida(date(2026, 10, 1), date(2026, 9, 15))
        assert resultado.estado == ESTADO_OMITIDA

    def test_abierta_el_primer_dia_de_m1_no_se_omite(self):
        resultado = self._omitida(date(2026, 8, 1), date(2026, 9, 15))
        assert resultado.estado == ESTADO_OK
        assert resultado.divisor == 6
        assert len(resultado.lineas) == 1

    def test_el_resumen_de_la_omitida_esta_en_ceros(self):
        resultado = self._omitida(date(2026, 9, 5), date(2026, 9, 15))
        assert resultado.resumen.total.unidades == 0
        assert len(resultado.resumen.filas) == 10


class TestDeterminismo:
    def _entradas(self):
        rng = random.Random(7)
        return [
            entrada(
                tuple(rng.randint(0, 40) for _ in range(6)),
                codigo=f"R{i:03d}",
                inventario=rng.randint(0, 30),
                transito=rng.randint(0, 10),
                unidad_empaque=rng.choice([1, 6, 12]),
            )
            for i in range(60)
        ]

    def test_misma_entrada_dos_veces_misma_salida(self):
        entradas = self._entradas()
        assert _calcular(entradas) == _calcular(entradas)

    def test_barajar_la_entrada_no_cambia_la_salida(self):
        entradas = self._entradas()
        barajadas = list(entradas)
        random.Random(11).shuffle(barajadas)
        assert barajadas != entradas
        assert _calcular(barajadas) == _calcular(entradas)

    def test_el_resultado_no_es_trivial(self):
        resultado = _calcular(self._entradas())
        assert len(resultado.lineas) > 50
        assert resultado.resumen.total.unidades > 0


class TestOffIdentidad:
    def _tabla(self):
        entradas = [
            entrada((n,) * 6, codigo=f"F{i}")
            for i, n in enumerate((800, 100, 60, 30, 10))
        ]
        entradas.append(entrada((0, 0, 0, 0, 0, 7), codigo="M0"))
        return entradas

    def test_cobertura_por_clase_iguala_la_formula_del_excel(self):
        lineas = _por_codigo(_calcular(self._tabla()))
        intervalo = F(15, 2)
        assert {c: ln.clase for c, ln in lineas.items()} == {
            "F0": "AF", "F1": "BF", "F2": "CF", "F3": "CF", "F4": "CF",
            "M0": "CM",
        }
        excel_f = 1 + intervalo * 3 / 30
        excel_m = 1 + intervalo * F(3, 2) / 30
        assert [lineas[f"F{i}"].cobertura for i in range(5)] == [excel_f] * 5
        assert excel_f == F(7, 4)
        assert lineas["M0"].cobertura == excel_m == F(11, 8)

    def test_dias_entre_pedidos_7_y_15_cambian_la_cobertura(self):
        for dias, esperado in (("7", F(59, 60)), ("15", F(5, 4))):
            atr = atributos(dias_entre_pedidos=dias)
            linea = _por_codigo(_calcular(self._tabla(), atr=atr))["F0"]
            assert linea.cobertura == esperado
            assert linea.stock_objetivo == linea.n * esperado

    def test_demanda_perdida_apagada_no_influye_en_nada(self):
        sin = [entrada((10,) * 6, codigo="X", inventario=5)]
        con = [entrada(
            (10,) * 6, (0, 0, 3, 0, 0, 9), codigo="X", inventario=5
        )]
        params = parametros_legacy(factor_demanda_perdida=F(5))
        assert _salidas(_calcular(con, params=params)) == _salidas(
            _calcular(sin, params=params)
        )

    def test_demanda_perdida_encendida_si_cambia_la_salida(self):
        fila = entrada((10,) * 6, (0, 0, 0, 0, 0, 6))
        params = parametros_legacy(incluir_demanda_perdida=True)
        linea = _por_codigo(_calcular([fila], params=params))["REF-1"]
        assert linea.n == F(246, 21)
        assert linea.k_perdida == F(6)

    def test_mes_en_curso_no_influye_con_el_preset_legacy(self):
        base = [entrada((10, 20, 30, 40, 50, 60), inventario=3)]
        con_m0 = [entrada(
            (10, 20, 30, 40, 50, 60), inventario=3, venta_m0=999, perdida_m0=50
        )]
        assert _salidas(_calcular(con_m0)) == _salidas(_calcular(base))

    def test_mes_en_curso_excluido_no_influye(self):
        excluido = parametros_legacy(mes_en_curso=MesEnCurso(
            modo="EXCLUIDO", dias_transcurridos=14, dias_del_mes=30,
            tope=F(3),
        ))
        base = [entrada((10,) * 6)]
        con_m0 = [entrada((10,) * 6, venta_m0=500)]
        assert _salidas(_calcular(con_m0, params=excluido)) == _salidas(
            _calcular(base)
        )


class TestTipos:
    def test_mes_en_curso_nombra_sus_campos_sin_letras_sueltas(self):
        m0 = MesEnCurso(
            modo="PONDERADO", dias_transcurridos=14, dias_del_mes=30,
            tope=F(3),
        )
        assert (m0.dias_transcurridos, m0.dias_del_mes) == (14, 30)
        assert not hasattr(m0, "d")
        assert not hasattr(m0, "D")


class TestAjustesPrueba:
    def test_divisor_por_referencia_reproduce_el_18_del_excel(self):
        ajustes = AjustesPrueba(divisor_por_referencia={CODIGO_PATRON: 18})
        linea = _por_codigo(_calcular([fila_patron()], ajustes=ajustes))[
            CODIGO_PATRON
        ]
        assert linea.n == F(1794, 18)
        sin_ajuste = _por_codigo(_calcular([fila_patron()]))[CODIGO_PATRON]
        assert sin_ajuste.n == F(598, 7)

    def test_orden_explicito_gobierna_el_desempate_del_abc(self):
        iguales = [
            entrada((10,) * 6, codigo="A"), entrada((10,) * 6, codigo="B"),
        ]
        por_codigo = _calcular(iguales)
        assert [ln.entrada.codigo for ln in por_codigo.lineas] == ["A", "B"]
        fisico = _calcular(iguales, ajustes=AjustesPrueba(
            orden_explicito=["B", "A"]
        ))
        assert [ln.entrada.codigo for ln in fisico.lineas] == ["B", "A"]
        assert fisico.lineas[0].clase_abc == "A"
        assert fisico.lineas[1].clase_abc == "C"


class TestRendimiento:
    def test_tres_mil_filas_en_menos_de_un_segundo(self):
        rng = random.Random(3)
        entradas = [
            entrada(
                tuple(rng.randint(0, 60) for _ in range(6)),
                (0, 0, 0, 0, 0, rng.randint(0, 3)),
                codigo=f"P{i:04d}",
                precio="100.5",
                inventario=rng.randint(0, 50),
                transito=rng.randint(0, 20),
                unidad_empaque=rng.choice([1, 4, 12]),
            )
            for i in range(3000)
        ]
        inicio = time.perf_counter()
        resultado = _calcular(entradas)
        transcurrido = time.perf_counter() - inicio
        assert len(resultado.lineas) > 2500
        assert transcurrido < 1.0
