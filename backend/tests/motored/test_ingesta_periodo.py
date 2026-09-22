"""
Fase 2 "Ingesta", Phase 5 "ADR-9 Period Module" (sdd/motored-pedidos-ingesta,
task 5.1) — `services/ingesta/periodo.py`.

Puro, sin DB ni archivo: el veredicto se calcula sobre un histograma
`{(anio, mes): cantidad}` ya construido por el caller (Fase 4's `ventas.py`,
en la MISMA pasada streaming) contra el conjunto de meses declarados. Cubre
la tabla de decisión completa de ADR-9 (5 filas), el caso límite del
histograma vacío (E6, no debe dividir por cero) y el cómputo de límites de
fecha mes/año incluyendo años bisiestos.
"""
from datetime import date

import pytest

from app.motored.services.ingesta import periodo

# 2026-09 es el mes "actual" de referencia en todo este archivo: adyacente
# anterior 2026-08, adyacente posterior 2026-10 (mismo mes que reprodujo el
# bug histórico real del owner, ver design ADR-9 / edge case E1).
_SEP_2026 = {(2026, 9)}


# ---------------------------------------------------------------------------
# bounds_de_mes / construir_periodo_declarado — límites mes/año -> date
# ---------------------------------------------------------------------------


def test_bounds_de_mes_febrero_bisiesto():
    desde, hasta = periodo.bounds_de_mes(2024, 2)
    assert desde == date(2024, 2, 1)
    assert hasta == date(2024, 2, 29)


def test_bounds_de_mes_febrero_no_bisiesto():
    desde, hasta = periodo.bounds_de_mes(2026, 2)
    assert desde == date(2026, 2, 1)
    assert hasta == date(2026, 2, 28)


def test_bounds_de_mes_mes_de_31_dias():
    desde, hasta = periodo.bounds_de_mes(2026, 1)
    assert desde == date(2026, 1, 1)
    assert hasta == date(2026, 1, 31)


def test_construir_periodo_declarado_un_solo_mes():
    desde, hasta = periodo.construir_periodo_declarado(2026, 9)
    assert desde == date(2026, 9, 1)
    assert hasta == date(2026, 9, 30)


def test_construir_periodo_declarado_rango_multi_mes_seed():
    desde, hasta = periodo.construir_periodo_declarado(2026, 1, 2026, 6)
    assert desde == date(2026, 1, 1)
    assert hasta == date(2026, 6, 30)


# ---------------------------------------------------------------------------
# meses_en_rango — conjunto D de (anio, mes) declarados
# ---------------------------------------------------------------------------


def test_meses_en_rango_un_solo_mes():
    meses = periodo.meses_en_rango(date(2026, 9, 1), date(2026, 9, 30))
    assert meses == {(2026, 9)}


def test_meses_en_rango_cruza_fin_de_anio():
    meses = periodo.meses_en_rango(date(2025, 11, 1), date(2026, 1, 31))
    assert meses == {(2025, 11), (2025, 12), (2026, 1)}


def test_meses_en_rango_seed_de_seis_meses():
    meses = periodo.meses_en_rango(date(2026, 1, 1), date(2026, 6, 30))
    assert meses == {(2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5), (2026, 6)}


# ---------------------------------------------------------------------------
# evaluar_periodo — tabla de decisión de ADR-9 (5 filas)
# ---------------------------------------------------------------------------


def test_regla_1_coincidencia_exacta_es_aceptado_silencioso():
    histograma = {(2026, 9): 51203}

    veredicto = periodo.evaluar_periodo(histograma, _SEP_2026, tolerancia_pct=0.5)

    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.ACEPTADO
    assert veredicto.codigo_error is None
    assert veredicto.meses_fuera_adyacentes == ()
    assert veredicto.meses_fuera_no_adyacentes == ()


def test_regla_2_fuera_adyacente_dentro_de_tolerancia_es_advertencia():
    # E2 del design: 12 de 51203 filas dated 2026-08-31 (mes anterior,
    # adyacente) -- 0.023% < 0.5%, dentro de tolerancia.
    histograma = {(2026, 9): 51191, (2026, 8): 12}

    veredicto = periodo.evaluar_periodo(histograma, _SEP_2026, tolerancia_pct=0.5)

    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.ADVERTENCIA
    assert veredicto.meses_fuera_adyacentes == ((2026, 8),)
    assert veredicto.meses_fuera_no_adyacentes == ()
    assert veredicto.filas_fuera_total == 12


def test_regla_3_fuera_adyacente_excede_tolerancia_es_rechazo():
    # E1 del design (el bug histórico real reproducido): TODAS las filas
    # (100%) caen en el mes anterior, adyacente -- pero 100% > 0.5%, así que
    # la adyacencia NO salva al archivo: rechazo por tolerancia excedida.
    histograma = {(2026, 8): 51203}

    veredicto = periodo.evaluar_periodo(histograma, _SEP_2026, tolerancia_pct=0.5)

    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.RECHAZO
    assert veredicto.codigo_error == periodo.CODIGO_PERIODO_NO_COINCIDE
    assert veredicto.filas_fuera_total == 51203


def test_regla_4_fuera_no_adyacente_rechaza_sin_importar_el_porcentaje():
    # E3 del design: 40 de 51203 filas (0.08% < 0.5%, DENTRO de tolerancia)
    # pero en 2019-04, que no es adyacente a 2026-09 -- rechazo igual.
    histograma = {(2026, 9): 51163, (2019, 4): 40}

    veredicto = periodo.evaluar_periodo(histograma, _SEP_2026, tolerancia_pct=0.5)

    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.RECHAZO
    assert veredicto.codigo_error == periodo.CODIGO_PERIODO_NO_COINCIDE
    assert veredicto.meses_fuera_no_adyacentes == ((2019, 4),)


def test_regla_4_tiene_prioridad_sobre_regla_3_cuando_hay_ambas():
    # Un mes no-adyacente (2019-04) Y un mes adyacente que por sí solo
    # excedería tolerancia (2026-08 con 100%) -- el rechazo es el mismo
    # E-CARGA-040 en cualquier caso, pero la no-adyacencia debe detectarse.
    histograma = {(2026, 8): 51163, (2019, 4): 40}

    veredicto = periodo.evaluar_periodo(histograma, _SEP_2026, tolerancia_pct=0.5)

    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.RECHAZO
    assert veredicto.meses_fuera_no_adyacentes == ((2019, 4),)


def test_regla_5_mes_declarado_sin_datos_es_advertencia_otros_meses_aplican():
    # E5 del design: seed de 6 meses, abril sin filas -- advertencia, el
    # resto de los meses declarados aplica igual (no hay rechazo).
    meses_declarados = periodo.meses_en_rango(date(2026, 1, 1), date(2026, 6, 30))
    histograma = {
        (2026, 1): 100, (2026, 2): 100, (2026, 3): 100,
        (2026, 5): 100, (2026, 6): 100,
    }

    veredicto = periodo.evaluar_periodo(histograma, meses_declarados, tolerancia_pct=0.5)

    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.ACEPTADO
    assert veredicto.meses_declarados_sin_datos == ((2026, 4),)


def test_regla_5_combinada_con_advertencia_adyacente():
    # Declarado agosto-septiembre 2026 (seed de 2 meses): septiembre sin
    # ninguna fila propia (regla 5) + 2 filas de julio, adyacente-anterior a
    # agosto (el mes más temprano declarado), dentro de tolerancia -- ambas
    # advertencias deben coexistir en el mismo veredicto.
    meses_declarados = {(2026, 8), (2026, 9)}
    histograma = {(2026, 8): 500, (2026, 9): 0, (2026, 7): 2}

    veredicto = periodo.evaluar_periodo(histograma, meses_declarados, tolerancia_pct=1.0)

    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.ADVERTENCIA
    assert veredicto.meses_fuera_adyacentes == ((2026, 7),)
    assert veredicto.meses_declarados_sin_datos == ((2026, 9),)


def test_histograma_vacio_no_crashea_y_no_divide_por_cero():
    # E6 del design: TODAS las fechas del archivo eran implausibles -- el
    # histograma queda vacío (ninguna fila con fecha válida contribuye). El
    # comparador no tiene evidencia para contradecir el período declarado;
    # la carga ya está 100% rechazada por otra vía (todo-error por fila).
    veredicto = periodo.evaluar_periodo({}, _SEP_2026, tolerancia_pct=0.5)

    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.ACEPTADO
    assert veredicto.filas_totales == 0
    assert veredicto.filas_fuera_total == 0


def test_meses_declarados_vacio_es_un_error_de_programador():
    with pytest.raises(ValueError):
        periodo.evaluar_periodo({(2026, 9): 10}, set(), tolerancia_pct=0.5)


# ---------------------------------------------------------------------------
# TIPOS_QUE_DECLARAN_PERIODO — tabla "¿Declara?" de ADR-9
# ---------------------------------------------------------------------------


def test_tipos_que_declaran_periodo_incluye_los_cuatro_tipos_de_la_tabla():
    assert periodo.TIPOS_QUE_DECLARAN_PERIODO == frozenset(
        {"VENTAS", "INVENTARIO", "BACKORDER", "DEMANDA_PERDIDA"}
    )
