"""Unit tests for `lore.handlers.admin` — `/vincular` and the Aprobar/
Rechazar callback buttons. Same `FakeClient`-double pattern as
`test_handlers_registro.py`."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest

from lore.api import (
    BackendCaido,
    CodigoInvalido,
    Inactivo,
    NoRegistrado,
    Pendiente,
    Rechazado,
    TelegramYaVinculado,
    YaResuelta,
)
from lore.handlers import admin
from lore.handlers._common import _MSG_CONEXION, teclado_resolver_solicitud
from lore.handlers.admin import _MAX_SOLICITUDES_POR_TOQUE, _MSG_SOLO_ADMIN

_UUID_1 = "11111111-1111-1111-1111-111111111111"


class FakeClient:
    def __init__(self):
        self.vincular = AsyncMock()
        self.aprobar_solicitud = AsyncMock()
        self.rechazar_solicitud = AsyncMock()
        self.listar_solicitudes = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _fake_cliente(fake_client):
    return lambda telegram_id: fake_client


def _make_update(*, callback_data=None, user_id=999, message_text=None, message_markup=None):
    update = MagicMock()
    update.effective_user.id = user_id
    if callback_data is not None:
        update.callback_query = MagicMock()
        update.callback_query.data = callback_data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.callback_query.message.text = message_text
        update.callback_query.message.reply_markup = message_markup
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


async def test_resolver_solicitud_callback_backend_caido_keeps_the_buttons_for_retry(monkeypatch):
    fake_client = FakeClient()
    fake_client.aprobar_solicitud.side_effect = BackendCaido("boom")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    botones = teclado_resolver_solicitud(_UUID_1)

    update = _make_update(
        callback_data=f"lore_apr:{_UUID_1}",
        message_text="Solicitud de acceso\nNombre: Ana",
        message_markup=botones,
    )
    await admin.resolver_solicitud_callback(update, _make_context())

    llamada = update.callback_query.edit_message_text.call_args
    assert llamada.args[0] == f"Solicitud de acceso\nNombre: Ana\n\n{_MSG_CONEXION}"
    assert llamada.kwargs["reply_markup"] is botones


async def test_resolver_solicitud_callback_backend_caido_twice_is_not_an_error(monkeypatch):
    fake_client = FakeClient()
    fake_client.aprobar_solicitud.side_effect = BackendCaido("boom")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    update = _make_update(
        callback_data=f"lore_apr:{_UUID_1}",
        message_text="Solicitud",
        message_markup=teclado_resolver_solicitud(_UUID_1),
    )
    update.callback_query.edit_message_text.side_effect = BadRequest("Message is not modified")

    await admin.resolver_solicitud_callback(update, _make_context())  # must not raise


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


# --- /pendientes and the "Solicitudes pendientes" button ---------------------

_PENDIENTE_ANA = {
    "id": _UUID_1,
    "nombre": "Ana_Gomez",
    "phone": "3001234567",
    "sucursales": ["Sede Norte"],
    "created_at": "2026-09-01T08:00:00",
}
_PENDIENTE_LUIS = {
    "id": "22222222-2222-2222-2222-222222222222",
    "nombre": "Luis",
    "phone": "3007654321",
    "sucursales": [],
    "created_at": "2026-09-02T09:00:00",
}


async def test_pendientes_sends_one_message_per_request_with_approve_reject_buttons(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_solicitudes.return_value = [_PENDIENTE_ANA, _PENDIENTE_LUIS]
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await admin.solicitudes_pendientes(update, _make_context())

    llamadas = update.message.reply_text.call_args_list
    assert len(llamadas) == 3  # summary + one per request
    assert "2" in llamadas[0].args[0]
    assert "Ana_Gomez" in llamadas[1].args[0]
    assert "3001234567" in llamadas[1].args[0]
    assert "Sede Norte" in llamadas[1].args[0]
    assert "Luis" in llamadas[2].args[0]
    botones = llamadas[1].kwargs["reply_markup"].inline_keyboard[0]
    assert [b.callback_data for b in botones] == [f"lore_apr:{_UUID_1}", f"lore_rej:{_UUID_1}"]
    assert "parse_mode" not in llamadas[1].kwargs  # names are shown as plain text


async def test_pendientes_with_nothing_pending_says_so(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_solicitudes.return_value = []
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await admin.solicitudes_pendientes(update, _make_context())

    update.message.reply_text.assert_awaited_once_with("No hay solicitudes pendientes.")


@pytest.mark.parametrize("error", [NoRegistrado, Pendiente, Rechazado, Inactivo])
async def test_pendientes_refuses_politely_when_the_caller_is_not_an_active_admin(monkeypatch, error):
    fake_client = FakeClient()
    fake_client.listar_solicitudes.side_effect = error("403")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await admin.solicitudes_pendientes(update, _make_context())

    update.message.reply_text.assert_awaited_once_with(_MSG_SOLO_ADMIN)


async def test_pendientes_backend_caido_shows_connection_message(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_solicitudes.side_effect = BackendCaido("boom")
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await admin.solicitudes_pendientes(update, _make_context())

    update.message.reply_text.assert_awaited_once_with(_MSG_CONEXION)


def _pendientes(cantidad: int) -> list[dict]:
    return [
        {
            "id": f"{n:08d}-1111-1111-1111-111111111111",
            "nombre": f"Asesor {n}",
            "phone": "3001234567",
            "sucursales": [],
        }
        for n in range(cantidad)
    ]


async def test_pendientes_caps_the_list_at_the_oldest_and_says_there_are_more(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_solicitudes.return_value = _pendientes(23)
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await admin.solicitudes_pendientes(update, _make_context())

    llamadas = update.message.reply_text.call_args_list
    assert _MAX_SOLICITUDES_POR_TOQUE == 10
    assert len(llamadas) == 1 + _MAX_SOLICITUDES_POR_TOQUE
    assert llamadas[0].args[0] == (
        "Hay 23 solicitudes pendientes. Te muestro las 10 más antiguas; aprobalas o "
        "rechazalas y volvé a tocar el botón para ver más, o revisalas todas en el "
        "panel (Usuarios)."
    )
    assert "Asesor 0" in llamadas[1].args[0]
    assert "Asesor 9" in llamadas[10].args[0]


async def test_pendientes_exactly_at_the_cap_has_no_more_notice(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_solicitudes.return_value = _pendientes(_MAX_SOLICITUDES_POR_TOQUE)
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    await admin.solicitudes_pendientes(update, _make_context())

    llamadas = update.message.reply_text.call_args_list
    assert len(llamadas) == 1 + _MAX_SOLICITUDES_POR_TOQUE
    assert "más antiguas" not in llamadas[0].args[0]


async def test_pendientes_skips_malformed_items_and_logs_a_warning(monkeypatch, caplog):
    fake_client = FakeClient()
    sin_id = {"nombre": "Sin id", "phone": "3000000000", "sucursales": []}
    fake_client.listar_solicitudes.return_value = [sin_id, "basura", _PENDIENTE_ANA]
    monkeypatch.setattr(admin, "_cliente", _fake_cliente(fake_client))
    update = _make_update()

    with caplog.at_level("WARNING", logger="lore.handlers.admin"):
        await admin.solicitudes_pendientes(update, _make_context())

    llamadas = update.message.reply_text.call_args_list
    assert len(llamadas) == 2  # summary + the one valid request
    assert "1" in llamadas[0].args[0]
    assert "Ana_Gomez" in llamadas[1].args[0]
    assert sum("malformada" in r.message for r in caplog.records) == 2
