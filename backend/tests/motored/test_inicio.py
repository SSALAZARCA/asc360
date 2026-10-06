"""
Motored "Inicio": `GET /api/motored/inicio` and its service.

The service composes existing read services into role-aware sections; each
section is computed on its own savepoint and fails soft. These tests use
fake sessions and patch the reused services where a real database would
be needed; `pg_real/test_inicio_pg.py` covers the SQL.
"""
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import (
    GERENCIA_ALLOWED_PREFIXES,
    SERVICIO_CLIENTE_ALLOWED_PREFIXES,
    get_motored_user_lookup,
)
from app.motored.services import caso_detractor
from app.motored.services import inicio
from app.motored.services import tablero_asesores_consultas
from app.motored.services import tablero_kpis
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import parametros_corrida, vigencia
from tests.motored.conftest import FakeAsyncSession, override_motored_db

HOY = date(2026, 10, 5)
INICIO = "/api/motored/inicio"

SECCIONES = {
    "ADMIN": {
        "pedidos_borrador", "datos_por_vencer", "detractores_sin_gestionar"},
    "COMPRAS": {
        "pedidos_borrador", "datos_por_vencer", "ultimo_pedido_enviado"},
    "GERENCIA": {"venta_mes", "tiendas_verde", "tiendas_rojo"},
    "SERVICIO_CLIENTE": {"detractores_sin_gestionar", "encuestas_mes"},
}


class _Savepoint:
    """`begin_nested()` stand-in: counts savepoints, never swallows."""

    def __init__(self, sesion):
        self._sesion = sesion

    async def __aenter__(self):
        self._sesion.savepoints += 1
        return self

    async def __aexit__(self, tipo, valor, traza):
        if tipo is not None:
            self._sesion.revertidos += 1
        return False


class Sesion(FakeAsyncSession):
    def __init__(self, execute_queue=None):
        super().__init__(execute_queue=execute_queue)
        self.savepoints = 0
        self.revertidos = 0

    def begin_nested(self):
        return _Savepoint(self)


def _fijas(monkeypatch, **valores):
    """Every section returns `{"marca": <name>}` unless overridden."""
    for nombre in inicio.CONSTRUCTORES:
        async def _fija(ctx, _nombre=nombre):
            if isinstance(valores.get(_nombre), Exception):
                raise valores[_nombre]
            return {"marca": _nombre}
        monkeypatch.setitem(inicio.CONSTRUCTORES, nombre, _fija)


# --- Composition -------------------------------------------------------------


@pytest.mark.parametrize("rol", sorted(SECCIONES))
async def test_each_role_gets_exactly_its_sections(monkeypatch, rol):
    _fijas(monkeypatch)
    sesion = Sesion()

    respuesta = await inicio.construir_inicio(sesion, rol, HOY)

    assert respuesta["rol"] == rol
    assert respuesta["hoy"] == "2026-10-05"
    assert set(respuesta["secciones"]) == SECCIONES[rol]
    for nombre, seccion in respuesta["secciones"].items():
        assert seccion == {"disponible": True, "marca": nombre}
    assert sesion.savepoints == len(SECCIONES[rol])


async def test_a_role_without_screens_gets_no_sections(monkeypatch):
    _fijas(monkeypatch)

    respuesta = await inicio.construir_inicio(Sesion(), "SUCURSAL", HOY)

    assert respuesta["secciones"] == {}


async def test_a_failing_section_is_unavailable_and_the_rest_return(
        monkeypatch, caplog):
    _fijas(monkeypatch, datos_por_vencer=RuntimeError("boom"))
    sesion = Sesion()

    respuesta = await inicio.construir_inicio(sesion, "ADMIN", HOY)

    secciones = respuesta["secciones"]
    assert secciones["datos_por_vencer"] == {"disponible": False}
    assert secciones["pedidos_borrador"]["disponible"] is True
    assert secciones["detractores_sin_gestionar"]["disponible"] is True
    assert sesion.revertidos == 1
    assert "datos_por_vencer" in caplog.text


# --- Pedidos -----------------------------------------------------------------


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _ctx(sesion, hoy=HOY):
    return inicio.Contexto(db=sesion, hoy=hoy)


async def test_pedidos_borrador_counts_the_latest_real_corrida():
    corrida_id = uuid.uuid4()
    sesion = Sesion(execute_queue=[
        [SimpleNamespace(id=corrida_id, codigo="PED-2026-S41-001")],
        # pedido_tienda.resumen_pedidos: (corrida, estado_pedido, count)
        [(corrida_id, "BORRADOR", 3), (corrida_id, "CERRADO", 2),
         (corrida_id, "ENVIADO", 1)],
    ])

    datos = await inicio.CONSTRUCTORES["pedidos_borrador"](_ctx(sesion))

    assert datos == {
        "corrida_id": str(corrida_id), "codigo": "PED-2026-S41-001",
        "tiendas": 3, "total": 6}
    consulta = str(sesion.executed_statements[0])
    assert "es_escenario" in consulta and "corrida.estado !=" in consulta


async def test_pedidos_borrador_without_any_corrida():
    sesion = Sesion(execute_queue=[[]])

    datos = await inicio.CONSTRUCTORES["pedidos_borrador"](_ctx(sesion))

    assert datos == {
        "corrida_id": None, "codigo": None, "tiendas": 0, "total": 0}


async def test_ultimo_pedido_enviado_counts_sent_out_of_total():
    corrida_id = uuid.uuid4()
    sesion = Sesion(execute_queue=[
        [SimpleNamespace(id=corrida_id, codigo="PED-2026-S40-002")],
        [(corrida_id, "ENVIADO", 4), (corrida_id, "CERRADO", 1)],
    ])

    datos = await inicio.CONSTRUCTORES["ultimo_pedido_enviado"](
        _ctx(sesion))

    assert datos == {
        "corrida_id": str(corrida_id), "codigo": "PED-2026-S40-002",
        "enviadas": 4, "total": 5}
    assert "'ENVIADO'" in _sql(sesion.executed_statements[0])


# --- Data staleness ----------------------------------------------------------


def _carga(tipo, desde=None, hasta=None, aplicado=None):
    return vigencia.CargaVista(
        carga_id=uuid.uuid4(), tipo=tipo, estado=vigencia.ESTADO_APLICADO,
        periodo_desde=desde, periodo_hasta=hasta, aplicado_en=aplicado,
        fecha_max_detectada=None)


LIMITES = {"inventario": 7, "backorder": 7, "facturas": 7, "ingresos": 7}


def _hechos(*cargas):
    return vigencia.HechosVigencia(
        cargas=cargas, hay_referencias=True, hay_demanda_perdida=True)


def _por_tipo(datos):
    return {d["tipo"]: d for d in datos}


def test_staleness_states_follow_the_preflight_and_the_avisos():
    hechos = _hechos(
        # vence 2026-10-06 (manana): por vencer, as the avisos say
        _carga("INVENTARIO", desde=date(2026, 9, 29)),
        # vence 2026-10-04: already past
        _carga("BACKORDER", desde=date(2026, 9, 27)),
        _carga("FACTURAS_PEDIDOS",
               aplicado=datetime(2026, 10, 4, 15, tzinfo=timezone.utc)),
        _carga("VENTAS", desde=date(2026, 3, 1), hasta=date(2026, 9, 30)),
    )

    datos = inicio.estado_de_los_datos(hechos, LIMITES, HOY)

    assert [d["tipo"] for d in datos] == [
        "INVENTARIO", "BACKORDER", "FACTURAS_PEDIDOS", "INGRESOS_FACTURAS",
        "VENTAS"]
    tipos = _por_tipo(datos)
    assert tipos["INVENTARIO"] == {
        "tipo": "INVENTARIO", "fecha": "2026-09-29", "antiguedad_dias": 6,
        "limite_dias": 7, "vence": "2026-10-06", "vence_cuando": "manana",
        "estado": "por_vencer"}
    assert tipos["BACKORDER"]["estado"] == "vencido"
    assert tipos["BACKORDER"]["vence_cuando"] is None
    assert tipos["FACTURAS_PEDIDOS"]["estado"] == "al_dia"
    assert tipos["FACTURAS_PEDIDOS"]["fecha"] == "2026-10-04"
    assert tipos["INGRESOS_FACTURAS"] == {
        "tipo": "INGRESOS_FACTURAS", "fecha": None, "antiguedad_dias": None,
        "limite_dias": 7, "vence": None, "vence_cuando": None,
        "estado": "sin_datos"}
    assert tipos["VENTAS"]["estado"] == "al_dia"
    assert tipos["VENTAS"]["fecha"] == "2026-09-30"


def test_sales_are_stale_when_the_last_closed_month_is_missing():
    hechos = _hechos(
        _carga("VENTAS", desde=date(2026, 3, 1), hasta=date(2026, 8, 31)))

    ventas = _por_tipo(inicio.estado_de_los_datos(
        hechos, LIMITES, HOY))["VENTAS"]

    assert ventas["estado"] == "vencido"
    assert ventas["limite_dias"] is None


def test_sales_are_por_vencer_on_the_last_day_of_the_month():
    hechos = _hechos(
        _carga("VENTAS", desde=date(2026, 3, 1), hasta=date(2026, 9, 30)))

    ventas = _por_tipo(inicio.estado_de_los_datos(
        hechos, LIMITES, date(2026, 10, 31)))["VENTAS"]

    assert ventas["estado"] == "por_vencer"
    assert ventas["vence"] == "2026-10-31"
    assert ventas["vence_cuando"] == "hoy"


def test_sales_without_any_load_have_no_data():
    ventas = _por_tipo(inicio.estado_de_los_datos(
        _hechos(), LIMITES, HOY))["VENTAS"]

    assert ventas["estado"] == "sin_datos"


async def test_datos_por_vencer_reads_the_preflight_facts_and_limits(
        monkeypatch):
    llamadas = {}

    async def _params(db, en_fecha, sucursal_ids, overrides=None):
        llamadas["params"] = (en_fecha, tuple(sucursal_ids))
        return SimpleNamespace(limites_antiguedad=LIMITES)

    async def _hechos_de(db, fecha_corte):
        llamadas["hechos"] = fecha_corte
        return _hechos(_carga("INVENTARIO", desde=date(2026, 9, 29)))

    monkeypatch.setattr(
        parametros_corrida, "cargar_parametros_corrida", _params)
    monkeypatch.setattr(vigencia, "cargar_hechos", _hechos_de)

    datos = await inicio.CONSTRUCTORES["datos_por_vencer"](_ctx(Sesion()))

    assert llamadas == {"params": (HOY, ()), "hechos": HOY}
    assert datos["cantidad"] == 5  # 1 por vencer + 4 sin datos
    assert datos["por_vencer"] == 1
    assert datos["vencidos"] == 0
    assert datos["sin_datos"] == 4
    assert len(datos["datos"]) == 5


# --- Survey ------------------------------------------------------------------


async def test_detractores_sin_gestionar_are_the_open_cases(monkeypatch):
    async def _listar(db, *, page, page_size, **filtros):
        assert (page, page_size, filtros) == (1, 1, {})
        return {"conteo_por_estado": {
            "ABIERTO": 7, "EN_GESTION": 2, "CERRADO": 9}}

    monkeypatch.setattr(caso_detractor, "listar", _listar)

    datos = await inicio.CONSTRUCTORES["detractores_sin_gestionar"](
        _ctx(Sesion()))

    assert datos == {"cantidad": 7}


async def test_encuestas_mes_counts_this_months_loads():
    ultima = datetime(2026, 10, 3, 14, 0)
    sesion = Sesion(execute_queue=[[(2, 340, ultima)]])

    datos = await inicio.CONSTRUCTORES["encuestas_mes"](_ctx(sesion))

    assert datos == {
        "cargas": 2, "registros": 340,
        "ultima_carga": "2026-10-03T14:00:00+00:00"}
    # Start of October in Bogota is 05:00 UTC.
    assert "2026-10-01 05:00:00" in _sql(sesion.executed_statements[0])


async def test_encuestas_mes_without_loads():
    sesion = Sesion(execute_queue=[[(0, None, None)]])

    datos = await inicio.CONSTRUCTORES["encuestas_mes"](_ctx(sesion))

    assert datos == {"cargas": 0, "registros": 0, "ultima_carga": None}


# --- Management --------------------------------------------------------------


def _kpis(monkeypatch, compania, tiendas=None, error=None):
    llamadas = []
    filtro = SimpleNamespace(reglas=SimpleNamespace(semaforo={
        "verde_desde": 100.0, "ambar_desde": 90.0}))

    async def _filtro(db, meses, modo_hmcl, sucursal_ids=None):
        llamadas.append(("filtro", meses, modo_hmcl, sucursal_ids))
        return filtro

    async def _ventas(db, filtro_):
        llamadas.append(("ventas", filtro_ is filtro))
        if error is not None:
            raise error
        return {
            "usando_resumen": True,
            "datos_actualizados_en": "2026-10-05T12:30:00+00:00",
            "cumplimiento": {
                "compania": compania,
                "conteos": {"tiendas": tiendas or {
                    "verde": 0, "ambar": 0, "violeta": 0}},
            },
        }

    monkeypatch.setattr(tablero_asesores_consultas, "cargar_filtro", _filtro)
    monkeypatch.setattr(tablero_kpis, "calcular_kpis_ventas", _ventas)
    return llamadas


async def test_gerencia_reads_the_kpi_sales_tab_once(monkeypatch):
    llamadas = _kpis(
        monkeypatch,
        {"venta": 1500.5, "presupuesto": 2000, "pct": 0.75025,
         "semaforo": "violeta"},
        {"verde": 4, "ambar": 3, "violeta": 2})

    respuesta = await inicio.construir_inicio(Sesion(), "GERENCIA", HOY)

    assert llamadas == [
        ("filtro", ["2026-10"], "incluir", None), ("ventas", True)]
    secciones = respuesta["secciones"]
    assert secciones["venta_mes"] == {
        "disponible": True, "estado": "ok", "mes": "2026-10",
        "venta": 1500.5, "presupuesto": 2000, "pct": 0.75025,
        "semaforo": "violeta", "usando_resumen": True,
        "datos_actualizados_en": "2026-10-05T12:30:00+00:00"}
    assert secciones["tiendas_verde"] == {
        "disponible": True, "cantidad": 4, "total": 9, "desde_pct": 100.0}
    assert secciones["tiendas_rojo"] == {
        "disponible": True, "cantidad": 2, "total": 9,
        "menor_a_pct": 90.0}


@pytest.mark.parametrize("compania", [None, {
    "venta": 10.0, "presupuesto": 0, "pct": None, "semaforo": None}])
async def test_venta_mes_without_budget(monkeypatch, compania):
    _kpis(monkeypatch, compania)

    respuesta = await inicio.construir_inicio(Sesion(), "GERENCIA", HOY)

    venta = respuesta["secciones"]["venta_mes"]
    assert venta["disponible"] is True
    assert venta["estado"] == "sin_presupuesto"


async def test_a_failing_kpi_read_makes_the_gerencia_cards_unavailable(
        monkeypatch):
    llamadas = _kpis(monkeypatch, None, error=RuntimeError("kpi"))

    respuesta = await inicio.construir_inicio(Sesion(), "GERENCIA", HOY)

    assert respuesta["secciones"] == {
        "venta_mes": {"disponible": False},
        "tiendas_verde": {"disponible": False},
        "tiendas_rojo": {"disponible": False},
    }
    assert [c for c in llamadas if c[0] == "ventas"] == [("ventas", True)]


# --- HTTP and the role guard -------------------------------------------------


@pytest.fixture
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "inicio-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "inicio-asc360")
    yield
    app.dependency_overrides.clear()


def _get(rol):
    """Through the REAL `get_current_motored_user` (path confinement)."""
    async def _lookup(user_id):
        return MotoredUser(user_id=user_id, role=rol)

    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(Sesion(execute_queue=[[]]))
    token = create_motored_token(sub=str(uuid.uuid4()), role=rol)
    with TestClient(app) as client:
        return client.get(INICIO, headers={"Authorization": f"Bearer {token}"})


@pytest.mark.usefixtures("_motored_ready")
@pytest.mark.parametrize("rol", sorted(SECCIONES))
def test_every_role_with_screens_reaches_inicio(monkeypatch, rol):
    _fijas(monkeypatch)

    respuesta = _get(rol)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["rol"] == rol
    assert set(cuerpo["secciones"]) == SECCIONES[rol]


@pytest.mark.usefixtures("_motored_ready")
@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA"])
def test_roles_without_screens_get_403(monkeypatch, rol):
    _fijas(monkeypatch)

    respuesta = _get(rol)

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == (
        "Tu rol todavía no tiene pantallas habilitadas.")


def test_confined_roles_allow_inicio():
    assert INICIO in GERENCIA_ALLOWED_PREFIXES
    assert INICIO in SERVICIO_CLIENTE_ALLOWED_PREFIXES
