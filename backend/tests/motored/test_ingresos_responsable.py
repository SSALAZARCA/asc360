"""Who enters each pending invoice (odd/tasks/motored-ingresos-responsable-plantilla.md, T2).

Pure rule: `num_referencias`, `responsable` (ASESOR up to the threshold,
ANALISTA above) and `puede_descargar_plantilla` (ANALISTA and LLEGO).
"""
import uuid
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.motored.services import ingresos_pendientes as ip
from app.motored.services import parametros

TIENDA = uuid.uuid4()
ASOCIADA = uuid.uuid4()
HOY = date(2026, 10, 8)
DESDE = date(2026, 9, 1)
PRINCIPAL = {TIENDA: TIENDA, ASOCIADA: TIENDA}
NOMBRES = {TIENDA: "Cali"}


def _linea(numero, referencias, suc=TIENDA):
    return SimpleNamespace(
        prefijo_rh="RH", numero_rh=numero, sucursal_id=suc,
        fecha_factura=date(2026, 10, 3), cantidad=D(len(referencias) or 1),
        valor_total=D(100), referencias=list(referencias))


def _calc(lineas, conf=None, **kwargs):
    return ip.calcular_pendientes(
        lineas, set(), DESDE, HOY, PRINCIPAL, NOMBRES, conf or {}, **kwargs)


def _refs(n):
    return [uuid.uuid4() for _ in range(n)]


def test_default_threshold_is_ten_and_inclusive():
    assert ip.UMBRAL_ASESOR_DEFECTO == 10
    [diez] = _calc([_linea(1, _refs(10))])
    [once] = _calc([_linea(2, _refs(11))])

    assert (diez["num_referencias"], diez["responsable"]) == (10, "ASESOR")
    assert (once["num_referencias"], once["responsable"]) == (11, "ANALISTA")


def test_threshold_is_configurable():
    [item] = _calc([_linea(1, _refs(11))], umbral=11)
    assert item["responsable"] == "ASESOR"
    [item] = _calc([_linea(2, _refs(3))], umbral=2)
    assert item["responsable"] == "ANALISTA"


def test_associated_stores_roll_up_without_double_counting_a_reference():
    compartida = uuid.uuid4()
    lineas = [
        _linea(7, [compartida, uuid.uuid4()], suc=TIENDA),
        _linea(7, [compartida, uuid.uuid4()], suc=ASOCIADA),
    ]

    [item] = _calc(lineas)

    assert item["num_referencias"] == 3


def test_an_offsetting_negative_row_at_an_associated_store_does_not_count():
    # Same netting as the ERP template: quantity summed per reference across
    # the whole principal group, kept only when the sum is positive.
    anulada, vigente = uuid.uuid4(), uuid.uuid4()
    positiva = _linea(7, [anulada, vigente], suc=TIENDA)
    positiva.cantidades = [D(5), D(2)]
    negativa = _linea(7, [anulada], suc=ASOCIADA)
    negativa.cantidades = [D(-5)]

    [item] = _calc([positiva, negativa])

    assert item["num_referencias"] == 1


def test_a_partial_offset_still_counts_the_reference():
    ref = uuid.uuid4()
    positiva = _linea(7, [ref], suc=TIENDA)
    positiva.cantidades = [D(5)]
    parcial = _linea(7, [ref], suc=ASOCIADA)
    parcial.cantidades = [D(-2)]

    [item] = _calc([positiva, parcial])

    assert item["num_referencias"] == 1


def test_rows_without_reference_data_count_zero_and_stay_with_the_asesor():
    sin_dato = SimpleNamespace(
        prefijo_rh="RH", numero_rh=9, sucursal_id=TIENDA,
        fecha_factura=date(2026, 10, 3), cantidad=D(1), valor_total=D(1))

    [item] = _calc([sin_dato])

    assert (item["num_referencias"], item["responsable"]) == (0, "ASESOR")


def test_a_null_reference_array_counts_zero():
    fila = _linea(3, [])
    fila.referencias = None

    [item] = _calc([fila])

    assert item["num_referencias"] == 0


def _conf(estado):
    return {("RH", 1, TIENDA): SimpleNamespace(
        estado=estado, actualizado_por_nombre="Ana", actualizado_en=None)}


@pytest.mark.parametrize("estado, esperado", [
    ("LLEGO", True), ("NO_HA_LLEGADO", False)])
def test_template_download_needs_an_analista_invoice_that_arrived(
        estado, esperado):
    [item] = _calc([_linea(1, _refs(12))], conf=_conf(estado))

    assert item["puede_descargar_plantilla"] is esperado


def test_unconfirmed_analista_invoice_cannot_download():
    [item] = _calc([_linea(1, _refs(12))])

    assert item["puede_descargar_plantilla"] is False


def test_asesor_invoice_that_arrived_cannot_download():
    [item] = _calc([_linea(1, _refs(3))], conf=_conf("LLEGO"))

    assert item["puede_descargar_plantilla"] is False


def test_the_other_fields_do_not_change():
    [item] = _calc([_linea(1, _refs(2))])

    assert item["factura"] == "RH 1" and item["estado"] == "SIN_CONFIRMAR"
    assert item["unidades"] == 2.0 and item["valor"] == 100.0


@pytest.mark.asyncio
async def test_the_threshold_is_read_from_the_parameter(monkeypatch):
    leer = AsyncMock(return_value={ip.CLAVE_UMBRAL: 4})
    monkeypatch.setattr(parametros, "leer_valores", leer)

    assert await ip.umbral_asesor(object(), HOY) == 4
    leer.assert_awaited_once_with(
        leer.await_args.args[0], HOY, {ip.CLAVE_UMBRAL: 10})
