"""
Motored satisfaction survey, slice T5: detractor case management API
(`/api/motored/detractores*`). Fake session, queued results in the exact order
the service issues its queries (the first queued list is the readiness probe).
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import get_motored_user_lookup
from app.motored.models.caso_detractor import CasoDetractor
from app.motored.models.caso_detractor_accion import CasoDetractorAccion
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

BASE = "/api/motored/detractores"
USER_ID = str(uuid.uuid4())
CASO_ID = uuid.uuid4()
MATRIX = [
    "p_explicacion_tecnica", "p_confianza_reparacion", "p_servicio_taller",
    "p_calidad_mecanicos", "p_claridad_cobros", "p_originalidad_repuestos",
]


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "detractores-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "detractores-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=USER_ID, role="ADMIN"))
    yield
    app.dependency_overrides.clear()


def _caso(estado="ABIERTO", resultado=None, asignado_a=None):
    return SimpleNamespace(
        id=CASO_ID, numero=12, estado=estado, resultado=resultado, asignado_a=asignado_a,
        created_at=datetime(2026, 9, 1, 10), updated_at=datetime(2026, 9, 1, 10), cerrado_at=None,
    )


def _real_caso(estado="ABIERTO", asignado_a=None):
    return CasoDetractor(
        id=CASO_ID, numero=12, estado=estado, resultado=None, asignado_a=asignado_a,
        created_at=datetime(2026, 9, 1, 10),
    )


def _row(**over):
    base = dict(
        id=CASO_ID, numero=12, estado="ABIERTO", resultado=None,
        created_at=datetime(2026, 9, 1, 10), cerrado_at=None,
        asignado_id=None, asignado_nombre=None,
        nombre="Ana Perez", cedula="123", celular="300", placa="ABC12D", linea="Xtreet 401",
        centro_servicio="Cali Norte", sic="S1", tipo="SERVICIO_TALLER",
        satisfaccion_general=2, autoriza_datos=False, ultima_accion_at=datetime(2026, 9, 2),
        respuesta_created_at=datetime(2026, 9, 1, 9), observaciones="malo",
        carga_nombre_archivo="mayo.xlsx", carga_created_at=datetime(2026, 8, 30),
        **{col: None for col in MATRIX},
    )
    base["p_servicio_taller"] = 1
    base.update(over)
    return SimpleNamespace(**base)


def _accion(tipo="APERTURA", nombre=None, usuario_id=None, **over):
    base = dict(
        id=uuid.uuid4(), tipo=tipo, descripcion="d", estado_anterior=None, estado_nuevo=None,
        created_at=datetime(2026, 9, 1, 10), usuario_id=usuario_id, usuario_nombre=nombre,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _client(*results, role="ADMIN"):
    override_motored_user(MotoredUser(user_id=USER_ID, role=role))
    session = FakeAsyncSession(execute_queue=[[], *results])
    override_motored_db(session)
    return session


def _sql(stmt):
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# --- roles -----------------------------------------------------------------

@pytest.mark.parametrize("role", ["ADMIN", "SERVICIO_CLIENTE"])
def test_allowed_roles_can_list(role):
    _client([(0,)], [], [], role=role)
    with TestClient(app) as client:
        assert client.get(BASE).status_code == 200


@pytest.mark.parametrize("role", ["COMPRAS", "CONSULTA", "SUCURSAL"])
def test_other_roles_are_forbidden_everywhere(role):
    session = _client([], [], [], [], role=role)
    with TestClient(app) as client:
        assert client.get(BASE).status_code == 403
        assert client.get(f"{BASE}/{CASO_ID}").status_code == 403
        body = {"tipo": "NOTA", "descripcion": "hola mundo"}
        assert client.post(f"{BASE}/{CASO_ID}/acciones", json=body).status_code == 403
        est = {"estado": "EN_GESTION", "comentario": "arrancamos"}
        assert client.post(f"{BASE}/{CASO_ID}/estado", json=est).status_code == 403
    assert session.added == [] and session.committed is False


def test_servicio_cliente_reaches_detractores_through_real_confinement():
    async def _lookup(user_id: str):
        return MotoredUser(user_id=user_id, role="SERVICIO_CLIENTE")

    app.dependency_overrides.clear()
    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(FakeAsyncSession(execute_queue=[[], [(0,)], [], [], []]))
    token = create_motored_token(sub=USER_ID, role="SERVICIO_CLIENTE")
    with TestClient(app) as client:
        response = client.get(BASE, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


# --- list ------------------------------------------------------------------

def test_list_shape_pagination_and_counts():
    asignado = uuid.uuid4()
    rows = [_row(), _row(id=uuid.uuid4(), numero=13, estado="EN_GESTION", asignado_id=asignado,
                         asignado_nombre="Carla", ultima_accion_at=None)]
    session = _client([(7,)], rows, [("ABIERTO", 3), ("CERRADO", 4)])
    with TestClient(app) as client:
        body = client.get(f"{BASE}?page=2&page_size=2").json()
    assert (body["total"], body["page"], body["page_size"]) == (7, 2, 2)
    assert body["conteo_por_estado"] == {"ABIERTO": 3, "EN_GESTION": 0, "CERRADO": 4}
    first, second = body["items"]
    assert first["numero"] == 12 and first["asignado_a"] is None
    assert first["codigo"] == "DET-2026-000012" and second["codigo"] == "DET-2026-000013"
    assert first["cliente"] == {
        "nombre": "Ana Perez", "cedula": "123", "celular": "300", "placa": "ABC12D",
        "linea": "Xtreet 401", "centro_servicio": "Cali Norte",
    }
    assert first["satisfaccion_general"] == 2 and first["autoriza_datos"] is False
    assert first["ultima_accion_at"] is not None
    assert second["asignado_a"] == {"id": str(asignado), "nombre": "Carla"}
    assert second["ultima_accion_at"] is None
    page_sql = _sql(session.executed_statements[2])
    assert "ORDER BY caso_detractor.created_at DESC" in page_sql
    assert "LIMIT 2 OFFSET 2" in page_sql


def test_list_filters_are_applied_in_sql():
    session = _client([(0,)], [], [])
    url = (f"{BASE}?estado=CERRADO&centro_servicio=Cali%20Norte&autoriza_datos=false"
           "&desde=2026-09-01&hasta=2026-09-30&q=50%25_x")
    with TestClient(app) as client:
        assert client.get(url).status_code == 200
    sql = _sql(session.executed_statements[1])
    assert "caso_detractor.estado = 'CERRADO'" in sql
    assert "encuesta_registro.centro_servicio = 'Cali Norte'" in sql
    assert "encuesta_respuesta.autoriza_datos IS false" in sql or "autoriza_datos = false" in sql
    assert "caso_detractor.created_at >= '2026-09-01" in sql
    assert "caso_detractor.created_at < '2026-10-01" in sql  # `hasta` is inclusive
    for column in ("nombre", "cedula", "placa"):
        assert f"encuesta_registro.{column} ILIKE" in sql
    assert "ESCAPE" in sql
    # Check the bound value, not its literal rendering: SQLAlchemy 2.1 stopped
    # doubling backslashes under literal_binds, but the value sent to Postgres
    # is what matters. User wildcards `%` and `_` must arrive escaped.
    params = session.executed_statements[1].compile(dialect=postgresql.dialect()).params
    assert "%50\\%\\_x%" in params.values()


def test_list_counts_ignore_filters():
    session = _client([(0,)], [], [])
    with TestClient(app) as client:
        client.get(f"{BASE}?estado=CERRADO&q=zzz")
    counts_sql = _sql(session.executed_statements[3])
    assert "GROUP BY caso_detractor.estado" in counts_sql
    assert "WHERE" not in counts_sql


@pytest.mark.parametrize("query", ["estado=NOPE", "page=0", "page_size=0", "page_size=1000", "desde=x"])
def test_list_rejects_invalid_query(query):
    _client([(0,)], [], [])
    with TestClient(app) as client:
        assert client.get(f"{BASE}?{query}").status_code == 422


# --- detail ----------------------------------------------------------------

def test_detail_has_consent_flag_full_registro_respuesta_and_ordered_log():
    actor = uuid.uuid4()
    log = [
        _accion("APERTURA", None),
        _accion("LLAMADA", "Carla", actor, created_at=datetime(2026, 9, 2)),
    ]
    session = _client([_row()], log)
    with TestClient(app) as client:
        body = client.get(f"{BASE}/{CASO_ID}").json()
    assert body["autoriza_datos"] is False
    assert body["registro"] == {
        "nombre": "Ana Perez", "cedula": "123", "celular": "300", "linea": "Xtreet 401",
        "placa": "ABC12D", "sic": "S1", "centro_servicio": "Cali Norte", "tipo": "SERVICIO_TALLER",
        "carga": {"nombre_archivo": "mayo.xlsx", "fecha": "2026-08-30T00:00:00"},
    }
    respuesta = body["respuesta"]
    assert respuesta["satisfaccion_general"] == 2 and respuesta["autoriza_datos"] is False
    assert respuesta["observaciones"] == "malo" and respuesta["p_servicio_taller"] == 1
    assert respuesta["p_explicacion_tecnica"] is None  # NS/NR
    assert [a["tipo"] for a in body["acciones"]] == ["APERTURA", "LLAMADA"]
    assert body["acciones"][0]["usuario"] is None  # Sistema
    assert body["acciones"][1]["usuario"] == {"id": str(actor), "nombre": "Carla"}
    assert set(body["acciones"][0]) == {
        "id", "tipo", "descripcion", "estado_anterior", "estado_nuevo", "created_at", "usuario",
    }
    assert "ORDER BY caso_detractor_accion.created_at ASC" in _sql(session.executed_statements[2])


def test_detail_unknown_case_is_404():
    _client([])
    with TestClient(app) as client:
        response = client.get(f"{BASE}/{uuid.uuid4()}")
    assert response.status_code == 404


# --- add action ------------------------------------------------------------

def _post_action(body, caso, nombre="Ana Admin"):
    session = _client([caso] if caso else [], [SimpleNamespace(nombre=nombre)])
    with TestClient(app) as client:
        response = client.post(f"{BASE}/{CASO_ID}/acciones", json=body)
    return response, session


def test_add_action_happy_path_appends_and_returns_it():
    response, session = _post_action(
        {"tipo": "LLAMADA", "descripcion": "  Llamé al cliente, no contestó  "}, _real_caso("EN_GESTION")
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tipo"] == "LLAMADA" and body["descripcion"] == "Llamé al cliente, no contestó"
    assert body["usuario"] == {"id": USER_ID, "nombre": "Ana Admin"}
    (accion,) = session.added_of_type(CasoDetractorAccion)
    assert str(accion.usuario_id) == USER_ID and accion.caso_id == CASO_ID
    assert accion.estado_anterior is None and accion.estado_nuevo is None
    assert session.committed is True
    assert "FOR UPDATE" in _sql(session.executed_statements[1])


@pytest.mark.parametrize("tipo", ["APERTURA", "CAMBIO_ESTADO", "OTRO"])
def test_system_only_or_unknown_tipos_are_rejected(tipo):
    response, session = _post_action({"tipo": tipo, "descripcion": "descripcion valida"}, _real_caso())
    assert response.status_code == 422
    assert session.added == []


@pytest.mark.parametrize("descripcion", ["abc", "   ab   ", "", "x" * 4001])
def test_action_description_length_is_enforced(descripcion):
    response, session = _post_action({"tipo": "NOTA", "descripcion": descripcion}, _real_caso())
    assert response.status_code == 422
    assert session.added == []


@pytest.mark.parametrize("tipo", ["LLAMADA", "WHATSAPP", "COMPENSACION"])
def test_closed_case_rejects_contact_actions(tipo):
    response, session = _post_action({"tipo": tipo, "descripcion": "descripcion valida"}, _real_caso("CERRADO"))
    assert response.status_code == 409
    assert session.added == [] and session.committed is False


@pytest.mark.parametrize("tipo", ["NOTA", "CORRECCION"])
def test_closed_case_still_accepts_notes_and_corrections(tipo):
    response, session = _post_action({"tipo": tipo, "descripcion": "descripcion valida"}, _real_caso("CERRADO"))
    assert response.status_code == 201
    assert len(session.added_of_type(CasoDetractorAccion)) == 1


def test_add_action_unknown_case_is_404():
    response, session = _post_action({"tipo": "NOTA", "descripcion": "descripcion valida"}, None)
    assert response.status_code == 404
    assert session.added == []


# --- change state ----------------------------------------------------------

def _post_state(body, caso):
    """Queue: lock the case, then the detail (row + log) re-read after commit."""
    detail_row = _row(estado=body.get("estado", "ABIERTO"))
    session = _client([caso] if caso else [], [detail_row], [_accion()])
    with TestClient(app) as client:
        response = client.post(f"{BASE}/{CASO_ID}/estado", json=body)
    return response, session


@pytest.mark.parametrize(
    "current,body",
    [
        ("ABIERTO", {"estado": "EN_GESTION", "comentario": "Tomo el caso"}),
        ("ABIERTO", {"estado": "CERRADO", "resultado": "NO_CONTACTABLE", "comentario": "Sin datos validos"}),
        ("EN_GESTION", {"estado": "CERRADO", "resultado": "RECUPERADO", "comentario": "Cliente conforme"}),
    ],
)
def test_allowed_transitions_update_case_and_append_log(current, body):
    caso = _real_caso(current)
    response, session = _post_state(body, caso)
    assert response.status_code == 200
    assert caso.estado == body["estado"]
    assert caso.resultado == body.get("resultado")
    assert (caso.cerrado_at is not None) == (body["estado"] == "CERRADO")
    assert caso.updated_at is not None and caso.updated_at > datetime(2026, 9, 2)
    (accion,) = session.added_of_type(CasoDetractorAccion)
    assert accion.tipo == "CAMBIO_ESTADO"
    assert (accion.estado_anterior, accion.estado_nuevo) == (current, body["estado"])
    assert body["comentario"] in accion.descripcion
    if "resultado" in body:
        assert body["resultado"] in accion.descripcion
    assert str(accion.usuario_id) == USER_ID
    assert session.committed is True
    assert response.json()["estado"] == body["estado"]


@pytest.mark.parametrize(
    "current,estado",
    [("CERRADO", "CERRADO"), ("EN_GESTION", "EN_GESTION")],
)
def test_forbidden_transitions_are_409(current, estado):
    body = {"estado": estado, "comentario": "intento invalido"}
    if estado == "CERRADO":
        body["resultado"] = "RECUPERADO"
    caso = _real_caso(current)
    response, session = _post_state(body, caso)
    assert response.status_code == 409
    assert caso.estado == current
    assert session.added == [] and session.committed is False


def test_closed_case_message_is_clear():
    response, _ = _post_state(
        {"estado": "CERRADO", "resultado": "RECUPERADO", "comentario": "cerrar de nuevo"},
        _real_caso("CERRADO"),
    )
    assert "cerrado" in response.json()["detail"].lower()


def _reopen(asignado_a=None):
    caso = _real_caso("CERRADO", asignado_a=asignado_a)
    caso.resultado = "RECUPERADO"
    caso.cerrado_at = datetime(2026, 9, 5, 10)
    response, session = _post_state({"estado": "EN_GESTION", "comentario": "Cliente volvio a llamar"}, caso)
    return caso, response, session


def test_reopen_closed_case_clears_closure_and_logs_transition():
    caso, response, session = _reopen()
    assert response.status_code == 200
    assert caso.estado == "EN_GESTION"
    assert caso.resultado is None and caso.cerrado_at is None
    assert caso.updated_at > datetime(2026, 9, 2)
    (accion,) = session.added_of_type(CasoDetractorAccion)
    assert accion.tipo == "CAMBIO_ESTADO"
    assert (accion.estado_anterior, accion.estado_nuevo) == ("CERRADO", "EN_GESTION")
    assert accion.descripcion == "Caso reabierto: Cliente volvio a llamar"
    assert session.committed is True


def test_reopen_assigns_current_user_when_unassigned():
    caso, _, _ = _reopen()
    assert str(caso.asignado_a) == USER_ID


def test_reopen_keeps_existing_assignee():
    other = uuid.uuid4()
    caso, _, _ = _reopen(asignado_a=other)
    assert caso.asignado_a == other


@pytest.mark.parametrize(
    "body",
    [
        {"estado": "CERRADO", "comentario": "cierre sin resultado"},
        {"estado": "EN_GESTION", "resultado": "RECUPERADO", "comentario": "resultado de mas"},
        {"estado": "CERRADO", "resultado": "OTRO", "comentario": "resultado invalido"},
        {"estado": "ABIERTO", "comentario": "no se puede volver"},
        {"estado": "EN_GESTION", "comentario": "abc"},
        {"estado": "EN_GESTION", "comentario": "     "},
    ],
)
def test_state_body_validation_is_422(body):
    response, session = _post_state(body, _real_caso("ABIERTO"))
    assert response.status_code == 422
    assert session.added == []


def test_moving_to_en_gestion_assigns_current_user_when_unassigned():
    caso = _real_caso("ABIERTO")
    _post_state({"estado": "EN_GESTION", "comentario": "Tomo el caso"}, caso)
    assert str(caso.asignado_a) == USER_ID


def test_moving_to_en_gestion_keeps_existing_assignee():
    other = uuid.uuid4()
    caso = _real_caso("ABIERTO", asignado_a=other)
    _post_state({"estado": "EN_GESTION", "comentario": "Tomo el caso"}, caso)
    assert caso.asignado_a == other


def test_state_change_locks_the_case_row_before_validating():
    _, session = _post_state({"estado": "EN_GESTION", "comentario": "Tomo el caso"}, _real_caso())
    lock_sql = _sql(session.executed_statements[1])
    assert "FROM caso_detractor" in lock_sql and "FOR UPDATE" in lock_sql


def test_state_change_unknown_case_is_404():
    response, session = _post_state({"estado": "EN_GESTION", "comentario": "Tomo el caso"}, None)
    assert response.status_code == 404
    assert session.added == []


def _list_sql(q):
    session = _client([(0,)], [], [])
    with TestClient(app) as client:
        assert client.get(f"{BASE}?q={q}").status_code == 200
    return session.executed_statements[1]


def test_search_by_case_code_filters_on_number_and_year_not_text():
    stmt = _list_sql("det-2026-000012")
    sql = _sql(stmt)
    assert "caso_detractor.numero = 12" in sql
    assert "EXTRACT(year FROM caso_detractor.created_at) = 2026" in sql
    assert "ILIKE" not in sql


def test_search_with_plain_digits_stays_a_text_search():
    sql = _sql(_list_sql("123456"))
    assert "encuesta_registro.cedula ILIKE" in sql
    assert "caso_detractor.numero =" not in sql
