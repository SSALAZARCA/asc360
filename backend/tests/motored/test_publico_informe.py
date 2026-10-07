"""
Public asesor report (odd/motored-reporte-diario-asesor, T3b):
`POST /api/motored/publico/informe/{token}` with `{"cedula"}`, no user auth.

Same `FakeAsyncSession` queue convention as `test_reporte_asesor_link_api.py`;
the leading `[]` is `get_motored_db_or_503`'s connectivity probe and the
next item is the locked `(link, usuario)` lookup. The detail calculation is
stubbed here (the pg_real file proves it against real data).
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import Usuario
from app.motored.services import informe_publico as servicio
from tests.motored.conftest import FakeAsyncSession, override_motored_db

CEDULA = "79845123"
TOKEN = "t" * 64
GENERICO = {"detail": "Enlace o cédula no válidos."}
DETALLE = {"asesor": {"nombre": "Ana"}, "tiles": []}


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "informe-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "informe-asc360")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "informe-sonia")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def detalle(monkeypatch):
    mock = AsyncMock(return_value=DETALLE)
    monkeypatch.setattr(servicio, "detalle_del_anio", mock)
    return mock


def _usuario(**extra):
    base = dict(
        id=uuid.uuid4(), nombre="Ana", role="ASESOR_MOSTRADOR", activo=True,
        status="approved", cedula=CEDULA, cedula_aprobada=True)
    base.update(extra)
    return Usuario(**base)


def _link(usuario, **extra):
    base = dict(
        id=uuid.uuid4(), usuario_id=usuario.id, cedula=usuario.cedula,
        token=TOKEN, intentos_fallidos=0)
    base.update(extra)
    return ReporteAsesorLink(**base)


def _post(filas, cedula=CEDULA, cuerpo=None):
    sesion = FakeAsyncSession(execute_queue=[[]] + list(filas))
    override_motored_db(sesion)
    json = {"cedula": cedula} if cuerpo is None else cuerpo
    respuesta = TestClient(app).post(
        f"/api/motored/publico/informe/{TOKEN}", json=json)
    return respuesta, sesion


def _fila(usuario=None, **link_extra):
    usuario = usuario or _usuario()
    return [(_link(usuario, **link_extra), usuario)]


def _cabeceras(r):
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-robots-tag"] == "noindex, nofollow"


def test_the_right_cedula_returns_the_detail_and_resets_the_counters(detalle):
    fila = _fila(intentos_fallidos=3, bloqueado_hasta=datetime(
        2020, 1, 1, tzinfo=timezone.utc))
    link = fila[0][0]

    r, sesion = _post([fila], cedula="79.845.123")

    assert r.status_code == 200
    assert r.json() == DETALLE
    assert (link.intentos_fallidos, link.bloqueado_hasta) == (0, None)
    assert link.ultimo_acceso_en is not None
    assert sesion.committed
    detalle.assert_awaited_once()
    assert detalle.await_args.args[1] == CEDULA
    _cabeceras(r)
    assert CEDULA not in r.text.replace(DETALLE["asesor"]["nombre"], "")


def test_no_data_is_a_404_but_still_counts_as_a_successful_login(monkeypatch):
    monkeypatch.setattr(
        servicio, "detalle_del_anio", AsyncMock(return_value=None))
    fila = _fila(intentos_fallidos=2)

    r, sesion = _post([fila])

    assert r.status_code == 404
    assert r.json() == {"detail": "Aún no hay información para mostrar."}
    assert fila[0][0].intentos_fallidos == 0
    assert sesion.committed
    _cabeceras(r)


def test_an_unknown_or_revoked_token_gets_the_generic_401(detalle):
    r, sesion = _post([[]])

    assert (r.status_code, r.json()) == (401, GENERICO)
    assert not sesion.committed
    _cabeceras(r)
    detalle.assert_not_awaited()


@pytest.mark.parametrize("cambio", [
    {"activo": False}, {"status": "pending"}, {"status": "rejected"},
    {"cedula_aprobada": False}, {"cedula": "11111111"},
])
def test_a_usuario_that_no_longer_qualifies_gets_the_same_401(detalle, cambio):
    fila = _fila(_usuario(**cambio))
    # The link keeps the original cédula; only the usuario changed.
    fila[0][0].cedula = CEDULA

    r, sesion = _post([fila])

    assert (r.status_code, r.json()) == (401, GENERICO)
    assert fila[0][0].intentos_fallidos == 0  # no counter change
    assert not sesion.committed
    _cabeceras(r)
    detalle.assert_not_awaited()


@pytest.mark.parametrize("cedula", ["99999999", "abc", "", "79-845-124"])
def test_a_wrong_cedula_counts_the_attempt_and_commits_before_the_401(
        detalle, cedula):
    fila = _fila()

    r, sesion = _post([fila], cedula=cedula)

    assert (r.status_code, r.json()) == (401, GENERICO)
    assert fila[0][0].intentos_fallidos == 1
    assert sesion.committed
    _cabeceras(r)
    detalle.assert_not_awaited()


def test_a_body_that_is_not_an_object_is_just_a_wrong_cedula(detalle):
    fila = _fila()

    r, sesion = _post([fila], cuerpo=["x"])

    assert (r.status_code, r.json()) == (401, GENERICO)
    assert fila[0][0].intentos_fallidos == 1
    _cabeceras(r)


def test_the_fifth_failure_locks_for_15_minutes_and_resets_the_counter(
        detalle):
    fila = _fila(intentos_fallidos=4)
    antes = datetime.now(timezone.utc)

    r, sesion = _post([fila], cedula="1")

    link = fila[0][0]
    assert (r.status_code, r.json()) == (401, GENERICO)
    assert link.intentos_fallidos == 0
    assert (antes + timedelta(minutes=14) < link.bloqueado_hasta
            < antes + timedelta(minutes=16))
    assert sesion.committed


def test_a_locked_link_answers_429_even_with_the_right_cedula(detalle):
    futuro = datetime.now(timezone.utc) + timedelta(minutes=5)
    fila = _fila(intentos_fallidos=0, bloqueado_hasta=futuro)

    r, sesion = _post([fila])

    assert r.status_code == 429
    assert r.json() == {
        "detail": "Demasiados intentos. Intenta de nuevo en unos minutos."}
    assert (fila[0][0].intentos_fallidos, fila[0][0].bloqueado_hasta) == (
        0, futuro)
    assert not sesion.committed
    _cabeceras(r)
    detalle.assert_not_awaited()


def test_an_expired_lock_lets_the_right_cedula_in(detalle):
    pasado = datetime.now(timezone.utc) - timedelta(minutes=1)
    fila = _fila(bloqueado_hasta=pasado)

    r, _ = _post([fila])

    assert r.status_code == 200
    assert fila[0][0].bloqueado_hasta is None


def test_the_lookup_locks_the_row_and_only_takes_active_links(detalle):
    _, sesion = _post([[]])

    consulta = str(sesion.executed_statements[1].compile(
        compile_kwargs={"literal_binds": False}))
    assert "FOR UPDATE" in consulta
    assert "revocado_en IS NULL" in consulta


def test_an_unavailable_module_still_carries_the_headers(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", False)

    r, _ = _post([[]])

    assert r.status_code == 503
    _cabeceras(r)
