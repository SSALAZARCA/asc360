"""
Daily asesor report against a real Postgres (opt-in). Same hand-computed world as the asesor detail
(`test_tablero_asesor_detalle_pg`: year 2097, sales on the 5th of Jan/Feb/Mar), with `fecha` 2097-03-20.

March: Ana sells 700 on a budget of 800 (0.875), Beto 900 on 600 (1.5), Cami 100 on 400 (0.25).
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import settings
from app.motored.models.presupuesto import PresupuestoLinea, PresupuestoVersion
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import kpi_resumen
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import reportes_asesores as r
from app.motored.services import tablero_asesor_detalle as d
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services.ingesta.ventas import normalizar_vendedor
from tests.motored.pg_real.test_tablero_asesor_detalle_pg import MESES, Mundo
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark, sesion  # noqa: F401

D = Decimal
FECHA = datetime.date(2097, 3, 20)


def _venta(db, mundo, quien, nro, dia, monto, tienda, cliente="Taller X", nombre=None):
    nom = nombre or f"{quien.title()} {mundo.sfx}"
    db.add(VentaDetalle(
        id=uuid.uuid4(), carga_id=mundo.carga.id, fecha=datetime.date(2097, 3, dia), anio=2097, mes=3,
        sucursal_id=tienda.id, referencia_id=mundo.ref.id, origen="MOSTRADOR", cantidad=D(1), vendedor=nom,
        vendedor_norm=normalizar_vendedor(nom), valor_bruto=D(monto), valor_descuentos=D(0),
        cliente_factura=cliente, nro_documento=f"{nro}-{mundo.sfx}"))


async def _detalle_endpoint(db, mundo, quien, meses):
    filtro = await q.cargar_filtro(db, meses, "incluir", None)
    return await k.calcular_kpis_asesor_detalle(db, filtro, mundo.cedulas[quien])


def _propias(resultado, mundo):
    return {c: v for c, v in resultado["reportes"].items() if c in set(mundo.cedulas.values())}


def _afirmar_detalle_contra_endpoint(detalle, endpoint, tendencia_anio, quien):
    """Field by field against the raw output of the asesor detail endpoint (money in whole pesos)."""
    asesor, mes, tarjeta = endpoint["asesor"], endpoint["cumplimiento_mes"], endpoint["comision"]
    assert detalle["ficha"] == {
        "nombre": asesor["nombre"], "cedula": asesor["cedula"], "tienda": asesor["tienda"], "cargo": asesor["cargo"],
        "sucursal_id": asesor["sucursal_id"], "tramo": tarjeta["tramo"]}, quien
    assert detalle["cumplimiento_mes"] == {
        "mes": mes["mes"], "venta": round(mes["venta"]), "presupuesto": mes["presupuesto"], "pct": mes["pct"],
        "semaforo": mes["semaforo"], "base": mes["base"]}, quien
    assert len(detalle["tendencia"]) == 3 and [x["mes"] for x in detalle["tendencia"]] == MESES, quien
    assert [x["pct"] for x in detalle["tendencia"]] == [x["pct"] for x in tendencia_anio], quien
    assert [(x["id"]) for x in detalle["tiles"]] == [x["id"] for x in endpoint["tiles"]], quien
    assert [x["linea"] for x in detalle["lineas"]] == [x["linea"] for x in endpoint["lineas"]], quien
    assert [x["pct"] for x in detalle["lineas"]] == [x["pct"] for x in endpoint["lineas"]], quien
    assert detalle["tecnired"]["clientes"] == endpoint["tecnired"]["clientes"], quien
    assert detalle["tecnired"]["pct"] == endpoint["tecnired"]["pct"], quien
    assert [x["nit"] for x in detalle["tecnired"]["top"]] == [x["nit"] for x in endpoint["tecnired"]["top"]], quien


async def test_the_report_of_each_asesor_matches_the_hand_computed_world(sesion):
    mundo = await Mundo().crear(sesion)

    resultado = await r.reportes_asesores(sesion, FECHA)
    ana = resultado["reportes"][mundo.cedulas["ana"]]

    assert set(_propias(resultado, mundo)) == {mundo.cedulas[n] for n in ("ana", "beto", "cami")}  # Dora: no budget
    assert (ana["mes"], ana["fecha_datos"], ana["nombre"]) == ("2097-03", "2097-03-05", f"Ana {mundo.sfx}")
    assert (ana["venta_cumplimiento"], ana["presupuesto"], ana["tramo"]["nombre"], ana["comision"]) == (
        700, 800, "BASE", 7)
    assert ana["cumplimiento_pct"] == pytest.approx(0.875)
    assert (ana["falta_100"], ana["compuerta"]["falta"], ana["siguiente_tramo"]["falta"]) == (100, 60, 20)


async def test_the_detail_equals_the_asesor_detail_endpoint_for_the_same_asesor_and_month(sesion):
    mundo = await Mundo().crear(sesion)

    resultado = await r.reportes_asesores(sesion, FECHA)

    for quien in ("ana", "beto", "cami"):
        cedula = mundo.cedulas[quien]
        del_mes = await _detalle_endpoint(sesion, mundo, quien, ["2097-03"])
        del_anio = await _detalle_endpoint(sesion, mundo, quien, MESES)
        reporte = resultado["reportes"][cedula]
        detalle = reporte["detalle"]
        _afirmar_detalle_contra_endpoint(detalle, del_mes, del_anio["tendencia"], quien)
        tarjeta = del_mes["comision"]
        assert reporte["comision"] == round(tarjeta["comision"])
        assert reporte["total_a_pagar"] == round(tarjeta["total_a_pagar"])
        assert reporte["dias_habiles_restantes"] == tarjeta["dias_habiles_restantes"]
        assert reporte["falta_100"] == tarjeta["falta_100"]
        assert reporte["compuerta"]["falta"] == tarjeta["falta_compuerta"]
        assert reporte["venta_diaria_necesaria"] == tarjeta["venta_diaria_necesaria"]
        comparaciones = reporte["detalle"]["comparaciones"]
        assert comparaciones["puestos"] == del_mes["puestos"]
        assert comparaciones["comparacion"] == del_mes["comparacion"]
        assert comparaciones["strip_otros"] == del_mes["strip"]["otros"]


async def test_the_detail_of_ana_matches_the_hand_computed_world(sesion):
    """Explicit expectations worked out by hand (module docstring), independent of the builders."""
    mundo = await Mundo().crear(sesion)

    ana = (await r.reportes_asesores(sesion, FECHA))["reportes"][mundo.cedulas["ana"]]["detalle"]

    assert ana["ficha"] == {
        "nombre": f"Ana {mundo.sfx}", "cedula": mundo.cedulas["ana"], "tienda": f"Norte {mundo.sfx}",
        "cargo": "ASESOR DE REPUESTOS", "sucursal_id": str(mundo.norte.id), "tramo": "BASE"}
    mes = ana["cumplimiento_mes"]
    assert (mes["mes"], mes["venta"], mes["presupuesto"]) == ("2097-03", 700, 800)
    assert mes["pct"] == pytest.approx(0.875) and mes["semaforo"] == k.AMBAR
    tarjeta = ana["comision"]
    assert (tarjeta["tramo"], tarjeta["comision"], tarjeta["venta_base"], tarjeta["presupuesto"]) == ("BASE", 7, 700, 800)
    assert (tarjeta["falta_100"], tarjeta["falta_compuerta"], tarjeta["fecha_datos"]) == (100, 60, "2097-03-05")
    assert (tarjeta["sig"]["tramo"], tarjeta["sig"]["falta"], tarjeta["sig"]["meta"]) == ("PRO", 20, 720)
    tiles = {x["id"]: x["valor"] for x in ana["tiles"]}
    assert (tiles["venta"], tiles["ticket"], tiles["facturas"], tiles["clientes_unicos"]) == (700, 700, 1, 1)
    assert [x["mes"] for x in ana["tendencia"]] == MESES
    assert [x["pct"] for x in ana["tendencia"]] == [pytest.approx(1.0), pytest.approx(1.0), pytest.approx(0.875)]
    assert ana["tecnired"] == {"venta": 0, "pct": 0.0, "clientes": 0, "top": []}
    assert sorted(ana["comparaciones"]["strip_otros"]) == [pytest.approx(0.25), pytest.approx(1.5)]
    assert ana["comparaciones"]["red"]["cumplimiento_pct"] == pytest.approx(1700 / 1800)


async def test_the_tecnired_top_of_each_asesor_comes_from_one_grouped_query(sesion):
    mundo = await Mundo().crear(sesion)
    _venta(sesion, mundo, "ana", "A9", 6, 250, mundo.norte, cliente=mundo.t1)
    _venta(sesion, mundo, "beto", "B9", 6, 90, mundo.norte, cliente=mundo.t2)
    await sesion.flush()

    resultado = await r.reportes_asesores(sesion, FECHA)

    ana = resultado["reportes"][mundo.cedulas["ana"]]["detalle"]["tecnired"]
    beto = resultado["reportes"][mundo.cedulas["beto"]]["detalle"]["tecnired"]
    assert ana["clientes"] == 1 and ana["top"] == [{"cliente": "Taller Uno", "nit": mundo.t1, "venta": 250}]
    assert beto["top"] == [{"cliente": mundo.t2, "nit": mundo.t2, "venta": 90}]
    for quien, nombre in (("ana", "ana"), ("beto", "beto")):
        endpoint = await _detalle_endpoint(sesion, mundo, nombre, ["2097-03"])
        propio = resultado["reportes"][mundo.cedulas[quien]]["detalle"]
        assert propio == d.para_reporte(endpoint, (await _detalle_endpoint(sesion, mundo, nombre, MESES))["tendencia"])


async def test_it_is_month_to_date_sales_after_fecha_do_not_count(sesion):
    mundo = await Mundo().crear(sesion)
    _venta(sesion, mundo, "ana", "A8", 25, 300, mundo.norte)
    await sesion.flush()

    a_mitad = await r.reportes_asesores(sesion, FECHA)
    a_fin = await r.reportes_asesores(sesion, datetime.date(2097, 3, 31))

    ana_mitad, ana_fin = (x["reportes"][mundo.cedulas["ana"]] for x in (a_mitad, a_fin))
    assert (ana_mitad["venta_cumplimiento"], ana_mitad["fecha_datos"]) == (700, "2097-03-05")
    assert (ana_fin["venta_cumplimiento"], ana_fin["fecha_datos"]) == (1000, "2097-03-25")
    assert ana_fin["cumplimiento_pct"] == pytest.approx(1.25)
    assert ana_fin["tramo"] == {"nombre": "ELITE", "tasa_pct": 1.8}
    assert ana_mitad["detalle"]["cumplimiento_mes"]["venta"] == 700


async def test_a_month_without_sales_has_no_reports(sesion):
    await Mundo().crear(sesion)

    resultado = await r.reportes_asesores(sesion, datetime.date(2098, 7, 10))

    assert resultado["reportes"] == {}


async def test_a_seller_with_a_budget_missing_goes_to_sin_presupuesto_and_a_master_name_without_cedula_to_sin_cedula(sesion):
    mundo = await Mundo().crear(sesion)
    nom = f"Sincedula {mundo.sfx}"
    sesion.add(Vendedor(
        id=uuid.uuid4(), nombre=nom, nombre_norm=normalizar_vendedor(nom), cargo="ASESOR DE REPUESTOS",
        cedula=None, sucursal_id=mundo.sur.id, activo=True))
    await sesion.flush()
    _venta(sesion, mundo, "x", "S1", 7, 55, mundo.sur, nombre=nom)
    _venta(sesion, mundo, "dora", "DD", 7, 40, mundo.sur)
    await sesion.flush()

    resultado = await r.reportes_asesores(sesion, FECHA)

    assert {"vendedor": nom, "venta": 55} in resultado["sin_cedula"]
    assert {"cedula": mundo.cedulas["dora"], "nombre": f"Dora {mundo.sfx}", "venta": 40} in resultado["sin_presupuesto"]


async def test_master_name_variants_of_one_cedula_add_up_to_one_report(sesion):
    mundo = await Mundo().crear(sesion)
    variante = f"Ana  {mundo.sfx} Dos"
    sesion.add(Vendedor(
        id=uuid.uuid4(), nombre=variante, nombre_norm=normalizar_vendedor(variante), cargo="ASESOR DE REPUESTOS",
        cedula=mundo.cedulas["ana"], sucursal_id=mundo.norte.id, activo=True))
    await sesion.flush()
    _venta(sesion, mundo, "x", "V1", 8, 100, mundo.norte, nombre=variante.upper())
    await sesion.flush()

    resultado = await r.reportes_asesores(sesion, FECHA)

    assert resultado["reportes"][mundo.cedulas["ana"]]["venta_cumplimiento"] == 800  # 700 + 100 of the variant
    assert len([c for c in resultado["reportes"] if c == mundo.cedulas["ana"]]) == 1


async def test_it_is_identical_from_the_summary_and_live(sesion, monkeypatch):
    mundo = await Mundo().crear(sesion)
    await kpi_resumen.reconstruir_todo(sesion)

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    en_vivo = _propias(await r.reportes_asesores(sesion, FECHA), mundo)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)
    desde_resumen = _propias(await r.reportes_asesores(sesion, FECHA), mundo)

    assert len(en_vivo) == 3 and desde_resumen == en_vivo


async def _fuente_usada(db, fecha, monkeypatch):
    usadas = []
    original = r._periodo

    async def espiar(db_, fecha_):
        periodo = await original(db_, fecha_)
        usadas.append(periodo.fuente)
        return periodo

    with monkeypatch.context() as parche:
        parche.setattr(r, "_periodo", espiar)
        resultado = await r.reportes_asesores(db, fecha)
    return usadas, resultado


async def test_the_source_is_live_when_the_month_has_sales_after_fecha_and_the_summary_at_month_end(sesion, monkeypatch):
    mundo = await Mundo().crear(sesion)
    _venta(sesion, mundo, "ana", "A8", 25, 300, mundo.norte)
    await sesion.flush()
    await kpi_resumen.reconstruir_todo(sesion)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)

    a_mitad, rep_mitad = await _fuente_usada(sesion, FECHA, monkeypatch)
    a_fin, rep_fin = await _fuente_usada(sesion, datetime.date(2097, 3, 31), monkeypatch)

    assert a_mitad == [r._Vivo]  # the 25th is after fecha: the summary cannot answer "as of the 20th"
    assert a_fin == [lectura]
    assert rep_mitad["reportes"][mundo.cedulas["ana"]]["venta_cumplimiento"] == 700
    assert rep_fin["reportes"][mundo.cedulas["ana"]]["venta_cumplimiento"] == 1000


async def _selects(db, fecha):
    cuenta = {"n": 0}

    def escuchar(conn, cursor, statement, *args, **kwargs):
        if statement.lstrip().upper().startswith("SELECT"):
            cuenta["n"] += 1

    event.listen(Engine, "before_cursor_execute", escuchar)
    try:
        await r.reportes_asesores(db, fecha)
    finally:
        event.remove(Engine, "before_cursor_execute", escuchar)
    return cuenta["n"]


async def test_the_number_of_queries_does_not_grow_with_the_number_of_asesores(sesion):
    mundo = await Mundo().crear(sesion)
    pocos = await _selects(sesion, FECHA)

    version = PresupuestoVersion(id=uuid.uuid4(), mes=datetime.date(2097, 3, 1), version=2, origen="MANUAL")
    sesion.add(version)
    await sesion.flush()
    lineas = [
        (n, (await _nuevo_asesor(sesion, mundo, n))) for n in range(8)]
    sesion.add_all([
        PresupuestoLinea(
            id=uuid.uuid4(), version_id=version.id, cedula=ced, sucursal_id=mundo.sur.id, monto=500)
        for _, ced in lineas] + [
        PresupuestoLinea(id=uuid.uuid4(), version_id=version.id, cedula=ced, sucursal_id=sid, monto=m)
        for ced, sid, m in [(mundo.cedulas["ana"], mundo.norte.id, 800), (mundo.cedulas["beto"], mundo.norte.id, 600),
                            (mundo.cedulas["cami"], mundo.sur.id, 400)]])
    await sesion.flush()
    muchos = await _selects(sesion, FECHA)
    resultado = await r.reportes_asesores(sesion, FECHA)

    assert len(_propias(resultado, mundo)) == 3 + 8
    assert muchos == pocos


async def _nuevo_asesor(db, mundo, n):
    nombre = f"Extra{n} {mundo.sfx}"
    cedula = str(uuid.uuid4().int)[:10]
    db.add(Vendedor(
        id=uuid.uuid4(), nombre=nombre, nombre_norm=normalizar_vendedor(nombre), cargo="ASESOR DE REPUESTOS",
        cedula=cedula, sucursal_id=mundo.sur.id, activo=True))
    await db.flush()
    _venta(db, mundo, "x", f"E{n}", 9, 100 + n, mundo.sur, cliente=mundo.t1 if n % 2 else "Taller X", nombre=nombre)
    await db.flush()
    mundo.cedulas[f"extra{n}"] = cedula
    return cedula
