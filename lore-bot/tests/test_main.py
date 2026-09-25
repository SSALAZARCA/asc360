import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler

from lore import config
from lore.estados import RegistroEstado
from lore.handlers import captura as captura_handlers
from lore.handlers import correccion as correccion_handlers
from lore.handlers import registro as registro_handlers
from lore.handlers._common import BOTON_CORRECCIONES, BOTON_REGISTRAR
from lore.main import build_application


def test_build_application_uses_the_configured_token():
    application = build_application()
    assert application.bot.token == config.LORE_BOT_TOKEN


def test_build_application_registers_registration_conversation():
    # Phase 9 — `/start` now begins the self-registration conversation
    # (handlers/registro.py), replacing Phase 8's inert skeleton.
    application = build_application()
    handlers = application.handlers[0]
    conv_handlers = [h for h in handlers if isinstance(h, ConversationHandler)]
    # Phase 10 added 2 more ConversationHandlers (captura, correccion)
    # alongside Phase 9's registration one.
    assert len(conv_handlers) == 3
    registro_conv = next(
        h
        for h in conv_handlers
        if any(isinstance(ep, CommandHandler) and "start" in ep.commands for ep in h.entry_points)
    )
    assert registro_conv is not None


def test_build_application_registers_captura_conversation():
    application = build_application()
    handlers = application.handlers[0]
    conv_handlers = [h for h in handlers if isinstance(h, ConversationHandler)]
    assert any(
        isinstance(ep, CommandHandler) and "registrar" in ep.commands
        for h in conv_handlers
        for ep in h.entry_points
    )


def test_build_application_captura_conversation_has_button_entry_point():
    # UX shortcut: the persistent Reply Keyboard's "Registrar venta perdida"
    # button must be wired as an ADDITIONAL entry point into the SAME
    # `captura_handlers.iniciar` the `/registrar` command already uses --
    # never a duplicated copy of its logic.
    application = build_application()
    handlers = application.handlers[0]
    conv_handlers = [h for h in handlers if isinstance(h, ConversationHandler)]
    captura_conv = next(
        h
        for h in conv_handlers
        for ep in h.entry_points
        if isinstance(ep, CommandHandler) and "registrar" in ep.commands
    )
    button_entry_points = [ep for ep in captura_conv.entry_points if isinstance(ep, MessageHandler)]
    assert len(button_entry_points) == 1
    assert button_entry_points[0].callback is captura_handlers.iniciar
    assert button_entry_points[0].filters.check_update(
        _text_only_update(BOTON_REGISTRAR)
    )
    assert not button_entry_points[0].filters.check_update(
        _text_only_update("cualquier otro texto")
    )


def test_build_application_correccion_conversation_has_button_entry_point():
    application = build_application()
    handlers = application.handlers[0]
    conv_handlers = [h for h in handlers if isinstance(h, ConversationHandler)]
    correccion_conv = next(
        h
        for h in conv_handlers
        for ep in h.entry_points
        if isinstance(ep, CommandHandler) and "correcciones" in ep.commands
    )
    button_entry_points = [ep for ep in correccion_conv.entry_points if isinstance(ep, MessageHandler)]
    assert len(button_entry_points) == 1
    assert button_entry_points[0].callback is correccion_handlers.iniciar
    assert button_entry_points[0].filters.check_update(
        _text_only_update(BOTON_CORRECCIONES)
    )
    assert not button_entry_points[0].filters.check_update(
        _text_only_update("cualquier otro texto")
    )


def test_build_application_registers_correccion_conversation():
    application = build_application()
    handlers = application.handlers[0]
    conv_handlers = [h for h in handlers if isinstance(h, ConversationHandler)]
    assert any(
        isinstance(ep, CommandHandler) and "correcciones" in ep.commands
        for h in conv_handlers
        for ep in h.entry_points
    )


def test_build_application_registers_vincular_command():
    application = build_application()
    handlers = application.handlers[0]
    command_handlers = [h for h in handlers if isinstance(h, CommandHandler)]
    assert any("vincular" in h.commands for h in command_handlers)


def test_build_application_registers_admin_approval_callback():
    application = build_application()
    handlers = application.handlers[0]
    callback_handlers = [h for h in handlers if isinstance(h, CallbackQueryHandler)]
    assert any(h.pattern.pattern == r"^lore_(apr|rej):" for h in callback_handlers)


def test_build_application_registers_orphaned_callback_fallback_last():
    # Phase 9 fix-up, finding #7 — the broad `^lore_` fallback must come
    # AFTER the more specific handlers in the default group (group=0):
    # python-telegram-bot dispatches to the FIRST handler in a group whose
    # `check_update` matches, so registering the fallback earlier would
    # shadow the real approval callback.
    application = build_application()
    handlers = application.handlers[0]
    callback_handlers = [h for h in handlers if isinstance(h, CallbackQueryHandler)]
    assert len(callback_handlers) == 2
    assert callback_handlers[-1].pattern.pattern == r"^lore_"
    assert callback_handlers[-1].callback is registro_handlers.callback_huerfano


def test_build_application_registers_error_handler():
    application = build_application()
    assert len(application.error_handlers) == 1


def _text_only_update(text: str) -> MagicMock:
    """Bare `Update` double for exercising a `MessageHandler`'s `.filters`
    directly (`filters.Text.filter` only ever reads `.text` off
    `update.effective_message`) -- no bot/chat wiring needed for this,
    unlike the full `process_update` end-to-end tests below."""
    update = MagicMock()
    update.effective_message.text = text
    return update


def _make_message(chat_id: int, user: User, bot, text: str | None = None) -> Message:
    message = Message(
        message_id=1,
        date=datetime.datetime.now(),
        chat=Chat(id=chat_id, type="private"),
        from_user=user,
        text=text,
    )
    message.set_bot(bot)
    return message


async def test_orphaned_lore_callback_triggers_session_expired_fallback():
    """End-to-end proof for finding #7: a `lore_*` callback with NO active
    conversation state (simulating a process restart having wiped in-memory
    `ConversationHandler` state) must not be silently dropped."""
    application = build_application()
    application._initialized = True

    with patch.object(type(application.bot), "answer_callback_query", AsyncMock()), patch.object(
        type(application.bot), "edit_message_text", AsyncMock()
    ) as edit_mock:
        user = User(id=1, is_bot=False, first_name="x")
        message = _make_message(1, user, application.bot)
        callback_query = CallbackQuery(
            id="1", from_user=user, chat_instance="c", data="lore_sucursal:s1", message=message
        )
        callback_query.set_bot(application.bot)
        update = Update(update_id=1, callback_query=callback_query)

        await application.process_update(update)

        edit_mock.assert_awaited_once()
        text = edit_mock.await_args.kwargs["text"]
        assert "expiró" in text.lower()


async def test_active_conversation_callback_is_not_intercepted_by_fallback():
    """End-to-end proof for finding #7: the fallback must NOT interfere with
    a genuinely active conversation — the exact same `lore_sucursal:` pattern
    must still be handled by `recibir_sucursal`, not the fallback."""
    application = build_application()
    application._initialized = True
    conv = next(h for h in application.handlers[0] if isinstance(h, ConversationHandler))

    with patch.object(type(application.bot), "answer_callback_query", AsyncMock()), patch.object(
        type(application.bot), "edit_message_text", AsyncMock()
    ) as edit_mock:
        user = User(id=2, is_bot=False, first_name="y")
        message = _make_message(2, user, application.bot)
        callback_query = CallbackQuery(
            id="2", from_user=user, chat_instance="c2", data="lore_sucursal:s1", message=message
        )
        callback_query.set_bot(application.bot)
        update = Update(update_id=2, callback_query=callback_query)

        # Seed the conversation as genuinely active in the SUCURSAL state,
        # with a matching draft — the private `_conversations`/`user_data`
        # pokes below are the only way to simulate "mid-conversation" without
        # driving the whole `/start` → nombre → celular chain through a real
        # `CommandHandler` (which additionally requires bot-username-bound
        # message entities to match).
        conv._conversations[conv._get_key(update)] = RegistroEstado.SUCURSAL
        application.user_data[user.id][registro_handlers._DRAFT_KEY] = {
            "nombre": "Ana",
            "phone": "3001234567",
            "sucursales": {"s1": "Bogotá"},
        }

        await application.process_update(update)

        edit_mock.assert_awaited_once()
        text = edit_mock.await_args.kwargs["text"]
        assert "Resumen de tu solicitud" in text
        assert "expiró" not in text.lower()


async def test_button_text_registrar_calls_the_same_iniciar_as_the_command():
    """Requirement #3: tapping "Registrar venta perdida" must behave
    identically to typing `/registrar` -- both dispatch to the exact same
    `captura_handlers.iniciar`, never a duplicated copy of its logic."""
    fake_iniciar = AsyncMock(return_value=ConversationHandler.END)
    with patch.object(captura_handlers, "iniciar", fake_iniciar):
        application = build_application()
        application._initialized = True

        user = User(id=11, is_bot=False, first_name="asesor")
        message = _make_message(11, user, application.bot, text=BOTON_REGISTRAR)
        update = Update(update_id=11, message=message)

        await application.process_update(update)

    fake_iniciar.assert_awaited_once()
    awaited_update = fake_iniciar.await_args.args[0]
    assert awaited_update.message.text == BOTON_REGISTRAR


async def test_button_text_correcciones_calls_the_same_iniciar_as_the_command():
    """Same proof as above for "Mis correcciones de hoy" /
    `correccion_handlers.iniciar`."""
    fake_iniciar = AsyncMock(return_value=ConversationHandler.END)
    with patch.object(correccion_handlers, "iniciar", fake_iniciar):
        application = build_application()
        application._initialized = True

        user = User(id=12, is_bot=False, first_name="asesor2")
        message = _make_message(12, user, application.bot, text=BOTON_CORRECCIONES)
        update = Update(update_id=12, message=message)

        await application.process_update(update)

    fake_iniciar.assert_awaited_once()
    awaited_update = fake_iniciar.await_args.args[0]
    assert awaited_update.message.text == BOTON_CORRECCIONES


async def test_button_text_does_not_trigger_unrelated_conversations():
    """Sanity check: arbitrary plain text (not one of the 2 exact button
    labels, not a command) must NOT be swallowed by either new entry point."""
    fake_captura_iniciar = AsyncMock(return_value=ConversationHandler.END)
    fake_correccion_iniciar = AsyncMock(return_value=ConversationHandler.END)
    with patch.object(captura_handlers, "iniciar", fake_captura_iniciar), patch.object(
        correccion_handlers, "iniciar", fake_correccion_iniciar
    ):
        application = build_application()
        application._initialized = True

        user = User(id=13, is_bot=False, first_name="asesor3")
        message = _make_message(13, user, application.bot, text="hola, tengo una duda")
        update = Update(update_id=13, message=message)

        await application.process_update(update)

    fake_captura_iniciar.assert_not_awaited()
    fake_correccion_iniciar.assert_not_awaited()
