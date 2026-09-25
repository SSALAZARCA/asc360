"""Unit tests for `lore.handlers.admin` — `/vincular` and the Aprobar/
Rechazar callback buttons. Same `FakeClient`-double pattern as
`test_handlers_registro.py`."""
from unittest.mock import AsyncMock, MagicMock

from lore.api import BackendCaido, CodigoInvalido, Pendiente, TelegramYaVinculado, YaResuelta
from lore.handlers import admin
from lore.handlers._common import _MSG_CONEXION

_UUID_1 = "11111111-1111-1111-1111-111111111111"


class FakeClient:
    def __init__(self):
        self.vincular = AsyncMock()
        self.aprobar_solicitud = AsyncMock()
        self.rechazar_solicitud = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _fake_cliente(fake_client):
    return lambda telegram_id: fake_client


def _make_update(*, callback_data=None, user_id=999):
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
        update.message.reply_text = AsyncMock()
    return update


def _make_context(*, args=None):
    context = MagicMock()
    context.args = args or []
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


# --- /vincular ---------------------------------------------------------


async def test_vincular_command_without_args_shows_usage():
    update = _make_update()
    context = _make_context(args=[])

    await admin.vincular_command(update, context)

    text = update.message.reply_text.call_args.args[0]
    assert "/vincular" in text


async def test_vincular_command_success(monkeypatch):
    fake_client = FakeClient()
    fake_client.vincular.return_value = {"id": "u2", "nombre": "Admin Uno", "role": "ADMIN"}
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context(args=["ABC12345"])

    await admin.vincular_command(update, context)

    fake_client.vincular.assert_awaited_once_with("ABC12345")
    text = update.message.reply_text.call_args.args[0]
    assert "Admin Uno" in text


async def test_vincular_command_codigo_invalido(monkeypatch):
    fake_client = FakeClient()
    fake_client.vincular.side_effect = CodigoInvalido("bad")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    await admin.vincular_command(update, _make_context(args=["BAD"]))

    text = update.message.reply_text.call_args.args[0]
    assert "inválido" in text.lower()


async def test_vincular_command_telegram_ya_vinculado(monkeypatch):
    fake_client = FakeClient()
    fake_client.vincular.side_effect = TelegramYaVinculado("dup")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    await admin.vincular_command(update, _make_context(args=["ABC12345"]))

    text = update.message.reply_text.call_args.args[0]
    assert "vinculado" in text.lower()


async def test_vincular_command_backend_caido(monkeypatch):
    fake_client = FakeClient()
    fake_client.vincular.side_effect = BackendCaido("boom")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    await admin.vincular_command(update, _make_context(args=["ABC12345"]))

    text = update.message.reply_text.call_args.args[0]
    assert text == _MSG_CONEXION


# --- aprobar / rechazar callback -----------------------------------------


async def test_resolver_solicitud_callback_aprobar_notifies_applicant(monkeypatch):
    fake_client = FakeClient()
    fake_client.aprobar_solicitud.return_value = {
        "usuario_id": _UUID_1,
        "status": "approved",
        "nombre": "Ana",
        "telegram_id_solicitante": 555,
    }
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_apr:{_UUID_1}")
    context = _make_context()

    await admin.resolver_solicitud_callback(update, context)

    fake_client.aprobar_solicitud.assert_awaited_once_with(_UUID_1)
    update.callback_query.edit_message_text.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["chat_id"] == 555


async def test_resolver_solicitud_callback_rechazar_calls_rechazar(monkeypatch):
    fake_client = FakeClient()
    fake_client.rechazar_solicitud.return_value = {
        "usuario_id": _UUID_1,
        "status": "rejected",
        "nombre": "Ana",
        "telegram_id_solicitante": 555,
    }
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_rej:{_UUID_1}")
    await admin.resolver_solicitud_callback(update, _make_context())

    fake_client.rechazar_solicitud.assert_awaited_once_with(_UUID_1)
    fake_client.aprobar_solicitud.assert_not_awaited()


async def test_resolver_solicitud_callback_ya_resuelta_edits_message_without_crashing(monkeypatch):
    fake_client = FakeClient()
    fake_client.aprobar_solicitud.side_effect = YaResuelta("YA_RESUELTA")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_apr:{_UUID_1}")
    context = _make_context()

    await admin.resolver_solicitud_callback(update, context)

    update.callback_query.edit_message_text.assert_awaited_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "resuelta" in text.lower()
    context.bot.send_message.assert_not_awaited()


async def test_resolver_solicitud_callback_backend_caido(monkeypatch):
    fake_client = FakeClient()
    fake_client.aprobar_solicitud.side_effect = BackendCaido("boom")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_apr:{_UUID_1}")
    await admin.resolver_solicitud_callback(update, _make_context())

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert text == _MSG_CONEXION


async def test_resolver_solicitud_callback_without_solicitante_id_skips_notify(monkeypatch):
    fake_client = FakeClient()
    fake_client.aprobar_solicitud.return_value = {
        "usuario_id": _UUID_1,
        "status": "approved",
        "nombre": "Ana",
        "telegram_id_solicitante": None,
    }
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_apr:{_UUID_1}")
    context = _make_context()

    await admin.resolver_solicitud_callback(update, context)

    context.bot.send_message.assert_not_awaited()


async def test_vincular_command_unmapped_lore_api_error_shows_generic_error(monkeypatch):
    # gga finding (post-4-lens-review): every BackendClient method shares
    # ONE global error-code map -- a LoreApiError subclass not explicitly
    # handled by this endpoint's own try/except must still reply, not
    # silently reach only the global logger.
    fake_client = FakeClient()
    fake_client.vincular.side_effect = Pendiente("PENDIENTE")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    await admin.vincular_command(update, _make_context(args=["ABC12345"]))

    text = update.message.reply_text.call_args.args[0]
    assert text == _MSG_CONEXION


async def test_resolver_solicitud_callback_unmapped_lore_api_error_shows_generic_error(monkeypatch):
    fake_client = FakeClient()
    fake_client.aprobar_solicitud.side_effect = Pendiente("PENDIENTE")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_apr:{_UUID_1}")
    context = _make_context()

    await admin.resolver_solicitud_callback(update, context)

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert text == _MSG_CONEXION
    context.bot.send_message.assert_not_awaited()


async def test_resolver_solicitud_callback_isolates_applicant_notification_failure(monkeypatch):
    # gga finding (post-4-lens-review): the applicant-notification
    # send_message must be isolated the same way _notificar_admins already
    # isolates its own per-admin sends -- a Forbidden/etc. here must not
    # propagate uncaught (the approval is already saved and the admin's own
    # message already edited by this point).
    fake_client = FakeClient()
    fake_client.aprobar_solicitud.return_value = {
        "usuario_id": _UUID_1,
        "status": "approved",
        "nombre": "Ana",
        "telegram_id_solicitante": 555,
    }
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_apr:{_UUID_1}")
    context = _make_context()
    context.bot.send_message.side_effect = Exception("Forbidden: bot was blocked by the user")

    await admin.resolver_solicitud_callback(update, context)  # must not raise

    update.callback_query.edit_message_text.assert_awaited_once()


async def test_resolver_solicitud_callback_malformed_usuario_id_shows_generic_error(monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data="lore_apr:../../etc")
    context = _make_context()

    await admin.resolver_solicitud_callback(update, context)

    fake_client.aprobar_solicitud.assert_not_awaited()
    fake_client.rechazar_solicitud.assert_not_awaited()
    update.callback_query.edit_message_text.assert_awaited_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "no pude procesar esta solicitud" in text.lower()
