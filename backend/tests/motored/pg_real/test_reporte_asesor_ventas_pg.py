"""
The light month read (`reporte_asesor_ventas.ventas_del_mes`) against the
full report builder (`reportes_asesores`) on a real Postgres (opt-in).

Same hand-computed world as the asesor detail (year 2097), plus Dora
selling without a budget, a master name without a cédula and a sale after
`fecha`. For every case the light read must give the same cédulas, the
same `con_reporte` flags, the same message numbers and the same counts as
the builder, live and from the KPI summary.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import settings
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import kpi_resumen
from app.motored.services import reporte_asesor_ventas as ventas
from app.motored.services import reportes_asesores as r
from app.motored.services.ingesta.ventas import normalizar_vendedor
from tests.motored.pg_real.test_tablero_asesor_detalle_pg import Mundo
from tests.motored.pg_real.test_tablero_asesores_pg import (  # noqa: F401
    URL, pytestmark, sesion,
)

FECHA = datetime.date(2097, 3, 20)
FIN_DE_MES = datetime.date(2097, 3, 31)


def _venta(db, mundo, nro, dia, monto, tienda, nombre):
    db.add(VentaDetalle(
        id=uuid.uuid4(), carga_id=mundo.carga.id,
        fecha=datetime.date(2097, 3, dia), anio=2097, mes=3,
        sucursal_id=tienda.id, referencia_id=mundo.ref.id,
        origen="MOSTRADOR", cantidad=Decimal(1), vendedor=nombre,
        vendedor_norm=normalizar_vendedor(nombre),
        valor_bruto=Decimal(monto), valor_descuentos=Decimal(0),
        cliente_factura="Taller X", nro_documento=f"{nro}-{mundo.sfx}"))


async def _mundo_completo(db):
    mundo = await Mundo().crear(db)
    sin_cedula = f"Sincedula {mundo.sfx}"
    db.add(Vendedor(
        id=uuid.uuid4(), nombre=sin_cedula,
        nombre_norm=normalizar_vendedor(sin_cedula),
        cargo="ASESOR DE REPUESTOS", cedula=None,
        sucursal_id=mundo.sur.id, activo=True))
    await db.flush()
    _venta(db, mundo, "S1", 7, 55, mundo.sur, sin_cedula)
    _venta(db, mundo, "DD", 7, 40, mundo.sur, f"Dora {mundo.sfx}")
    _venta(db, mundo, "A8", 25, 300, mundo.norte, f"Ana {mundo.sfx}")
    await db.flush()
    return mundo


def _del_builder(datos):
    """The builder output in the light shape (only what the send uses)."""
    filas = {
        c: (True, x["cumplimiento_pct"], x["total_a_pagar"])
        for c, x in datos["reportes"].items()}
    for x in datos["sin_presupuesto"]:
        filas.setdefault(x["cedula"], (False, None, None))
    return filas, len(datos["sin_cedula"])


def _de_la_lectura(lectura):
    filas = {
        c: (x["con_reporte"], x["cumplimiento_pct"], x["total_a_pagar"])
        for c, x in lectura.asesores.items()}
    return filas, lectura.sin_cedula


async def _comparar(db, fecha):
    esperado = _del_builder(await r.reportes_asesores(db, fecha))
    obtenido = _de_la_lectura(await ventas.ventas_del_mes(db, fecha))
    assert obtenido == esperado, fecha
    return obtenido


@pytest.mark.parametrize("resumen", [False, True])
async def test_the_light_read_matches_the_builder(
        sesion, monkeypatch, resumen):
    mundo = await _mundo_completo(sesion)
    await kpi_resumen.reconstruir_todo(sesion)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", resumen)

    a_mitad, sin_cedula = await _comparar(sesion, FECHA)
    a_fin, _ = await _comparar(sesion, FIN_DE_MES)
    await _comparar(sesion, datetime.date(2097, 2, 28))
    await _comparar(sesion, datetime.date(2098, 7, 10))

    ana, dora = mundo.cedulas["ana"], mundo.cedulas["dora"]
    assert a_mitad[ana][:2] == (True, pytest.approx(0.875))
    assert a_fin[ana][:2] == (True, pytest.approx(1.25))
    assert a_mitad[dora] == (False, None, None)
    assert sin_cedula >= 1


async def test_the_light_read_names_and_stores_match_the_builder(sesion):
    mundo = await _mundo_completo(sesion)

    datos = await r.reportes_asesores(sesion, FECHA)
    lectura = await ventas.ventas_del_mes(sesion, FECHA)

    for cedula in mundo.cedulas.values():
        if cedula in datos["reportes"]:
            x = datos["reportes"][cedula]
            assert lectura.asesores[cedula]["nombre"] == x["nombre"]
            assert lectura.asesores[cedula]["tienda"] == x["tienda"]
    sin_pres = {x["cedula"]: x["nombre"] for x in datos["sin_presupuesto"]}
    for cedula, nombre in sin_pres.items():
        assert lectura.asesores[cedula]["nombre"] == nombre


async def _selects(db, funcion, fecha):
    cuenta = {"n": 0}

    def escuchar(conn, cursor, statement, *args, **kwargs):
        if statement.lstrip().upper().startswith("SELECT"):
            cuenta["n"] += 1

    event.listen(Engine, "before_cursor_execute", escuchar)
    try:
        await funcion(db, fecha)
    finally:
        event.remove(Engine, "before_cursor_execute", escuchar)
    return cuenta["n"]


async def test_the_light_read_issues_fewer_queries_than_the_builder(
        sesion):
    await _mundo_completo(sesion)

    ligera = await _selects(sesion, ventas.ventas_del_mes, FECHA)
    completa = await _selects(sesion, r.reportes_asesores, FECHA)

    assert ligera < completa
