import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import CallbackQuery, Chat, Message, MessageEntity, Update, User
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler

from lore import config
from lore.estados import Borrador, CapturaEstado, CorreccionEstado, RegistroEstado
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
    # admin approval + global stray-Cancelar handler + this fallback.
    assert len(callback_handlers) == 3
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


# --- lore-boton-cancelar: dispatch ----------------------------------------------


def _command_update(user: User, bot, comando: str, update_id: int = 100) -> Update:
    texto = f"/{comando}"
    message = Message(
        message_id=1,
        date=datetime.datetime.now(),
        chat=Chat(id=user.id, type="private"),
        from_user=user,
        text=texto,
        entities=[MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(texto))],
    )
    message.set_bot(bot)
    return Update(update_id=update_id, message=message)


def _cancel_tap_update(user: User, bot, data: str = "lore_cancelar", update_id: int = 200) -> Update:
    message = _make_message(user.id, user, bot)
    callback_query = CallbackQuery(
        id=str(update_id), from_user=user, chat_instance="c", data=data, message=message
    )
    callback_query.set_bot(bot)
    return Update(update_id=update_id, callback_query=callback_query)


def _conv_por_comando(application, comando: str) -> ConversationHandler:
    return next(
        h
        for h in application.handlers[0]
        if isinstance(h, ConversationHandler)
        and any(isinstance(ep, CommandHandler) and comando in ep.commands for ep in h.entry_points)
    )


def _patch_bot(application):
    bot_type = type(application.bot)
    return (
        patch.object(bot_type, "answer_callback_query", AsyncMock()),
        patch.object(bot_type, "edit_message_text", AsyncMock()),
        patch.object(bot_type, "send_message", AsyncMock()),
    )


def _app():
    application = build_application()
    application._initialized = True
    # `CommandHandler` compares against `bot.username`, which needs the bot's
    # own `User` (normally fetched by `get_me()` during `initialize()`).
    application.bot._bot_user = User(id=999, is_bot=True, first_name="lore", username="lore_bot")
    return application


async def test_global_cancelar_command_without_conversation_replies_nothing_to_cancel():
    application = _app()
    p1, p2, p3 = _patch_bot(application)
    with p1, p2, p3 as send_mock:
        user = User(id=301, is_bot=False, first_name="a")
        await application.process_update(_command_update(user, application.bot, "cancelar"))
    send_mock.assert_awaited_once()
    assert send_mock.await_args.kwargs["text"] == "No hay nada para cancelar."


async def test_global_cancela_alias_without_conversation_replies_nothing_to_cancel():
    application = _app()
    p1, p2, p3 = _patch_bot(application)
    with p1, p2, p3 as send_mock:
        user = User(id=302, is_bot=False, first_name="a")
        await application.process_update(_command_update(user, application.bot, "cancela"))
    send_mock.assert_awaited_once()
    assert send_mock.await_args.kwargs["text"] == "No hay nada para cancelar."


async def test_stray_cancel_tap_without_conversation_is_not_treated_as_expired_session():
    application = _app()
    p1, p2, p3 = _patch_bot(application)
    with p1 as answer_mock, p2 as edit_mock, p3:
        user = User(id=303, is_bot=False, first_name="a")
        await application.process_update(_cancel_tap_update(user, application.bot))
    answer_mock.assert_awaited_once()
    assert edit_mock.await_args.kwargs["text"] == "No hay nada para cancelar."


async def test_cancelar_command_in_active_conversation_is_still_handled_by_the_conversation():
    application = _app()
    conv = _conv_por_comando(application, "start")
    p1, p2, p3 = _patch_bot(application)
    with p1, p2, p3 as send_mock:
        user = User(id=304, is_bot=False, first_name="a")
        update = _command_update(user, application.bot, "cancelar")
        conv._conversations[conv._get_key(update)] = RegistroEstado.NOMBRE
        application.user_data[user.id][registro_handlers._DRAFT_KEY] = {}
        await application.process_update(update)
    assert "Registro cancelado" in send_mock.await_args.kwargs["text"]
    assert registro_handlers._DRAFT_KEY not in application.user_data[user.id]
    assert conv._get_key(update) not in conv._conversations


async def _tap_cancel_in_state(comando, estado, draft_key, draft, user_id):
    application = _app()
    conv = _conv_por_comando(application, comando)
    p1, p2, p3 = _patch_bot(application)
    with p1 as answer_mock, p2 as edit_mock, p3:
        user = User(id=user_id, is_bot=False, first_name="a")
        update = _cancel_tap_update(user, application.bot, update_id=user_id)
        conv._conversations[conv._get_key(update)] = estado
        application.user_data[user.id][draft_key] = draft
        await application.process_update(update)
    answer_mock.assert_awaited_once()
    assert conv._get_key(update) not in conv._conversations
    assert draft_key not in application.user_data[user.id]
    return edit_mock.await_args.kwargs["text"]


async def test_cancel_tap_from_free_text_state_ends_registro_and_clears_draft():
    texto = await _tap_cancel_in_state(
        "start", RegistroEstado.NOMBRE, registro_handlers._DRAFT_KEY, {}, 401
    )
    assert "Registro cancelado" in texto


async def test_cancel_tap_from_inline_state_ends_captura_and_clears_draft():
    texto = await _tap_cancel_in_state(
        "registrar", CapturaEstado.SELECCION, captura_handlers._DRAFT_KEY, Borrador(), 402
    )
    assert "Registro cancelado" in texto


async def test_cancel_tap_from_foto_state_ends_captura_and_clears_draft():
    texto = await _tap_cancel_in_state(
        "registrar", CapturaEstado.FOTO, captura_handlers._DRAFT_KEY, Borrador(), 403
    )
    assert "Registro cancelado" in texto


async def test_cancel_tap_from_correccion_cantidad_ends_and_clears_state():
    texto = await _tap_cancel_in_state(
        "correcciones", CorreccionEstado.CANTIDAD, correccion_handlers._DATA_KEY, {"cargas": {}}, 404
    )
    assert "no se hizo ningún cambio" in texto


def _conversacion(entry_point_check):
    handlers = build_application().handlers[0]
    return next(
        h for h in handlers
        if isinstance(h, ConversationHandler) and any(entry_point_check(ep) for ep in h.entry_points)
    )


def test_registro_conversation_can_be_entered_from_the_register_another_advisor_button():
    conv = _conversacion(lambda ep: isinstance(ep, CommandHandler) and "start" in ep.commands)

    botones = [
        ep for ep in conv.entry_points
        if isinstance(ep, CallbackQueryHandler) and ep.callback is registro_handlers.iniciar_otro
    ]
    assert len(botones) == 1
    assert botones[0].pattern.match("lore_reg_otro")


def test_captura_conversation_routes_the_who_registers_answer():
    conv = _conversacion(lambda ep: isinstance(ep, CommandHandler) and "registrar" in ep.commands)

    handlers = conv.states[CapturaEstado.ASESOR]
    assert [h.callback for h in handlers] == [captura_handlers.recibir_asesor]
    assert handlers[0].pattern.match("lore_cap_ase:abc")


def test_correccion_conversation_routes_the_who_registers_answer():
    conv = _conversacion(lambda ep: isinstance(ep, CommandHandler) and "correcciones" in ep.commands)

    handlers = conv.states[CorreccionEstado.ASESOR]
    assert [h.callback for h in handlers] == [correccion_handlers.recibir_asesor]
    assert handlers[0].pattern.match("lore_cor_ase:abc")
