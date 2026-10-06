"""
Motored "Inicio": `GET /api/motored/inicio` and its service.

One page, the same for every role that reaches it: Repuestos sales of the
last complete month and of the year to date, the active principal stores
and the active vendedores. Each figure is computed on its own savepoint and
fails soft. These tests use fake sessions and patch the KPI reads where a
real database would be needed; `pg_real/test_inicio_pg.py` covers the SQL
(the annulled loads, the inactive stores and vendedores).
"""
import uuid
from datetime import date
from decimal import Decimal

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
from app.motored.services import inicio
from app.motored.services import kpi_resumen_lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db

HOY = date(2026, 10, 6)
INICIO = "/api/motored/inicio"
FIGURAS = {"ventas_mes", "ventas_anio", "puntos_venta", "asesores"}
ROLES = ["ADMIN", "COMPRAS", "GERENCIA", "SERVICIO_CLIENTE"]


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


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


TIENDA_1, TIENDA_2 = str(uuid.uuid4()), str(uuid.uuid4())


def _fila(mes, linea, venta, hmcl=False, tienda=TIENDA_1):
    venta = Decimal(venta)
    return t.FilaCubo(
        tienda, mes, linea, hmcl, False, False, False, venta,
        venta, Decimal(0), Decimal(1), 1, Decimal(0))


CUBO = [
    _fila("2026-09", "REPUESTOS", "1000.25"),
    _fila("2026-09", "REPUESTOS", "500", hmcl=True, tienda=TIENDA_2),
    _fila("2026-09", "ACCESORIOS", "9999"),
    _fila("2026-09", None, "7777"),
]


def _kpi(monkeypatch, cubo=CUBO, reglas=t.REGLAS_POR_DEFECTO):
    """Patches the KPI reads; returns the calls `(meses, hmcl, tiendas,
    dimension)` they received."""
    llamadas = []

    async def _filtro(db, meses, modo_hmcl, sucursal_ids=None):
        llamadas.append([list(meses), modo_hmcl, sucursal_ids])
        return t.filtro_de_meses(meses, modo_hmcl, sucursal_ids, reglas)

    async def _cubo(db, filtro, fecha_corte, dimension=t.DIM_ASESOR):
        llamadas[-1].append(dimension)
        return cubo

    monkeypatch.setattr(tablero_asesores_consultas, "cargar_filtro", _filtro)
    monkeypatch.setattr(kpi_resumen_lectura, "cubo", _cubo)
    return llamadas


def _fijas(monkeypatch, **valores):
    """Every figure returns `{"marca": <name>}` unless overridden."""
    for nombre in inicio.CONSTRUCTORES:
        async def _fija(ctx, _nombre=nombre):
            if isinstance(valores.get(_nombre), Exception):
                raise valores[_nombre]
            return {"marca": _nombre}
        monkeypatch.setitem(inicio.CONSTRUCTORES, nombre, _fija)


def _ctx(sesion, hoy=HOY):
    return inicio.Contexto(db=sesion, hoy=hoy)


# --- Composition -------------------------------------------------------------


async def test_the_page_has_exactly_the_four_figures(monkeypatch):
    _fijas(monkeypatch)
    sesion = Sesion()

    respuesta = await inicio.construir_inicio(sesion, HOY)

    assert respuesta["hoy"] == "2026-10-06"
    assert set(respuesta) == {"hoy", *FIGURAS}
    for nombre in FIGURAS:
        assert respuesta[nombre] == {"disponible": True, "marca": nombre}
    assert sesion.savepoints == 4


async def test_a_failing_figure_is_unavailable_and_the_rest_return(
        monkeypatch, caplog):
    _fijas(monkeypatch, ventas_anio=RuntimeError("boom"))
    sesion = Sesion()

    respuesta = await inicio.construir_inicio(sesion, HOY)

    assert respuesta["ventas_anio"] == {"disponible": False}
    for nombre in FIGURAS - {"ventas_anio"}:
        assert respuesta[nombre]["disponible"] is True
    assert sesion.revertidos == 1
    assert "ventas_anio" in caplog.text


async def test_every_figure_can_fail_on_its_own(monkeypatch):
    errores = {nombre: RuntimeError(nombre) for nombre in FIGURAS}
    _fijas(monkeypatch, **errores)

    respuesta = await inicio.construir_inicio(Sesion(), HOY)

    assert {n: respuesta[n] for n in FIGURAS} == {
        n: {"disponible": False} for n in FIGURAS}


# --- Repuestos sales ---------------------------------------------------------


async def test_ventas_mes_is_the_last_complete_month_of_repuestos(
        monkeypatch):
    llamadas = _kpi(monkeypatch)

    datos = await inicio.CONSTRUCTORES["ventas_mes"](_ctx(Sesion()))

    # HMCL included, as the KPI's default; only the REPUESTOS line.
    assert datos == {"valor": 1500.25, "mes": "2026-09"}
    assert llamadas == [[["2026-09"], t.HMCL_INCLUIR, None, t.DIM_SUCURSAL]]


async def test_ventas_mes_in_january_is_december_of_last_year(
        monkeypatch):
    llamadas = _kpi(monkeypatch, cubo=[])

    datos = await inicio.CONSTRUCTORES["ventas_mes"](
        _ctx(Sesion(), date(2027, 1, 1)))

    assert datos == {"valor": 0.0, "mes": "2026-12"}
    assert llamadas[0][0] == ["2026-12"]


async def test_ventas_anio_runs_from_january_to_today(monkeypatch):
    llamadas = _kpi(monkeypatch)

    datos = await inicio.CONSTRUCTORES["ventas_anio"](_ctx(Sesion()))

    assert datos == {
        "valor": 1500.25, "desde": "2026-01-01", "hasta": "2026-10-06"}
    assert llamadas == [[
        [f"2026-{m:02d}" for m in range(1, 11)], t.HMCL_INCLUIR, None,
        t.DIM_SUCURSAL]]


async def test_ventas_anio_on_new_years_day_is_january_only(monkeypatch):
    llamadas = _kpi(monkeypatch, cubo=[])

    datos = await inicio.CONSTRUCTORES["ventas_anio"](
        _ctx(Sesion(), date(2027, 1, 1)))

    assert datos == {
        "valor": 0.0, "desde": "2027-01-01", "hasta": "2027-01-01"}
    assert llamadas[0][0] == ["2027-01"]


async def test_repuestos_follows_the_configured_lines(monkeypatch):
    """Without REPUESTOS among the configured lines the KPI does not
    recognize it either: nothing is counted."""
    reglas = t.REGLAS_POR_DEFECTO._replace(lineas=("ACCESORIOS",))
    _kpi(monkeypatch, reglas=reglas)

    datos = await inicio.CONSTRUCTORES["ventas_mes"](_ctx(Sesion()))

    assert datos["valor"] == 0.0


def test_the_bogota_today_is_the_default(monkeypatch):
    monkeypatch.setattr(inicio, "hoy_bogota", lambda: date(2026, 3, 2))

    assert inicio.Contexto.de(Sesion()).hoy == date(2026, 3, 2)


# --- Counts ------------------------------------------------------------------


async def test_puntos_venta_counts_the_active_principal_stores():
    sesion = Sesion(execute_queue=[[
        (uuid.uuid4(), "Cali"), (uuid.uuid4(), "Bogota")]])

    datos = await inicio.CONSTRUCTORES["puntos_venta"](_ctx(sesion))

    assert datos == {"cantidad": 2}
    sql = _sql(sesion.executed_statements[0])
    assert "sucursal.activa IS true" in sql
    assert "sucursal.principal_id IS NULL" in sql


async def test_asesores_counts_the_active_vendedores():
    sesion = Sesion(execute_queue=[[(37,)]])

    datos = await inicio.CONSTRUCTORES["asesores"](_ctx(sesion))

    assert datos == {"cantidad": 37}
    sql = _sql(sesion.executed_statements[0])
    assert "count(" in sql
    assert "vendedor.activo IS true" in sql


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
def test_every_role_with_screens_gets_the_same_page(monkeypatch):
    _fijas(monkeypatch)
    monkeypatch.setattr(inicio, "hoy_bogota", lambda: HOY)

    cuerpos = []
    for rol in ROLES:
        respuesta = _get(rol)
        assert respuesta.status_code == 200, respuesta.text
        cuerpos.append(respuesta.json())

    assert set(cuerpos[0]) == {"hoy", *FIGURAS}
    assert all(cuerpo == cuerpos[0] for cuerpo in cuerpos)


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
