"""Unit tests for `lore.handlers._common` — shared helpers/constants used by
every handler module.

Phase 10 fix-up finding #6: the quantity-validation logic (`_CANTIDAD_MINIMA`,
`_CANTIDAD_MAXIMA`, and the `isdigit()`+bounds check) used to be duplicated
byte-for-byte between `captura.py::recibir_cantidad` and
`correccion.py::recibir_cantidad`. Hoisted here so a future bounds change
only needs to happen in one place.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from lore.handlers._common import (
    _CANTIDAD_MAXIMA,
    _CANTIDAD_MINIMA,
    BOTON_CORRECCIONES,
    BOTON_PENDIENTES,
    BOTON_REGISTRAR,
    CALLBACK_CANCELAR,
    TECLADO_ADMIN,
    TECLADO_CAPTURA,
    _validar_cantidad,
    boton_cancelar,
    con_cancelar,
    editar_o_ignorar_sin_cambios,
    nada_para_cancelar,
    responder_cancelacion,
    teclado_para_rol,
    teclado_resolver_solicitud,
    teclado_solo_cancelar,
)


def test_validar_cantidad_accepts_minimum_boundary():
    assert _validar_cantidad("1") == 1
    assert _CANTIDAD_MINIMA == 1


def test_validar_cantidad_accepts_maximum_boundary():
    assert _validar_cantidad("9999") == 9999
    assert _CANTIDAD_MAXIMA == 9999


def test_validar_cantidad_rejects_zero():
    assert _validar_cantidad("0") is None


def test_validar_cantidad_rejects_above_maximum():
    assert _validar_cantidad("10000") is None


def test_validar_cantidad_rejects_non_digit_text():
    assert _validar_cantidad("abc") is None
    assert _validar_cantidad("") is None
    assert _validar_cantidad("-5") is None


# --- Cancel button (lore-boton-cancelar T1) -----------------------------------


def test_boton_cancelar_uses_shared_callback_data():
    boton = boton_cancelar()
    assert boton.text == "✖️ Cancelar"
    assert boton.callback_data == CALLBACK_CANCELAR == "lore_cancelar"


def test_teclado_solo_cancelar_has_only_the_cancel_row():
    kb = teclado_solo_cancelar()
    assert [[b.callback_data for b in fila] for fila in kb.inline_keyboard] == [["lore_cancelar"]]


def test_con_cancelar_appends_cancel_as_last_row_of_a_markup():
    original = InlineKeyboardMarkup([[InlineKeyboardButton("A", callback_data="lore_x:1")]])
    kb = con_cancelar(original)
    datos = [[b.callback_data for b in fila] for fila in kb.inline_keyboard]
    assert datos == [["lore_x:1"], ["lore_cancelar"]]


def test_con_cancelar_accepts_a_list_of_rows():
    kb = con_cancelar([[InlineKeyboardButton("A", callback_data="lore_x:1")]])
    assert kb.inline_keyboard[-1][0].callback_data == "lore_cancelar"


def _callback_update(data="lore_cancelar"):
    update = MagicMock()
    update.message = None
    update.callback_query = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update


def _command_update():
    update = MagicMock()
    update.callback_query = None
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


async def test_responder_cancelacion_on_callback_answers_and_edits_without_keyboard():
    update = _callback_update()
    await responder_cancelacion(update, "Cancelado.")
    update.callback_query.answer.assert_awaited_once()
    update.callback_query.edit_message_text.assert_awaited_once_with("Cancelado.")


async def test_responder_cancelacion_on_command_replies():
    update = _command_update()
    await responder_cancelacion(update, "Cancelado.")
    update.message.reply_text.assert_awaited_once_with("Cancelado.")


async def test_nada_para_cancelar_replies_to_command():
    update = _command_update()
    await nada_para_cancelar(update, MagicMock())
    assert update.message.reply_text.call_args.args[0] == "No hay nada para cancelar."


async def test_nada_para_cancelar_answers_stray_callback():
    update = _callback_update()
    await nada_para_cancelar(update, MagicMock())
    update.callback_query.answer.assert_awaited_once()
    assert update.callback_query.edit_message_text.call_args.args[0] == "No hay nada para cancelar."


# --- "Message is not modified" on repeated retry edits -------------------------

_NO_MODIFICADO = (
    "Message is not modified: specified new message content and reply markup are "
    "exactly the same as a current content and reply markup of the message"
)


async def test_editar_o_ignorar_sin_cambios_passes_text_and_kwargs_through():
    query = MagicMock()
    query.edit_message_text = AsyncMock()
    await editar_o_ignorar_sin_cambios(query, "Hola", reply_markup="kb")
    query.edit_message_text.assert_awaited_once_with("Hola", reply_markup="kb")


async def test_editar_o_ignorar_sin_cambios_swallows_not_modified():
    query = MagicMock()
    query.edit_message_text = AsyncMock(side_effect=BadRequest(_NO_MODIFICADO))
    await editar_o_ignorar_sin_cambios(query, "Hola")


async def test_editar_o_ignorar_sin_cambios_reraises_other_bad_requests():
    query = MagicMock()
    query.edit_message_text = AsyncMock(side_effect=BadRequest("Can't parse entities"))
    with pytest.raises(BadRequest):
        await editar_o_ignorar_sin_cambios(query, "Hola")


def _etiquetas(teclado) -> list[str]:
    return [boton.text for fila in teclado.keyboard for boton in fila]


def test_admin_keyboard_has_the_capture_buttons_plus_pending_requests():
    assert _etiquetas(TECLADO_ADMIN) == [BOTON_REGISTRAR, BOTON_CORRECCIONES, BOTON_PENDIENTES]


def test_advisor_keyboard_does_not_offer_pending_requests():
    assert BOTON_PENDIENTES not in _etiquetas(TECLADO_CAPTURA)


def test_teclado_para_rol_depends_on_the_role():
    assert teclado_para_rol("ADMIN") is TECLADO_ADMIN
    assert teclado_para_rol("ASESOR_MOSTRADOR") is TECLADO_CAPTURA
    assert teclado_para_rol("OTRO") is None
    assert teclado_para_rol(None) is None


def test_teclado_resolver_solicitud_has_approve_and_reject_callbacks():
    teclado = teclado_resolver_solicitud("u-1")

    botones = teclado.inline_keyboard[0]
    assert [b.callback_data for b in botones] == ["lore_apr:u-1", "lore_rej:u-1"]
