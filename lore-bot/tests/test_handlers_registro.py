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

from lore.api import (
    BackendCaido,
    LoreApiError,
    NoRegistrado,
    SucursalNoEncontrada,
    TelegramEsAdmin,
    YaRegistrado,
)
from lore.estados import RegistroEstado
from lore.handlers import registro
from lore.handlers._common import TECLADO_ADMIN, TECLADO_CAPTURA, _MSG_SESION_EXPIRADA, _escapar_markdown


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
    # A pending applicant can't use the capture/correction flows yet -- must
    # NOT get the keyboard that shortcuts into them.
    assert "reply_markup" not in update.message.reply_text.call_args.kwargs


async def test_start_rejected_status_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"status": "rejected", "nombre": "Ana"}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await registro.start(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "rechazada" in text.lower()
    assert "reply_markup" not in update.message.reply_text.call_args.kwargs


async def test_start_approved_asesor_greets_by_name_and_role(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {
        "status": "approved", "nombre": "Ana", "role": "ASESOR_MOSTRADOR",
    }
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await registro.start(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args_list[0].args[0]
    assert "Ana" in text
    assert "asesor de mostrador" in text
    assert "administrador" not in text
    # UX shortcut: an approved advisor's welcome-back is the ONE send-site
    # that attaches the persistent capture/correction Reply Keyboard (see
    # `_common.py::TECLADO_CAPTURA`'s docstring for why elsewhere is not
    # needed).
    assert update.message.reply_text.call_args_list[0].kwargs["reply_markup"] is TECLADO_CAPTURA


async def test_start_approved_compras_greets_with_real_role(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {
        "status": "approved", "nombre": "Luis", "role": "COMPRAS",
    }
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    await registro.start(update, _make_context())

    text = update.message.reply_text.call_args_list[0].args[0]
    assert "registrado como Compras." in text


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
    # An ADMIN also drives `/registrar`/`/correcciones`, and additionally
    # gets the "Solicitudes pendientes" button: the keyboard depends on role.
    assert update.message.reply_text.call_args.kwargs["reply_markup"] is TECLADO_ADMIN


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


async def test_cancelar_from_cancel_button_answers_edits_and_clears_draft():
    update = _make_update(callback_data="lore_cancelar")
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})

    result = await registro.cancelar(update, context)

    assert result == ConversationHandler.END
    assert registro._DRAFT_KEY not in context.user_data
    update.callback_query.answer.assert_awaited_once()
    assert "Registro cancelado" in update.callback_query.edit_message_text.call_args.args[0]


# --- T2: every prompt carries the Cancelar button ---------------------------------


async def test_prompt_nombre_has_cancel_button(monkeypatch, termina_en_cancelar):
    fake_client = FakeClient()
    fake_client.yo.side_effect = NoRegistrado("nope")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    update = _make_update(text="/start")

    await registro.start(update, _make_context())

    assert termina_en_cancelar(update.message.reply_text.call_args)


async def test_prompts_nombre_retry_and_celular_have_cancel_button(termina_en_cancelar):
    context = _make_context(user_data={registro._DRAFT_KEY: {}})
    invalido = _make_update(text="A")
    valido = _make_update(text="Ana Pérez")

    await registro.recibir_nombre(invalido, context)
    await registro.recibir_nombre(valido, context)

    assert termina_en_cancelar(invalido.message.reply_text.call_args)
    assert termina_en_cancelar(valido.message.reply_text.call_args)


async def test_prompts_celular_retry_and_sucursal_picker_have_cancel_button(monkeypatch, termina_en_cancelar):
    fake_client = FakeClient()
    fake_client.sucursales.return_value = [{"id": "s1", "nombre": "Bogotá"}]
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    context = _make_context(user_data={registro._DRAFT_KEY: {"nombre": "Ana"}})
    invalido = _make_update(text="12")
    valido = _make_update(text="3001234567")

    await registro.recibir_celular(invalido, context)
    await registro.recibir_celular(valido, context)

    assert termina_en_cancelar(invalido.message.reply_text.call_args)
    llamada = valido.message.reply_text.call_args
    assert termina_en_cancelar(llamada)
    assert llamada.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "lore_sucursal:s1"


async def test_resumen_confirm_step_has_exactly_one_cancel_control():
    context = _make_context(
        user_data={registro._DRAFT_KEY: {"nombre": "Ana", "phone": "3001234567", "sucursales": {"s1": "Bogotá"}}}
    )
    update = _make_update(callback_data="lore_sucursal:s1")

    await registro.recibir_sucursal(update, context)

    # The step's own "❌ Cancelar" (next to ✅ Confirmar) is the only cancel.
    markup = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    datos = [b.callback_data for fila in markup.inline_keyboard for b in fila]
    assert datos == ["lore_reg_confirmar", "lore_reg_cancelar"]


# --- several advisors on one Telegram ---------------------------------------


def _boton_otro(llamada):
    """The "Registrar otro asesor" inline button of a `reply_text` call, if any."""
    markup = llamada.kwargs.get("reply_markup")
    filas = getattr(markup, "inline_keyboard", None) or []
    return [b for fila in filas for b in fila if b.callback_data == "lore_reg_otro"]


def _asesor_yo(status, nombre="Ana"):
    return {"nombre": nombre, "role": "ASESOR_MOSTRADOR", "status": status, "activo": True}


async def test_start_approved_asesor_offers_to_register_another_advisor(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {**_asesor_yo("approved"), "asesores": [_asesor_yo("approved")]}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await registro.start(update, _make_context())

    llamadas = update.message.reply_text.call_args_list
    assert llamadas[0].kwargs["reply_markup"] is TECLADO_CAPTURA  # greeting unchanged
    boton = _boton_otro(llamadas[-1])
    assert [b.text for b in boton] == ["➕ Registrar otro asesor"]


async def test_start_pending_asesor_can_still_register_another_advisor(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {**_asesor_yo("pending"), "asesores": [_asesor_yo("pending")]}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await registro.start(update, _make_context())

    assert "pendiente" in update.message.reply_text.call_args.args[0].lower()
    assert _boton_otro(update.message.reply_text.call_args)


async def test_start_rejected_asesor_can_still_register_another_advisor(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {**_asesor_yo("rejected"), "asesores": [_asesor_yo("rejected")]}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await registro.start(update, _make_context())

    assert "rechazada" in update.message.reply_text.call_args.args[0].lower()
    assert _boton_otro(update.message.reply_text.call_args)


async def test_start_admin_is_never_offered_to_share_the_telegram(monkeypatch):
    fake_client = FakeClient()
    admin = {"nombre": "Ana", "role": "ADMIN", "status": "approved", "activo": True}
    fake_client.yo.return_value = {**admin, "asesores": [admin]}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await registro.start(update, _make_context())

    assert update.message.reply_text.await_count == 1
    assert not _boton_otro(update.message.reply_text.call_args)


async def test_start_with_several_advisors_lists_each_with_its_state_and_offers_another(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"asesores": [
        _asesor_yo("approved", "Ana"), _asesor_yo("pending", "Beto"), _asesor_yo("rejected", "Caro"),
    ]}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    result = await registro.start(update, _make_context())

    assert result == ConversationHandler.END
    llamadas = update.message.reply_text.call_args_list
    texto = llamadas[0].args[0]
    assert "Ana" in texto and "Beto" in texto and "Caro" in texto
    assert "pendiente" in texto and "rechazad" in texto
    assert llamadas[0].kwargs["reply_markup"] is TECLADO_CAPTURA  # one is approved
    assert _boton_otro(llamadas[-1])


async def test_start_with_several_advisors_none_approved_gets_no_capture_keyboard(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"asesores": [_asesor_yo("pending", "Ana"), _asesor_yo("pending", "Beto")]}
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await registro.start(update, _make_context())

    assert all(
        c.kwargs.get("reply_markup") is not TECLADO_CAPTURA
        for c in update.message.reply_text.call_args_list
    )
    assert _boton_otro(update.message.reply_text.call_args)


async def test_iniciar_otro_starts_the_normal_registration_flow_from_the_button():
    update = _make_update(callback_data="lore_reg_otro")
    update.callback_query.message = MagicMock()
    update.callback_query.message.reply_text = AsyncMock()
    context = _make_context()

    result = await registro.iniciar_otro(update, context)

    assert result == RegistroEstado.NOMBRE
    assert context.user_data[registro._DRAFT_KEY] == {}
    update.callback_query.answer.assert_awaited()
    assert "nombre completo" in update.callback_query.message.reply_text.call_args.args[0]


async def test_confirmar_telegram_es_admin_explains_it_cannot_be_shared(monkeypatch):
    fake_client = FakeClient()
    fake_client.registro.side_effect = TelegramEsAdmin("TELEGRAM_ES_ADMIN")
    monkeypatch.setattr(registro, "_cliente", _fake_cliente(fake_client))
    update = _make_update(callback_data="lore_reg_confirmar")
    draft = {"nombre": "Ana Perez", "phone": "3001234567", "sucursal_id": "s1"}
    context = _make_context(user_data={registro._DRAFT_KEY: draft})

    result = await registro.confirmar(update, context)

    assert result == ConversationHandler.END
    assert "administrador" in update.callback_query.edit_message_text.call_args.args[0]
    assert registro._DRAFT_KEY not in context.user_data
