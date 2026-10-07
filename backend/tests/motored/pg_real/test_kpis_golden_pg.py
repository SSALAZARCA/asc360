"""
Golden outputs of the KPI reads (odd/motored-kpis-velocidad) against a real Postgres (opt-in).

The speed work on the KPI tabs must not change a single figure. This test builds ONE fixed world
(deterministic ids, names and cedulas; two stores, three months of 2097, asesores with and without
budgets, a second budget version, HMCL / Tecnired clients, unrecognized lines, costs) and stores the
exact output of every KPI read, with the summaries ON and OFF, under the default and a changed
Configuracion, in `golden/kpis_golden.json`. Any change of any figure fails here with the case name.

Refresh the file ONLY for an intended change of figures:
`MOTORED_GOLDEN_UPDATE=1 pytest tests/motored/pg_real/test_kpis_golden_pg.py`.
The world needs an empty database (the summaries rebuild covers all of it), so a database that
already holds sales or vendors skips the test.
"""
import datetime
import hashlib
import itertools
import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.motored.models.presupuesto import PresupuestoLinea, PresupuestoVersion
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import inicio, kpi_resumen, reportes_asesores
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as kpis
from tests.motored.pg_real.test_kpi_resumen_lectura_pg import MESES, _mundo
from tests.motored.pg_real.test_kpi_resumen_pg import URL, pytestmark, sesion  # noqa: F401

GOLDEN = Path(__file__).parent / "golden" / "kpis_golden.json"
ACTUALIZAR = bool(os.environ.get("MOTORED_GOLDEN_UPDATE"))
ASESOR = "ASESOR DE REPUESTOS"


def _ids_fijos(monkeypatch):
    """`uuid.uuid4` as a counter of digests: the same ids, names and cedulas on every run."""
    contador = itertools.count(1)
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(bytes=hashlib.md5(str(next(contador)).encode()).digest()))


def _sin_hora(valor):
    """The moment the summary was refreshed changes on every run; everything else must not."""
    if isinstance(valor, dict):
        return {k: ("<hora>" if k == "datos_actualizados_en" and v else _sin_hora(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sin_hora(v) for v in valor]
    return valor


def _como_json(valor):
    """The output as the API would send it (decimals and dates as text), without the refresh moment."""
    return json.loads(json.dumps(_sin_hora(valor), sort_keys=True, ensure_ascii=False, default=str))


async def _presupuestos(db):
    """Budgets of the three months (February has two versions: the latest one rules)."""
    vendedores = {
        n: (await db.execute(select(Vendedor.cedula, Vendedor.sucursal_id).where(Vendedor.nombre == n))).one()
        for n in ("ANA", "EVA", "FELIPE")}
    for mes, version, montos in [
        (1, 1, {"ANA": 900, "EVA": 500, "FELIPE": 400}),
        (2, 1, {"ANA": 500, "EVA": 100, "FELIPE": 100}),
        (2, 2, {"ANA": 700, "EVA": 800, "FELIPE": 300}),
        (3, 1, {"ANA": 800, "EVA": 600}),
    ]:
        v = PresupuestoVersion(id=uuid.uuid4(), mes=datetime.date(2097, mes, 1), version=version, origen="MANUAL")
        db.add(v)
        await db.flush()
        db.add_all([
            PresupuestoLinea(id=uuid.uuid4(), version_id=v.id, cedula=vendedores[n][0], sucursal_id=vendedores[n][1],
                             monto=monto)
            for n, monto in montos.items()])
    await db.flush()


async def _mundo_dorado(db, configuracion):
    mundo = await _mundo(db, configuracion)
    for nombre, suc in (("EVA", mundo.s1), ("FELIPE", mundo.s2)):
        db.add(Vendedor(id=uuid.uuid4(), nombre=nombre, nombre_norm=nombre, cargo=ASESOR,
                        cedula=str(uuid.uuid4().int)[:10], sucursal_id=suc.id, activo=True))
    await db.flush()
    for fila in [
        (mundo.s1, "R1", "EVA", "Taller X", 1, 20, "E1", 2, 700, 70, "MOSTRADOR", mundo.c_venta),
        (mundo.s1, "R2", "EVA", mundo.tec, 2, 21, "E2", 1, 300, 0, "CRM", mundo.c_venta),
        (mundo.s1, "R1", "EVA", "Taller Y", 3, 9, "E3", 3, 900, 90, "MOSTRADOR", mundo.c_mar),
        (mundo.s2, "R2", "FELIPE", "Taller Z", 1, 22, "F1", 1, 400, 0, "VENTA", mundo.c_venta),
        (mundo.s2, "R1", "FELIPE", "900883086", 2, 23, "F2", 2, 600, 60, "VENTA", mundo.c_venta),
        (mundo.s2, "R5", "FELIPE", mundo.tec, 3, 24, "F3", 1, 250, 0, "MOSTRADOR", mundo.c_mar),
    ]:
        await mundo.linea(db, *fila)
    await db.flush()
    await _presupuestos(db)
    cedulas = {n: (await db.execute(select(Vendedor.cedula).where(Vendedor.nombre == n))).scalar()
               for n in ("ANA", "EVA", "FELIPE", "LUIS")}
    await kpi_resumen.reconstruir_todo(db)
    return mundo, cedulas


async def _salidas(db, mundo, cedulas):
    """Every KPI read of the world, by case name."""
    s1, ambas = [mundo.s1.id], [mundo.s1.id, mundo.s2.id]
    filtros = {
        "anio-todas": (MESES["todo"], t.HMCL_INCLUIR, None),
        "anio-s1-excluir": (MESES["todo"], t.HMCL_EXCLUIR, s1),
        "ultimo-todas": (MESES["ultimo"], t.HMCL_INCLUIR, None),
        "salteado-ambas-solo": (MESES["salteado"], t.HMCL_SOLO, ambas),
    }
    salidas = {}
    for nombre, (meses, modo, tiendas) in filtros.items():
        filtro = await q.cargar_filtro(db, meses, modo, tiendas)
        for lectura_, funcion in (
            ("ventas", kpis.calcular_kpis_ventas), ("tiendas", kpis.calcular_kpis_tiendas),
            ("asesores", kpis.calcular_kpis_asesores), ("comisiones", kpis.calcular_kpis_comisiones),
            ("opciones_asesores", kpis.calcular_opciones_asesores),
        ):
            salidas[f"{lectura_}/{nombre}"] = await funcion(db, filtro)
    detalles = {
        "anio-todas": ("ANA", "EVA", "FELIPE", "LUIS", "DESCONOCIDO"),
        "ultimo-todas": ("ANA", "EVA", "FELIPE"),
        "anio-s1-excluir": ("ANA", "EVA", "FELIPE"),
    }
    for nombre, quienes in detalles.items():
        meses, modo, tiendas = filtros[nombre]
        filtro = await q.cargar_filtro(db, meses, modo, tiendas)
        for quien in quienes:
            cedula = cedulas.get(quien, "9999999999")
            salidas[f"detalle/{nombre}/{quien}"] = await kpis.calcular_kpis_asesor_detalle(db, filtro, cedula)
    salidas["opciones"] = await kpis.calcular_opciones(db)
    salidas["inicio"] = await inicio.construir_inicio(db, datetime.date(2097, 4, 10))
    for dia in (20, 13):  # after the last sale (the summaries answer) and before it (live)
        salidas[f"reportes_asesores/{dia}"] = await reportes_asesores.reportes_asesores(
            db, datetime.date(2097, 3, dia))
    return salidas


def _cargar_dorado():
    return json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {}


def _guardar_dorado(dorado):
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(dorado, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


@pytest.mark.parametrize("configuracion", [False, True], ids=["default-config", "changed-config"])
@pytest.mark.parametrize("resumen", [False, True], ids=["summary-off", "summary-on"])
async def test_every_kpi_read_keeps_its_golden_output(sesion, monkeypatch, configuracion, resumen):
    hay = (await sesion.execute(select(func.count()).select_from(VentaDetalle))).scalar()
    hay += (await sesion.execute(select(func.count()).select_from(Vendedor))).scalar()
    if hay:
        pytest.skip("the golden world needs an empty database")
    _ids_fijos(monkeypatch)
    mundo, cedulas = await _mundo_dorado(sesion, configuracion)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", resumen)
    assert await lectura.usar_resumen(sesion) is resumen

    salidas = {nombre: _como_json(valor) for nombre, valor in (await _salidas(sesion, mundo, cedulas)).items()}

    clave = f"{'on' if resumen else 'off'}/{'cambiada' if configuracion else 'defecto'}"
    if ACTUALIZAR:
        dorado = _cargar_dorado()
        dorado[clave] = salidas
        _guardar_dorado(dorado)
        return
    esperado = _cargar_dorado().get(clave)
    assert esperado is not None, f"no golden for {clave}; run with MOTORED_GOLDEN_UPDATE=1"
    assert set(salidas) == set(esperado)
    for nombre in sorted(salidas):
        assert salidas[nombre] == esperado[nombre], (clave, nombre)
    assert salidas["detalle/anio-todas/ANA"] and salidas["reportes_asesores/20"]["reportes"]
