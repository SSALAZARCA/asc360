"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S3-1) — consolidación
de sustituidas detrás de `consolidar_sustituidas` (decisiones #10, #12, #13,
T20 y [OFF-ID]).

Convención de los fixtures: cada referencia se identifica con una letra (A,
B, C...) y sus ventas van de M6 a M1. Corte 2026-09-29: ventana Mar..Ago.
"""
from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

import pytest

from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import (
    COD_CADENA_CICLICA,
    MOTIVO_SIN_REEMPLAZO,
    MOTIVO_SUSTITUIDA,
    NodoMaestro,
)
from tests.motored.fixtures.motor.constructores import (
    atributos,
    entrada,
    parametros_legacy,
)

IDS = {letra: UUID(int=i) for i, letra in enumerate("ABCDEFX", start=1)}
CEROS = (0, 0, 0, 0, 0, 0)
UNOS = (1, 1, 1, 1, 1, 1)


def _dec(valores):
    return tuple(Decimal(v) for v in valores)


def _ref(letra, ventas=CEROS, perdidas=CEROS, **kw):
    return entrada(
        ventas, perdidas, codigo=f"REF-{letra}",
        referencia_id=IDS[letra], **kw,
    )


def _nodo(letra, *, activa=True, sustituida_por=None):
    destino = None if sustituida_por is None else IDS[sustituida_por]
    return NodoMaestro(IDS[letra], activa, destino)


def _vieja(letra, sustituida_por=None):
    """Referencia inactiva (con o sin sustituta declarada)."""
    return _nodo(letra, activa=False, sustituida_por=sustituida_por)


def _maestro(*nodos):
    return {n.referencia_id: n for n in nodos}


def _calcular(entradas, nodos=(), *, consolidar=True, perdida=False,
              sucursal=None):
    params = parametros_legacy(
        consolidar_sustituidas=consolidar, incluir_demanda_perdida=perdida
    )
    return calcular_sucursal(
        entradas, sucursal or atributos(), params,
        resolver_cadenas(_maestro(*nodos)),
    )


def _codigos(resultado):
    return [linea.entrada.codigo for linea in resultado.lineas]


def _linea_de(resultado, letra):
    return next(
        linea for linea in resultado.lineas
        if linea.entrada.referencia_id == IDS[letra]
    )


# --- resolver_cadenas -------------------------------------------------------


def test_cadena_simple_resuelve_a_la_sustituta_activa():
    res = resolver_cadenas(_maestro(_vieja("A", "B")))
    assert res[IDS["A"]].final_id == IDS["B"]
    assert res[IDS["A"]].motivo == MOTIVO_SUSTITUIDA
    assert res[IDS["A"]].cadena == (IDS["A"], IDS["B"])


def test_cadena_transitiva_a_b_c_resuelve_a_la_final():
    res = resolver_cadenas(_maestro(
        _vieja("A", "B"), _vieja("B", "C"), _nodo("C")
    ))
    assert res[IDS["A"]].final_id == IDS["C"]
    assert res[IDS["B"]].final_id == IDS["C"]
    assert res[IDS["A"]].cadena == (IDS["A"], IDS["B"], IDS["C"])
    assert res[IDS["C"]].motivo is None


def test_una_activa_con_sustituta_propia_tambien_se_sigue():
    res = resolver_cadenas(_maestro(_nodo("A", sustituida_por="B")))
    assert res[IDS["A"]].final_id == IDS["B"]


def test_ciclo_y_autorreferencia_quedan_sin_reemplazo():
    res = resolver_cadenas(_maestro(
        _vieja("A", "B"), _vieja("B", "A"), _vieja("C", "C"),
    ))
    for letra in "ABC":
        assert res[IDS[letra]].final_id is None
        assert res[IDS[letra]].motivo == MOTIVO_SIN_REEMPLAZO
        assert res[IDS[letra]].ciclo is True


def test_ciclo_con_cola_tambien_es_ciclo():
    res = resolver_cadenas(_maestro(
        _vieja("A", "B"), _vieja("B", "C"), _vieja("C", "B"),
    ))
    assert res[IDS["A"]].ciclo is True
    assert res[IDS["A"]].final_id is None


def test_cadena_que_termina_en_inactiva_no_es_ciclo():
    res = resolver_cadenas(_maestro(_vieja("A", "B"), _vieja("B")))
    assert res[IDS["A"]].motivo == MOTIVO_SIN_REEMPLAZO
    assert res[IDS["B"]].motivo == MOTIVO_SIN_REEMPLAZO
    assert res[IDS["A"]].ciclo is False


def test_sustituta_fuera_del_maestro_es_final():
    res = resolver_cadenas(_maestro(_vieja("A", "X")))
    assert res[IDS["A"]].final_id == IDS["X"]


def _cadena_larga(nodos_totales):
    ids = [UUID(int=1000 + i) for i in range(nodos_totales)]
    nodos = [
        NodoMaestro(ids[i], False, ids[i + 1])
        for i in range(nodos_totales - 1)
    ]
    nodos.append(NodoMaestro(ids[-1], True, None))
    return ids, {n.referencia_id: n for n in nodos}


def test_cadena_de_50_nodos_resuelve_y_la_de_51_se_corta():
    ids, corta = _cadena_larga(50)
    assert resolver_cadenas(corta)[ids[0]].final_id == ids[-1]
    ids, larga = _cadena_larga(51)
    resolucion = resolver_cadenas(larga)[ids[0]]
    assert resolucion.final_id is None and resolucion.ciclo is True


# --- T20: transferencia de ventas ------------------------------------------


def test_t20_las_ventas_pasan_mes_a_mes_a_la_sustituta():
    resultado = _calcular(
        [_ref("A", (5, 0, 3, 0, 2, 4)), _ref("B", UNOS)],
        [_vieja("A", "B")],
    )
    (linea,) = resultado.lineas
    assert linea.entrada.ventas == _dec((6, 1, 4, 1, 3, 5))
    assert linea.n == Fraction(6 + 2 + 12 + 4 + 15 + 30, 21)


def test_t20_la_vieja_sale_del_pedido_y_queda_listada():
    resultado = _calcular(
        [_ref("A", (5, 0, 3, 0, 2, 4)), _ref("B", UNOS)],
        [_vieja("A", "B")],
    )
    assert _codigos(resultado) == ["REF-B"]
    (excluida,) = resultado.excluidas
    assert excluida.entrada.codigo == "REF-A"
    assert excluida.motivo == MOTIVO_SUSTITUIDA
    assert excluida.sustituta_final_id == IDS["B"]
    assert excluida.sustituta_final_codigo == "REF-B"
    assert excluida.entrada.ventas == _dec((5, 0, 3, 0, 2, 4))


def test_cadena_a_b_c_las_dos_viejas_van_a_la_final():
    resultado = _calcular(
        [_ref("A", (1, 0, 0, 0, 0, 0)), _ref("B", (0, 2, 0, 0, 0, 0)),
         _ref("C", (0, 0, 3, 0, 0, 0))],
        [_vieja("A", "B"), _vieja("B", "C")],
    )
    assert _codigos(resultado) == ["REF-C"]
    assert _linea_de(resultado, "C").entrada.ventas == _dec(
        (1, 2, 3, 0, 0, 0)
    )
    assert [e.entrada.codigo for e in resultado.excluidas] == [
        "REF-A", "REF-B",
    ]
    assert {e.sustituta_final_id for e in resultado.excluidas} == {IDS["C"]}


def test_la_sustituta_sin_ventas_propias_entra_al_universo():
    resultado = _calcular(
        [_ref("A", (0, 0, 0, 0, 0, 7)), _ref("B")], [_vieja("A", "B")]
    )
    assert _codigos(resultado) == ["REF-B"]
    assert _linea_de(resultado, "B").entrada.ventas == _dec((0,) * 5 + (7,))


def test_la_z_de_la_vieja_no_se_transfiere():
    resultado = _calcular(
        [_ref("A", UNOS, ajuste=5), _ref("B", UNOS, ajuste=-2)],
        [_vieja("A", "B")],
    )
    assert _linea_de(resultado, "B").entrada.ajuste == Decimal(-2)


def test_las_ventas_previas_a_la_apertura_no_se_transfieren_ni_listan():
    sucursal = atributos(fecha_apertura=date(2026, 6, 1))
    resultado = _calcular(
        [_ref("A", (0, 9, 0, 0, 0, 0)), _ref("B", (0, 0, 0, 1, 1, 1))],
        [_vieja("A", "B")], sucursal=sucursal,
    )
    assert resultado.divisor == 15
    assert _linea_de(resultado, "B").n == Fraction(4 + 5 + 6, 15)
    assert resultado.excluidas == ()


def test_el_divisor_dinamico_compone_con_la_transferencia():
    sucursal = atributos(fecha_apertura=date(2026, 6, 1))
    resultado = _calcular(
        [_ref("A", (0, 0, 0, 2, 0, 3)), _ref("B", (0, 0, 0, 1, 1, 1))],
        [_vieja("A", "B")], sucursal=sucursal,
    )
    assert _linea_de(resultado, "B").n == Fraction(3 * 4 + 5 + 4 * 6, 15)


# --- demanda perdida (#13) --------------------------------------------------


def _perdidas_m2(cantidad):
    return (0, 0, 0, 0, cantidad, 0)


def _par_con_perdida():
    return [
        _ref("A", (0, 0, 0, 0, 3, 0), _perdidas_m2(4)),
        _ref("B", (0, 0, 0, 0, 2, 0), _perdidas_m2(1)),
    ]


def test_13_con_ambos_switches_la_perdida_tambien_se_transfiere():
    resultado = _calcular(
        _par_con_perdida(), [_vieja("A", "B")], perdida=True
    )
    assert _linea_de(resultado, "B").n == Fraction((3 + 2 + 5) * 5, 21)


def test_13_con_perdida_apagada_no_juega_ningun_papel():
    resultado = _calcular(
        _par_con_perdida(), [_vieja("A", "B")], perdida=False
    )
    assert _linea_de(resultado, "B").n == Fraction((3 + 2) * 5, 21)


def test_13_el_factor_se_aplica_una_sola_vez_sobre_lo_consolidado():
    params = parametros_legacy(
        consolidar_sustituidas=True, incluir_demanda_perdida=True,
        factor_demanda_perdida=Fraction(2),
    )
    resultado = calcular_sucursal(
        _par_con_perdida(), atributos(), params,
        resolver_cadenas(_maestro(_vieja("A", "B"))),
    )
    assert _linea_de(resultado, "B").n == Fraction((3 + 2 + 10) * 5, 21)


def test_la_perdida_sola_de_la_vieja_no_crea_listado_pero_si_transfiere():
    resultado = _calcular(
        [_ref("A", CEROS, _perdidas_m2(4)), _ref("B", (0, 0, 0, 0, 2, 0))],
        [_vieja("A", "B")], perdida=True,
    )
    assert resultado.excluidas == ()
    assert _linea_de(resultado, "B").n == Fraction((2 + 4) * 5, 21)


# --- V/W/X (#10c) -----------------------------------------------------------


def _caso_netting():
    """SS de B = 100 (N 400/7, clase F, cobertura 7/4)."""
    return [
        _ref("A", (0, 0, 0, 0, 60, 100), inventario=30, transito=20,
             backorder=5),
        _ref("B", (0, 0, 0, 0, 0, 50), inventario=10),
    ]


def test_t20_el_stock_de_la_vieja_se_resta_del_pedido_de_la_sustituta():
    resultado = _calcular(_caso_netting(), [_vieja("A", "B")])
    linea = _linea_de(resultado, "B")
    assert linea.stock_objetivo == Fraction(100)
    assert linea.inventario_efectivo == Fraction(65)
    assert linea.pedido == Fraction(35)


def test_sin_consolidar_cada_una_va_con_su_propio_stock():
    resultado = _calcular(
        _caso_netting(), [_vieja("A", "B")], consolidar=False
    )
    assert sorted(_codigos(resultado)) == ["REF-A", "REF-B"]
    assert _linea_de(resultado, "A").inventario_efectivo == Fraction(55)
    assert _linea_de(resultado, "B").inventario_efectivo == Fraction(10)


def test_la_vieja_con_stock_y_sin_ventas_igual_resta_a_la_sustituta():
    resultado = _calcular(
        [_ref("A", CEROS, inventario=30), _ref("B", (0, 0, 0, 0, 0, 9),
                                                inventario=1)],
        [_vieja("A", "B")],
    )
    assert _linea_de(resultado, "B").inventario_efectivo == Fraction(31)
    (excluida,) = resultado.excluidas
    assert excluida.entrada.codigo == "REF-A"
    assert excluida.motivo == MOTIVO_SUSTITUIDA


def test_el_listado_se_limita_a_ventas_en_ventana_o_vwx_positivo():
    resultado = _calcular(
        [_ref("A"), _ref("B", (0, 0, 0, 0, 0, 5))], [_vieja("A", "B")]
    )
    assert resultado.excluidas == ()
    assert _codigos(resultado) == ["REF-B"]


def test_no_hay_doble_conteo_del_stock_de_la_cadena():
    entradas = [
        _ref("A", (1, 0, 0, 0, 0, 0), inventario=4, transito=1),
        _ref("B", (0, 1, 0, 0, 0, 0), inventario=6, backorder=2),
        _ref("C", (0, 0, 1, 0, 0, 0), inventario=9),
    ]
    resultado = _calcular(
        entradas, [_vieja("A", "B"), _vieja("B", "C")]
    )
    assert _linea_de(resultado, "C").inventario_efectivo == Fraction(22)


# --- sin reemplazo (#12) ----------------------------------------------------


def _base_c():
    return _ref("C", (10, 10, 10, 10, 10, 10), inventario=3)


def test_12_inactiva_sin_sustituta_sale_sin_influir_y_queda_listada():
    sola = _calcular([_base_c()])
    resultado = _calcular(
        [_base_c(), _ref("A", (99,) * 6, inventario=50)], [_vieja("A")]
    )
    assert resultado.lineas == sola.lineas
    assert resultado.resumen == sola.resumen
    (excluida,) = resultado.excluidas
    assert excluida.motivo == MOTIVO_SIN_REEMPLAZO
    assert excluida.sustituta_final_id is None
    assert excluida.sustituta_final_codigo is None
    assert resultado.advertencias == ()


def test_12_cadena_que_termina_en_inactiva_lista_a_las_dos():
    resultado = _calcular(
        [_base_c(), _ref("A", UNOS), _ref("B", UNOS)],
        [_vieja("A", "B"), _vieja("B")],
    )
    assert _codigos(resultado) == ["REF-C"]
    assert [e.motivo for e in resultado.excluidas] == [
        MOTIVO_SIN_REEMPLAZO, MOTIVO_SIN_REEMPLAZO,
    ]
    assert resultado.advertencias == ()


def test_12_ciclo_no_cuelga_lista_y_avisa_a_cada_una_con_a_corrida_103():
    resultado = _calcular(
        [_base_c(), _ref("A", UNOS), _ref("B", UNOS)],
        [_vieja("A", "B"), _vieja("B", "A")],
    )
    assert _codigos(resultado) == ["REF-C"]
    assert [e.entrada.codigo for e in resultado.excluidas] == [
        "REF-A", "REF-B",
    ]
    assert [a.codigo for a in resultado.advertencias] == [
        COD_CADENA_CICLICA, COD_CADENA_CICLICA,
    ]
    assert "REF-A" in resultado.advertencias[0].mensaje


def test_12_autorreferencia_queda_sin_reemplazo_con_aviso():
    resultado = _calcular(
        [_base_c(), _ref("A", UNOS)], [_vieja("A", "A")]
    )
    assert _codigos(resultado) == ["REF-C"]
    assert resultado.excluidas[0].motivo == MOTIVO_SIN_REEMPLAZO
    assert [a.codigo for a in resultado.advertencias] == [
        COD_CADENA_CICLICA
    ]


def test_ciclo_sin_ventas_ni_stock_no_se_lista_ni_avisa():
    resultado = _calcular(
        [_base_c(), _ref("A"), _ref("B")],
        [_vieja("A", "B"), _vieja("B", "A")],
    )
    assert resultado.excluidas == ()
    assert resultado.advertencias == ()


def test_sustituta_ausente_de_las_entradas_se_trata_como_sin_reemplazo():
    resultado = _calcular(
        [_base_c(), _ref("A", UNOS)], [_vieja("A", "X")]
    )
    assert _codigos(resultado) == ["REF-C"]
    assert resultado.excluidas[0].motivo == MOTIVO_SIN_REEMPLAZO
    assert resultado.advertencias == ()


def test_excluidas_y_transferidas_no_entran_al_abc_ni_al_resumen():
    resultado = _calcular(
        [_base_c(), _ref("A", UNOS), _ref("B", UNOS), _ref("D", UNOS)],
        [_vieja("A", "B"), _vieja("D")],
    )
    assert [linea.orden_abc for linea in resultado.lineas] == [1, 2]
    assert resultado.lineas[-1].acumulado == Fraction(1)
    assert resultado.resumen.total.unidades == sum(
        (linea.pedido for linea in resultado.lineas), Fraction(0)
    )


def test_el_listado_sale_en_orden_de_codigo():
    resultado = _calcular(
        [_ref("D", UNOS), _ref("A", UNOS), _ref("B", UNOS),
         _ref("C", UNOS)],
        [_vieja("D", "C"), _vieja("A", "C"), _vieja("B", "C")],
    )
    assert [e.entrada.codigo for e in resultado.excluidas] == [
        "REF-A", "REF-B", "REF-D",
    ]


# --- mes en curso, conservación y errores ------------------------------------


def test_el_mes_en_curso_de_la_vieja_tambien_se_transfiere():
    resultado = _calcular(
        [_ref("A", UNOS, venta_m0=4, perdida_m0=1),
         _ref("B", UNOS, venta_m0=2)],
        [_vieja("A", "B")],
    )
    entrada_b = _linea_de(resultado, "B").entrada
    assert entrada_b.venta_m0 == Decimal(6)
    assert entrada_b.perdida_m0 == Decimal(1)


def test_sin_mes_en_curso_en_ninguna_queda_nulo():
    resultado = _calcular(
        [_ref("A", UNOS), _ref("B", UNOS)], [_vieja("A", "B")]
    )
    entrada_b = _linea_de(resultado, "B").entrada
    assert entrada_b.venta_m0 is None and entrada_b.perdida_m0 is None


@pytest.mark.parametrize("largo", [2, 3, 5])
def test_conservacion_de_demanda_y_de_y_a_lo_largo_de_la_cadena(largo):
    letras = "ABCDE"[:largo]
    entradas = [
        _ref(letra, tuple(i + k for k in range(6)), inventario=i + 1,
             transito=2 * i, backorder=i % 2)
        for i, letra in enumerate(letras)
    ]
    nodos = [_vieja(letras[i], letras[i + 1]) for i in range(largo - 1)]
    nodos.append(_nodo(letras[-1]))
    resultado = _calcular(entradas, nodos)
    (linea,) = resultado.lineas
    esperado_ventas = tuple(
        sum(e.ventas[m] for e in entradas) for m in range(6)
    )
    assert linea.entrada.ventas == esperado_ventas
    assert linea.inventario_efectivo == sum(
        (Fraction(e.inventario + e.transito + e.backorder)
         for e in entradas), Fraction(0)
    )
    assert len(resultado.excluidas) == largo - 1


def test_referencia_id_repetido_es_un_error():
    with pytest.raises(ValueError, match="repetid"):
        _calcular(
            [_ref("A", UNOS), _ref("A", UNOS)], [_vieja("A", "B")]
        )


def test_sucursal_omitida_no_lista_nada():
    sucursal = atributos(fecha_apertura=date(2026, 9, 5))
    resultado = _calcular(
        [_ref("A", UNOS), _ref("B", UNOS)], [_vieja("A", "B")],
        sucursal=sucursal,
    )
    assert resultado.lineas == () and resultado.excluidas == ()


def test_meses_mal_formados_en_la_vieja_son_un_error():
    with pytest.raises(ValueError, match="meses"):
        _calcular(
            [_ref("A", (1, 1, 1)), _ref("B", UNOS)], [_vieja("A", "B")]
        )


# --- [OFF-ID] ---------------------------------------------------------------


def _escenario_con_mapa():
    entradas = [
        _base_c(), _ref("A", (5, 0, 3, 0, 2, 4), inventario=7),
        _ref("B", UNOS), _ref("D", UNOS, transito=2),
    ]
    nodos = [_vieja("A", "B"), _vieja("D")]
    return entradas, nodos


def test_off_id_apagado_con_mapa_igual_que_sin_mapa_y_que_el_baseline():
    entradas, nodos = _escenario_con_mapa()
    params = parametros_legacy()
    base = calcular_sucursal(entradas, atributos(), params)
    con_mapa = calcular_sucursal(
        entradas, atributos(), params,
        resolver_cadenas(_maestro(*nodos)),
    )
    mapa_vacio = calcular_sucursal(entradas, atributos(), params, {})
    assert con_mapa == base == mapa_vacio
    assert con_mapa.excluidas == ()
    assert sorted(_codigos(con_mapa)) == [
        "REF-A", "REF-B", "REF-C", "REF-D",
    ]


def test_off_id_encendido_sin_mapa_es_igual_al_baseline():
    entradas, _ = _escenario_con_mapa()
    base = calcular_sucursal(entradas, atributos(), parametros_legacy())
    con_switch = calcular_sucursal(
        entradas, atributos(), parametros_legacy(consolidar_sustituidas=True)
    )
    assert con_switch == base


def test_off_id_encender_y_volver_a_apagar_vuelve_al_baseline():
    entradas, nodos = _escenario_con_mapa()
    mapa = resolver_cadenas(_maestro(*nodos))
    apagado = parametros_legacy()
    antes = calcular_sucursal(entradas, atributos(), apagado, mapa)
    encendido = calcular_sucursal(
        entradas, atributos(),
        parametros_legacy(consolidar_sustituidas=True), mapa,
    )
    despues = calcular_sucursal(entradas, atributos(), apagado, mapa)
    assert encendido != antes
    assert despues == antes


def test_el_resultado_no_depende_del_orden_de_las_entradas():
    entradas, nodos = _escenario_con_mapa()
    directo = _calcular(entradas, nodos)
    invertido = _calcular(list(reversed(entradas)), nodos)
    assert directo == invertido
