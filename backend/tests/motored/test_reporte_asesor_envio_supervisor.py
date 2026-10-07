"""
The daily loop of the asesor report send and the resend runner
(odd/motored-reporte-diario-asesor, T3b). A tick does nothing without
`LORE_BOT_TOKEN` or `MOTORED_PUBLIC_URL` (no DB at all), with the switch
off, before the minimum hour or when another worker holds the lock. The
resend runs even with the switch off, records `reenvio`, and only one runs
at a time in a process.
"""
import datetime
import uuid
from datetime import date, time, timezone

import pytest

from app.config import settings
from app.motored.models.reporte_asesor_envio import ReporteAsesorEnvio
from app.motored.services import reporte_asesor_envio as envio
from app.motored.services.trabajos import supervisor_reporte_asesor as sup
from tests.motored.conftest import FakeAsyncSession

AYER = date(2026, 10, 6)
SIETE_AM = datetime.datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
async def _limpio(monkeypatch):
    monkeypatch.setattr(settings, "LORE_BOT_TOKEN", "1:tok")
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", "https://m.co")
    yield
    await sup.detener()


class Fabrica:
    """A session factory that counts the sessions it opened."""

    def __init__(self):
        self.sesiones = []

    def __call__(self):
        fabrica = self

        class _Contexto:
            async def __aenter__(self):
                sesion = FakeAsyncSession()
                fabrica.sesiones.append(sesion)
                return sesion

            async def __aexit__(self, *exc):
                return False

        return _Contexto()


def _config(monkeypatch, activo=True, minima=time(6)):
    async def leer(db, ahora, memoria):
        return envio.ConfigEnvio(activo, time(10), minima)
    monkeypatch.setattr(envio, "leer_config", leer)


def _candado(monkeypatch, obtenido=True):
    tomados = []

    async def tomar(db, clave):
        tomados.append(clave)
        return obtenido
    monkeypatch.setattr(envio, "tomar_candado", tomar)
    return tomados


def _diario(monkeypatch):
    llamadas = []

    async def diario(db, ahora, config, enviar, dormir, sin_reporte):
        llamadas.append((ahora, config))
        return envio.Conteo(enviados=1)
    monkeypatch.setattr(envio, "envio_diario", diario)
    return llamadas


@pytest.mark.parametrize("variable", ["LORE_BOT_TOKEN", "MOTORED_PUBLIC_URL"])
async def test_a_missing_setting_skips_the_tick_without_the_db(
        monkeypatch, variable):
    monkeypatch.setattr(settings, variable, "")
    fabrica = Fabrica()

    assert await sup.run_tick(session_factory=fabrica, ahora=SIETE_AM) is None
    assert fabrica.sesiones == []


async def test_the_switch_off_sends_nothing(monkeypatch):
    _config(monkeypatch, activo=False)
    tomados = _candado(monkeypatch)
    llamadas = _diario(monkeypatch)

    resultado = await sup.run_tick(
        session_factory=Fabrica(), ahora=SIETE_AM)

    assert resultado is None
    assert tomados == [] and llamadas == []


async def test_nothing_before_the_minimum_hour(monkeypatch):
    _config(monkeypatch, minima=time(8))
    tomados = _candado(monkeypatch)
    llamadas = _diario(monkeypatch)

    assert await sup.run_tick(
        session_factory=Fabrica(), ahora=SIETE_AM) is None
    assert tomados == [] and llamadas == []


async def test_another_worker_holding_the_lock_skips_the_tick(monkeypatch):
    _config(monkeypatch)
    tomados = _candado(monkeypatch, obtenido=False)
    llamadas = _diario(monkeypatch)

    assert await sup.run_tick(
        session_factory=Fabrica(), ahora=SIETE_AM) is None
    assert tomados == [envio.LOCK_ENVIO]
    assert llamadas == []


async def test_a_tick_with_the_lock_runs_the_daily_send(monkeypatch):
    _config(monkeypatch)
    _candado(monkeypatch)
    llamadas = _diario(monkeypatch)
    fabrica = Fabrica()

    conteo = await sup.run_tick(session_factory=fabrica, ahora=SIETE_AM)

    assert conteo == envio.Conteo(enviados=1)
    assert len(llamadas) == 1
    assert len(fabrica.sesiones) == 3  # config, lock, work


def test_falta_configuracion_names_the_missing_setting(monkeypatch):
    assert sup.falta_configuracion() is None
    monkeypatch.setattr(settings, "LORE_BOT_TOKEN", "")
    assert "LORE_BOT_TOKEN" in sup.falta_configuracion()
    monkeypatch.setattr(settings, "LORE_BOT_TOKEN", "1:tok")
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", "  ")
    assert "MOTORED_PUBLIC_URL" in sup.falta_configuracion()


def test_only_one_resend_at_a_time():
    assert sup.reservar_reenvio() is True
    assert sup.reservar_reenvio() is False
    sup.liberar_reenvio()
    assert sup.reservar_reenvio() is True
    sup.liberar_reenvio()


def _asesor():
    return envio.Asesor(uuid.uuid4(), "Ana", "1", True, 555, "t" * 40)


async def test_the_resend_records_reenvio_and_who_asked(monkeypatch):
    tomados = _candado(monkeypatch)

    async def esperar(db, clave, segundos):
        tomados.append(clave)
        return True
    monkeypatch.setattr(envio, "esperar_candado", esperar)
    admin = uuid.uuid4()
    fabrica = Fabrica()
    enviados = []

    async def enviar(chat_id, texto):
        enviados.append(chat_id)
        return envio.Respuesta(envio.RES_OK)

    async def dormir(_):
        return None

    conteo = await sup.ejecutar_reenvio(
        [envio.Destino(_asesor(), "hola")], AYER, admin,
        session_factory=fabrica, enviar=enviar, dormir=dormir)

    assert conteo == envio.Conteo(enviados=1)
    assert enviados == [555]
    assert tomados == [envio.LOCK_REENVIO, envio.LOCK_ENVIO]
    fila = fabrica.sesiones[-1].added_of_type(ReporteAsesorEnvio)[0]
    assert fila.reenvio is True and fila.solicitado_por == admin


async def test_a_resend_running_in_another_worker_is_skipped(monkeypatch):
    _candado(monkeypatch, obtenido=False)
    enviados = []

    async def enviar(chat_id, texto):
        enviados.append(chat_id)
        return envio.Respuesta(envio.RES_OK)

    conteo = await sup.ejecutar_reenvio(
        [envio.Destino(_asesor(), "hola")], AYER, uuid.uuid4(),
        session_factory=Fabrica(), enviar=enviar)

    assert conteo is None and enviados == []


async def test_the_background_resend_always_releases_the_guard(
        monkeypatch):
    async def falla(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(sup, "ejecutar_reenvio", falla)
    assert sup.reservar_reenvio()

    await sup.reenviar_en_segundo_plano([], AYER, uuid.uuid4())

    assert sup.reservar_reenvio() is True
    sup.liberar_reenvio()


async def test_ensure_started_needs_motored_enabled(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", False)

    sup.ensure_started()

    assert sup._task is None


async def test_ensure_started_is_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)

    sup.ensure_started()
    primera = sup._task
    sup.ensure_started()

    assert primera is not None and sup._task is primera
