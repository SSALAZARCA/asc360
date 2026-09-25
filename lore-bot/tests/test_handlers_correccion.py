"""Unit tests for `lore.handlers.correccion` — the today-only self-service
correction menu. Same `_cliente`-monkeypatch pattern as
`test_handlers_registro.py`/`test_handlers_captura.py`.
"""
from unittest.mock import AsyncMock, MagicMock

from telegram.ext import ConversationHandler

from lore.api import (
    BackendCaido,
    CargaNoEncontrada,
    FueraDeVentana,
    LineaAnulada,
    LineaNoEncontrada,
    LoreApiError,
    NoRegistrado,
    Pendiente,
    Rechazado,
    YaAnulada,
)
from lore.estados import CorreccionEstado
from lore.handlers import correccion

_CARGA_1 = "44444444-4444-4444-4444-444444444444"
_LINEA_1 = "55555555-5555-5555-5555-555555555555"


class FakeClient:
    def __init__(self):
        self.listar_hoy = AsyncMock()
        self.editar_linea = AsyncMock()
        self.anular_registro = AsyncMock()

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
    return context


def _carga_ejemplo():
    return {
        "carga_id": _CARGA_1,
        "creado_en": "2026-09-25T10:00:00",
        "sucursal": {"id": "s1", "nombre": "Bogotá"},
        "lineas": [
            {"linea_id": _LINEA_1, "referencia": {"codigo": "ABC", "nombre": "Filtro"}, "cantidad": 3.0}
        ],
    }


# --- iniciar -----------------------------------------------------------------


async def test_iniciar_no_registrado_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_hoy.side_effect = NoRegistrado("nope")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    result = await correccion.iniciar(_make_update(), _make_context())

    assert result == ConversationHandler.END


async def test_iniciar_pendiente_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_hoy.side_effect = Pendiente("pending")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await correccion.iniciar(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "pendiente" in text.lower()


async def test_iniciar_rechazado_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_hoy.side_effect = Rechazado("rejected")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await correccion.iniciar(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "rechazada" in text.lower()


async def test_iniciar_backend_caido_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_hoy.side_effect = BackendCaido("boom")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    result = await correccion.iniciar(_make_update(), _make_context())

    assert result == ConversationHandler.END


async def test_iniciar_unmapped_lore_api_error_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_hoy.side_effect = LoreApiError("unmapped")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    result = await correccion.iniciar(_make_update(), _make_context())

    assert result == ConversationHandler.END


async def test_iniciar_empty_list_ends_with_no_registros_message(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_hoy.return_value = []
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await correccion.iniciar(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "no tenés registros" in text.lower()


async def test_iniciar_with_registros_shows_list_and_caches_them(monkeypatch):
    fake_client = FakeClient()
    fake_client.listar_hoy.return_value = [_carga_ejemplo()]
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context()
    result = await correccion.iniciar(update, context)

    assert result == CorreccionEstado.LISTA
    assert _CARGA_1 in context.user_data[correccion._DATA_KEY]["cargas"]


# --- seleccionar_carga / _mostrar_acciones ------------------------------------


async def test_seleccionar_carga_unknown_id_ends_conversation():
    update = _make_update(callback_data="lore_cor_carga:99999999-9999-9999-9999-999999999999")
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {}}})

    result = await correccion.seleccionar_carga(update, context)

    assert result == ConversationHandler.END


async def test_seleccionar_carga_malformed_id_never_reaches_url():
    update = _make_update(callback_data="lore_cor_carga:not-a-uuid")
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {_CARGA_1: _carga_ejemplo()}}})

    result = await correccion.seleccionar_carga(update, context)

    assert result == ConversationHandler.END
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "ya no está disponible" in text.lower()


async def test_seleccionar_carga_known_id_shows_actions():
    update = _make_update(callback_data=f"lore_cor_carga:{_CARGA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {_CARGA_1: _carga_ejemplo()}}})

    result = await correccion.seleccionar_carga(update, context)

    assert result == CorreccionEstado.ACCION
    assert context.user_data[correccion._DATA_KEY]["carga_id_actual"] == _CARGA_1
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "qué querés hacer" in text.lower()


async def test_seleccionar_carga_line_with_deleted_reference_shows_placeholder():
    """Phase 10 fix-up finding #5: `referencia.codigo`/`.nombre` can be `None`
    per the backend's own documented behavior (a reference deleted after the
    original registration) — the button label must never render the literal
    string "None"."""
    carga = _carga_ejemplo()
    carga["lineas"][0]["referencia"] = {"codigo": None, "nombre": None}
    update = _make_update(callback_data=f"lore_cor_carga:{_CARGA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {_CARGA_1: carga}}})

    result = await correccion.seleccionar_carga(update, context)

    assert result == CorreccionEstado.ACCION
    _, kwargs = update.callback_query.edit_message_text.call_args
    boton = kwargs["reply_markup"].inline_keyboard[0][0]
    assert "None" not in boton.text
    assert "(referencia eliminada)" in boton.text


async def test_volver_a_lista_returns_to_lista_state():
    update = _make_update(callback_data="lore_cor_volver")
    context = _make_context(
        user_data={
            correccion._DATA_KEY: {
                "cargas": {_CARGA_1: _carga_ejemplo()},
                "carga_id_actual": _CARGA_1,
            }
        }
    )

    result = await correccion.volver_a_lista(update, context)

    assert result == CorreccionEstado.LISTA
    assert "carga_id_actual" not in context.user_data[correccion._DATA_KEY]


# --- elegir_linea / recibir_cantidad ------------------------------------------


async def test_elegir_linea_malformed_id_ends_conversation():
    update = _make_update(callback_data="lore_cor_linea:not-a-uuid")
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {}}})

    result = await correccion.elegir_linea(update, context)

    assert result == ConversationHandler.END


async def test_elegir_linea_valid_id_moves_to_cantidad():
    update = _make_update(callback_data=f"lore_cor_linea:{_LINEA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {}}})

    result = await correccion.elegir_linea(update, context)

    assert result == CorreccionEstado.CANTIDAD
    assert context.user_data[correccion._DATA_KEY]["linea_id_actual"] == _LINEA_1


async def test_recibir_cantidad_invalid_reprompts():
    update = _make_update(text="0")
    context = _make_context(user_data={correccion._DATA_KEY: {"linea_id_actual": _LINEA_1}})

    result = await correccion.recibir_cantidad(update, context)

    assert result == CorreccionEstado.CANTIDAD


async def test_recibir_cantidad_missing_linea_id_ends_cleanly_without_building_a_request(monkeypatch):
    """gga finding: every other handler in this module validates an id
    before it reaches URL construction (`_uuid_valido`); this one skipped
    that check — a missing `linea_id_actual` would otherwise send a literal
    '/demanda-perdida/lineas/None' request instead of failing cleanly. The
    guard must return BEFORE `_cliente`/`editar_linea` is ever reached."""
    fake_client = FakeClient()
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))
    update = _make_update(text="7")
    context = _make_context(user_data={correccion._DATA_KEY: {}})

    result = await correccion.recibir_cantidad(update, context)

    assert result == ConversationHandler.END
    fake_client.editar_linea.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()
    assert correccion._DATA_KEY not in context.user_data


async def test_recibir_cantidad_success_ends_and_clears_state(monkeypatch):
    fake_client = FakeClient()
    fake_client.editar_linea.return_value = {"linea_id": _LINEA_1, "cantidad": 7.0}
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="7")
    context = _make_context(user_data={correccion._DATA_KEY: {"linea_id_actual": _LINEA_1}})

    result = await correccion.recibir_cantidad(update, context)

    assert result == ConversationHandler.END
    assert correccion._DATA_KEY not in context.user_data
    fake_client.editar_linea.assert_awaited_once_with(_LINEA_1, 7)
    text = update.message.reply_text.call_args.args[0]
    assert "actualizada a 7" in text.lower()


async def test_recibir_cantidad_linea_no_encontrada_ends_and_clears_state(monkeypatch):
    fake_client = FakeClient()
    fake_client.editar_linea.side_effect = LineaNoEncontrada("nope")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="7")
    context = _make_context(user_data={correccion._DATA_KEY: {"linea_id_actual": _LINEA_1}})

    result = await correccion.recibir_cantidad(update, context)

    assert result == ConversationHandler.END
    assert correccion._DATA_KEY not in context.user_data


async def test_recibir_cantidad_fuera_de_ventana_ends_and_clears_state(monkeypatch):
    fake_client = FakeClient()
    fake_client.editar_linea.side_effect = FueraDeVentana("stale")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="7")
    context = _make_context(user_data={correccion._DATA_KEY: {"linea_id_actual": _LINEA_1}})

    result = await correccion.recibir_cantidad(update, context)

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "no es de hoy" in text.lower()


async def test_recibir_cantidad_linea_anulada_ends_and_clears_state(monkeypatch):
    fake_client = FakeClient()
    fake_client.editar_linea.side_effect = LineaAnulada("gone")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="7")
    context = _make_context(user_data={correccion._DATA_KEY: {"linea_id_actual": _LINEA_1}})

    result = await correccion.recibir_cantidad(update, context)

    assert result == ConversationHandler.END


async def test_recibir_cantidad_backend_caido_keeps_state_for_retry(monkeypatch):
    fake_client = FakeClient()
    fake_client.editar_linea.side_effect = BackendCaido("boom")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="7")
    context = _make_context(user_data={correccion._DATA_KEY: {"linea_id_actual": _LINEA_1}})

    result = await correccion.recibir_cantidad(update, context)

    assert result == CorreccionEstado.CANTIDAD
    assert correccion._DATA_KEY in context.user_data


async def test_recibir_cantidad_unmapped_lore_api_error_keeps_state(monkeypatch):
    fake_client = FakeClient()
    fake_client.editar_linea.side_effect = LoreApiError("unmapped")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="7")
    context = _make_context(user_data={correccion._DATA_KEY: {"linea_id_actual": _LINEA_1}})

    result = await correccion.recibir_cantidad(update, context)

    assert result == CorreccionEstado.CANTIDAD


# --- pedir_confirmacion_anular / resolver_confirmacion_anular -----------------


async def test_pedir_confirmacion_anular_malformed_id_ends_conversation():
    update = _make_update(callback_data="lore_cor_anular:not-a-uuid")
    context = _make_context(user_data={correccion._DATA_KEY: {}})

    result = await correccion.pedir_confirmacion_anular(update, context)

    assert result == ConversationHandler.END


async def test_pedir_confirmacion_anular_valid_id_moves_to_confirmar():
    update = _make_update(callback_data=f"lore_cor_anular:{_CARGA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {}})

    result = await correccion.pedir_confirmacion_anular(update, context)

    assert result == CorreccionEstado.CONFIRMAR_ANULAR


async def test_resolver_confirmacion_anular_cancelar_ends_without_calling_backend(monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data="lore_cor_anular_cancelar")
    context = _make_context(user_data={correccion._DATA_KEY: {"carga_id_actual": _CARGA_1}})

    result = await correccion.resolver_confirmacion_anular(update, context)

    assert result == ConversationHandler.END
    fake_client.anular_registro.assert_not_awaited()


async def test_resolver_confirmacion_anular_success_ends_and_clears_state(monkeypatch):
    fake_client = FakeClient()
    fake_client.anular_registro.return_value = {"carga_id": _CARGA_1, "estado": "ANULADO"}
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_cor_anular_confirmar:{_CARGA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {"carga_id_actual": _CARGA_1}})

    result = await correccion.resolver_confirmacion_anular(update, context)

    assert result == ConversationHandler.END
    assert correccion._DATA_KEY not in context.user_data
    fake_client.anular_registro.assert_awaited_once_with(_CARGA_1)
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert text == "✅ Registro anulado."


async def test_resolver_confirmacion_anular_carga_no_encontrada_ends_and_clears(monkeypatch):
    fake_client = FakeClient()
    fake_client.anular_registro.side_effect = CargaNoEncontrada("nope")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_cor_anular_confirmar:{_CARGA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {"carga_id_actual": _CARGA_1}})

    result = await correccion.resolver_confirmacion_anular(update, context)

    assert result == ConversationHandler.END


async def test_resolver_confirmacion_anular_fuera_de_ventana_ends_and_clears(monkeypatch):
    fake_client = FakeClient()
    fake_client.anular_registro.side_effect = FueraDeVentana("stale")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_cor_anular_confirmar:{_CARGA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {"carga_id_actual": _CARGA_1}})

    result = await correccion.resolver_confirmacion_anular(update, context)

    assert result == ConversationHandler.END
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "no es de hoy" in text.lower()


async def test_resolver_confirmacion_anular_ya_anulada_ends_and_clears(monkeypatch):
    fake_client = FakeClient()
    fake_client.anular_registro.side_effect = YaAnulada("gone")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_cor_anular_confirmar:{_CARGA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {"carga_id_actual": _CARGA_1}})

    result = await correccion.resolver_confirmacion_anular(update, context)

    assert result == ConversationHandler.END
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "ya estaba anulado" in text.lower()


async def test_resolver_confirmacion_anular_backend_caido_keeps_state(monkeypatch):
    fake_client = FakeClient()
    fake_client.anular_registro.side_effect = BackendCaido("boom")
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data=f"lore_cor_anular_confirmar:{_CARGA_1}")
    context = _make_context(user_data={correccion._DATA_KEY: {"carga_id_actual": _CARGA_1}})

    result = await correccion.resolver_confirmacion_anular(update, context)

    assert result == CorreccionEstado.CONFIRMAR_ANULAR
    assert correccion._DATA_KEY in context.user_data


async def test_resolver_confirmacion_anular_malformed_id_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr(correccion, "_cliente", _fake_cliente(fake_client))

    update = _make_update(callback_data="lore_cor_anular_confirmar:not-a-uuid")
    context = _make_context(user_data={correccion._DATA_KEY: {"carga_id_actual": _CARGA_1}})

    result = await correccion.resolver_confirmacion_anular(update, context)

    assert result == ConversationHandler.END
    fake_client.anular_registro.assert_not_awaited()


# --- cancelar ------------------------------------------------------------------


async def test_cancelar_clears_state():
    update = _make_update()
    context = _make_context(user_data={correccion._DATA_KEY: {"cargas": {}}})

    result = await correccion.cancelar(update, context)

    assert result == ConversationHandler.END
    assert correccion._DATA_KEY not in context.user_data
