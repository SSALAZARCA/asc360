"""Unit tests for `lore.handlers.registro` — the self-registration
conversation. `BackendClient` is never hit over HTTP here (that transport
contract is `test_api.py`'s job); instead `_cliente` is monkeypatched to a
`FakeClient` test double, per this project's established pattern for
testing `python-telegram-bot` handlers by calling them directly with a
mocked `Update`/`Context`.
"""
import logging
from unittest.mock import AsyncMock, MagicMock

from telegram.ext import ConversationHandler

from lore.api import BackendCaido, LoreApiError, NoRegistrado, SucursalNoEncontrada, YaRegistrado
from lore.estados import RegistroEstado
from lore.handlers import registro
from lore.handlers._common import _MSG_SESION_EXPIRADA, _escapar_markdown


class FakeClient:
    def __init__(self):
        self.yo = AsyncMock()
        self.sucursales = AsyncMock()
        self.registro = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _fake_cliente(fake_client):
    return lambda telegram_id: fake_client


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
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


# --- /start -------------------------------------------------------------


async def test_start_no_registrado_starts_registration_flow(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.side_effect = NoRegistrado("nope")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context()

    result = await registro.start(update, context)

    assert result == RegistroEstado.NOMBRE
    assert registro._DRAFT_KEY in context.user_data
    update.message.reply_text.assert_awaited_once()


async def test_start_pending_status_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"status": "pending", "nombre": "Ana"}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context()

    result = await registro.start(update, context)

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "pendiente" in text.lower()


async def test_start_rejected_status_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"status": "rejected", "nombre": "Ana"}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await registro.start(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "rechazada" in text.lower()


async def test_start_approved_asesor_greets_by_name_and_role(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {
        "status": "approved", "nombre": "Ana", "role": "ASESOR_MOSTRADOR",
    }
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await registro.start(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "Ana" in text
    assert "asesor de mostrador" in text
    assert "administrador" not in text


async def test_start_approved_admin_greets_by_name_and_role(monkeypatch):
    # Found via live testing right after Phase 9's first production deploy:
    # this branch used to hardcode "asesor de mostrador" for EVERY approved
    # role -- an ADMIN who just linked their Telegram via /vincular got told
    # they were an asesor. Regression test for that exact scenario.
    fake_client = FakeClient()
    fake_client.yo.return_value = {
        "status": "approved", "nombre": "asalazar", "role": "ADMIN",
    }
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await registro.start(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "asalazar" in text
    assert "administrador" in text
    assert "asesor de mostrador" not in text


async def test_start_backend_caido_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.side_effect = BackendCaido("boom")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await registro.start(update, _make_context())

    assert result == ConversationHandler.END
    update.message.reply_text.assert_awaited_once()


async def test_start_unmapped_lore_api_error_ends_conversation(monkeypatch):
    # gga finding (post-4-lens-review): `/yo` shares ONE global error-code
    # map with every other endpoint -- a LoreApiError subclass this handler
    # doesn't explicitly branch on must still reply, not silently reach
    # only the global logger (main.py::_manejar_error).
    fake_client = FakeClient()
    fake_client.yo.side_effect = LoreApiError("unmapped")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await registro.start(update, _make_context())

    assert result == ConversationHandler.END
    update.message.reply_text.assert_awaited_once()


# --- recibir_nombre / recibir_celular ------------------------------------


async def test_recibir_nombre_valid_moves_to_celular():
    update = _make_update(text="Ana Torres")
    context = _make_context(user_data={registro._DRAFT_KEY: {}})

    result = await registro.recibir_nombre(update, context)

    assert result == RegistroEstado.CELULAR
    assert context.user_data[registro._DRAFT_KEY]["nombre"] == "Ana Torres"


async def test_recibir_nombre_exactly_two_chars_reprompts():
    """Boundary: the name-length check uses `<`, so exactly 2 chars (one
    under the 3-char minimum) must still reprompt."""
    update = _make_update(text="Al")
    context = _make_context(user_data={registro._DRAFT_KEY: {}})

    result = await registro.recibir_nombre(update, context)

    assert result == RegistroEstado.NOMBRE
    assert "nombre" not in context.user_data[registro._DRAFT_KEY]


async def test_recibir_nombre_exactly_three_chars_accepted():
    update = _make_update(text="Ana")
    context = _make_context(user_data={registro._DRAFT_KEY: {}})

    result = await registro.recibir_nombre(update, context)

    assert result == RegistroEstado.CELULAR
    assert context.user_data[registro._DRAFT_KEY]["nombre"] == "Ana"


async def test_recibir_celular_invalid_reprompts():
    update = _make_update(text="abc")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.recibir_celular(update, context)

    assert result == RegistroEstado.CELULAR


# --- boundary tests for _PHONE_MIN_DIGITS/_PHONE_MAX_DIGITS ---------------


async def test_recibir_celular_six_digits_rejected():
    """Boundary: one digit under `_PHONE_MIN_DIGITS` (7) must reprompt."""
    update = _make_update(text="123456")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.recibir_celular(update, context)

    assert result == RegistroEstado.CELULAR
    assert "phone" not in context.user_data[registro._DRAFT_KEY]


async def test_recibir_celular_seven_digits_accepted(monkeypatch):
    """Boundary: exactly `_PHONE_MIN_DIGITS` (7) digits must be accepted."""
    fake_client = FakeClient()
    fake_client.sucursales.return_value = [{"id": "s1", "nombre": "Bogotá"}]
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="1234567")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.recibir_celular(update, context)

    assert result == RegistroEstado.SUCURSAL
    assert context.user_data[registro._DRAFT_KEY]["phone"] == "1234567"


async def test_recibir_celular_fifteen_digits_accepted(monkeypatch):
    """Boundary: exactly `_PHONE_MAX_DIGITS` (15) digits must be accepted."""
    fake_client = FakeClient()
    fake_client.sucursales.return_value = [{"id": "s1", "nombre": "Bogotá"}]
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="123456789012345")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.recibir_celular(update, context)

    assert result == RegistroEstado.SUCURSAL
    assert context.user_data[registro._DRAFT_KEY]["phone"] == "123456789012345"


async def test_recibir_celular_sixteen_digits_rejected():
    """Boundary: one digit over `_PHONE_MAX_DIGITS` (15) must reprompt."""
    update = _make_update(text="1234567890123456")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.recibir_celular(update, context)

    assert result == RegistroEstado.CELULAR
    assert "phone" not in context.user_data[registro._DRAFT_KEY]


async def test_recibir_celular_valid_shows_sucursal_picker(monkeypatch):
    fake_client = FakeClient()
    fake_client.sucursales.return_value = [{"id": "s1", "nombre": "Bogotá"}]
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="3001234567")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.recibir_celular(update, context)

    assert result == RegistroEstado.SUCURSAL
    assert context.user_data[registro._DRAFT_KEY]["phone"] == "3001234567"
    assert context.user_data[registro._DRAFT_KEY]["sucursales"] == {"s1": "Bogotá"}
    _, kwargs = update.message.reply_text.call_args
    assert kwargs["reply_markup"] is not None


async def test_recibir_celular_empty_sucursales_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.sucursales.return_value = []
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="3001234567")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.recibir_celular(update, context)

    assert result == ConversationHandler.END


async def test_recibir_celular_backend_caido_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.sucursales.side_effect = BackendCaido("boom")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="3001234567")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.recibir_celular(update, context)

    assert result == ConversationHandler.END


# --- recibir_sucursal / confirmar -----------------------------------------


async def test_recibir_sucursal_shows_confirmation_summary():
    update = _make_update(callback_data="lore_sucursal:s1")
    context = _make_context(
        user_data={
            registro._DRAFT_KEY: {
                "nombre": "Ana",
                "phone": "3001234567",
                "sucursales": {"s1": "Bogotá"},
            }
        }
    )

    result = await registro.recibir_sucursal(update, context)

    assert result == RegistroEstado.CONFIRMAR
    assert context.user_data[registro._DRAFT_KEY]["sucursal_id"] == "s1"
    update.callback_query.answer.assert_awaited_once()
    update.callback_query.edit_message_text.assert_awaited_once()
    resumen = update.callback_query.edit_message_text.call_args.args[0]
    assert "Bogotá" in resumen
    assert "Ana" in resumen


async def test_recibir_sucursal_escapes_markdown_special_chars_in_nombre():
    update = _make_update(callback_data="lore_sucursal:s1")
    context = _make_context(
        user_data={
            registro._DRAFT_KEY: {
                "nombre": "Juan_Perez*Test",
                "phone": "3001234567",
                "sucursales": {"s1": "Bogotá"},
            }
        }
    )

    result = await registro.recibir_sucursal(update, context)

    assert result == RegistroEstado.CONFIRMAR
    resumen = update.callback_query.edit_message_text.call_args.args[0]
    assert _escapar_markdown("Juan_Perez*Test") in resumen
    assert "Juan_Perez*Test" not in resumen  # unescaped form must not leak through


async def test_recibir_sucursal_unknown_id_ends_conversation_as_expired():
    update = _make_update(callback_data="lore_sucursal:stale")
    context = _make_context(
        user_data={
            registro._DRAFT_KEY: {
                "nombre": "Ana",
                "phone": "3001234567",
                "sucursales": {"s1": "Bogotá"},
            }
        }
    )

    result = await registro.recibir_sucursal(update, context)

    assert result == ConversationHandler.END
    assert registro._DRAFT_KEY not in context.user_data
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert text == _MSG_SESION_EXPIRADA


async def test_confirmar_cancelar_clears_draft_and_ends():
    update = _make_update(callback_data="lore_reg_cancelar")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.confirmar(update, context)

    assert result == ConversationHandler.END
    assert registro._DRAFT_KEY not in context.user_data


async def test_confirmar_success_sends_registro_and_notifies_admins(monkeypatch):
    fake_client = FakeClient()
    fake_client.registro.return_value = {
        "usuario": {"id": "u1", "nombre": "Ana", "status": "pending"},
        "admin_telegram_ids": [111, 222],
    }
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data="lore_reg_confirmar")
    context = _make_context(
        user_data={
            registro._DRAFT_KEY: {
                "nombre": "Ana",
                "phone": "3001234567",
                "sucursal_id": "s1",
            }
        }
    )

    result = await registro.confirmar(update, context)

    assert result == ConversationHandler.END
    assert registro._DRAFT_KEY not in context.user_data
    fake_client.registro.assert_awaited_once_with(nombre="Ana", phone="3001234567", sucursal_id="s1")
    assert context.bot.send_message.await_count == 2
    sent_chat_ids = {call.kwargs["chat_id"] for call in context.bot.send_message.await_args_list}
    assert sent_chat_ids == {111, 222}
    for call in context.bot.send_message.await_args_list:
        callback_datas = [
            button.callback_data
            for row in call.kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        assert callback_datas == ["lore_apr:u1", "lore_rej:u1"]


async def test_confirmar_ya_registrado_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.registro.side_effect = YaRegistrado("dup")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data="lore_reg_confirmar")
    context = _make_context(
        user_data={registro._DRAFT_KEY: {"nombre": "Ana", "phone": "3001234567", "sucursal_id": "s1"}}
    )

    result = await registro.confirmar(update, context)

    assert result == ConversationHandler.END
    assert registro._DRAFT_KEY not in context.user_data
    assert context.bot.send_message.await_count == 0
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "ya tenés una solicitud" in text.lower()


async def test_confirmar_sucursal_no_encontrada_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.registro.side_effect = SucursalNoEncontrada("nope")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data="lore_reg_confirmar")
    context = _make_context(
        user_data={registro._DRAFT_KEY: {"nombre": "Ana", "phone": "3001234567", "sucursal_id": "s1"}}
    )

    result = await registro.confirmar(update, context)

    assert result == ConversationHandler.END
    assert registro._DRAFT_KEY not in context.user_data
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "sucursal seleccionada ya no está disponible" in text.lower()


async def test_confirmar_backend_caido_keeps_draft(monkeypatch):
    fake_client = FakeClient()
    fake_client.registro.side_effect = BackendCaido("boom")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data="lore_reg_confirmar")
    context = _make_context(
        user_data={registro._DRAFT_KEY: {"nombre": "Ana", "phone": "3001234567", "sucursal_id": "s1"}}
    )

    result = await registro.confirmar(update, context)

    assert result == ConversationHandler.END
    # A transient backend failure should not silently drop the collected
    # draft — the advisor can retry without re-typing everything.
    assert registro._DRAFT_KEY in context.user_data
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert text == registro._MSG_CONEXION


# --- _notificar_admins ------------------------------------------------------


async def test_notificar_admins_isolates_per_admin_send_failures():
    """One admin's `send_message` raising (e.g. `Forbidden` because they
    blocked the bot) must never stop the OTHER admins from being notified."""
    context = _make_context()
    context.bot.send_message.side_effect = [None, Exception("blocked"), None]
    resultado = {
        "usuario": {"id": "u1", "nombre": "Ana"},
        "admin_telegram_ids": [111, 222, 333],
    }

    await registro._notificar_admins(context, resultado)

    assert context.bot.send_message.await_count == 3
    sent_chat_ids = [call.kwargs["chat_id"] for call in context.bot.send_message.await_args_list]
    assert sent_chat_ids == [111, 222, 333]


async def test_notificar_admins_escapes_markdown_special_chars_in_nombre():
    context = _make_context()
    resultado = {
        "usuario": {"id": "u1", "nombre": "Juan_Perez*Test"},
        "admin_telegram_ids": [111],
    }

    await registro._notificar_admins(context, resultado)

    text = context.bot.send_message.call_args.kwargs["text"]
    assert _escapar_markdown("Juan_Perez*Test") in text
    assert "Juan_Perez*Test" not in text


async def test_notificar_admins_empty_admin_ids_logs_warning(caplog):
    context = _make_context()
    resultado = {"usuario": {"id": "u1", "nombre": "Ana"}, "admin_telegram_ids": []}

    with caplog.at_level(logging.WARNING, logger="lore.handlers.registro"):
        await registro._notificar_admins(context, resultado)

    context.bot.send_message.assert_not_awaited()
    assert any("u1" in record.getMessage() for record in caplog.records)


# --- cancelar --------------------------------------------------------------


async def test_cancelar_clears_draft():
    update = _make_update()
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.cancelar(update, context)

    assert result == ConversationHandler.END
    assert registro._DRAFT_KEY not in context.user_data


# --- callback_huerfano -------------------------------------------------


async def test_callback_huerfano_answers_and_shows_session_expired():
    update = _make_update(callback_data="lore_sucursal:whatever")
    context = _make_context()

    await registro.callback_huerfano(update, context)

    update.callback_query.answer.assert_awaited_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert text == _MSG_SESION_EXPIRADA


async def test_callback_huerfano_shows_generic_message_for_stale_captura_callback():
    """Phase 10 fix-up finding #3: this same fallback also catches stale
    `lore_cap_*`/`lore_cor_*` callbacks now that those conversations exist —
    the message must be generic (never name a command wrong for those
    flows, e.g. telling a mid-capture advisor to send /start)."""
    update = _make_update(callback_data="lore_cap_toggle:whatever")
    context = _make_context()

    await registro.callback_huerfano(update, context)

    update.callback_query.answer.assert_awaited_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert text == _MSG_SESION_EXPIRADA
    assert "/start" not in text


async def test_callback_huerfano_shows_generic_message_for_stale_correccion_callback():
    update = _make_update(callback_data="lore_cor_volver")
    context = _make_context()

    await registro.callback_huerfano(update, context)

    update.callback_query.answer.assert_awaited_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert text == _MSG_SESION_EXPIRADA
    assert "/start" not in text


# --- _escapar_markdown ---------------------------------------------------


def test_escapar_markdown_escapes_all_legacy_special_chars():
    assert _escapar_markdown("a_b*c`d[e") == "a\\_b\\*c\\`d\\[e"


def test_escapar_markdown_leaves_plain_text_untouched():
    assert _escapar_markdown("Ana Torres") == "Ana Torres"
