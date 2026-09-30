"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S1-2) — núcleo puro:
ventana, divisor dinámico, demanda ponderada N, cobertura y pedido.

Mapa spec -> tests: [§10.1] TestPatron*, T03-T07 TestPedido, T15 TestDivisor,
T16 TestVentana, [OFF-ID] lost/cobertura/CERCANO TestDemandaPerdida y
TestCobertura.
"""
import random
from datetime import date
from fractions import Fraction

import pytest

from app.motored.services.motor.aritmetica import cuantizar
from app.motored.services.motor.cobertura import (
    cobertura_actual,
    cobertura_clase,
    intervalo_dias,
    punto_maximo,
    punto_minimo,
    stock_objetivo,
)
from app.motored.services.motor.demanda import (
    demanda_ponderada,
    indicadores_informativos,
    serie_demanda,
)
from app.motored.services.motor.pedido import (
    ADV_UNIDAD_EMPAQUE_INVALIDA,
    calcular_pedido,
    cobertura_final,
    inventario_efectivo,
    valor_pedido,
)
from app.motored.services.motor.ventana import construir_ventana
from tests.motored.fixtures.motor.constructores import (
    atributos,
    entrada,
    fila_patron,
    parametros_legacy,
)

F = Fraction


def _n(ventas, *, perdidas=(0,) * 6, params=None, apertura=None,
       corte=date(2026, 9, 29)):
    """N exacto de una fila sintética (helper de las tablas)."""
    ventana = construir_ventana(corte, apertura)
    serie = serie_demanda(
        entrada(ventas, perdidas), ventana, params or parametros_legacy()
    )
    return demanda_ponderada(serie, ventana)


def _etapas_patron():
    """Encadena las etapas del motor sobre la fila patrón §10.1."""
    fila, atr, par = fila_patron(), atributos(), parametros_legacy()
    ventana = construir_ventana(atr.fecha_corte, atr.fecha_apertura)
    n = demanda_ponderada(serie_demanda(fila, ventana, par), ventana)
    cob = cobertura_clase("AF", atr, par)
    ss = stock_objetivo(n, cob)
    y = inventario_efectivo(fila)
    res = calcular_pedido(
        ss, y, F(fila.ajuste), fila.unidad_empaque, par.modo_redondeo
    )
    return fila, n, cob, ss, y, res


class TestPatronEtapas:
    """[§10.1] valores intermedios exactos de la fila patrón."""

    def test_n_exacto(self):
        _, n, *_ = _etapas_patron()
        assert n == F(598, 7)

    def test_cobertura_y_stock_objetivo(self):
        _, _, cob, ss, *_ = _etapas_patron()
        assert cob == F(7, 4)
        assert ss == F(299, 2)

    def test_inventario_efectivo(self):
        *_, y, _ = _etapas_patron()
        assert y == 97

    def test_pedido_50_y_derivados(self):
        fila, n, _, _, y, res = _etapas_patron()
        assert res.pedido == 50
        assert valor_pedido(res.pedido, F(fila.precio)) == F("23037.5")
        assert cobertura_final(y, res.pedido, n) == F(1029, 598)
        assert str(cuantizar(F(1029, 598), 6)) == "1.720736"

    def test_trampa_de_cuantizacion(self):
        """N guardado a 6 decimales daría 49; el motor exacto da 50."""
        _, n, cob, ss, y, res = _etapas_patron()
        n_guardado = F(cuantizar(n, 6))
        assert n_guardado == F("85.428571")
        ss_mal = stock_objetivo(n_guardado, cob)
        mal = calcular_pedido(ss_mal, y, F(-3), 1, "CERCANO")
        assert mal.pedido == 49
        assert res.pedido == 50


class TestVentana:
    @pytest.mark.parametrize(
        "corte, primero, ultimo",
        [
            (date(2026, 9, 2), (2026, 3), (2026, 8)),   # T16 día 2
            (date(2026, 9, 30), (2026, 3), (2026, 8)),  # T16 último día
            (date(2026, 10, 1), (2026, 4), (2026, 9)),
            (date(2026, 2, 15), (2025, 8), (2026, 1)),  # cruce de año
        ],
    )
    def test_seis_meses_completos_antes_del_corte(self, corte, primero, ultimo):
        ventana = construir_ventana(corte, None)
        assert len(ventana.meses) == 6
        assert ventana.meses[0] == primero  # M6
        assert ventana.meses[-1] == ultimo  # M1

    def test_pesos_y_divisor_base(self):
        ventana = construir_ventana(date(2026, 9, 29), None)
        assert ventana.pesos == (1, 2, 3, 4, 5, 6)
        assert ventana.divisor == 21
        assert not ventana.sin_historia


class TestDivisorDinamico:
    """T15 y §6.4.5: sólo cuentan los meses abiertos el día 1."""

    @pytest.mark.parametrize(
        "apertura, divisor",
        [
            (date(2026, 6, 1), 15),   # Jun, Jul, Ago = 4+5+6
            (date(2026, 6, 10), 11),  # junio excluido
            (date(2026, 8, 1), 6),    # sólo M1
            (None, 21),
            (date(2020, 1, 1), 21),
            (date(2026, 3, 1), 21),   # exacto al primer día de M6
            (date(2026, 3, 2), 20),   # marzo excluido
        ],
    )
    def test_divisor(self, apertura, divisor):
        ventana = construir_ventana(date(2026, 9, 15), apertura)
        assert ventana.divisor == divisor

    @pytest.mark.parametrize(
        "apertura",
        [date(2026, 8, 2), date(2026, 9, 5), date(2026, 12, 1)],
    )
    def test_divisor_cero_marca_omitida(self, apertura):
        ventana = construir_ventana(date(2026, 9, 15), apertura)
        assert ventana.divisor == 0
        assert ventana.sin_historia

    def test_ventas_previas_a_la_apertura_se_ignoran(self):
        apertura = date(2026, 6, 1)
        con_residuo = _n((50, 40, 30, 10, 10, 10), apertura=apertura,
                         corte=date(2026, 9, 15))
        sin_residuo = _n((0, 0, 0, 10, 10, 10), apertura=apertura,
                         corte=date(2026, 9, 15))
        assert con_residuo == sin_residuo == F(10 * 4 + 10 * 5 + 10 * 6, 15)

    def test_demanda_perdida_previa_a_la_apertura_se_ignora(self):
        params = parametros_legacy(incluir_demanda_perdida=True)
        n = _n((0, 0, 0, 10, 10, 10), perdidas=(9, 9, 9, 0, 0, 0),
               params=params, apertura=date(2026, 6, 1),
               corte=date(2026, 9, 15))
        assert n == F(150, 15)

    def test_n_con_divisor_cero_falla_explicito(self):
        ventana = construir_ventana(date(2026, 9, 15), date(2026, 9, 5))
        serie = serie_demanda(entrada((1,) * 6), ventana, parametros_legacy())
        with pytest.raises(ValueError):
            demanda_ponderada(serie, ventana)


class TestDemandaPonderada:
    def test_n_patron(self):
        assert _n((102, 112, 108, 105, 74, 59)) == F(598, 7)

    def test_sin_ventas_tempranas_no_cambia_el_divisor(self):
        assert _n((0, 0, 0, 0, 0, 21)) == F(6)

    def test_serie_exige_seis_meses(self):
        ventana = construir_ventana(date(2026, 9, 29), None)
        with pytest.raises(ValueError):
            serie_demanda(entrada((1, 2, 3)), ventana, parametros_legacy())

    def test_ventas_netas_negativas_entran_tal_cual(self):
        assert _n((0, 0, 0, 0, 0, -21)) == F(-6)


class TestDemandaPerdida:
    def test_on_factor_1_suma_en_el_mes_de_ocurrencia(self):
        params = parametros_legacy(incluir_demanda_perdida=True)
        n = _n((10,) * 6, perdidas=(0, 0, 0, 0, 0, 6), params=params)
        assert n == F(10 + 20 + 30 + 40 + 50 + 96, 21)

    def test_factor_se_aplica_por_mes(self):
        params = parametros_legacy(
            incluir_demanda_perdida=True, factor_demanda_perdida=F(2)
        )
        ventana = construir_ventana(date(2026, 9, 29), None)
        serie = serie_demanda(
            entrada((10,) * 6, (0, 3, 0, 0, 0, 0)), ventana, params
        )
        assert serie[1] == 10 + 6  # M5 = segundo elemento

    def test_off_es_identico_a_no_tener_perdida(self):
        """[OFF-ID] con switch OFF el factor y los datos no influyen."""
        params = parametros_legacy(factor_demanda_perdida=F(5))
        con = _n((3, 5, 7, 9, 11, 13), perdidas=(4, 4, 4, 4, 4, 4), params=params)
        sin = _n((3, 5, 7, 9, 11, 13))
        assert con == sin

    def test_perdida_de_mes_en_curso_se_ignora_en_s1(self):
        params = parametros_legacy(incluir_demanda_perdida=True)
        ventana = construir_ventana(date(2026, 9, 29), None)
        fila = entrada((10,) * 6, perdida_m0=99, venta_m0=99)
        assert serie_demanda(fila, ventana, params) == (10,) * 6

    def test_duplicados_llegan_sumados_y_no_se_deduplican(self):
        params = parametros_legacy(incluir_demanda_perdida=True)
        ventana = construir_ventana(date(2026, 9, 29), None)
        serie = serie_demanda(entrada((0,) * 6, (0, 0, 0, 0, 0, 6)), ventana, params)
        assert serie[-1] == 6  # dos registros de 3, ya agregados por el cargador

    def test_solo_perdida_no_es_venta(self):
        """La serie usa perdida, pero el universo/FMS (S2) sólo ve ventas."""
        params = parametros_legacy(incluir_demanda_perdida=True)
        ventana = construir_ventana(date(2026, 9, 29), None)
        fila = entrada((0,) * 6, (0, 0, 0, 0, 0, 5))
        assert fila.ventas == (0,) * 6
        assert serie_demanda(fila, ventana, params)[-1] == 5


class TestIndicadoresKLM:
    def test_off_todo_cero_salvo_l_y_m_de_ventas(self):
        ventana = construir_ventana(date(2026, 9, 29), None)
        params = parametros_legacy()
        fila = entrada((6, 6, 6, 6, 6, 6), (1, 1, 1, 1, 1, 1))
        ind = indicadores_informativos(fila, ventana, params)
        assert (ind.k_perdida, ind.l_ultimo_mes, ind.m_promedio) == (0, 6, 6)

    def test_on_suma_la_perdida_usada(self):
        ventana = construir_ventana(date(2026, 9, 29), None)
        params = parametros_legacy(
            incluir_demanda_perdida=True, factor_demanda_perdida=F(2)
        )
        fila = entrada((6,) * 6, (1, 0, 0, 0, 0, 3))
        ind = indicadores_informativos(fila, ventana, params)
        assert ind.k_perdida == 8
        assert ind.l_ultimo_mes == 12
        assert ind.m_promedio == F(6 * 6 + 8, 6)

    def test_k_l_m_no_alteran_n_pedido_con_switch_off(self):
        base = _n((10, 20, 30, 40, 50, 60))
        con = _n((10, 20, 30, 40, 50, 60), perdidas=(99, 0, 0, 0, 0, 99))
        assert base == con


class TestCobertura:
    """Manizales I = 7.5; k F/M/S = 3/1.5/1."""

    @pytest.mark.parametrize(
        "dias, esperado",
        [
            ("30", {"AF": F(7, 4), "AM": F(11, 8), "AS": F(5, 4)}),
            ("7", {"AF": F(59, 60), "AM": F(73, 120), "AS": F(29, 60)}),
            ("15", {"AF": F(5, 4), "AM": F(7, 8), "AS": F(3, 4)}),
        ],
    )
    def test_tabla_por_dias_entre_pedidos(self, dias, esperado):
        atr, par = atributos(dias_entre_pedidos=dias), parametros_legacy()
        for clase, cob in esperado.items():
            assert cobertura_clase(clase, atr, par) == cob

    def test_dias_30_iguala_formula_excel(self):
        """[OFF-ID] 1 + I*k/30 para cada clase."""
        atr, par = atributos(), parametros_legacy()
        i = intervalo_dias(atr)
        assert i == F(15, 2)
        for clase, k in (("AF", 3), ("BM", F(3, 2)), ("CS", 1)):
            assert cobertura_clase(clase, atr, par) == 1 + i * F(k) / 30

    def test_depende_solo_de_fms(self):
        atr, par = atributos(), parametros_legacy()
        assert (cobertura_clase("AF", atr, par)
                == cobertura_clase("BF", atr, par)
                == cobertura_clase("CF", atr, par))

    def test_clase_ds_es_cero(self):
        """T08: N=0 -> DS -> cobertura 0."""
        assert cobertura_clase("DS", atributos(), parametros_legacy()) == 0

    def test_por_sucursal(self):
        par = parametros_legacy()
        a7 = cobertura_clase("AF", atributos(dias_entre_pedidos="7"), par)
        a30 = cobertura_clase("AF", atributos(dias_entre_pedidos="30"), par)
        assert a7 != a30

    def test_clase_desconocida_falla(self):
        with pytest.raises(ValueError):
            cobertura_clase("AX", atributos(), parametros_legacy())


class TestPuntos:
    def test_punto_maximo_es_el_stock_objetivo(self):
        assert punto_maximo(F(299, 2)) == F(299, 2)

    def test_punto_maximo_sigue_dias_entre_pedidos(self):
        atr, par = atributos(dias_entre_pedidos="7"), parametros_legacy()
        n = F(598, 7)
        ss = stock_objetivo(n, cobertura_clase("AF", atr, par))
        assert punto_maximo(ss) == n * F(59, 60)

    @pytest.mark.parametrize("dias", ["7", "15", "30"])
    def test_punto_minimo_no_incluye_periodo_de_revision(self, dias):
        atr, par = atributos(dias_entre_pedidos=dias), parametros_legacy()
        n = F(598, 7)
        assert punto_minimo(n, "AF", atr, par) == n * F(15, 2) * 3 / 30

    def test_punto_minimo_ds_es_cero(self):
        assert punto_minimo(F(0), "DS", atributos(), parametros_legacy()) == 0

    def test_cobertura_actual(self):
        assert cobertura_actual(F(97), F(598, 7)) == F(679, 598)
        assert cobertura_actual(F(5), F(0)) is None


def _pedido(ss, y, z, u, modo="CERCANO"):
    return calcular_pedido(F(ss), F(y), F(z), u, modo).pedido


class TestPedido:
    def test_t03_neto_7_u_12(self):
        assert _pedido(7, 0, 0, 12, "CERCANO") == 12
        assert _pedido(7, 0, 0, 12, "ARRIBA") == 12

    def test_t04_neto_5_u_12(self):
        assert _pedido(5, 0, 0, 12, "CERCANO") == 0
        assert _pedido(5, 0, 0, 12, "ARRIBA") == 12

    def test_t05_sobrestock(self):
        assert _pedido(10, 30, 0, 1) == 0

    def test_t06_neto_cero_y_z_15(self):
        assert _pedido(0, 15, 15, 12) == 15  # Z sin redondear a U

    def test_t07_neto_negativo_y_z_15(self):
        assert _pedido(0, 20, 15, 1) == 15  # el clamp precede a la regla de Z

    def test_mitad_negativa_redondea_lejos_de_cero_y_se_recorta(self):
        assert _pedido(F(-1, 2) * 12, 0, 0, 12) == 0

    def test_mitad_positiva_redondea_lejos_de_cero(self):
        assert _pedido(F(99, 2), 0, 0, 1) == 50

    @pytest.mark.parametrize("unidad", [0, -3])
    def test_unidad_invalida_da_cero_con_advertencia(self, unidad):
        res = calcular_pedido(F(50), F(0), F(15), unidad, "CERCANO")
        assert res.pedido == 0
        assert ADV_UNIDAD_EMPAQUE_INVALIDA in res.advertencias

    def test_unidad_valida_no_advierte(self):
        assert calcular_pedido(F(5), F(0), F(0), 1, "CERCANO").advertencias == ()

    def test_z_negativo_no_activa_fallback(self):
        assert _pedido(0, 0, -3, 1) == 0

    def test_valor_sin_precio_es_cero(self):
        assert valor_pedido(F(5), None) == 0

    def test_cobertura_final_nula_solo_si_n_cero(self):
        assert cobertura_final(F(3), F(2), F(0)) is None
        assert cobertura_final(F(3), F(2), F(-5)) == F(-1)


def _oraculo_pedido_entero(num: int, den: int, u: int, z: F, modo: str):
    """Oráculo independiente en aritmética entera (sin `Fraction`).

    neto = num/den. ROUND lejos de cero: (2|num| + den) // (2 den).
    """
    signo = -1 if num < 0 else 1
    if modo == "CERCANO":
        # neto/u = num / (den*u)
        magnitud = (2 * abs(num) + den * u) // (2 * den * u)
        cuentas = signo * magnitud
    else:
        cuentas = -((-num) // (den * u))  # techo de num/(den*u)
    pedido = max(0, cuentas * u)
    if pedido == 0 and z > 0:
        return z
    return F(pedido)


class TestFronteraDeMitad:
    """Neto exactamente .5 con divisores 21/15/11 y dias 7/15/30."""

    @pytest.mark.parametrize("apertura, divisor", [
        (None, 21), (date(2026, 6, 1), 15), (date(2026, 6, 10), 11),
    ])
    @pytest.mark.parametrize("dias", ["7", "15", "30"])
    @pytest.mark.parametrize("clase", ["AF", "AM", "AS"])
    def test_contra_oraculo_racional(self, apertura, divisor, dias, clase):
        azar = random.Random(f"{divisor}-{dias}-{clase}")
        atr = atributos(fecha_apertura=apertura, dias_entre_pedidos=dias,
                        fecha_corte=date(2026, 9, 15))
        par = parametros_legacy()
        ventana = construir_ventana(atr.fecha_corte, atr.fecha_apertura)
        assert ventana.divisor == divisor
        cob = cobertura_clase(clase, atr, par)
        mitades = 0
        for _ in range(60):
            ventas = tuple(azar.randint(0, 200) for _ in range(6))
            n = demanda_ponderada(
                serie_demanda(entrada(ventas), ventana, par), ventana
            )
            ss = stock_objetivo(n, cob)
            y = azar.randint(0, 300)
            z = F(1, 2) - (ss % 1)  # fuerza neto = entero + 1/2 exacto
            neto = ss - y + z
            assert neto.denominator == 2
            mitades += 1
            for u, modo in ((1, "CERCANO"), (1, "ARRIBA"), (6, "CERCANO")):
                real = calcular_pedido(ss, F(y), z, u, modo).pedido
                esperado = _oraculo_pedido_entero(
                    neto.numerator, neto.denominator, u, z, modo
                )
                assert real == esperado, (ventas, y, u, modo)
        assert mitades == 60
