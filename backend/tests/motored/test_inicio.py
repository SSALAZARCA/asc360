"""
Motored "Inicio": `GET /api/motored/inicio` and its service.

One page, the same for every role that reaches it: the KPI Ventas tab's
total of the last complete month and of its "Año corrido", the active
principal stores and the asesores with sales in the last complete month.
Each figure is computed on its own savepoint and fails soft. These tests
use fake sessions and patch the KPI reads where a real database would be
needed; `pg_real/test_inicio_pg.py` covers the SQL
(the annulled loads, the inactive stores, the asesores with sales).
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
CORTE = date(2026, 9, 30)
HASTA_SEPTIEMBRE = [f"2026-{m:02d}" for m in range(1, 10)]


def _fila(mes, linea, venta, hmcl=False, clave=TIENDA_1):
    venta = Decimal(venta)
    return t.FilaCubo(
        clave, mes, linea, hmcl, False, False, False, venta,
        venta, Decimal(0), Decimal(1), 1, Decimal(0))


CUBO = [
    _fila("2026-09", "REPUESTOS", "1000.25"),
    _fila("2026-09", "REPUESTOS", "500", hmcl=True, clave=TIENDA_2),
    _fila("2026-09", "ACCESORIOS", "9999"),
    _fila("2026-09", None, "7777"),
]
# Every recognized line, HMCL included; the line-less row never counts.
TOTAL_CUBO = 11499.25


def _kpi(monkeypatch, cubo=CUBO, reglas=t.REGLAS_POR_DEFECTO,
         disponibles=HASTA_SEPTIEMBRE):
    """Patches the KPI reads; returns the calls `(meses, hmcl, tiendas,
    dimension)` they received. `disponibles` are the months with sales
    (`kpi_resumen_lectura.meses`)."""
    llamadas = []

    async def _filtro(db, meses, modo_hmcl, sucursal_ids=None):
        llamadas.append([list(meses), modo_hmcl, sucursal_ids])
        return t.filtro_de_meses(meses, modo_hmcl, sucursal_ids, reglas)

    async def _corte(db):
        return CORTE

    async def _cubo(db, filtro, fecha_corte, dimension=t.DIM_ASESOR):
        assert fecha_corte == CORTE  # the KPI's own cost cut
        llamadas[-1].append(dimension)
        return cubo

    async def _meses(db):
        return list(disponibles)

    monkeypatch.setattr(tablero_asesores_consultas, "cargar_filtro", _filtro)
    monkeypatch.setattr(kpi_resumen_lectura, "fecha_corte_costos", _corte)
    monkeypatch.setattr(kpi_resumen_lectura, "cubo", _cubo)
    monkeypatch.setattr(kpi_resumen_lectura, "meses", _meses)
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


# --- Sales: the KPI Ventas tab's total ---------------------------------------


async def test_ventas_mes_is_the_kpi_total_of_the_last_complete_month(
        monkeypatch):
    llamadas = _kpi(monkeypatch)

    datos = await inicio.CONSTRUCTORES["ventas_mes"](_ctx(Sesion()))

    # HMCL included, as the KPI's default; every commercial line.
    assert datos == {"valor": TOTAL_CUBO, "mes": "2026-09"}
    assert llamadas == [[["2026-09"], t.HMCL_INCLUIR, None, t.DIM_SUCURSAL]]


async def test_ventas_mes_in_january_is_december_of_last_year(
        monkeypatch):
    llamadas = _kpi(monkeypatch, cubo=[])

    datos = await inicio.CONSTRUCTORES["ventas_mes"](
        _ctx(Sesion(), date(2027, 1, 1)))

    assert datos == {"valor": 0.0, "mes": "2026-12"}
    assert llamadas[0][0] == ["2026-12"]


async def test_ventas_anio_is_the_kpi_ano_corrido(monkeypatch):
    """January to the last month with sales, the KPI's `ultimo_mes`."""
    llamadas = _kpi(monkeypatch)

    datos = await inicio.CONSTRUCTORES["ventas_anio"](_ctx(Sesion()))

    assert datos == {
        "valor": TOTAL_CUBO, "desde": "2026-01", "hasta": "2026-09"}
    assert llamadas == [
        [HASTA_SEPTIEMBRE, t.HMCL_INCLUIR, None, t.DIM_SUCURSAL]]


async def test_ventas_anio_follows_the_kpi_when_the_month_has_sales(
        monkeypatch):
    """Like the KPI's "Año corrido": a month with sales loaded counts,
    even the current one."""
    llamadas = _kpi(monkeypatch, disponibles=["2025-12", "2026-10"])

    datos = await inicio.CONSTRUCTORES["ventas_anio"](_ctx(Sesion()))

    assert (datos["desde"], datos["hasta"]) == ("2026-01", "2026-10")
    assert llamadas[0][0] == [f"2026-{m:02d}" for m in range(1, 11)]


async def test_ventas_anio_is_the_year_of_the_last_month_with_sales(
        monkeypatch):
    llamadas = _kpi(monkeypatch, disponibles=["2026-11", "2026-12"])

    datos = await inicio.CONSTRUCTORES["ventas_anio"](
        _ctx(Sesion(), date(2027, 1, 3)))

    assert (datos["desde"], datos["hasta"]) == ("2026-01", "2026-12")
    assert llamadas[0][0] == [f"2026-{m:02d}" for m in range(1, 13)]


async def test_ventas_anio_without_any_sales_is_zero(monkeypatch):
    llamadas = _kpi(monkeypatch, disponibles=[])

    datos = await inicio.CONSTRUCTORES["ventas_anio"](_ctx(Sesion()))

    assert datos == {"valor": 0.0, "desde": None, "hasta": None}
    assert llamadas == []


async def test_sales_follow_the_configured_lines(monkeypatch):
    """A line outside the configured ones is not recognized by the KPI
    either: it is not counted."""
    reglas = t.REGLAS_POR_DEFECTO._replace(lineas=("ACCESORIOS",))
    _kpi(monkeypatch, reglas=reglas)

    datos = await inicio.CONSTRUCTORES["ventas_mes"](_ctx(Sesion()))

    assert datos["valor"] == 9999.0


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


CUBO_ASESORES = [
    _fila("2026-09", "REPUESTOS", "100", clave="P:ANA"),
    _fila("2026-09", "LLANTAS", "50", hmcl=True, clave="P:LUIS"),
    _fila("2026-09", None, "900", clave="P:SIN-LINEA"),
    _fila("2026-09", "REPUESTOS", "100", clave="P:DEVOLVIO"),
    _fila("2026-09", "REPUESTOS", "-100", clave="P:DEVOLVIO"),
    _fila("2026-09", "REPUESTOS", "800", clave=t.GRUPO_RESTO),
    _fila("2026-09", "REPUESTOS", "700", clave=t.GRUPO_OTROS),
]


async def test_asesores_are_the_kpi_asesores_with_sales_last_month(
        monkeypatch):
    """Like KPIs > Asesores "con venta": a person row of the asesor cube
    with a positive sale; groups, line-less sales and a net zero do not
    count."""
    llamadas = _kpi(monkeypatch, cubo=CUBO_ASESORES)

    datos = await inicio.CONSTRUCTORES["asesores"](_ctx(Sesion()))

    assert datos == {"cantidad": 2, "mes": "2026-09"}
    assert llamadas == [[["2026-09"], t.HMCL_INCLUIR, None, t.DIM_ASESOR]]


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
