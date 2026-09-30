"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S3b-1) — mes en curso
(M0) en modo PONDERADO detrás de `modo_mes_en_curso` (decisión #15).

Mapa spec -> tests: [§10.1-PONDERADO] TestEjemploResuelto, convergencia y
tope TestFormula, divisor dinámico TestDivisorDinamico, demanda perdida en M0
TestDemandaPerdida, M0 fuera de FMS/universo/omisión TestFueraDeFmsYUniverso,
[OFF-ID] TestExcluidoIdentico, consolidación TestConsolidacion, origen de d y
modo efectivo (A-CORRIDA-105/106) TestModoEfectivo.

Convención: corte 2026-09-29 (ventana Mar..Ago), D = 30 salvo que se indique.
"""
import dataclasses
import random
from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

import pytest

from app.motored.services.motor.mes_en_curso import (
    peso_m0,
    resolver_mes_en_curso,
)
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import (
    COD_MES_EN_CURSO_CORTO,
    COD_MES_EN_CURSO_NO_DISPONIBLE,
    COD_SUCURSAL_OMITIDA,
    ESTADO_OMITIDA,
    MesEnCurso,
    NodoMaestro,
)
from tests.motored.fixtures.motor.constructores import (
    VENTAS_PATRON,
    atributos,
    entrada,
    parametros_legacy,
)

F = Fraction
PESOS = (1, 2, 3, 4, 5, 6)


def _mes(d=14, dias_mes=30, tope=3, modo="PONDERADO"):
    return MesEnCurso(
        modo=modo, dias_transcurridos=d, dias_del_mes=dias_mes,
        tope=F(tope),
    )


def _params(d=14, dias_mes=30, tope=3, modo="PONDERADO", **extra):
    return parametros_legacy(
        mes_en_curso=_mes(d, dias_mes, tope, modo), **extra
    )


def _calcular(entradas, params, atr=None, resoluciones=None):
    return calcular_sucursal(
        entradas, atr or atributos(), params, resoluciones
    )


def _unica(entradas, params, atr=None):
    resultado = _calcular(entradas, params, atr)
    assert len(resultado.lineas) == 1
    return resultado.lineas[0]


def _suma_pesada(ventas):
    return sum(p * F(v) for p, v in zip(PESOS, ventas))


def _fila_patron(**kw):
    return entrada(
        VENTAS_PATRON, codigo="94109-12000S", precio="460.75",
        inventario=27, transito=70, ajuste=-3, **kw,
    )


# --- [§10.1-PONDERADO] ----------------------------------------------------


class TestEjemploResuelto:
    def test_63_unidades_al_dia_14_de_30_dan_pedido_61(self):
        linea = _unica([_fila_patron(venta_m0=63)], _params())
        assert linea.venta_m0_proyectada == F(135)
        assert linea.n == F(33525, 364)
        assert linea.stock_objetivo == F(33525, 364) * F(7, 4)
        assert linea.pedido == F(61)
        assert linea.cobertura_final == F(158) / F(33525, 364)

    def test_el_peso_del_mes_en_curso_es_49_sobre_15(self):
        assert peso_m0(_mes(14, 30)) == F(49, 15)

    def test_la_cobertura_final_ronda_1_7155(self):
        linea = _unica([_fila_patron(venta_m0=63)], _params())
        assert round(float(linea.cobertura_final), 4) == 1.7155

    def test_con_excluido_el_mismo_caso_da_50(self):
        excluido = _params(modo="EXCLUIDO")
        linea = _unica([_fila_patron(venta_m0=63)], excluido)
        assert linea.pedido == F(50)
        assert linea.n == F(598, 7)
        assert linea.venta_m0_proyectada is None


# --- fórmula: convergencia, tope, sin tope --------------------------------


class TestFormula:
    def test_convergencia_con_d_igual_a_D(self):
        ventas = VENTAS_PATRON
        linea = _unica(
            [entrada(ventas, venta_m0=40)], _params(d=30, dias_mes=30)
        )
        assert peso_m0(_mes(30, 30)) == F(7)
        assert linea.venta_m0_proyectada == F(40)
        assert linea.n == (_suma_pesada(ventas) + 7 * 40) / 28

    def test_el_tope_ata_cuando_la_proyeccion_lo_supera(self):
        # M3..M1 = 20, 10, 5: tope 3 * 20 = 60 -> min(600, 100 + 60) = 160
        ventas = (0, 0, 0, 20, 10, 5)
        linea = _unica(
            [entrada(ventas, venta_m0=100)], _params(d=5, dias_mes=30)
        )
        w0 = F(7, 6)
        assert linea.venta_m0_proyectada == F(160)
        assert linea.n == (_suma_pesada(ventas) + 160 * w0) / (21 + w0)

    def test_tope_cero_no_limita(self):
        ventas = (0, 0, 0, 20, 10, 5)
        linea = _unica(
            [entrada(ventas, venta_m0=100)],
            _params(d=5, dias_mes=30, tope=0),
        )
        assert linea.venta_m0_proyectada == F(600)

    def test_el_tope_no_ata_cuando_la_proyeccion_es_menor(self):
        ventas = (0, 0, 0, 20, 10, 5)
        linea = _unica(
            [entrada(ventas, venta_m0=10)], _params(d=15, dias_mes=30)
        )
        assert linea.venta_m0_proyectada == F(20)

    def test_venta_negativa_se_proyecta_tal_cual(self):
        ventas = (10, 10, 10, 10, 10, 10)
        linea = _unica(
            [entrada(ventas, venta_m0=-4)], _params(d=15, dias_mes=30)
        )
        assert linea.venta_m0_proyectada == F(-8)
        w0 = F(7, 2)
        assert linea.n == (_suma_pesada(ventas) - 8 * w0) / (21 + w0)

    def test_sin_datos_de_m0_cuenta_como_cero(self):
        ventas = (10, 10, 10, 10, 10, 10)
        linea = _unica([entrada(ventas)], _params(d=15, dias_mes=30))
        assert linea.venta_m0_proyectada == F(0)
        assert linea.n == _suma_pesada(ventas) / (21 + F(7, 2))

    @pytest.mark.parametrize("semilla", range(6))
    def test_el_pedido_coincide_con_un_oraculo_entero(self, semilla):
        azar = random.Random(semilla)
        for _ in range(40):
            ventas = tuple(azar.randint(1, 90) for _ in range(6))
            v0 = azar.randint(0, 120)
            dias_mes = azar.choice([28, 30, 31])
            d = azar.randint(5, dias_mes)
            inv = azar.randint(0, 200)
            linea = _unica(
                [entrada(ventas, venta_m0=v0, inventario=inv)],
                _params(d=d, dias_mes=dias_mes),
            )
            assert linea.pedido == _oraculo_pedido(
                ventas, v0, d, dias_mes, inv
            )

    def test_mitad_exacta_redondea_lejos_de_cero(self):
        # d = D: N = (1794 + 7*10)/28, SS = N * 7/4 = 1864/16 = 116,5
        linea = _unica(
            [entrada(VENTAS_PATRON, venta_m0=10)],
            _params(d=30, dias_mes=30),
        )
        assert linea.stock_objetivo == F(233, 2)
        assert linea.pedido == F(117)

    def test_entradas_invalidas_se_rechazan(self):
        for d, dias_mes in ((0, 30), (31, 30), (-1, 30), (5, 0)):
            with pytest.raises(ValueError):
                _calcular(
                    [entrada(VENTAS_PATRON, venta_m0=1)],
                    _params(d=d, dias_mes=dias_mes),
                )
        with pytest.raises(ValueError):
            _calcular(
                [entrada(VENTAS_PATRON, venta_m0=1)], _params(tope=-1)
            )


def _oraculo_pedido(ventas, v0, d, dias_mes, inventario):
    """Pedido con aritmética de enteros: sin Fraction ni redondeos previos."""
    cerrado = sum(p * v for p, v in zip(PESOS, ventas))
    proy_num = v0 * dias_mes  # v0_proy = proy_num / d
    tope_num = (v0 * d + 3 * max(ventas[-3:]) * d)  # v0 + 3*max, sobre d
    proy_num = min(proy_num, tope_num)
    w0_num = 7 * min(d, dias_mes)  # w0 = w0_num / dias_mes
    # N = (cerrado + proy*w0) / (21 + w0), todo sobre d * dias_mes
    num = cerrado * d * dias_mes + proy_num * w0_num
    den = (21 * dias_mes + w0_num) * d
    # SS = N * 7/4; neto = SS - inventario, redondeo mitad lejos de cero
    ss_num, ss_den = num * 7, den * 4
    neto_num = ss_num - inventario * ss_den
    if neto_num <= 0:
        return F(0)
    return F((2 * neto_num + ss_den) // (2 * ss_den))


# --- divisor dinámico + w0 ------------------------------------------------


class TestDivisorDinamico:
    def test_el_divisor_dinamico_suma_w0(self):
        apertura = date(2026, 6, 1)  # opera Jun, Jul, Ago: pesos 4, 5, 6
        ventas = (0, 0, 0, 10, 20, 30)
        linea = _unica(
            [entrada(ventas, venta_m0=15)],
            _params(d=15, dias_mes=30),
            atributos(fecha_apertura=apertura),
        )
        w0 = F(7, 2)
        dinamico = 4 * 10 + 5 * 20 + 6 * 30
        assert linea.venta_m0_proyectada == F(30)
        assert linea.n == (dinamico + 30 * w0) / (15 + w0)

    def test_los_meses_no_operados_no_entran_al_tope(self):
        apertura = date(2026, 8, 1)  # sólo opera Ago (peso 6)
        ventas = (99, 99, 99, 99, 99, 10)
        linea = _unica(
            [entrada(ventas, venta_m0=50)],
            _params(d=5, dias_mes=30),
            atributos(fecha_apertura=apertura),
        )
        # d1 = 10; d2 = d3 = 0 (no operados): tope = 50 + 3*10 = 80
        assert linea.venta_m0_proyectada == F(80)

    def test_sucursal_abierta_en_m0_sigue_omitida(self):
        resultado = _calcular(
            [entrada(VENTAS_PATRON, venta_m0=50)], _params(),
            atributos(fecha_apertura=date(2026, 9, 5)),
        )
        assert resultado.estado == ESTADO_OMITIDA
        assert resultado.advertencias[0].codigo == COD_SUCURSAL_OMITIDA
        assert resultado.lineas == ()


# --- demanda perdida en M0 ------------------------------------------------


class TestDemandaPerdida:
    def test_con_ambos_switches_encendidos_la_perdida_suma(self):
        fila = entrada((20,) * 6, venta_m0=40, perdida_m0=10)
        params = _params(d=15, dias_mes=30, incluir_demanda_perdida=True)
        assert _unica([fila], params).venta_m0_proyectada == F(100)

    def test_el_factor_multiplica_la_perdida_de_m0(self):
        fila = entrada((20,) * 6, venta_m0=40, perdida_m0=10)
        params = _params(
            d=15, dias_mes=30, incluir_demanda_perdida=True,
            factor_demanda_perdida=F(2),
        )
        assert _unica([fila], params).venta_m0_proyectada == F(120)

    def test_con_perdida_apagada_se_ignora_aun_con_ponderado(self):
        fila = entrada((20,) * 6, venta_m0=40, perdida_m0=10)
        params = _params(d=15, dias_mes=30)
        assert _unica([fila], params).venta_m0_proyectada == F(80)

    def test_la_perdida_cuenta_en_el_tope_cuando_esta_encendida(self):
        ventas = (0, 0, 0, 0, 0, 10)
        perdidas = (0, 0, 0, 0, 0, 10)
        fila = entrada(ventas, perdidas, venta_m0=100)
        apagada = _params(d=5, dias_mes=30)
        encendida = _params(d=5, dias_mes=30, incluir_demanda_perdida=True)
        # apagada: 100 + 3*10 = 130; encendida: d1 = 20 -> 100 + 3*20 = 160
        assert _unica([fila], apagada).venta_m0_proyectada == F(130)
        assert _unica([fila], encendida).venta_m0_proyectada == F(160)

    def test_la_perdida_sola_en_m0_no_crea_linea(self):
        fila = entrada((0,) * 6, perdida_m0=30)
        params = _params(incluir_demanda_perdida=True)
        assert _calcular([fila], params).lineas == ()


# --- M0 no cuenta para FMS ni universo ------------------------------------


class TestFueraDeFmsYUniverso:
    def test_referencia_con_ventas_solo_en_m0_no_tiene_linea(self):
        fila = entrada((0,) * 6, venta_m0=50)
        assert _calcular([fila], _params()).lineas == ()

    def test_una_venta_temprana_no_cambia_la_letra_fms(self):
        con_m0 = entrada((0, 0, 0, 0, 0, 10), venta_m0=8)
        sin_m0 = entrada((0, 0, 0, 0, 0, 10))
        linea = _unica([con_m0], _params())
        referencia = _unica([sin_m0], _params(modo="EXCLUIDO"))
        assert linea.clase_fms == "M" and linea.meses_con_venta == 1
        assert linea.cobertura == referencia.cobertura

    def test_abc_usa_n_con_m0_y_fms_no(self):
        a = entrada((10,) * 6, codigo="REF-A")
        b = entrada((5,) * 6, codigo="REF-B", venta_m0=300)
        pond = _calcular([a, b], _params(d=15, dias_mes=30))
        excl = _calcular([a, b], _params(modo="EXCLUIDO"))
        assert [x.entrada.codigo for x in pond.lineas] == ["REF-B", "REF-A"]
        assert [x.entrada.codigo for x in excl.lineas] == ["REF-A", "REF-B"]
        assert pond.lineas[0].clase_fms == "F"


# --- [OFF-ID] EXCLUIDO idéntico -------------------------------------------


def _salidas(resultado):
    """Todo lo calculado; las líneas se comparan sin los insumos de M0."""
    return (
        resultado.estado, resultado.resumen, resultado.advertencias,
        resultado.divisor, resultado.excluidas,
        tuple(_sin_m0(linea) for linea in resultado.lineas),
    )


def _sin_m0(linea):
    crudo = dataclasses.replace(
        linea.entrada, venta_m0=None, perdida_m0=None
    )
    return dataclasses.replace(linea, entrada=crudo)


class TestExcluidoIdentico:
    def test_venta_m0_proyectada_es_nula_con_excluido(self):
        fila = entrada(VENTAS_PATRON, venta_m0=63)
        assert _unica([fila], _params(modo="EXCLUIDO")) \
            .venta_m0_proyectada is None
        assert _unica([fila], parametros_legacy()) \
            .venta_m0_proyectada is None

    @pytest.mark.parametrize("semilla", range(8))
    def test_propiedad_la_salida_no_depende_de_m0(self, semilla):
        azar = random.Random(semilla)
        base = [
            entrada(
                tuple(azar.randint(0, 60) for _ in range(6)),
                codigo=f"R{i}", inventario=azar.randint(0, 50),
            )
            for i in range(12)
        ]
        for perdida_on in (False, True):
            legacy = parametros_legacy(incluir_demanda_perdida=perdida_on)
            referencia = _salidas(_calcular(base, legacy))
            for _ in range(10):
                dias_mes = azar.choice([28, 30, 31])
                params = _params(
                    d=azar.randint(1, dias_mes), dias_mes=dias_mes,
                    tope=azar.choice([0, 1, 3, 10]), modo="EXCLUIDO",
                    incluir_demanda_perdida=perdida_on,
                )
                con_m0 = [
                    _con_m0(fila, azar.randint(-5, 500),
                            azar.randint(0, 99))
                    for fila in base
                ]
                assert _salidas(_calcular(con_m0, params)) == referencia

    def test_los_caminos_de_respaldo_son_identicos_a_excluido(self):
        fila = entrada(VENTAS_PATRON, venta_m0=63, inventario=27)
        legacy = _calcular([fila], parametros_legacy())
        resolucion = resolver_mes_en_curso(
            "PONDERADO", date(2026, 9, 29), None, F(3), 5
        )
        respaldo = parametros_legacy(mes_en_curso=resolucion.mes_en_curso)
        assert resolucion.mes_en_curso is None
        assert _calcular([fila], respaldo) == legacy


def _con_m0(fila, venta, perdida):
    return dataclasses.replace(
        fila, venta_m0=Decimal(venta), perdida_m0=Decimal(perdida)
    )


# --- consolidación compone con M0 -----------------------------------------


IDS = {"A": UUID(int=1), "B": UUID(int=2)}


class TestConsolidacion:
    def test_m0_de_la_vieja_se_transfiere_a_la_sustituta(self):
        vieja = entrada(
            (5, 0, 3, 0, 2, 4), codigo="REF-A", referencia_id=IDS["A"],
            venta_m0=2,
        )
        nueva = entrada(
            (1, 1, 1, 1, 1, 1), codigo="REF-B", referencia_id=IDS["B"],
            venta_m0=1,
        )
        maestro = {
            IDS["A"]: NodoMaestro(IDS["A"], False, IDS["B"]),
        }
        params = _params(consolidar_sustituidas=True)
        con = _calcular(
            [vieja, nueva], params, resoluciones=resolver_cadenas(maestro)
        )
        junta = entrada(
            (6, 1, 4, 1, 3, 5), codigo="REF-B", referencia_id=IDS["B"],
            venta_m0=3,
        )
        esperada = _unica([junta], _params())
        linea = con.lineas[0]
        assert linea.entrada.codigo == "REF-B"
        assert linea.venta_m0_proyectada == F(3 * 30, 14)
        assert linea.n == esperada.n


# --- origen de d y modo efectivo ------------------------------------------


CORTE = date(2026, 9, 21)


def _resolver(modo="PONDERADO", corte=CORTE, ultima=date(2026, 9, 14),
              tope=3, minimo=5):
    return resolver_mes_en_curso(modo, corte, ultima, F(tope), minimo)


class TestModoEfectivo:
    def test_corte_el_21_con_ultima_venta_el_14_da_d_14(self):
        resolucion = _resolver()
        assert resolucion.advertencia is None
        assert resolucion.mes_en_curso == _mes(14, 30, 3)

    def test_ultima_venta_posterior_al_corte_se_recorta_al_corte(self):
        resolucion = _resolver(ultima=date(2026, 9, 28))
        assert resolucion.mes_en_curso.dias_transcurridos == 21

    def test_dias_del_mes_sigue_el_calendario(self):
        bisiesto = _resolver(
            corte=date(2028, 2, 20), ultima=date(2028, 2, 10)
        )
        assert bisiesto.mes_en_curso == _mes(10, 29, 3)

    def test_excluido_configurado_no_avisa(self):
        resolucion = _resolver(modo="EXCLUIDO")
        assert resolucion.mes_en_curso is None
        assert resolucion.advertencia is None

    def test_sin_carga_del_mes_avisa_105(self):
        resolucion = _resolver(ultima=None)
        assert resolucion.mes_en_curso is None
        assert resolucion.advertencia.codigo == COD_MES_EN_CURSO_NO_DISPONIBLE
        assert COD_MES_EN_CURSO_NO_DISPONIBLE == "A-CORRIDA-105"

    def test_ultima_venta_fuera_del_mes_avisa_105(self):
        resolucion = _resolver(ultima=date(2026, 8, 31))
        assert resolucion.mes_en_curso is None
        assert resolucion.advertencia.codigo == COD_MES_EN_CURSO_NO_DISPONIBLE

    def test_menos_de_min_dias_avisa_106(self):
        resolucion = _resolver(ultima=date(2026, 9, 4))
        assert resolucion.mes_en_curso is None
        assert resolucion.advertencia.codigo == COD_MES_EN_CURSO_CORTO
        assert COD_MES_EN_CURSO_CORTO == "A-CORRIDA-106"
        assert resolucion.advertencia.mensaje == (
            "Mes en curso con solo 4 días: excluido del cálculo"
        )

    def test_con_exactamente_min_dias_es_ponderado(self):
        resolucion = _resolver(ultima=date(2026, 9, 5))
        assert resolucion.advertencia is None
        assert resolucion.mes_en_curso.dias_transcurridos == 5

    def test_min_dias_configurable(self):
        resolucion = _resolver(ultima=date(2026, 9, 9), minimo=10)
        assert resolucion.advertencia.codigo == COD_MES_EN_CURSO_CORTO

    def test_el_tope_pasa_al_resultado(self):
        assert _resolver(tope=0).mes_en_curso.tope == F(0)
