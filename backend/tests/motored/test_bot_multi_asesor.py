"""
Several advisors sharing one Telegram account (odd/tasks/lore-multi-asesor-telegram.md, T1).

Security property under test: the optional `X-Lore-Usuario-Id` header can
NEVER let a caller act as a `usuario` that is not linked to the calling
`telegram_id`. The fake session enforces the `telegram_id` WHERE clause for
real (`_FilteringFakeSession`), so a foreign usuario sitting in the queued
rows is only excluded if the production query actually filters by Telegram.

Endpoint used to exercise actor resolution: `GET /bot/demanda-perdida/hoy`
(behind `require_bot_asesor_o_admin`, one cheap query after the actor).
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.models.usuario import MotoredRole
from app.motored.models.usuario_sucursal import UsuarioSucursal
from tests.motored.conftest import FakeAsyncSession, override_motored_db
from tests.motored.test_bot_api import (
    LORE_SECRET,
    BOT_URL,
    _admin,
    _asesor,
    _FakeAdminTelegramRow,
    _FilteringFakeSession,
    _headers,
)

TELEGRAM = 900
OTRO_TELEGRAM = 901


@pytest.fixture(autouse=True)
def _lore_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "bot-test-motored-secret-ma")
    monkeypatch.setattr(settings, "SECRET_KEY", "bot-test-asc360-secret-ma")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "bot-test-sonia-secret-ma")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", LORE_SECRET)
    yield
    app.dependency_overrides.clear()


def _con_usuario(telegram_id, usuario_id) -> dict:
    headers = _headers(telegram_id)
    headers["X-Lore-Usuario-Id"] = usuario_id
    return headers


def _persona(nombre, telegram_id=TELEGRAM, **overrides):
    return _asesor(nombre=nombre, telegram_id=telegram_id, status="approved", **overrides)


def _client(*filas_por_consulta):
    """`[[]]` = readiness probe; each following list is one queued result,
    filtered by the WHERE clause of the statement that consumes it."""
    session = _FilteringFakeSession(execute_queue=[[]] + [list(f) for f in filas_por_consulta])
    override_motored_db(session)
    return TestClient(app), session


def _hoy(client, headers):
    return client.get(f"{BOT_URL}/demanda-perdida/hoy", headers=headers)


def _codigo(response) -> str:
    return response.json()["detail"]["code"]


# ---------------------------------------------------------------------------
# Header absent
# ---------------------------------------------------------------------------

def test_no_header_with_exactly_one_advisor_is_backward_compatible():
    ana = _persona("Ana")
    client, _ = _client([ana], [])

    response = _hoy(client, _headers(TELEGRAM))

    assert response.status_code == 200, response.text


def test_no_header_with_more_than_one_usable_advisor_returns_409_asesor_requerido():
    client, _ = _client([_persona("Ana"), _persona("Beto")])

    response = _hoy(client, _headers(TELEGRAM))

    assert response.status_code == 409
    assert _codigo(response) == "ASESOR_REQUERIDO"


def test_no_header_uses_the_only_usable_advisor_when_the_others_are_pending():
    ana = _persona("Ana")
    beto_pendiente = _asesor(nombre="Beto", telegram_id=TELEGRAM, status="pending")
    client, session = _client([beto_pendiente, ana], [])

    response = _hoy(client, _headers(TELEGRAM))

    assert response.status_code == 200, response.text
    assert str(ana.id) in _valores_de_ultima_consulta(session)


def test_no_header_with_several_candidates_and_none_usable_is_denied():
    beto = _asesor(nombre="Beto", telegram_id=TELEGRAM, status="pending")
    caro = _asesor(nombre="Caro", telegram_id=TELEGRAM, status="rejected")
    client, _ = _client([beto, caro])

    response = _hoy(client, _headers(TELEGRAM))

    assert response.status_code == 403
    assert _codigo(response) in {"PENDIENTE", "RECHAZADO"}


def test_no_header_and_no_usuario_is_still_no_registrado():
    client, _ = _client([])

    response = _hoy(client, _headers(TELEGRAM))

    assert response.status_code == 403
    assert _codigo(response) == "NO_REGISTRADO"


# ---------------------------------------------------------------------------
# Header present: it must belong to the calling Telegram
# ---------------------------------------------------------------------------

def _valores_de_ultima_consulta(session) -> list:
    params = session.executed_statements[-1].compile().params
    return [str(v) for v in params.values()]


def test_header_selects_that_advisor_and_scopes_the_query_to_them():
    ana, beto = _persona("Ana"), _persona("Beto")
    client, session = _client([ana, beto], [])

    response = _hoy(client, _con_usuario(TELEGRAM, str(beto.id)))

    assert response.status_code == 200, response.text
    valores = _valores_de_ultima_consulta(session)
    assert str(beto.id) in valores
    assert str(ana.id) not in valores


def test_header_uppercase_uuid_is_accepted():
    ana, beto = _persona("Ana"), _persona("Beto")
    client, session = _client([ana, beto], [])

    response = _hoy(client, _con_usuario(TELEGRAM, str(beto.id).upper()))

    assert response.status_code == 200, response.text
    assert str(beto.id) in _valores_de_ultima_consulta(session)


def test_header_matching_the_only_advisor_is_accepted():
    ana = _persona("Ana")
    client, _ = _client([ana], [])

    response = _hoy(client, _con_usuario(TELEGRAM, str(ana.id)))

    assert response.status_code == 200, response.text


def test_header_with_a_usuario_of_another_telegram_returns_403_not_belongs():
    """The foreign usuario IS in the queued rows: only the production
    `WHERE telegram_id = ...` keeps it out of the candidates."""
    ana = _persona("Ana")
    ajeno = _persona("Ajeno", telegram_id=OTRO_TELEGRAM)
    client, _ = _client([ana, ajeno])

    response = _hoy(client, _con_usuario(TELEGRAM, str(ajeno.id)))

    assert response.status_code == 403
    assert _codigo(response) == "ASESOR_NO_PERTENECE"


def test_header_with_a_usuario_of_another_telegram_never_reaches_the_business_query():
    ana = _persona("Ana")
    ajeno = _persona("Ajeno", telegram_id=OTRO_TELEGRAM)
    client, session = _client([ana, ajeno], [])

    _hoy(client, _con_usuario(TELEGRAM, str(ajeno.id)))

    assert len(session.executed_statements) == 2  # probe + candidates, nothing else


def test_header_with_an_unknown_uuid_returns_403_not_belongs():
    client, _ = _client([_persona("Ana")])

    response = _hoy(client, _con_usuario(TELEGRAM, str(uuid.uuid4())))

    assert response.status_code == 403
    assert _codigo(response) == "ASESOR_NO_PERTENECE"


@pytest.mark.parametrize(
    "valor",
    ["abc", "", "1", "not-a-uuid", "' OR 1=1 --", "0" * 40, " ", str(uuid.uuid4()) + "x"],
)
def test_header_malformed_returns_403_not_belongs(valor):
    client, _ = _client([_persona("Ana")])

    response = _hoy(client, _con_usuario(TELEGRAM, valor))

    assert response.status_code == 403
    assert _codigo(response) == "ASESOR_NO_PERTENECE"


def test_header_with_a_usuario_of_another_telegram_is_denied_even_for_a_single_advisor_telegram():
    """Backward compatibility must not turn the header into a bypass."""
    ana = _persona("Ana")
    ajeno = _persona("Ajeno", telegram_id=OTRO_TELEGRAM)
    client, _ = _client([ana, ajeno])

    response = _hoy(client, _con_usuario(TELEGRAM, str(ajeno.id)))

    assert response.status_code == 403


@pytest.mark.parametrize(
    "overrides, codigo",
    [
        ({"status": "pending"}, "PENDIENTE"),
        ({"status": "rejected"}, "RECHAZADO"),
        ({"status": "approved", "activo": False}, "INACTIVO"),
    ],
)
def test_header_chosen_advisor_still_passes_the_status_and_activo_gates(overrides, codigo):
    ana = _persona("Ana")
    elegido = _asesor(nombre="Beto", telegram_id=TELEGRAM, **{"status": "approved", **overrides})
    client, session = _client([ana, elegido], [])

    response = _hoy(client, _con_usuario(TELEGRAM, str(elegido.id)))

    assert response.status_code == 403
    assert _codigo(response) == codigo
    assert len(session.executed_statements) == 2  # nothing ran on that advisor's behalf


# ---------------------------------------------------------------------------
# GET /yo
# ---------------------------------------------------------------------------

def test_yo_with_two_advisors_lists_both_without_single_actor_fields():
    sucursal = uuid.uuid4()
    ana = _persona("Ana")
    ana.sucursales = [UsuarioSucursal(id=uuid.uuid4(), usuario_id=ana.id, sucursal_id=sucursal)]
    beto = _asesor(nombre="Beto", telegram_id=TELEGRAM, status="pending", activo=True)
    client, _ = _client([ana, beto])

    response = client.get(f"{BOT_URL}/yo", headers=_headers(TELEGRAM))

    assert response.status_code == 200, response.text
    body = response.json()
    assert "id" not in body
    por_id = {a["id"]: a for a in body["asesores"]}
    assert set(por_id) == {str(ana.id), str(beto.id)}
    assert por_id[str(ana.id)] == {
        "id": str(ana.id), "nombre": "Ana", "role": "ASESOR_MOSTRADOR",
        "status": "approved", "activo": True, "sucursales": [str(sucursal)],
    }
    assert por_id[str(beto.id)]["status"] == "pending"


def test_yo_with_one_advisor_keeps_the_legacy_fields_and_adds_the_list():
    ana = _persona("Ana")
    client, _ = _client([ana])

    body = client.get(f"{BOT_URL}/yo", headers=_headers(TELEGRAM)).json()

    assert body["id"] == str(ana.id)
    assert body["nombre"] == "Ana"
    assert body["status"] == "approved"
    assert [a["id"] for a in body["asesores"]] == [str(ana.id)]


def test_yo_does_not_list_advisors_of_another_telegram():
    ana = _persona("Ana")
    ajeno = _persona("Ajeno", telegram_id=OTRO_TELEGRAM)
    client, _ = _client([ana, ajeno])

    body = client.get(f"{BOT_URL}/yo", headers=_headers(TELEGRAM)).json()

    assert [a["id"] for a in body["asesores"]] == [str(ana.id)]


def test_yo_ignores_the_usuario_header_and_still_lists_only_own_telegram():
    ana = _persona("Ana")
    ajeno = _persona("Ajeno", telegram_id=OTRO_TELEGRAM)
    client, _ = _client([ana, ajeno])

    response = client.get(f"{BOT_URL}/yo", headers=_con_usuario(TELEGRAM, str(ajeno.id)))

    assert response.status_code == 200
    assert [a["id"] for a in response.json()["asesores"]] == [str(ana.id)]


def test_yo_returns_404_when_the_telegram_has_no_usuario():
    client, _ = _client([_persona("Ajeno", telegram_id=OTRO_TELEGRAM)])

    response = client.get(f"{BOT_URL}/yo", headers=_headers(TELEGRAM))

    assert response.status_code == 404
    assert _codigo(response) == "NO_REGISTRADO"


# ---------------------------------------------------------------------------
# POST /registro
# ---------------------------------------------------------------------------

def _registro(client, phone="3009998888", telegram_id=TELEGRAM):
    payload = {"nombre": "Beto Nuevo", "phone": phone, "sucursal_id": str(uuid.uuid4())}
    return client.post(f"{BOT_URL}/registro", json=payload, headers=_headers(telegram_id))


def _client_registro(existentes, admin_rows=()):
    session = _FilteringFakeSession(execute_queue=[[], list(existentes), list(admin_rows)])
    override_motored_db(session)
    return TestClient(app), session


def test_registro_allows_a_second_advisor_with_a_different_phone_on_the_same_telegram():
    ana = _persona("Ana", phone="3001234567")
    client, session = _client_registro([ana])

    response = _registro(client, phone="3009998888")

    assert response.status_code == 201, response.text
    assert len(session.added_of_type(type(ana))) == 1


@pytest.mark.parametrize("status", ["pending", "approved"])
def test_registro_rejects_the_same_person_same_telegram_and_phone(status):
    ana = _asesor(nombre="Ana", telegram_id=TELEGRAM, phone="3009998888", status=status)
    client, session = _client_registro([ana])

    response = _registro(client, phone="3009998888")

    assert response.status_code == 409
    assert _codigo(response) == "YA_REGISTRADO"
    assert session.added == []


def test_registro_allows_the_same_phone_again_after_a_rejection():
    rechazada = _asesor(nombre="Ana", telegram_id=TELEGRAM, phone="3009998888", status="rejected")
    client, _ = _client_registro([rechazada])

    response = _registro(client, phone="3009998888")

    assert response.status_code == 201, response.text


def test_registro_rejects_adding_an_advisor_to_a_telegram_that_belongs_to_an_admin():
    admin = _admin(telegram_id=TELEGRAM)
    client, session = _client_registro([admin])

    response = _registro(client)

    assert response.status_code == 409
    assert _codigo(response) == "TELEGRAM_ES_ADMIN"
    assert session.added == []


def test_registro_race_on_the_new_partial_unique_index_returns_409_not_500():
    session = FakeAsyncSession(
        execute_queue=[[], []],
        raise_integrity_error=IntegrityError(
            "INSERT usuario", {},
            Exception('duplicate key value violates unique constraint "uq_usuario_telegram_phone_activo"'),
        ),
    )
    override_motored_db(session)

    response = _registro(TestClient(app))

    assert response.status_code == 409
    assert _codigo(response) == "YA_REGISTRADO"
    assert session.rolled_back is True


def test_registro_admin_notification_ids_are_deduplicated_keeping_order():
    filas = [
        _FakeAdminTelegramRow(telegram_id=111, role=MotoredRole.ADMIN, activo=True),
        _FakeAdminTelegramRow(telegram_id=222, role=MotoredRole.ADMIN, activo=True),
        _FakeAdminTelegramRow(telegram_id=111, role=MotoredRole.ADMIN, activo=True),
    ]
    client, _ = _client_registro([], admin_rows=filas)

    response = _registro(client)

    assert response.status_code == 201, response.text
    assert response.json()["admin_telegram_ids"] == [111, 222]


# ---------------------------------------------------------------------------
# POST /admin/vincular keeps refusing a Telegram that already has usuarios
# ---------------------------------------------------------------------------

def test_vincular_still_refuses_a_telegram_that_already_has_advisors():
    ana = _persona("Ana")
    session = _FilteringFakeSession(execute_queue=[[], [ana]])
    override_motored_db(session)

    response = TestClient(app).post(
        f"{BOT_URL}/admin/vincular", json={"codigo": "ABC"}, headers=_headers(TELEGRAM)
    )

    assert response.status_code == 409
    assert _codigo(response) == "TELEGRAM_YA_VINCULADO"
