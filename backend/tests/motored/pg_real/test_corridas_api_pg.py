"""
Motored Pedidos F3 "Motor", S7 (sdd/motored-pedidos-motor): la API de
corridas y la guarda de anulación contra un Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base migrada con `alembic -c alembic_motored.ini upgrade head`. Una única
conexión dentro de una transacción que se revierte al final
(`join_transaction_mode="create_savepoint"`: cada commit sólo libera un
savepoint). Las peticiones entran por la app real (ASGI, `httpx`), con el
usuario inyectado y la sesión real; el runner calcula en línea.

Recorre lo que los tests unitarios no pueden probar: que crear con el POST
deja la corrida PENDIENTE y calculable por el job, que las consultas leen lo
que la persistencia escribió, el alcance por sucursal en SQL, y que anular una
carga usada por una corrida CERRADA (incluidas las EXCEL de demanda perdida
que lee el cargador) se bloquea de verdad.
"""
import datetime
import json
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.database import get_motored_db
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.sucursal import Sucursal
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import ejecucion as ej
from app.motored.services.corridas import servicio as sv
from app.motored.services.trabajos import supervisor, supervisor_corridas
from app.motored.services.trabajos.runner_corridas import (
    SupervisorCorridaRunner,
)
from tests.motored.conftest import override_motored_user
from tests.motored.pg_real.test_corrida_pg import (
    CORTE,
    _carga,
    _guardar,
    _sembrar,
)

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

BASE = "/api/motored/corridas"
CARGAS = "/api/motored/cargas"


class RunnerEnLinea:
    """Reclama y calcula la corrida dentro de la petición (los tests no
    esperan al loop de fondo)."""

    def __init__(self, fabrica):
        self.fabrica = fabrica

    async def enqueue(self, corrida_id):
        await ej.reclamar_y_ejecutar(
            corrida_id, session_factory=self.fabrica)


@pytest.fixture
async def fabrica():
    motor = create_async_engine(URL)
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        yield async_sessionmaker(
            bind=conexion, class_=AsyncSession, expire_on_commit=False,
            autoflush=False, join_transaction_mode="create_savepoint")
        await transaccion.rollback()
    await motor.dispose()


@pytest.fixture(autouse=True)
def _app_lista(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "api-pg-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "api-pg-asc360")
    monkeypatch.setattr(supervisor, "ensure_started", lambda: None)
    monkeypatch.setattr(supervisor_corridas, "ensure_started", lambda: None)
    monkeypatch.setattr(sv, "hoy_bogota", lambda: CORTE)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def mundo(fabrica):
    """Datos sintéticos de S6a más dos cargas EXCEL de demanda perdida: una
    con filas dentro de la ventana del cargador y otra con filas fuera."""
    async with fabrica() as db:
        datos = await _sembrar(db)
        fuera = _carga("DEMANDA_PERDIDA")
        await _guardar(db, fuera)
        await _guardar(db, *_perdidas(datos, fuera))
        await db.commit()
    app.dependency_overrides[get_motored_db] = _sesion_de(fabrica)
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: RunnerEnLinea(fabrica))
    return SimpleNamespace(fabrica=fabrica, datos=datos, fuera=fuera)


def _perdidas(datos, fuera):
    def fila(carga, fecha):
        return DemandaPerdida(
            id=uuid.uuid4(), fecha=fecha, sucursal_id=datos.uno.id,
            referencia_id=datos.patron.id, cantidad_solicitada=Decimal(3),
            origen="EXCEL", carga_id=carga.id)
    return [
        fila(datos.cargas.perdida, datetime.date(2026, 8, 10)),
        fila(fuera, datetime.date(2026, 1, 10)),
    ]


def _sesion_de(fabrica):
    async def dependencia():
        async with fabrica() as db:
            try:
                yield db
            except Exception:
                await db.rollback()
                raise
    return dependencia


def _cliente():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba")


def _como(rol, usuario_id, sucursales=()):
    override_motored_user(MotoredUser(
        user_id=str(usuario_id), role=rol,
        sucursal_ids=[str(s) for s in sucursales]))


async def _crear(cliente, **cuerpo):
    cuerpo = {"fecha_corte": CORTE.isoformat(), **cuerpo}
    return await cliente.post(BASE, json=cuerpo)


async def _corrida_en_borrador(mundo, **cuerpo):
    _como("COMPRAS", mundo.datos.usuario.id)
    async with _cliente() as cliente:
        respuesta = await _crear(cliente, **cuerpo)
    assert respuesta.status_code == 202, respuesta.text
    return respuesta.json()


# --- POST, cálculo, lectura y cierre -----------------------------------------


async def test_post_creates_the_corrida_and_the_runner_computes_it(mundo):
    _como("COMPRAS", mundo.datos.usuario.id)

    async with _cliente() as cliente:
        creada = await _crear(cliente, nota="corrida de la semana")
        detalle = await cliente.get(f"{BASE}/{creada.json()['id']}")

    assert creada.status_code == 202, creada.text
    assert creada.json()["estado"] == "PENDIENTE"
    assert creada.json()["codigo"] == "PED-2026-S39-001"
    cuerpo = detalle.json()
    assert cuerpo["estado"] == "BORRADOR" and cuerpo["nota"] == (
        "corrida de la semana")
    assert (cuerpo["sucursales_total"], cuerpo["sucursales_procesadas"]) == (
        3, 3)
    assert {s["estado"] for s in cuerpo["sucursales"]} == {"OK", "OMITIDA"}


async def test_post_returns_pending_and_the_loop_computes_it_later(mundo):
    """Con el runner de producción el POST sólo deja la corrida PENDIENTE:
    nada se calcula en la petición; el tick del loop la reclama y termina."""
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: SupervisorCorridaRunner())
    _como("COMPRAS", mundo.datos.usuario.id)

    async with _cliente() as cliente:
        creada = (await _crear(cliente)).json()
        antes = (await cliente.get(
            f"{BASE}/{creada['id']}/progreso")).json()
        await supervisor_corridas.run_tick(session_factory=mundo.fabrica)
        despues = (await cliente.get(
            f"{BASE}/{creada['id']}/progreso")).json()

    assert (antes["estado"], antes["procesadas"], antes["total"]) == (
        "PENDIENTE", 0, 3)
    assert antes["actual"] is None
    assert (despues["estado"], despues["procesadas"]) == ("BORRADOR", 3)


async def test_the_detail_shows_the_age_of_every_input(mundo):
    creada = await _corrida_en_borrador(mundo)

    async with _cliente() as cliente:
        cuerpo = (await cliente.get(f"{BASE}/{creada['id']}")).json()

    assert cuerpo["antiguedad"]["inventario"]["antiguedad_dias"] == 2
    assert cuerpo["antiguedad"]["backorder"]["antiguedad_dias"] == 3
    assert cuerpo["antiguedad"]["inventario"]["limite_dias"] == 7
    assert set(cuerpo["antiguedad"]) == {
        "inventario", "backorder", "facturas", "ingresos"}
    assert cuerpo["mes_en_curso"]["modo_efectivo"] == "EXCLUIDO"


async def test_the_lines_come_with_exact_decimals_and_pedido_final(mundo):
    creada = await _corrida_en_borrador(mundo)
    uno = mundo.datos.uno.id

    async with _cliente() as cliente:
        pagina = (await cliente.get(
            f"{BASE}/{creada['id']}/lineas",
            params={"sucursal_id": str(uno)})).json()

    (linea,) = pagina["items"]
    assert pagina["total"] == 1
    assert linea["codigo_referencia"] == "94109-12000S"
    assert linea["pedido_sugerido"] == linea["pedido_final"] == "53.00"
    assert linea["valor_pedido"] == "24419.75"
    assert linea["demanda_ponderada"] == "85.428571"


async def test_the_line_filters_and_paging_work_on_real_data(mundo):
    creada = await _corrida_en_borrador(mundo)
    url = f"{BASE}/{creada['id']}/lineas"

    async with _cliente() as cliente:
        todas = (await cliente.get(url)).json()
        una = (await cliente.get(url, params={"limite": 1})).json()
        otra = (await cliente.get(
            url, params={"limite": 1, "offset": 1})).json()
        por_clase = (await cliente.get(url, params={"clase": "CF"})).json()
        nadie = (await cliente.get(url, params={"clase": "ZZ"})).json()

    assert todas["total"] == 3
    assert una["total"] == 3 and len(una["items"]) == 1
    assert una["items"][0]["referencia_id"] != otra["items"][0][
        "referencia_id"] or una["items"][0]["sucursal_id"] != otra[
        "items"][0]["sucursal_id"]
    assert por_clase["total"] >= 1 and nadie == {
        "items": [], "total": 0, "limite": 500, "offset": 0}


async def test_the_list_filters_by_state_scenario_and_dates(mundo):
    await _corrida_en_borrador(mundo)
    await _corrida_en_borrador(mundo, overrides={
        "consolidar_sustituidas": True})

    async with _cliente() as cliente:
        todas = (await cliente.get(BASE)).json()
        escenarios = (await cliente.get(
            BASE, params={"escenario": "true"})).json()
        produccion = (await cliente.get(BASE, params={
            "escenario": "false", "estado": "BORRADOR",
            "desde": "2026-09-21", "hasta": "2026-09-21"})).json()
        ninguna = (await cliente.get(
            BASE, params={"estado": "CERRADA"})).json()

    assert todas["total"] == 2
    assert [c["codigo"] for c in escenarios["items"]] == ["ESC-2026-S39-001"]
    assert [c["codigo"] for c in produccion["items"]] == ["PED-2026-S39-001"]
    assert ninguna["total"] == 0


async def test_the_progress_of_a_finished_corrida(mundo):
    creada = await _corrida_en_borrador(mundo)

    async with _cliente() as cliente:
        cuerpo = (await cliente.get(
            f"{BASE}/{creada['id']}/progreso")).json()

    assert (cuerpo["total"], cuerpo["procesadas"]) == (3, 3)
    assert (cuerpo["ok"], cuerpo["omitidas"], cuerpo["fallidas"]) == (2, 1, 0)
    assert cuerpo["actual"] is None and cuerpo["errores"] == []
    assert [a["codigo"] for a in cuerpo["advertencias"]] == ["A-CORRIDA-102"]


async def test_a_rejected_preflight_is_a_422_and_leaves_no_corrida(mundo):
    async with mundo.fabrica() as db:
        inventario = await db.get(
            CargaArchivo, mundo.datos.cargas.inventario.id)
        inventario.periodo_desde = datetime.date(2026, 9, 10)
        await db.commit()
    _como("ADMIN", mundo.datos.usuario.id)

    async with _cliente() as cliente:
        respuesta = await _crear(cliente)

    detalle = respuesta.json()["detail"]
    assert respuesta.status_code == 422 and detalle["code"] == "E-CORRIDA-003"
    assert detalle["detalle"]["antiguedad"]["inventario"][
        "antiguedad_dias"] == 11
    async with mundo.fabrica() as db:
        assert (await db.execute(
            select(func.count()).select_from(Corrida))).scalar_one() == 0


async def test_an_unknown_sucursal_is_a_422_and_leaves_no_corrida(mundo):
    _como("ADMIN", mundo.datos.usuario.id)

    async with _cliente() as cliente:
        respuesta = await _crear(cliente, sucursal_ids=[str(uuid.uuid4())])

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-011"


async def test_close_then_a_second_close_is_a_409(mundo):
    creada = await _corrida_en_borrador(mundo)
    _como("ADMIN", mundo.datos.usuario.id)

    async with _cliente() as cliente:
        cierre = await cliente.post(f"{BASE}/{creada['id']}/cerrar")
        otra = await cliente.post(f"{BASE}/{creada['id']}/cerrar")
        anulada = await cliente.post(
            f"{BASE}/{creada['id']}/anular", json={"motivo": "ya cerrada"})

    assert cierre.status_code == 200 and cierre.json()["estado"] == "CERRADA"
    assert otra.status_code == 409
    assert otra.json()["detail"]["code"] == "E-CORRIDA-040"
    assert anulada.status_code == 409


async def test_annulling_a_draft_keeps_its_lines_readable(mundo):
    creada = await _corrida_en_borrador(mundo)

    async with _cliente() as cliente:
        anulada = await cliente.post(
            f"{BASE}/{creada['id']}/anular", json={"motivo": "datos viejos"})
        lineas = await cliente.get(f"{BASE}/{creada['id']}/lineas")
        detalle = (await cliente.get(f"{BASE}/{creada['id']}")).json()

    assert anulada.json()["estado"] == "ANULADA"
    assert lineas.json()["total"] == 3
    assert detalle["motivo_anulacion"] == "datos viejos"


# --- Guarda de anulación de cargas ------------------------------------------


async def _anular_carga(carga_id):
    async with _cliente() as cliente:
        return await cliente.post(f"{CARGAS}/{carga_id}/anular")


async def test_a_closed_corrida_blocks_annulling_the_cargas_it_used(mundo):
    creada = await _corrida_en_borrador(mundo)
    _como("ADMIN", mundo.datos.usuario.id)
    async with _cliente() as cliente:
        await cliente.post(f"{BASE}/{creada['id']}/cerrar")

    cargas = mundo.datos.cargas
    for carga in (cargas.ventas, cargas.inventario, cargas.backorder,
                  cargas.facturas, cargas.ingresos):
        respuesta = await _anular_carga(carga.id)
        detalle = respuesta.json()["detail"]
        assert respuesta.status_code == 409, carga.tipo
        assert detalle["code"] == "E-CARGA-050"
        assert creada["codigo"] in detalle["message"]
    async with mundo.fabrica() as db:
        estado = (await db.get(CargaArchivo, cargas.ventas.id)).estado
    assert estado == "APLICADO"


async def test_the_excel_lost_demand_carga_the_loader_read_is_protected(
        mundo):
    creada = await _corrida_en_borrador(mundo)
    _como("ADMIN", mundo.datos.usuario.id)
    async with _cliente() as cliente:
        detalle = (await cliente.get(f"{BASE}/{creada['id']}")).json()
        await cliente.post(f"{BASE}/{creada['id']}/cerrar")

    respuesta = await _anular_carga(mundo.datos.cargas.perdida.id)

    assert [c["nombre_archivo"] for c in detalle["cargas_usadas"][
        "DEMANDA_PERDIDA"]] == ["f.xlsx"]
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CARGA-050"


async def test_a_lost_demand_carga_outside_the_window_is_not_linked(mundo):
    creada = await _corrida_en_borrador(mundo)
    _como("ADMIN", mundo.datos.usuario.id)
    async with _cliente() as cliente:
        await cliente.post(f"{BASE}/{creada['id']}/cerrar")
    async with mundo.fabrica() as db:
        vinculadas = (await db.execute(
            select(CorridaCarga.carga_id).where(
                CorridaCarga.tipo == "DEMANDA_PERDIDA"))).scalars().all()

    respuesta = await _anular_carga(mundo.fuera.id)

    assert vinculadas == [mundo.datos.cargas.perdida.id]
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "ANULADO"


async def test_annulling_a_carga_of_a_draft_invalidates_it(mundo):
    creada = await _corrida_en_borrador(mundo)
    _como("ADMIN", mundo.datos.usuario.id)

    anulada = await _anular_carga(mundo.datos.cargas.ingresos.id)
    async with _cliente() as cliente:
        detalle = (await cliente.get(f"{BASE}/{creada['id']}")).json()
        cierre = await cliente.post(f"{BASE}/{creada['id']}/cerrar")

    assert anulada.status_code == 200
    assert detalle["invalidada"] is True
    assert detalle["motivo_invalidacion"]["tipo"] == "CARGA_ANULADA"
    assert cierre.status_code == 409
    assert cierre.json()["detail"]["code"] == "E-CORRIDA-041"


async def test_a_carga_used_by_no_corrida_is_annulled_as_in_f2(mundo):
    suelta = _carga("VENTAS")
    async with mundo.fabrica() as db:
        await _guardar(db, suelta)
        await db.commit()
    _como("ADMIN", mundo.datos.usuario.id)

    respuesta = await _anular_carga(suelta.id)

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ANULADO"


async def test_a_carga_used_only_by_an_annulled_corrida_can_be_annulled(
        mundo):
    creada = await _corrida_en_borrador(mundo)
    async with _cliente() as cliente:
        await cliente.post(
            f"{BASE}/{creada['id']}/anular", json={"motivo": "descartada"})
    _como("ADMIN", mundo.datos.usuario.id)

    respuesta = await _anular_carga(mundo.datos.cargas.backorder.id)

    assert respuesta.status_code == 200


# --- Alcance por sucursal (T19) ---------------------------------------------


async def test_a_sucursal_user_reads_only_its_own_sucursal(mundo):
    creada = await _corrida_en_borrador(mundo)
    uno, dos, tres = (mundo.datos.uno, mundo.datos.dos, mundo.datos.tres)
    _como("SUCURSAL", mundo.datos.usuario.id, [uno.id])
    ajenos = [str(dos.id), str(tres.id), dos.nombre, tres.nombre]

    async with _cliente() as cliente:
        detalle = await cliente.get(f"{BASE}/{creada['id']}")
        progreso = await cliente.get(f"{BASE}/{creada['id']}/progreso")
        lineas = await cliente.get(f"{BASE}/{creada['id']}/lineas")
        lista = await cliente.get(BASE)

    for respuesta in (detalle, progreso, lineas, lista):
        assert respuesta.status_code == 200
        assert not [a for a in ajenos if a in respuesta.text], respuesta.url
    cuerpo = detalle.json()
    assert [s["sucursal_id"] for s in cuerpo["sucursales"]] == [str(uno.id)]
    assert {r["sucursal_id"] for r in cuerpo["resumen"]} == {str(uno.id)}
    assert (cuerpo["sucursales_total"], cuerpo["totales"]["unidades"]) == (
        1, "53.00")
    assert list(cuerpo["parametros"][
        "dias_entre_pedidos_por_sucursal"]) == [str(uno.id)]
    assert progreso.json()["total"] == 1 and progreso.json()[
        "actual"] is None
    assert {i["sucursal_id"] for i in lineas.json()["items"]} == {str(uno.id)}
    assert lista.json()["items"][0]["sucursales_total"] == 1


async def test_a_sucursal_user_cannot_ask_for_another_sucursals_lines(mundo):
    creada = await _corrida_en_borrador(mundo)
    _como("SUCURSAL", mundo.datos.usuario.id, [mundo.datos.uno.id])

    async with _cliente() as cliente:
        ajena = await cliente.get(
            f"{BASE}/{creada['id']}/lineas",
            params={"sucursal_id": str(mundo.datos.dos.id)})

    assert ajena.status_code == 403


async def test_a_corrida_without_an_own_sucursal_does_not_exist_for_it(
        mundo):
    creada = await _corrida_en_borrador(
        mundo, sucursal_ids=[str(mundo.datos.dos.id)])
    _como("SUCURSAL", mundo.datos.usuario.id, [mundo.datos.uno.id])

    async with _cliente() as cliente:
        detalle = await cliente.get(f"{BASE}/{creada['id']}")
        progreso = await cliente.get(f"{BASE}/{creada['id']}/progreso")
        lineas = await cliente.get(f"{BASE}/{creada['id']}/lineas")
        lista = await cliente.get(BASE)

    assert (detalle.status_code, progreso.status_code,
            lineas.status_code) == (404, 404, 404)
    assert lista.json()["total"] == 0


async def test_unrestricted_roles_see_the_whole_network(mundo):
    creada = await _corrida_en_borrador(mundo)
    _como("CONSULTA", mundo.datos.usuario.id, [mundo.datos.uno.id])

    async with _cliente() as cliente:
        detalle = (await cliente.get(f"{BASE}/{creada['id']}")).json()
        lineas = (await cliente.get(f"{BASE}/{creada['id']}/lineas")).json()

    assert detalle["sucursales_total"] == 3 and lineas["total"] == 3
    assert len(json.dumps(detalle["parametros"])) > 0


async def test_an_inactive_sucursal_user_sees_an_empty_list(mundo):
    await _corrida_en_borrador(mundo)
    async with mundo.fabrica() as db:
        nueva = Sucursal(
            id=uuid.uuid4(), nombre=f"SIN CORRIDA {uuid.uuid4().hex[:6]}",
            sic="X", activa=False, dias_empaque=1, dias_transito=1)
        await _guardar(db, nueva)
        await db.commit()
    _como("SUCURSAL", mundo.datos.usuario.id, [nueva.id])

    async with _cliente() as cliente:
        lista = (await cliente.get(BASE)).json()

    assert lista["total"] == 0 and lista["items"] == []
