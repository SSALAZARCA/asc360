"""
Motored aviso de antiguedad: el tick que decide que mandar (con la base y
Telegram reemplazados), el envio por la Bot API de Lore (sin filtrar el
token ni el chat) y el arranque perezoso del loop con su interruptor.
"""
import logging
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.motored.services import avisos_antiguedad as av
from app.motored.services import avisos_telegram as tg
from app.motored.services.trabajos import supervisor_avisos as sv

BOGOTA = timezone(timedelta(hours=-5))
TOKEN = "123456:SECRETO-DE-LORE"


def _venc(vence, tipo="inventario"):
    return av.Vencimiento(
        tipo=tipo, nombre=tipo, fecha_carga=vence - timedelta(days=7),
        fecha_vencimiento=vence, limite_dias=7)


class FakeDb:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@pytest.fixture
def mundo(monkeypatch):
    estado = {"vencs": [_venc(date(2026, 10, 3))], "chats": [111, 222],
              "ganadas": set(), "liberadas": []}

    async def leer(db, hoy):
        return estado["vencs"]

    async def chats(db):
        return estado["chats"]

    async def reservar(db, tipo, umbral, vence, ahora):
        clave = (tipo, umbral, vence)
        if clave in estado["ganadas"]:
            return False
        estado["ganadas"].add(clave)
        return True

    async def liberar(db, tipo, umbral, vence):
        estado["liberadas"].append((tipo, umbral, vence))
        estado["ganadas"].discard((tipo, umbral, vence))

    monkeypatch.setattr(av, "leer_vencimientos", leer)
    monkeypatch.setattr(av, "destinatarios", chats)
    monkeypatch.setattr(av, "reservar", reservar)
    monkeypatch.setattr(av, "liberar", liberar)
    return estado


def _recolector(ok=True):
    enviados = []

    async def enviar(chat, texto):
        enviados.append((chat, texto))
        return ok

    return enviados, enviar


async def test_manda_un_mensaje_a_cada_chat_y_no_repite(mundo):
    enviados, enviar = _recolector()
    ahora = datetime(2026, 10, 2, 16, 30, tzinfo=BOGOTA)

    primero = await av.procesar_avisos(FakeDb(), ahora, enviar)
    segundo = await av.procesar_avisos(FakeDb(), ahora, enviar)

    assert primero == 2 and segundo == 0
    assert [c for c, _ in enviados] == [111, 222]


async def test_no_manda_antes_de_la_hora(mundo):
    enviados, enviar = _recolector()

    n = await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 16, 29, tzinfo=BOGOTA), enviar)

    assert n == 0 and enviados == []


async def test_un_solo_mensaje_agrupa_los_datos_de_la_vispera(mundo):
    mundo["vencs"] = [
        _venc(date(2026, 10, 3), "inventario"),
        _venc(date(2026, 10, 3), "backorder"),
    ]
    mundo["chats"] = [111]
    enviados, enviar = _recolector()

    await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 17, 0, tzinfo=BOGOTA), enviar)

    assert len(enviados) == 1
    assert "inventario" in enviados[0][1] and "backorder" in enviados[0][1]


async def test_si_nadie_recibe_libera_la_reserva_para_reintentar(mundo):
    _, enviar = _recolector(ok=False)
    ahora = datetime(2026, 10, 2, 16, 30, tzinfo=BOGOTA)

    n = await av.procesar_avisos(FakeDb(), ahora, enviar)

    assert n == 0 and len(mundo["liberadas"]) == 1
    assert mundo["ganadas"] == set()


async def test_sin_destinatarios_no_reserva_nada(mundo):
    mundo["chats"] = []
    enviados, enviar = _recolector()

    await av.procesar_avisos(
        FakeDb(), datetime(2026, 10, 2, 16, 30, tzinfo=BOGOTA), enviar)

    assert enviados == [] and mundo["ganadas"] == set()


# --- Envio por la Bot API ----------------------------------------------


def _cliente(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_enviar_llama_sendmessage_con_el_token_de_lore():
    vistos = []

    def handler(request):
        vistos.append(request)
        return httpx.Response(200, json={"ok": True})

    async with _cliente(handler) as cliente:
        ok = await tg.enviar_mensaje(TOKEN, 111, "hola", cliente=cliente)

    assert ok is True
    assert vistos[0].url.path == f"/bot{TOKEN}/sendMessage"
    assert b'"chat_id":111' in vistos[0].content.replace(b" ", b"")


async def test_enviar_no_lanza_ni_filtra_token_o_chat(caplog):
    def handler(request):
        raise httpx.ConnectError("fallo " + str(request.url))

    caplog.set_level(logging.DEBUG)
    async with _cliente(handler) as cliente:
        ok = await tg.enviar_mensaje(
            TOKEN, 1234567890, "hola", cliente=cliente)

    assert ok is False
    log = caplog.text
    assert "ConnectError" in log
    assert TOKEN not in log and "SECRETO" not in log
    assert "1234567890" not in log


async def test_enviar_trata_un_no_2xx_como_fallo():
    def handler(request):
        return httpx.Response(403, json={"ok": False})

    async with _cliente(handler) as cliente:
        ok = await tg.enviar_mensaje(TOKEN, 5, "hola", cliente=cliente)

    assert ok is False


# --- Loop ----------------------------------------------------------------


async def test_ensure_started_respeta_el_interruptor(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_AVISOS_ANTIGUEDAD_ENABLED", False)

    sv.ensure_started()

    assert sv._task is None


async def test_ensure_started_es_idempotente(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_AVISOS_ANTIGUEDAD_ENABLED", True)
    try:
        sv.ensure_started()
        primera = sv._task
        sv.ensure_started()
        assert primera is not None and sv._task is primera
    finally:
        await sv.detener()


async def test_sin_token_no_toca_la_base_y_avisa_una_sola_vez(
        monkeypatch, caplog):
    monkeypatch.setattr(settings, "LORE_BOT_TOKEN", "")
    sv._aviso_sin_token = False
    llamadas = []

    def fabrica():
        llamadas.append(1)
        raise AssertionError("no debe abrir sesion sin token")

    caplog.set_level(logging.INFO)
    await sv.run_tick(session_factory=fabrica)
    await sv.run_tick(session_factory=fabrica)

    assert llamadas == []
    assert caplog.text.count("LORE_BOT_TOKEN") == 1


async def test_un_tick_que_falla_no_mata_el_loop(monkeypatch):
    llamadas = []

    async def tick():
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("boom")

    async def dormir(segundos):
        if len(llamadas) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(sv, "run_tick", tick)
    with pytest.raises(KeyboardInterrupt):
        await sv._run_forever(dormir=dormir)

    assert len(llamadas) == 2
