"""Correccion when several advisors share one Telegram: "¿Quién registra?"
first, then only THAT advisor's registrations, with the choice sent on every
backend call of the conversation."""
from unittest.mock import AsyncMock, MagicMock

import httpx
from telegram.ext import ConversationHandler

from lore.api import BackendClient
from lore.estados import CorreccionEstado
from lore.handlers import correccion

_ANA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_BETO = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_CARGA = "44444444-4444-4444-4444-444444444444"
_LINEA = "55555555-5555-5555-5555-555555555555"


class FakeClient:
    def __init__(self):
        self.yo = AsyncMock()
        self.listar_hoy = AsyncMock(return_value=[])
        self.editar_linea = AsyncMock()
        self.anular_registro = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _asesor(id, nombre, status="approved", activo=True):
    return {
        "id": id, "nombre": nombre, "role": "ASESOR_MOSTRADOR",
        "status": status, "activo": activo, "sucursales": [],
    }


def _preparar(monkeypatch, yo):
    fake = FakeClient()
    fake.yo.return_value = yo
    llamadas = []

    def fabrica(telegram_id, usuario_id=None):
        llamadas.append((telegram_id, usuario_id))
        return fake

    monkeypatch.setattr(correccion, "_cliente", fabrica)
    return fake, llamadas


def _make_update(*, text=None, callback_data=None, user_id=123):
    update = MagicMock()
    update.effective_user.id = user_id
    if callback_data is not None:
        update.callback_query = MagicMock()
        update.callback_query.data = callback_data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = None
    else:
        update.callback_query = None
        update.message = MagicMock()
        update.message.text = text
        update.message.reply_text = AsyncMock()
    return update


def _make_context(*, user_data=None):
    context = MagicMock()
    context.user_data = user_data if user_data is not None else {}
    return context


def _dos():
    return {"asesores": [_asesor(_ANA, "Ana"), _asesor(_BETO, "Beto")]}


def _carga():
    return {
        "carga_id": _CARGA, "creado_en": "2026-09-25T10:00:00",
        "sucursal": {"id": "s1", "nombre": "Bogotá"},
        "lineas": [{"linea_id": _LINEA, "referencia": {"codigo": "ABC"}, "cantidad": 3.0}],
    }


async def test_iniciar_with_two_usable_advisors_asks_who_before_listing(monkeypatch):
    fake, _ = _preparar(monkeypatch, _dos())
    update, context = _make_update(), _make_context()

    result = await correccion.iniciar(update, context)

    assert result == CorreccionEstado.ASESOR
    llamada = update.message.reply_text.call_args
    assert "¿Quién registra?" in llamada.args[0]
    botones = [fila[0] for fila in llamada.kwargs["reply_markup"].inline_keyboard]
    assert [(b.text, b.callback_data) for b in botones[:2]] == [
        ("Ana", f"lore_cor_ase:{_ANA}"), ("Beto", f"lore_cor_ase:{_BETO}"),
    ]
    fake.listar_hoy.assert_not_awaited()


async def test_iniciar_asks_again_even_if_a_previous_conversation_chose(monkeypatch):
    fake, _ = _preparar(monkeypatch, _dos())
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {}, "usuario_id": _ANA}})

    result = await correccion.iniciar(_make_update(), context)

    assert result == CorreccionEstado.ASESOR
    fake.listar_hoy.assert_not_awaited()


async def test_iniciar_single_advisor_lists_directly_without_a_usuario_id(monkeypatch):
    yo = {**_asesor(_ANA, "Ana"), "asesores": [_asesor(_ANA, "Ana")]}
    fake, llamadas = _preparar(monkeypatch, yo)
    fake.listar_hoy.return_value = [_carga()]

    result = await correccion.iniciar(_make_update(), _make_context())

    assert result == CorreccionEstado.LISTA
    assert all(usuario_id is None for _, usuario_id in llamadas)


async def test_iniciar_one_usable_among_several_lists_for_that_advisor(monkeypatch):
    yo = {"asesores": [_asesor("c", "Caro", status="pending"), _asesor(_ANA, "Ana")]}
    fake, llamadas = _preparar(monkeypatch, yo)
    fake.listar_hoy.return_value = [_carga()]
    context = _make_context()

    result = await correccion.iniciar(_make_update(), context)

    assert result == CorreccionEstado.LISTA
    assert llamadas[-1] == (123, _ANA)
    assert context.user_data[correccion._DATA_KEY]["usuario_id"] == _ANA


async def test_iniciar_several_registered_but_none_usable_ends_with_a_message(monkeypatch):
    yo = {"asesores": [_asesor(_ANA, "Ana", status="pending"), _asesor(_BETO, "Beto", activo=False)]}
    _preparar(monkeypatch, yo)
    update = _make_update()

    result = await correccion.iniciar(update, _make_context())

    assert result == ConversationHandler.END
    assert "habilitado" in update.message.reply_text.call_args.args[0]


async def test_recibir_asesor_lists_only_the_chosen_advisors_registrations(monkeypatch):
    fake, llamadas = _preparar(monkeypatch, _dos())
    fake.listar_hoy.return_value = [_carga()]
    context = _make_context()
    await correccion.iniciar(_make_update(), context)

    update = _make_update(callback_data=f"lore_cor_ase:{_BETO}")
    result = await correccion.recibir_asesor(update, context)

    assert result == CorreccionEstado.LISTA
    assert llamadas[-1] == (123, _BETO)
    assert context.user_data[correccion._DATA_KEY]["usuario_id"] == _BETO
    update.callback_query.edit_message_text.assert_awaited()


async def test_recibir_asesor_with_nothing_registered_today_ends(monkeypatch):
    fake, _ = _preparar(monkeypatch, _dos())
    context = _make_context()
    await correccion.iniciar(_make_update(), context)

    update = _make_update(callback_data=f"lore_cor_ase:{_ANA}")
    result = await correccion.recibir_asesor(update, context)

    assert result == ConversationHandler.END
    assert "No tenés registros" in update.callback_query.edit_message_text.call_args.args[0]


async def test_recibir_asesor_rejects_an_advisor_that_was_not_offered(monkeypatch):
    fake, _ = _preparar(monkeypatch, _dos())
    context = _make_context()
    await correccion.iniciar(_make_update(), context)

    update = _make_update(callback_data="lore_cor_ase:ffffffff-ffff-ffff-ffff-ffffffffffff")
    result = await correccion.recibir_asesor(update, context)

    assert result == ConversationHandler.END
    fake.listar_hoy.assert_not_awaited()
    assert correccion._DATA_KEY not in context.user_data


async def test_edit_and_cancel_calls_send_the_chosen_usuario(monkeypatch):
    fake, llamadas = _preparar(monkeypatch, _dos())

    def contexto():  # each success path clears its conversation state
        estado = {"cargas": {}, "usuario_id": _BETO, "linea_id_actual": _LINEA}
        return _make_context(user_data={correccion._DATA_KEY: estado})

    await correccion.recibir_cantidad(_make_update(text="4"), contexto())
    await correccion.resolver_confirmacion_anular(
        _make_update(callback_data=f"lore_cor_anular_confirmar:{_CARGA}"), contexto()
    )

    assert llamadas == [(123, _BETO), (123, _BETO)]


async def test_anular_without_a_conversation_state_does_not_crash(monkeypatch):
    fake, llamadas = _preparar(monkeypatch, _dos())

    await correccion.resolver_confirmacion_anular(
        _make_update(callback_data=f"lore_cor_anular_confirmar:{_CARGA}"), _make_context()
    )

    assert llamadas == [(123, None)]


async def test_out_of_window_edit_ends_with_its_own_message_over_the_real_error_shape(monkeypatch):
    """End to end through the real `BackendClient` and FastAPI's real error
    body: the 409 code is now recognised, so the conversation ends instead
    of offering a pointless retry."""
    def handler(request):
        return httpx.Response(409, json={"detail": {"code": "FUERA_DE_VENTANA"}})

    monkeypatch.setattr(
        correccion, "_cliente",
        lambda telegram_id, usuario_id=None: BackendClient(
            telegram_id, usuario_id=usuario_id, base_url="http://test",
            transport=httpx.MockTransport(handler),
        ),
    )
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {}, "linea_id_actual": _LINEA}})
    update = _make_update(text="4")

    result = await correccion.recibir_cantidad(update, context)

    assert result == ConversationHandler.END
    assert "ya no es de hoy" in update.message.reply_text.call_args.args[0]
    assert correccion._DATA_KEY not in context.user_data
