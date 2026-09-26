"""
Motored Pedidos — HTTP-layer coverage for `GET /api/motored/demanda-perdida/
bot-lineas` (sdd/motored-ventas-perdidas-panel, Phase 4 "GET listing
endpoint" — S4 commit slice; design D2, spec "Per-line listing scoped to
bot-origin data only" / "Filterable by date range..." / "Deactivated
sucursal or asesor does not restrict visibility or action").

ADMIN-only (mirrors `api/usuarios.py`'s `_require_admin` pattern). `desde`/
`hasta` are REQUIRED FastAPI query params (unlike `GET /cargas?origen=BOT`,
which keeps them `Optional` because that endpoint also serves the
`origen=EXCEL` default path) — a span over 31 days is `422 {"code":
"RANGO_MAXIMO_31_DIAS"}` (design D2's own words), mirroring `api/cargas.py`'s
`_BOT_RANGO_MAX_DIAS` guard for the same volume reason (~940 bot lines/day).

Same `FakeAsyncSession`/`override_motored_db`/`override_motored_user`
convention as `test_cargas_api.py`/`test_usuarios_api.py`. `get_motored_
db_or_503`'s own `SELECT 1` connectivity probe consumes the FIRST queued
page on every request (same convention `test_usuarios_api.py`'s `_client_as`
documents) — every `execute_queue` below is prefixed with `[]` for that
reason.

`_FilteringFakeSession` (local to this file, per the established
per-file-filter convention already documented in `conftest.py`'s docstring
for `AdditiveDemandaPerdidaFakeSession`) actually evaluates the compiled
`WHERE` clause's top-level equality/range predicates against the queued
candidate `DemandaPerdidaBotLinea` row of each tuple — proving the endpoint's
SQL filters real rows, not just that a filter parameter was accepted.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, _ExecuteResult, override_motored_db, override_motored_user

ALL_ROLES = ["ADMIN", "COMPRAS", "SUCURSAL", "CONSULTA"]
BOT_LINEAS_URL = "/api/motored/demanda-perdida/bot-lineas"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "bot-lineas-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "bot-lineas-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _client_as(role: str, execute_queue) -> TestClient:
    """`[]` prepended for `get_motored_db_or_503`'s own `SELECT 1` probe —
    same convention as `test_usuarios_api.py`'s `_client_as`."""
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(FakeAsyncSession(execute_queue=[[]] + list(execute_queue)))
    return TestClient(app)


def _client_with_session(role: str, session: "FakeAsyncSession") -> TestClient:
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(session)
    return TestClient(app)


def _linea(**overrides) -> DemandaPerdidaBotLinea:
    """Construido a mano (nunca vía `db.add()`) para fijar TODOS los campos
    explícitamente — mismo criterio que `_carga()` en `test_cargas_api.py`."""
    base = dict(
        id=uuid.uuid4(),
        carga_id=uuid.uuid4(),
        usuario_id=uuid.uuid4(),
        fecha=date(2026, 9, 20),
        sucursal_id=uuid.uuid4(),
        referencia_id=uuid.uuid4(),
        cantidad=Decimal("3"),
        estado="ACTIVA",
        editado_por=None,
        editado_en=None,
        anulado_por=None,
        anulado_en=None,
        created_at=datetime(2026, 9, 20, 10, 0, 0),
    )
    base.update(overrides)
    return DemandaPerdidaBotLinea(**base)


def _fila(
    linea: DemandaPerdidaBotLinea,
    *,
    sucursal_nombre: str = "Sucursal Centro",
    sucursal_activa: bool = True,
    asesor_nombre: str = "Juan Asesor",
    asesor_activo: bool = True,
    referencia_codigo: str = "REF-1",
    referencia_nombre: str = "Referencia Uno",
    carga_log=None,
    editor: "tuple | None" = None,
    anulador: "tuple | None" = None,
) -> tuple:
    """Una fila del `SELECT` con joins que el endpoint ejecuta (design D2):
    `(linea, sucursal_nombre, sucursal_activa, asesor_nombre, asesor_activo,
    referencia_codigo, referencia_nombre, carga_log, editor_id, editor_nombre,
    editor_activo, anulador_id, anulador_nombre, anulador_activo)`.
    `editor`/`anulador` son `(id, nombre, activo)` o `None` (LEFT JOIN sin
    match, columnas todas NULL)."""
    editor_id, editor_nombre, editor_activo = editor or (None, None, None)
    anulador_id, anulador_nombre, anulador_activo = anulador or (None, None, None)
    return (
        linea,
        sucursal_nombre,
        sucursal_activa,
        asesor_nombre,
        asesor_activo,
        referencia_codigo,
        referencia_nombre,
        carga_log,
        editor_id,
        editor_nombre,
        editor_activo,
        anulador_id,
        anulador_nombre,
        anulador_activo,
    )


def _extraer_predicados(stmt) -> list:
    """Copiado de `test_cargas_api.py::_extraer_predicados` (convención
    establecida: cada archivo lo define localmente, ver el docstring de
    `AdditiveDemandaPerdidaFakeSession` en `conftest.py`) — camina el WHERE
    compilado de nivel superior (unido por AND) y devuelve `(columna,
    operador, valor)` por cada comparación directa columna-vs-literal."""
    whereclause = getattr(stmt, "whereclause", None)
    if whereclause is None:
        return []
    clausulas = getattr(whereclause, "clauses", [whereclause])
    predicados = []
    for clausula in clausulas:
        left = getattr(clausula, "left", None)
        right = getattr(clausula, "right", None)
        operador = getattr(clausula, "operator", None)
        nombre_columna = getattr(left, "key", None)
        if nombre_columna is None or operador is None or not hasattr(right, "value"):
            continue
        predicados.append((nombre_columna, operador, right.value))
    return predicados


class _FilteringFakeSession(FakeAsyncSession):
    """Como `FakeAsyncSession`, pero filtra la página encolada (una lista de
    tuplas `_fila(...)`) por los predicados REALES extraídos del `select`
    compilado, evaluados contra `fila[0]` (la instancia `DemandaPerdidaBot
    Linea`, dueña de TODAS las columnas que el endpoint filtra) — prueba
    comportamiento real, no solo que el parámetro fue aceptado."""

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if not self._execute_queue:
            raise AssertionError(
                "FakeAsyncSession.execute() called more times than expected "
                "— update the test's execute_queue."
            )
        rows = self._execute_queue.pop(0)
        predicados = _extraer_predicados(stmt)
        if predicados and rows and isinstance(rows[0], tuple):
            rows = [
                fila for fila in rows
                if all(operador(getattr(fila[0], nombre), valor) for nombre, operador, valor in predicados)
            ]
        return _ExecuteResult(rows)


def _client_filtering(role: str, paginas) -> TestClient:
    """`paginas` es la lista de resultados a encolar DESPUÉS del `SELECT 1`
    de disponibilidad (que se antepone acá, como en `_client_as`)."""
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(_FilteringFakeSession(execute_queue=[[]] + list(paginas)))
    return TestClient(app)


# ---------------------------------------------------------------------------
# ADMIN-only + validación de rango
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["COMPRAS", "SUCURSAL", "CONSULTA"])
def test_listar_bot_lineas_rechaza_roles_no_admin(role):
    client = _client_as(role, execute_queue=[])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-20"})

    assert response.status_code == 403


def test_listar_bot_lineas_admin_puede_acceder():
    client = _client_as("ADMIN", execute_queue=[[]])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-20"})

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_listar_bot_lineas_sin_desde_hasta_es_422():
    client = _client_as("ADMIN", execute_queue=[])

    response = client.get(BOT_LINEAS_URL)

    assert response.status_code == 422


def test_listar_bot_lineas_solo_desde_es_422():
    client = _client_as("ADMIN", execute_queue=[])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01"})

    assert response.status_code == 422


def test_listar_bot_lineas_hasta_anterior_a_desde_es_422():
    client = _client_as("ADMIN", execute_queue=[])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-20", "hasta": "2026-09-01"})

    assert response.status_code == 422


def test_listar_bot_lineas_rango_mayor_a_31_dias_es_422_con_codigo():
    client = _client_as("ADMIN", execute_queue=[])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-01-01", "hasta": "2026-03-01"})

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "RANGO_MAXIMO_31_DIAS"}


def test_listar_bot_lineas_rango_de_exactos_31_dias_es_valido():
    """Límite inclusive: 31 días exactos NO debe rechazarse (solo > 31)."""
    client = _client_as("ADMIN", execute_queue=[[]])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-08-01", "hasta": "2026-09-01"})

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Forma de la respuesta — campos, método desde carga_archivo.log, referencias
# de editor/anulador nulas cuando la línea nunca fue tocada desde el panel
# ---------------------------------------------------------------------------

def test_listar_bot_lineas_mapea_todos_los_campos_de_una_linea_activa_sin_tocar():
    linea = _linea(estado="ACTIVA", cantidad=Decimal("5"))
    fila = _fila(
        linea,
        sucursal_nombre="Sucursal Norte",
        sucursal_activa=True,
        asesor_nombre="María Asesora",
        asesor_activo=True,
        referencia_codigo="ABC-100",
        referencia_nombre="Filtro de aceite",
        carga_log={"metodo": "FOTO"},
    )
    client = _client_as("ADMIN", execute_queue=[[fila]])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-24"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["linea_id"] == str(linea.id)
    assert row["carga_id"] == str(linea.carga_id)
    assert row["fecha"] == "2026-09-20"
    assert row["cantidad"] == 5.0
    assert row["estado"] == "ACTIVA"
    assert row["metodo"] == "FOTO"
    assert row["asesor"] == {"id": str(linea.usuario_id), "nombre": "María Asesora", "activo": True}
    assert row["sucursal"] == {"id": str(linea.sucursal_id), "nombre": "Sucursal Norte", "activa": True}
    assert row["referencia"] == {
        "id": str(linea.referencia_id), "codigo": "ABC-100", "nombre": "Filtro de aceite",
    }
    assert row["editado_por"] is None
    assert row["editado_en"] is None
    assert row["anulado_por"] is None
    assert row["anulado_en"] is None


def test_listar_bot_lineas_metodo_manual_desde_carga_log():
    """Task instruction: `metodo` viene de `carga_archivo.log['metodo']`,
    no de la propia `DemandaPerdidaBotLinea` (que no tiene esa columna)."""
    linea = _linea()
    fila = _fila(linea, carga_log={"metodo": "MANUAL"})
    client = _client_as("ADMIN", execute_queue=[[fila]])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-24"})

    assert response.status_code == 200, response.text
    assert response.json()[0]["metodo"] == "MANUAL"


def test_listar_bot_lineas_linea_editada_y_anulada_incluye_ambas_referencias():
    editor_id = uuid.uuid4()
    anulador_id = uuid.uuid4()
    linea = _linea(
        estado="ANULADA",
        editado_por=editor_id,
        editado_en=datetime(2026, 9, 21, 8, 0, 0, tzinfo=timezone.utc),
        anulado_por=anulador_id,
        anulado_en=datetime(2026, 9, 22, 9, 0, 0, tzinfo=timezone.utc),
    )
    fila = _fila(
        linea,
        editor=(editor_id, "Ana Editora", True),
        anulador=(anulador_id, "Beto Anulador", False),
    )
    client = _client_as("ADMIN", execute_queue=[[fila]])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-24"})

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["editado_por"] == {"id": str(editor_id), "nombre": "Ana Editora", "activo": True}
    assert row["editado_en"] is not None
    assert row["anulado_por"] == {"id": str(anulador_id), "nombre": "Beto Anulador", "activo": False}
    assert row["anulado_en"] is not None


def test_listar_bot_lineas_sin_resultados_devuelve_lista_vacia():
    """Empty state honesto: `desde`/`hasta` válidos, ninguna fila en rango
    (el `WHERE fecha` real excluye la única candidata encolada) — no un
    error, una lista vacía real."""
    linea_fuera_de_rango = _linea(fecha=date(2026, 1, 1))
    session = _FilteringFakeSession(execute_queue=[[], [_fila(linea_fuera_de_rango)]])
    client = _client_with_session("ADMIN", session)

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-24"})

    assert response.status_code == 200, response.text
    assert response.json() == []


# ---------------------------------------------------------------------------
# Filtros — sucursal_id, usuario_id, estado, individuales y combinados
# ---------------------------------------------------------------------------

def test_listar_bot_lineas_filtra_por_sucursal_id():
    sucursal_buscada = uuid.uuid4()
    linea_match = _linea(sucursal_id=sucursal_buscada)
    linea_otra_sucursal = _linea(sucursal_id=uuid.uuid4())
    client = _client_filtering("ADMIN", [[_fila(linea_match), _fila(linea_otra_sucursal)]])

    response = client.get(
        BOT_LINEAS_URL,
        params={"desde": "2026-09-01", "hasta": "2026-09-24", "sucursal_id": str(sucursal_buscada)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["linea_id"] for row in body] == [str(linea_match.id)]


def test_listar_bot_lineas_filtra_por_usuario_id():
    asesor_buscado = uuid.uuid4()
    linea_match = _linea(usuario_id=asesor_buscado)
    linea_otro_asesor = _linea(usuario_id=uuid.uuid4())
    client = _client_filtering("ADMIN", [[_fila(linea_match), _fila(linea_otro_asesor)]])

    response = client.get(
        BOT_LINEAS_URL,
        params={"desde": "2026-09-01", "hasta": "2026-09-24", "usuario_id": str(asesor_buscado)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["linea_id"] for row in body] == [str(linea_match.id)]


def test_listar_bot_lineas_filtra_por_estado():
    linea_activa = _linea(estado="ACTIVA")
    linea_anulada = _linea(estado="ANULADA")
    client = _client_filtering("ADMIN", [[_fila(linea_activa), _fila(linea_anulada)]])

    response = client.get(
        BOT_LINEAS_URL,
        params={"desde": "2026-09-01", "hasta": "2026-09-24", "estado": "ANULADA"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["linea_id"] for row in body] == [str(linea_anulada.id)]


def test_listar_bot_lineas_filtros_combinados_reducen_resultado():
    sucursal_buscada = uuid.uuid4()
    asesor_buscado = uuid.uuid4()
    linea_match = _linea(sucursal_id=sucursal_buscada, usuario_id=asesor_buscado, estado="ACTIVA")
    linea_sucursal_correcta_pero_otro_asesor = _linea(
        sucursal_id=sucursal_buscada, usuario_id=uuid.uuid4(), estado="ACTIVA",
    )
    linea_todo_correcto_pero_anulada = _linea(
        sucursal_id=sucursal_buscada, usuario_id=asesor_buscado, estado="ANULADA",
    )
    client = _client_filtering(
        "ADMIN",
        [[
            _fila(linea_match),
            _fila(linea_sucursal_correcta_pero_otro_asesor),
            _fila(linea_todo_correcto_pero_anulada),
        ]],
    )

    response = client.get(
        BOT_LINEAS_URL,
        params={
            "desde": "2026-09-01", "hasta": "2026-09-24",
            "sucursal_id": str(sucursal_buscada), "usuario_id": str(asesor_buscado), "estado": "ACTIVA",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["linea_id"] for row in body] == [str(linea_match.id)]


# ---------------------------------------------------------------------------
# Q1 resuelto (design): una sucursal/asesor desactivado NO restringe
# visibilidad — la línea sigue apareciendo con su flag activo/activa en
# `False`, nunca oculta.
# ---------------------------------------------------------------------------

def test_listar_bot_lineas_de_sucursal_desactivada_sigue_apareciendo():
    linea = _linea()
    fila = _fila(linea, sucursal_nombre="Sucursal Cerrada", sucursal_activa=False)
    client = _client_as("ADMIN", execute_queue=[[fila]])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-24"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["sucursal"] == {
        "id": str(linea.sucursal_id), "nombre": "Sucursal Cerrada", "activa": False,
    }


def test_listar_bot_lineas_de_asesor_desactivado_sigue_apareciendo():
    linea = _linea()
    fila = _fila(linea, asesor_nombre="Ex Asesor", asesor_activo=False)
    client = _client_as("ADMIN", execute_queue=[[fila]])

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-24"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["asesor"] == {
        "id": str(linea.usuario_id), "nombre": "Ex Asesor", "activo": False,
    }


# ---------------------------------------------------------------------------
# Tope de 2000 filas + orden fecha DESC (design D2)
# ---------------------------------------------------------------------------

def test_listar_bot_lineas_aplica_limite_de_2000_filas():
    """Enfoque de la propia instrucción de la tarea: probar que el `LIMIT`
    está presente en el statement compilado, no insertar 2000+ filas."""
    session = FakeAsyncSession(execute_queue=[[], []])
    client = _client_with_session("ADMIN", session)

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-24"})

    assert response.status_code == 200, response.text
    consultas_reales = [
        stmt for stmt in session.executed_statements
        if getattr(stmt, "_limit_clause", None) is not None
    ]
    assert len(consultas_reales) == 1
    assert consultas_reales[0]._limit_clause.value == 2000


def test_listar_bot_lineas_ordena_por_fecha_desc_created_at_desc():
    """`FakeAsyncSession` no ordena por sí sola (solo devuelve la página
    encolada) -- esta prueba introspecciona el `ORDER BY` REAL del statement
    compilado (design D2: "ordenado por fecha DESC, created_at DESC"), en
    vez de confiar en el orden en que el test encoló las filas."""
    session = FakeAsyncSession(execute_queue=[[], []])
    client = _client_with_session("ADMIN", session)

    response = client.get(BOT_LINEAS_URL, params={"desde": "2026-09-01", "hasta": "2026-09-24"})

    assert response.status_code == 200, response.text
    stmt = session.executed_statements[-1]
    columnas = [
        (getattr(getattr(clausula, "element", None), "key", None), clausula.modifier.__name__)
        for clausula in stmt._order_by_clauses
    ]
    assert columnas == [("fecha", "desc_op"), ("created_at", "desc_op")]
