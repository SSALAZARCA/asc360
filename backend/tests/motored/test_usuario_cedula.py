"""
usuario.cedula (odd/motored-reporte-diario-asesor, T1): the link Telegram ->
usuario -> cédula. Lore stores a self-entered cédula PENDING; an ADMIN sets
(approved directly), approves, rejects or clears it. Approving requires an
ACTIVE vendedor with that cédula and no other APPROVED usuario holding it;
pending duplicates are allowed so an impostor never blocks the real owner.

Service rules run against `FakeAsyncSession` queues; the HTTP layer uses the
same `_client_as` convention as `test_usuarios_api.py`. The real partial
unique index lives in `pg_real/test_usuario_cedula_pg.py`.
"""
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.usuario import Usuario
from app.motored.services import cedula_usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

URL = "/api/motored/usuarios"
_RAIZ = Path(__file__).resolve().parents[2]
_MIGRACION = (
    _RAIZ / "alembic_motored" / "versions"
    / "c6d2f8a41b97_usuario_cedula.py")
NO_ADMIN = ["COMPRAS", "SUCURSAL", "CONSULTA", "GERENCIA"]


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "cedula-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "cedula-asc360")
    yield
    app.dependency_overrides.clear()


def _usuario(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Juan Asesor", email=None,
        hashed_password=None, role="ASESOR_MOSTRADOR", activo=True,
        status="approved", telegram_id=555, phone="3001234567",
    )
    base.update(overrides)
    return Usuario(**base)


def _cliente(role, cola):
    sesion = FakeAsyncSession(execute_queue=[[]] + list(cola))
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(sesion)
    return TestClient(app), sesion


def _auditorias(sesion):
    return [a for a in sesion.added if isinstance(a, AuditoriaMaestro)]


# --- normalizar_cedula ----------------------------------------------------

@pytest.mark.parametrize("entrada, esperada", [
    ("1.130.123.456", "1130123456"),
    (" 79 845 123 ", "79845123"),
    ("52123456.0", "52123456"),
])
def test_normalizar_cleans_like_the_vendedor_master(entrada, esperada):
    assert cedula_usuario.normalizar_cedula(entrada) == esperada


@pytest.mark.parametrize("entrada", ["", "  ", "12A45", "10-20", None])
def test_normalizar_rejects_empty_or_non_digits(entrada):
    with pytest.raises(cedula_usuario.CedulaInvalida):
        cedula_usuario.normalizar_cedula(entrada)


def test_normalizar_rejects_more_than_twenty_digits():
    with pytest.raises(cedula_usuario.CedulaInvalida, match="20"):
        cedula_usuario.normalizar_cedula("1" * 21)


@pytest.mark.parametrize("corta", ["123", "1234"])
def test_enmascarar_hides_a_short_cedula_completely(corta):
    assert cedula_usuario.enmascarar(corta) == "*" * len(corta)


def test_enmascarar_keeps_only_the_last_four_digits():
    assert cedula_usuario.enmascarar("1045747194") == "******7194"


# --- validar_cedula -------------------------------------------------------

async def test_validar_for_approval_returns_the_clean_value():
    sesion = FakeAsyncSession(execute_queue=[[uuid.uuid4()], []])

    validada = await cedula_usuario.validar_cedula(
        sesion, "1.130.123.456", uuid.uuid4(), para_aprobar=True)

    assert validada.cedula == "1130123456"
    assert validada.en_maestro is True


async def test_validar_for_approval_requires_an_active_vendedor():
    sesion = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(cedula_usuario.CedulaInvalida, match="activo"):
        await cedula_usuario.validar_cedula(
            sesion, "123456", uuid.uuid4(), para_aprobar=True)


async def test_validar_only_counts_active_vendedores():
    sesion = FakeAsyncSession(execute_queue=[[uuid.uuid4()], []])

    await cedula_usuario.validar_cedula(
        sesion, "123456", uuid.uuid4(), para_aprobar=True)

    sql = str(sesion.executed_statements[0])
    assert "vendedor.activo" in sql
    assert "vendedor.cedula" in sql


async def test_validar_for_approval_names_the_other_approved_holder():
    sesion = FakeAsyncSession(
        execute_queue=[[uuid.uuid4()], ["Pedro Pérez"]])

    with pytest.raises(cedula_usuario.CedulaDuplicada, match="Pedro Pérez"):
        await cedula_usuario.validar_cedula(
            sesion, "123456", uuid.uuid4(), para_aprobar=True)


async def test_duplicate_check_counts_only_other_approved_usuarios():
    sesion = FakeAsyncSession(execute_queue=[[uuid.uuid4()], []])

    await cedula_usuario.validar_cedula(
        sesion, "123456", uuid.uuid4(), para_aprobar=True)

    sql = str(sesion.executed_statements[1])
    assert "usuario.id !=" in sql
    assert "usuario.cedula_aprobada IS true" in sql


async def test_validar_pending_accepts_a_cedula_outside_the_master():
    sesion = FakeAsyncSession(execute_queue=[[]])

    validada = await cedula_usuario.validar_cedula(
        sesion, "123456", uuid.uuid4(), para_aprobar=False)

    assert validada == cedula_usuario.CedulaValidada("123456", False)
    assert len(sesion.executed_statements) == 1


async def test_validar_pending_still_rejects_a_bad_format():
    sesion = FakeAsyncSession(execute_queue=[])

    with pytest.raises(cedula_usuario.CedulaInvalida):
        await cedula_usuario.validar_cedula(
            sesion, "12-AB", uuid.uuid4(), para_aprobar=False)


# --- PUT /usuarios/{id}/cedula (ADMIN set = approved) --------------------

def test_admin_set_stores_it_clean_approved_and_audited():
    usuario = _usuario()
    client, sesion = _cliente("ADMIN", [[usuario], [uuid.uuid4()], []])

    response = client.put(
        f"{URL}/{usuario.id}/cedula", json={"cedula": "1.130.123.456"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cedula"] == "1130123456"
    assert body["cedula_aprobada"] is True
    assert body["cedula_en_maestro"] is True
    assert (usuario.cedula, usuario.cedula_aprobada) == ("1130123456", True)
    assert sesion.committed
    auditoria = {a.campo: a for a in _auditorias(sesion)}
    assert auditoria["cedula"].valor_nuevo == "******3456"
    assert auditoria["cedula_aprobada"].valor_nuevo == "True"


def test_admin_edit_replaces_a_pending_cedula_and_approves_it():
    usuario = _usuario(cedula="111222", cedula_aprobada=False)
    client, sesion = _cliente("ADMIN", [[usuario], [uuid.uuid4()], []])

    response = client.put(
        f"{URL}/{usuario.id}/cedula", json={"cedula": "333444"})

    assert response.status_code == 200
    assert (usuario.cedula, usuario.cedula_aprobada) == ("333444", True)
    auditoria = {a.campo: a for a in _auditorias(sesion)}
    assert auditoria["cedula"].valor_anterior == "**1222"


def test_set_cedula_not_in_master_returns_422_in_spanish():
    usuario = _usuario()
    client, sesion = _cliente("ADMIN", [[usuario], []])

    response = client.put(
        f"{URL}/{usuario.id}/cedula", json={"cedula": "123456"})

    assert response.status_code == 422
    assert "maestro de Vendedores" in response.json()["detail"]
    assert usuario.cedula is None
    assert not sesion.committed


def test_set_invalid_format_returns_422():
    usuario = _usuario()
    client, _ = _cliente("ADMIN", [[usuario]])

    response = client.put(
        f"{URL}/{usuario.id}/cedula", json={"cedula": "12AB"})

    assert response.status_code == 422
    assert "números" in response.json()["detail"]


def test_set_cedula_approved_for_another_usuario_returns_409_naming_it():
    usuario = _usuario()
    client, sesion = _cliente(
        "ADMIN", [[usuario], [uuid.uuid4()], ["Pedro Pérez"]])

    response = client.put(
        f"{URL}/{usuario.id}/cedula", json={"cedula": "123456"})

    assert response.status_code == 409
    assert "Pedro Pérez" in response.json()["detail"]
    assert not sesion.committed


def test_set_cedula_unique_race_at_commit_returns_409_not_500():
    usuario = _usuario()
    error = IntegrityError(
        "UPDATE", {}, Exception('violates "uq_usuario_cedula_aprobada"'))
    sesion = FakeAsyncSession(
        execute_queue=[[], [usuario], [uuid.uuid4()], []],
        raise_integrity_error=error)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    override_motored_db(sesion)

    response = TestClient(app).put(
        f"{URL}/{usuario.id}/cedula", json={"cedula": "123456"})

    assert response.status_code == 409
    assert "otro usuario" in response.json()["detail"]
    assert sesion.rolled_back


def test_set_cedula_unknown_usuario_returns_404():
    client, _ = _cliente("ADMIN", [[]])

    response = client.put(
        f"{URL}/{uuid.uuid4()}/cedula", json={"cedula": "123456"})

    assert response.status_code == 404


# --- POST /usuarios/{id}/cedula/aprobar ----------------------------------

def test_admin_approves_a_pending_cedula():
    usuario = _usuario(cedula="79845123", cedula_aprobada=False)
    client, sesion = _cliente("ADMIN", [[usuario], [uuid.uuid4()], []])

    response = client.post(f"{URL}/{usuario.id}/cedula/aprobar")

    assert response.status_code == 200, response.text
    assert response.json()["cedula_aprobada"] is True
    assert usuario.cedula_aprobada is True
    assert sesion.committed
    assert [a.campo for a in _auditorias(sesion)] == ["cedula_aprobada"]


def test_approve_fails_when_no_active_vendedor_has_it():
    usuario = _usuario(cedula="79845123", cedula_aprobada=False)
    client, sesion = _cliente("ADMIN", [[usuario], []])

    response = client.post(f"{URL}/{usuario.id}/cedula/aprobar")

    assert response.status_code == 422
    assert usuario.cedula_aprobada is False
    assert not sesion.committed


def test_approve_fails_when_another_usuario_already_holds_it_approved():
    usuario = _usuario(cedula="79845123", cedula_aprobada=False)
    client, _ = _cliente(
        "ADMIN", [[usuario], [uuid.uuid4()], ["Pedro Pérez"]])

    response = client.post(f"{URL}/{usuario.id}/cedula/aprobar")

    assert response.status_code == 409
    assert "Pedro Pérez" in response.json()["detail"]


def test_approve_without_a_cedula_returns_409():
    usuario = _usuario()
    client, _ = _cliente("ADMIN", [[usuario]])

    response = client.post(f"{URL}/{usuario.id}/cedula/aprobar")

    assert response.status_code == 409
    assert "pendiente" in response.json()["detail"]


# --- POST /cedula/rechazar and DELETE /cedula (both clear it) ------------

def test_admin_rejects_a_pending_cedula_which_clears_it():
    usuario = _usuario(cedula="79845123", cedula_aprobada=False)
    client, sesion = _cliente("ADMIN", [[usuario]])

    response = client.post(f"{URL}/{usuario.id}/cedula/rechazar")

    assert response.status_code == 200
    assert response.json()["cedula"] is None
    assert usuario.cedula is None
    assert sesion.committed


def test_reject_an_approved_cedula_returns_409():
    usuario = _usuario(cedula="79845123", cedula_aprobada=True)
    client, sesion = _cliente("ADMIN", [[usuario]])

    response = client.post(f"{URL}/{usuario.id}/cedula/rechazar")

    assert response.status_code == 409
    assert usuario.cedula == "79845123"
    assert not sesion.committed


def test_admin_clears_an_approved_cedula_and_audits_it():
    usuario = _usuario(cedula="79845123", cedula_aprobada=True)
    client, sesion = _cliente("ADMIN", [[usuario]])

    response = client.delete(f"{URL}/{usuario.id}/cedula")

    assert response.status_code == 200
    body = response.json()
    assert (body["cedula"], body["cedula_aprobada"]) == (None, False)
    assert sesion.committed
    auditoria = {a.campo: a for a in _auditorias(sesion)}
    assert auditoria["cedula"].valor_anterior == "****5123"
    assert auditoria["cedula"].valor_nuevo is None


# --- POST /usuarios with an optional cédula ------------------------------

def _crear(cola, **extra):
    payload = {
        "nombre": "Nuevo Usuario", "email": "nuevo@test.co",
        "password": "clave-segura-123", "role": "COMPRAS",
    }
    payload.update(extra)
    client, sesion = _cliente("ADMIN", cola)
    return client.post(URL, json=payload), sesion


def test_create_with_a_cedula_stores_it_approved():
    response, sesion = _crear([[uuid.uuid4()], []], cedula="79.845.123")

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["cedula"], body["cedula_aprobada"]) == ("79845123", True)
    creado = sesion.added_of_type(Usuario)[0]
    assert (creado.cedula, creado.cedula_aprobada) == ("79845123", True)


def test_create_with_a_cedula_outside_the_master_returns_422():
    response, sesion = _crear([[]], cedula="79845123")

    assert response.status_code == 422
    assert "maestro de Vendedores" in response.json()["detail"]
    assert not sesion.committed


def test_create_with_an_approved_duplicate_returns_409():
    response, _ = _crear([[uuid.uuid4()], ["Pedro Pérez"]], cedula="123456")

    assert response.status_code == 409
    assert "Pedro Pérez" in response.json()["detail"]


@pytest.mark.parametrize("vacia", [None, "", "   "])
def test_create_without_a_cedula_runs_no_cedula_query(vacia):
    response, sesion = _crear([], cedula=vacia)

    assert response.status_code == 201, response.text
    assert response.json()["cedula"] is None
    assert sesion.added_of_type(Usuario)[0].cedula_aprobada is False


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize("role", NO_ADMIN)
@pytest.mark.parametrize("metodo, ruta", [
    ("put", "cedula"), ("delete", "cedula"),
    ("post", "cedula/aprobar"), ("post", "cedula/rechazar"),
])
def test_non_admin_gets_403_on_every_cedula_action(role, metodo, ruta):
    client, _ = _cliente(role, [])
    kwargs = {"json": {"cedula": "123456"}} if metodo == "put" else {}

    response = client.request(
        metodo.upper(), f"{URL}/{uuid.uuid4()}/{ruta}", **kwargs)

    assert response.status_code == 403


# --- list -----------------------------------------------------------------

def test_list_exposes_cedula_state_and_master_flag():
    aprobada = _usuario(cedula="79845123", cedula_aprobada=True)
    pendiente = _usuario(cedula="555666", cedula_aprobada=False)
    sin = _usuario(nombre="Sin Cédula")
    client, _ = _cliente("ADMIN", [[aprobada, pendiente, sin], ["79845123"]])

    body = client.get(URL).json()

    resumen = [
        (u["cedula"], u["cedula_aprobada"], u["cedula_en_maestro"])
        for u in body
    ]
    assert resumen == [
        ("79845123", True, True),
        ("555666", False, False),
        (None, False, None),
    ]


def test_list_without_cedulas_skips_the_master_query():
    client, _ = _cliente("ADMIN", [[_usuario()]])

    assert client.get(URL).status_code == 200


# --- migration (static) ---------------------------------------------------

def _migracion():
    spec = importlib.util.spec_from_file_location("usuario_cedula", _MIGRACION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_migration_chains_onto_the_kpi_head():
    modulo = _migracion()

    assert modulo.revision == "c6d2f8a41b97"
    assert modulo.down_revision == "e5c9b3d8f024"


def test_migration_adds_columns_and_a_partial_unique_index():
    modulo = _migracion()
    with patch.object(modulo, "op") as op_mock:
        modulo.upgrade()

    columnas = {
        c.args[1].name: c.args[1] for c in op_mock.add_column.call_args_list
    }
    assert columnas["cedula"].nullable
    assert not columnas["cedula_aprobada"].nullable
    assert "false" in str(columnas["cedula_aprobada"].server_default.arg)
    indice = op_mock.create_index.call_args
    assert indice.args[0] == "uq_usuario_cedula_aprobada"
    assert indice.kwargs["unique"] is True
    assert str(indice.kwargs["postgresql_where"]) == "cedula_aprobada"


def test_migration_downgrade_drops_index_then_columns():
    modulo = _migracion()
    with patch.object(modulo, "op") as op_mock:
        modulo.downgrade()

    nombres = [c[0] for c in op_mock.method_calls]
    assert nombres == ["drop_index", "drop_column", "drop_column"]
