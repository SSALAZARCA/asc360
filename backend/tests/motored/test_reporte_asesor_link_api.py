"""
reporte_asesor_link over HTTP (odd/motored-reporte-diario-asesor, T3a):

- `GET|POST|DELETE /usuarios/{id}/enlace-informe` (ADMIN only). No
  response, audit row or Telegram failure path ever carries the token or
  the URL; a failed Lore send rolls back so the old link stays as it was.
- Every write path that breaks the link's conditions revokes it: usuario
  deactivated, cédula changed/cleared/rejected, own Telegram unlinked, and
  a Telegram linked through the bot's one-time code.

Same `FakeAsyncSession` queue convention as `test_usuario_cedula.py`; the
leading `[]` is `get_motored_db_or_503`'s connectivity probe.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import Usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

URL = "/api/motored/usuarios"
BOT_URL = "/api/motored/bot"
LORE_SECRET = "enlace-test-lore-secret"
LORE_TOKEN = "123456:lore-token"
PUBLICA = "https://motored.example.co"
NO_ADMIN = ["COMPRAS", "SUCURSAL", "CONSULTA", "GERENCIA"]
ENVIAR = "app.motored.services.avisos_telegram.enviar_mensaje"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "enlace-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "enlace-asc360")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "enlace-sonia")
    monkeypatch.setattr(settings, "LORE_BOT_SECRET", LORE_SECRET)
    monkeypatch.setattr(settings, "LORE_BOT_TOKEN", LORE_TOKEN)
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", PUBLICA)
    yield
    app.dependency_overrides.clear()


def _usuario(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Ana Asesora", email=None,
        hashed_password=None, role="ASESOR_MOSTRADOR", activo=True,
        status="approved", telegram_id=555, phone="3001234567",
        cedula="79845123", cedula_aprobada=True,
    )
    base.update(overrides)
    return Usuario(**base)


def _link(usuario: Usuario, **overrides) -> ReporteAsesorLink:
    base = dict(
        id=uuid.uuid4(), usuario_id=usuario.id, cedula=usuario.cedula,
        token="viejo-" + "x" * 40,
        creado_en=datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc),
        ultimo_acceso_en=datetime(2026, 10, 7, 9, 30, tzinfo=timezone.utc),
        intentos_fallidos=0,
    )
    base.update(overrides)
    return ReporteAsesorLink(**base)


def _cliente(role, cola, user_id=None, **kwargs):
    sesion = FakeAsyncSession(execute_queue=[[]] + list(cola), **kwargs)
    override_motored_user(MotoredUser(
        user_id=str(user_id or uuid.uuid4()), role=role))
    override_motored_db(sesion)
    return TestClient(app), sesion


def _revocaciones(sesion) -> list:
    return [
        str(s.compile(compile_kwargs={"literal_binds": True}))
        for s in sesion.executed_statements
        if str(s).startswith("UPDATE reporte_asesor_link")
    ]


def _nuevo(sesion) -> ReporteAsesorLink:
    return sesion.added_of_type(ReporteAsesorLink)[0]


def _sin_secretos(texto: str, sesion) -> None:
    for link in sesion.added_of_type(ReporteAsesorLink):
        assert link.token not in texto
    assert "/motored/informe/" not in texto


def _auditorias(sesion) -> list:
    return [a for a in sesion.added if isinstance(a, AuditoriaMaestro)]


# --- GET ------------------------------------------------------------------

def test_get_reports_the_active_link_without_the_token():
    usuario = _usuario()
    link = _link(usuario)
    client, _ = _cliente("ADMIN", [[usuario], [link]])

    response = client.get(f"{URL}/{usuario.id}/enlace-informe")

    assert response.status_code == 200
    assert response.json() == {
        "activo": True,
        "creado_en": "2026-10-01T14:00:00+00:00",
        "ultimo_acceso_en": "2026-10-07T09:30:00+00:00",
    }
    assert link.token not in response.text


def test_get_without_a_link_reports_inactive():
    usuario = _usuario()
    client, _ = _cliente("ADMIN", [[usuario], []])

    body = client.get(f"{URL}/{usuario.id}/enlace-informe").json()

    assert body == {"activo": False, "creado_en": None,
                    "ultimo_acceso_en": None}


def test_get_unknown_usuario_returns_404():
    client, _ = _cliente("ADMIN", [[]])

    response = client.get(f"{URL}/{uuid.uuid4()}/enlace-informe")

    assert response.status_code == 404


# --- POST -----------------------------------------------------------------

def test_post_generates_sends_by_lore_and_commits():
    usuario = _usuario()
    viejo = _link(usuario)
    client, sesion = _cliente("ADMIN", [[usuario], [viejo], []])

    with patch(ENVIAR, AsyncMock(return_value=True)) as enviar:
        response = client.post(f"{URL}/{usuario.id}/enlace-informe")

    assert response.status_code == 200, response.text
    nuevo = _nuevo(sesion)
    assert response.json()["activo"] is True
    assert response.json()["ultimo_acceso_en"] is None
    token, chat, texto = enviar.await_args.args
    assert (token, chat) == (LORE_TOKEN, 555)
    assert texto == (
        "Hola Ana Asesora, este es tu enlace personal al informe de ventas "
        "y comisión. Ábrelo y escribe tu cédula para verlo: "
        f"{PUBLICA}/motored/informe/{nuevo.token}\nNo lo compartas.")
    assert "'regenerado'" in _revocaciones(sesion)[0]
    assert sesion.committed and not sesion.rolled_back
    _sin_secretos(response.text, sesion)


def test_post_audits_the_change_without_token_values():
    usuario = _usuario()
    client, sesion = _cliente("ADMIN", [[usuario], [_link(usuario)], []])

    with patch(ENVIAR, AsyncMock(return_value=True)):
        client.post(f"{URL}/{usuario.id}/enlace-informe")

    filas = _auditorias(sesion)
    assert filas, "the regeneration must be audited"
    nuevo = _nuevo(sesion)
    for fila in filas:
        valores = f"{fila.campo} {fila.valor_anterior} {fila.valor_nuevo}"
        assert nuevo.token not in valores
        assert "viejo-" not in valores
        assert "/motored/informe/" not in valores


def test_post_send_failure_rolls_back_and_keeps_the_old_link():
    usuario = _usuario()
    viejo = _link(usuario)
    client, sesion = _cliente("ADMIN", [[usuario], [viejo], []])

    with patch(ENVIAR, AsyncMock(return_value=False)):
        response = client.post(f"{URL}/{usuario.id}/enlace-informe")

    assert response.status_code == 502
    assert "anterior sigue" in response.json()["detail"]
    assert sesion.rolled_back and not sesion.committed
    assert viejo.revocado_en is None
    _sin_secretos(response.text, sesion)


@pytest.mark.parametrize("ajuste, texto", [
    ("LORE_BOT_TOKEN", "LORE_BOT_TOKEN"),
    ("MOTORED_PUBLIC_URL", "Falta configurar MOTORED_PUBLIC_URL"),
])
def test_post_with_an_empty_setting_changes_nothing(
        monkeypatch, ajuste, texto):
    monkeypatch.setattr(settings, ajuste, "")
    usuario = _usuario()
    client, sesion = _cliente("ADMIN", [[usuario]])

    with patch(ENVIAR, AsyncMock(return_value=True)) as enviar:
        response = client.post(f"{URL}/{usuario.id}/enlace-informe")

    assert response.status_code == 409
    assert texto in response.json()["detail"]
    enviar.assert_not_awaited()
    assert not sesion.committed
    assert _revocaciones(sesion) == []


@pytest.mark.parametrize("cambio, texto", [
    ({"cedula_aprobada": False}, "cédula aprobada"),
    ({"telegram_id": None}, "Telegram"),
    ({"activo": False}, "inactivo"),
])
def test_post_for_an_ineligible_usuario_returns_422(cambio, texto):
    usuario = _usuario(**cambio)
    client, sesion = _cliente("ADMIN", [[usuario], []])

    with patch(ENVIAR, AsyncMock(return_value=True)) as enviar:
        response = client.post(f"{URL}/{usuario.id}/enlace-informe")

    assert response.status_code == 422
    assert texto in response.json()["detail"]
    enviar.assert_not_awaited()
    assert not sesion.committed


def test_post_racing_another_admin_returns_409():
    usuario = _usuario()
    choque = IntegrityError(
        "INSERT", {}, Exception("uq_reporte_asesor_link_activo"))
    client, sesion = _cliente(
        "ADMIN", [[usuario], [], []], raise_integrity_error=choque)

    with patch(ENVIAR, AsyncMock(return_value=True)):
        response = client.post(f"{URL}/{usuario.id}/enlace-informe")

    assert response.status_code == 409
    assert sesion.rolled_back
    _sin_secretos(response.text, sesion)


# --- DELETE ---------------------------------------------------------------

def test_delete_revokes_the_link_and_audits_it():
    usuario = _usuario()
    viejo = _link(usuario)
    client, sesion = _cliente("ADMIN", [[usuario], [viejo], []])

    response = client.delete(f"{URL}/{usuario.id}/enlace-informe")

    assert response.status_code == 200
    assert response.json()["activo"] is False
    assert "'anulado por admin'" in _revocaciones(sesion)[0]
    assert sesion.committed
    filas = {a.campo: a for a in _auditorias(sesion)}
    assert filas["enlace_informe"].valor_anterior == "activo"
    assert filas["enlace_informe"].valor_nuevo == "anulado"
    assert viejo.token not in response.text


def test_delete_without_a_link_is_a_no_op():
    usuario = _usuario()
    client, sesion = _cliente("ADMIN", [[usuario], []])

    response = client.delete(f"{URL}/{usuario.id}/enlace-informe")

    assert response.status_code == 200
    assert response.json()["activo"] is False
    assert _revocaciones(sesion) == []
    assert _auditorias(sesion) == []


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize("role", NO_ADMIN)
@pytest.mark.parametrize("metodo", ["GET", "POST", "DELETE"])
def test_non_admin_gets_403(role, metodo):
    client, _ = _cliente(role, [])

    with patch(ENVIAR, AsyncMock(return_value=True)) as enviar:
        response = client.request(
            metodo, f"{URL}/{uuid.uuid4()}/enlace-informe")

    assert response.status_code == 403
    enviar.assert_not_awaited()


# --- auto-revocation: usuarios API ----------------------------------------

def test_deactivating_the_usuario_revokes_its_link():
    usuario = _usuario()
    client, sesion = _cliente("ADMIN", [[usuario], []])

    response = client.delete(f"{URL}/{usuario.id}")

    assert response.status_code == 200
    assert "'usuario desactivado'" in _revocaciones(sesion)[0]
    assert sesion.committed


def test_deactivating_a_usuario_without_a_cedula_runs_no_revocation():
    usuario = _usuario(cedula=None, cedula_aprobada=False)
    client, sesion = _cliente("ADMIN", [[usuario]])

    assert client.delete(f"{URL}/{usuario.id}").status_code == 200
    assert _revocaciones(sesion) == []


def test_changing_the_cedula_revokes_the_link():
    usuario = _usuario()
    # [usuario, vendedor activo, otro aprobado -> none, revoke]
    client, sesion = _cliente(
        "ADMIN", [[usuario], [uuid.uuid4()], [], []])

    response = client.put(
        f"{URL}/{usuario.id}/cedula", json={"cedula": "11223344"})

    assert response.status_code == 200, response.text
    assert "'cédula cambiada'" in _revocaciones(sesion)[0]


def test_saving_the_same_cedula_keeps_the_link():
    usuario = _usuario()
    client, sesion = _cliente("ADMIN", [[usuario], [uuid.uuid4()], []])

    response = client.put(
        f"{URL}/{usuario.id}/cedula", json={"cedula": "79.845.123"})

    assert response.status_code == 200, response.text
    assert _revocaciones(sesion) == []


def test_clearing_an_approved_cedula_revokes_the_link():
    usuario = _usuario()
    client, sesion = _cliente("ADMIN", [[usuario], []])

    response = client.delete(f"{URL}/{usuario.id}/cedula")

    assert response.status_code == 200
    assert "'cédula cambiada'" in _revocaciones(sesion)[0]


def test_rejecting_a_pending_cedula_runs_no_revocation():
    """A pending cédula never had a link (only an approved one can)."""
    usuario = _usuario(cedula_aprobada=False)
    client, sesion = _cliente("ADMIN", [[usuario]])

    response = client.post(f"{URL}/{usuario.id}/cedula/rechazar")

    assert response.status_code == 200
    assert _revocaciones(sesion) == []


def test_approving_a_pending_cedula_runs_no_revocation():
    usuario = _usuario(cedula_aprobada=False)
    client, sesion = _cliente("ADMIN", [[usuario], [uuid.uuid4()], []])

    response = client.post(f"{URL}/{usuario.id}/cedula/aprobar")

    assert response.status_code == 200, response.text
    assert _revocaciones(sesion) == []


def test_unlinking_the_own_telegram_revokes_the_link():
    admin_id = uuid.uuid4()
    propio = _usuario(
        id=admin_id, role="ADMIN", email="a@motored.co",
        hashed_password="hash")
    client, sesion = _cliente("ADMIN", [[propio], []], user_id=admin_id)

    response = client.delete(f"{URL}/me/telegram")

    assert response.status_code == 200
    assert propio.telegram_id is None
    assert "'telegram cambiado'" in _revocaciones(sesion)[0]


# --- auto-revocation: bot one-time code -----------------------------------

def test_linking_a_new_telegram_by_code_revokes_the_link():
    admin = _usuario(
        role="ADMIN", email="a@motored.co", hashed_password="hash",
        telegram_id=None)
    admin.sucursales = []
    codigo = "AB23CD45"
    admin.codigo_vinculacion_hash = hashlib.sha256(
        codigo.encode("utf-8")).hexdigest()
    admin.codigo_vinculacion_expira = (
        datetime.now(timezone.utc) + timedelta(minutes=5))
    sesion = FakeAsyncSession(
        execute_queue=[[], [], [admin.id], [admin], []])
    override_motored_db(sesion)

    response = TestClient(app).post(
        f"{BOT_URL}/admin/vincular", json={"codigo": codigo},
        headers={"X-Lore-Secret": LORE_SECRET,
                 "X-Lore-Telegram-Id": "777"})

    assert response.status_code == 200, response.text
    assert "'telegram cambiado'" in _revocaciones(sesion)[0]
    assert sesion.committed
