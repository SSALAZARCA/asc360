"""
Motored aviso anticipado de antiguedad: cuando vence cada dato del pedido y
a quien y cuando se le avisa. El dia de vencimiento es el ultimo dia en que
el dato todavia sirve (`fecha usada + limite`); el preflight bloquea desde
el dia siguiente. Las reglas de "que carga cuenta" son las del preflight.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from app.motored.services import avisos_antiguedad as av
from app.motored.services.corridas.vigencia import (
    CargaVista,
    HechosVigencia,
)

BOGOTA = timezone(timedelta(hours=-5))
LIMITES = {"inventario": 7, "backorder": 7, "facturas": 7, "ingresos": 7}


def _carga(tipo, desde=None, aplicado=None, estado="APLICADO"):
    return CargaVista(
        carga_id=uuid.uuid4(), tipo=tipo, estado=estado,
        periodo_desde=desde, periodo_hasta=desde, aplicado_en=aplicado,
        fecha_max_detectada=None)


def _hechos(*cargas):
    return HechosVigencia(
        cargas=tuple(cargas), hay_referencias=True,
        hay_demanda_perdida=True)


def _por_tipo(vencimientos):
    return {v.tipo: v for v in vencimientos}


def test_inventario_vence_en_la_fecha_del_corte_mas_el_limite():
    hechos = _hechos(_carga("INVENTARIO", desde=date(2026, 9, 26)))

    res = _por_tipo(av.calcular_vencimientos(
        hechos, LIMITES, date(2026, 10, 2)))

    assert res["inventario"].fecha_carga == date(2026, 9, 26)
    assert res["inventario"].fecha_vencimiento == date(2026, 10, 3)
    assert res["inventario"].limite_dias == 7


def test_facturas_usa_la_fecha_de_aplicacion_en_bogota():
    # 03:00 UTC del 27 son las 22:00 del 26 en Bogota.
    aplicado = datetime(2026, 9, 27, 3, 0, tzinfo=timezone.utc)
    hechos = _hechos(_carga("FACTURAS_PEDIDOS", aplicado=aplicado))

    res = _por_tipo(av.calcular_vencimientos(
        hechos, LIMITES, date(2026, 10, 2)))

    assert res["facturas"].fecha_carga == date(2026, 9, 26)
    assert res["facturas"].fecha_vencimiento == date(2026, 10, 3)


def test_un_dato_ya_vencido_o_ausente_no_genera_aviso():
    hechos = _hechos(_carga("INVENTARIO", desde=date(2026, 9, 20)))

    res = av.calcular_vencimientos(hechos, LIMITES, date(2026, 10, 2))

    assert res == []


def test_ignora_cargas_no_aplicadas_y_elige_la_mas_reciente():
    hechos = _hechos(
        _carga("INVENTARIO", desde=date(2026, 9, 25)),
        _carga("INVENTARIO", desde=date(2026, 9, 28)),
        _carga("INVENTARIO", desde=date(2026, 9, 30), estado="ANULADO"),
    )

    res = _por_tipo(av.calcular_vencimientos(
        hechos, LIMITES, date(2026, 10, 2)))

    assert res["inventario"].fecha_carga == date(2026, 9, 28)


def test_usa_el_limite_propio_de_cada_tipo():
    hechos = _hechos(_carga("BACKORDER", desde=date(2026, 9, 30)))

    res = _por_tipo(av.calcular_vencimientos(
        hechos, {**LIMITES, "backorder": 3}, date(2026, 10, 2)))

    assert res["backorder"].fecha_vencimiento == date(2026, 10, 3)


def _vencimiento(vence: date, tipo="inventario"):
    return av.Vencimiento(
        tipo=tipo, nombre=tipo, fecha_carga=vence - timedelta(days=7),
        fecha_vencimiento=vence, limite_dias=7)


def test_avisos_de_hoy_y_manana_con_su_etiqueta():
    hoy = date(2026, 10, 2)
    lista = [
        _vencimiento(date(2026, 10, 2), "inventario"),
        _vencimiento(date(2026, 10, 3), "backorder"),
        _vencimiento(date(2026, 10, 4), "facturas"),
    ]

    res = av.avisos_del_dia(lista, hoy)

    assert [(v.tipo, e) for v, e in res] == [
        ("inventario", "hoy"), ("backorder", "manana")]


def test_umbrales_vispera_a_las_1630_y_dia_a_las_0830():
    lista = [
        _vencimiento(date(2026, 10, 3), "inventario"),
        _vencimiento(date(2026, 10, 2), "backorder"),
    ]

    def umbrales(hora, minuto):
        ahora = datetime(2026, 10, 2, hora, minuto, tzinfo=BOGOTA)
        return [(u, v.tipo) for u, v in av.umbrales_a_enviar(lista, ahora)]

    assert umbrales(8, 29) == []
    assert umbrales(8, 30) == [("DIA", "backorder")]
    assert umbrales(16, 29) == [("DIA", "backorder")]
    assert umbrales(16, 30) == [
        ("VISPERA", "inventario"), ("DIA", "backorder")]


def test_el_mensaje_de_vispera_lista_los_datos_y_pide_subirlos():
    texto = av.armar_mensaje("VISPERA", [
        _vencimiento(date(2026, 10, 3), "inventario"),
        _vencimiento(date(2026, 10, 3), "facturas"),
    ])

    assert "mañana" in texto
    assert "inventario" in texto and "facturas" in texto
    assert "26/09" in texto and "03/10" in texto


def test_el_mensaje_del_dia_dice_que_vence_hoy():
    texto = av.armar_mensaje(
        "DIA", [_vencimiento(date(2026, 10, 2), "inventario")])

    assert "hoy" in texto
    assert "mañana" not in texto
