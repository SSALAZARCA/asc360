"""
Motored aviso de antigüedad, Configuración T3: las horas y los roles
destino salen de las claves `aviso_*` (una lectura por tick); una hora
cambiada dispara a la hora nueva y la reserva única sigue evitando repetidos.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.config import settings
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.usuario import MotoredRole
from app.motored.services import avisos_antiguedad as av
from app.motored.services.trabajos import supervisor_avisos as sv
from tests.motored.conftest import FakeAsyncSession

BOGOTA = timezone(timedelta(hours=-5))
D = date(2026, 10, 1)
AM9 = datetime(2026, 10, 2, 9, tzinfo=BOGOTA)


def _fila(clave, valor):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=D)


def _venc(vence, tipo="inventario"):
    return av.Vencimiento(
        tipo=tipo, nombre=tipo, fecha_carga=vence - timedelta(days=7),
        fecha_vencimiento=vence, limite_dias=7)


class FakeDb:
    async def commit(self):
        pass


class SesionQueFalla(FakeAsyncSession):
    async def execute(self, stmt, params=None):
        raise RuntimeError("db caída")


@pytest.fixture
def mundo(monkeypatch):
    estado = {"vencs": [_venc(date(2026, 10, 3))], "chats": [111],
              "ganadas": set(), "roles": None}

    async def leer(db, hoy):
        return estado["vencs"]

    async def chats(db, roles=None):
        estado["roles"] = roles
        return estado["chats"]

    async def reservar(db, tipo, umbral, vence, ahora):
        clave = (tipo, umbral, vence)
        if clave in estado["ganadas"]:
            return False
        estado["ganadas"].add(clave)
        return True

    monkeypatch.setattr(av, "leer_vencimientos", leer)
    monkeypatch.setattr(av, "destinatarios", chats)
    monkeypatch.setattr(av, "reservar", reservar)
    return estado


def _recolector():
    enviados = []

    async def enviar(chat, texto):
        enviados.append((chat, texto))
        return True

    return enviados, enviar


def _config(vispera="16:30", dia="08:30", roles=("COMPRAS",)):
    return av.ConfigAvisos(
        av.parsear_hora(vispera), av.parsear_hora(dia),
        tuple(MotoredRole(r) for r in roles))


# --- leer_config -----------------------------------------------------------


async def test_without_rows_the_config_is_the_old_constants():
    db = FakeAsyncSession(execute_queue=[[]])

    config = await av.leer_config(db, AM9, {})

    assert config == av.CONFIG_POR_DEFECTO
    assert config.hora_vispera == time(16, 30)
    assert config.hora_dia == time(8, 30)
    assert config.roles == (MotoredRole.COMPRAS,)


async def test_stored_rows_become_the_config():
    db = FakeAsyncSession(execute_queue=[[
        _fila("aviso_hora_vispera", "17:45"),
        _fila("aviso_hora_dia", "07:15"),
        _fila("aviso_roles_destino", ["ADMIN", "COMPRAS"]),
    ]])

    config = await av.leer_config(db, AM9, {})

    assert config.hora_vispera == time(17, 45)
    assert config.hora_dia == time(7, 15)
    assert config.roles == (MotoredRole.ADMIN, MotoredRole.COMPRAS)
    assert len(db.executed_statements) == 1


async def test_a_broken_stored_hour_falls_back_to_its_constant():
    db = FakeAsyncSession(execute_queue=[[
        _fila("aviso_hora_vispera", "25:99"),
        _fila("aviso_hora_dia", "07:15")]])

    config = await av.leer_config(db, AM9, {})

    assert config.hora_vispera == av.HORA_VISPERA
    assert config.hora_dia == time(7, 15)


# --- el tick usa la configuración -----------------------------------------


async def test_a_changed_day_hour_fires_at_the_new_time(mundo):
    mundo["vencs"] = [_venc(date(2026, 10, 2))]
    enviados, enviar = _recolector()
    config = _config(dia="07:00")

    antes = await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 6, 59, tzinfo=BOGOTA), enviar, config)
    a_la_hora = await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 7, 0, tzinfo=BOGOTA), enviar, config)

    assert (antes, a_la_hora) == (0, 1)
    assert "vencen hoy" in enviados[0][1]


async def test_a_changed_eve_hour_fires_at_the_new_time(mundo):
    enviados, enviar = _recolector()
    config = _config(vispera="18:00")

    antes = await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 17, 59, tzinfo=BOGOTA), enviar, config)
    a_la_hora = await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 18, 0, tzinfo=BOGOTA), enviar, config)

    assert (antes, a_la_hora) == (0, 1)
    assert "vencen mañana" in enviados[0][1]


async def test_the_old_hour_no_longer_fires_after_the_change(mundo):
    enviados, enviar = _recolector()

    n = await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 16, 30, tzinfo=BOGOTA), enviar,
        _config(vispera="18:00"))

    assert n == 0 and enviados == []


async def test_an_eve_hour_before_the_day_hour_is_not_skipped(mundo):
    enviados, enviar = _recolector()

    n = await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 7, 10, tzinfo=BOGOTA), enviar,
        _config(vispera="07:00", dia="08:30"))

    assert n == 1


async def test_idempotency_is_unchanged_with_a_custom_config(mundo):
    enviados, enviar = _recolector()
    config = _config(vispera="17:00")
    ahora = datetime(2026, 10, 2, 17, 5, tzinfo=BOGOTA)

    primero = await av.procesar_avisos(FakeDb(), ahora, enviar, config)
    segundo = await av.procesar_avisos(FakeDb(), ahora, enviar, config)

    assert (primero, segundo) == (1, 0)
    assert len(enviados) == 1


async def test_the_configured_roles_choose_the_recipients(mundo):
    _, enviar = _recolector()
    config = _config(roles=("ADMIN", "COMPRAS"))

    await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 17, 0, tzinfo=BOGOTA), enviar, config)

    assert tuple(mundo["roles"]) == (MotoredRole.ADMIN, MotoredRole.COMPRAS)


async def test_without_a_config_the_constants_still_apply(mundo):
    enviados, enviar = _recolector()

    n = await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 16, 30, tzinfo=BOGOTA), enviar)

    assert n == 1
    assert tuple(mundo["roles"]) == av.ROLES_DESTINO


# --- supervisor: una lectura por tick, último valor conocido ---------------


@pytest.fixture
def tick_env(monkeypatch):
    monkeypatch.setattr(settings, "LORE_BOT_TOKEN", "123:token")
    capturado = []

    async def procesar(db, ahora, enviar, config=None):
        capturado.append(config)
        return 0

    monkeypatch.setattr(av, "procesar_avisos", procesar)
    sv._memoria_config.clear()
    yield capturado
    sv._memoria_config.clear()


def _fabrica(*sesiones):
    cola = list(sesiones)

    class Contexto:
        def __init__(self, sesion):
            self.sesion = sesion

        async def __aenter__(self):
            return self.sesion

        async def __aexit__(self, *args):
            return False

    return lambda: Contexto(cola.pop(0))


async def test_each_tick_reads_the_config_once(tick_env):
    db = FakeAsyncSession(execute_queue=[[_fila("aviso_hora_dia", "07:15")]])

    await sv.run_tick(session_factory=_fabrica(db))

    assert len(db.executed_statements) == 1
    assert tick_env[0].hora_dia == time(7, 15)


async def test_a_failed_read_keeps_the_last_known_config(tick_env):
    ok = FakeAsyncSession(execute_queue=[[_fila("aviso_hora_dia", "07:15")]])
    roto = SesionQueFalla()

    await sv.run_tick(session_factory=_fabrica(ok))
    await sv.run_tick(session_factory=_fabrica(roto))

    assert tick_env[1].hora_dia == time(7, 15)


async def test_a_failed_first_read_uses_the_constants(tick_env):
    await sv.run_tick(session_factory=_fabrica(SesionQueFalla()))

    assert tick_env == [av.CONFIG_POR_DEFECTO]
