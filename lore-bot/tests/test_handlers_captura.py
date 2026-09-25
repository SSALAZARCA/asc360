"""Unit tests for `lore.handlers.captura` — the manual lost-sale capture
conversation (Method A only). Same pattern as `test_handlers_registro.py`:
`_cliente` is monkeypatched to a `FakeClient` test double, no real HTTP.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

from telegram.ext import ConversationHandler

from lore.api import (
    BackendCaido,
    IdempotencyKeyEnUso,
    LoreApiError,
    NoRegistrado,
    Pendiente,
    Rechazado,
    ReferenciaNoEncontrada,
    RegistroInconsistente,
    SucursalNoAutorizada,
    SucursalNoEncontrada,
)
from lore.estados import CapturaEstado
from lore.handlers import captura


class FakeClient:
    def __init__(self):
        self.yo = AsyncMock()
        self.sucursales = AsyncMock()
        self.resolver_referencias = AsyncMock()
        self.registrar_demanda_perdida = AsyncMock()

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
        update.callback_query.edit_message_reply_markup = AsyncMock()
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


# --- iniciar ---------------------------------------------------------------


async def test_iniciar_no_registrado_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.side_effect = NoRegistrado("nope")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    result = await captura.iniciar(_make_update(), _make_context())

    assert result == ConversationHandler.END


async def test_iniciar_pendiente_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.side_effect = Pendiente("pending")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await captura.iniciar(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "pendiente" in text.lower()


async def test_iniciar_rechazado_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.side_effect = Rechazado("rejected")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await captura.iniciar(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "rechazada" in text.lower()


async def test_iniciar_backend_caido_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.side_effect = BackendCaido("boom")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    result = await captura.iniciar(_make_update(), _make_context())

    assert result == ConversationHandler.END


async def test_iniciar_unmapped_lore_api_error_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.side_effect = LoreApiError("unmapped")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    result = await captura.iniciar(_make_update(), _make_context())

    assert result == ConversationHandler.END


async def test_iniciar_no_sucursales_asignadas_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"sucursales": []}
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await captura.iniciar(update, _make_context())

    assert result == ConversationHandler.END
    text = update.message.reply_text.call_args.args[0]
    assert "sucursal" in text.lower()


_S1 = "11111111-1111-1111-1111-111111111111"
_S2 = "22222222-2222-2222-2222-222222222222"
_S3 = "33333333-3333-3333-3333-333333333333"


async def test_iniciar_single_sucursal_skips_picker_and_asks_metodo(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"sucursales": [_S1]}
    fake_client.sucursales.return_value = [{"id": _S1, "nombre": "Bogotá"}]
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context()
    result = await captura.iniciar(update, context)

    assert result == CapturaEstado.METODO
    assert str(context.user_data[captura._DRAFT_KEY].sucursal_id) == _S1


async def test_iniciar_multiple_sucursales_shows_picker(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"sucursales": [_S1, _S2]}
    fake_client.sucursales.return_value = [
        {"id": _S1, "nombre": "Bogotá"},
        {"id": _S2, "nombre": "Medellín"},
        {"id": _S3, "nombre": "Cali"},  # not one of the actor's own — must be filtered out
    ]
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context()
    result = await captura.iniciar(update, context)

    assert result == CapturaEstado.SUCURSAL
    assert set(context.user_data[captura._SUCURSALES_KEY].keys()) == {_S1, _S2}


async def test_iniciar_own_sucursal_not_in_active_list_ends_conversation(monkeypatch):
    # actor.sucursal_ids references a branch that GET /sucursales no longer
    # returns (e.g. deactivated) — must not crash or fabricate a picker.
    fake_client = FakeClient()
    fake_client.yo.return_value = {"sucursales": [_S3]}
    fake_client.sucursales.return_value = [{"id": _S1, "nombre": "Bogotá"}]
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    result = await captura.iniciar(_make_update(), _make_context())

    assert result == ConversationHandler.END


# --- iniciar (ADMIN) --------------------------------------------------------
# Ad-hoc addition (post-Phase-10, product-owner request, NOT a numbered SDD
# task): an ADMIN has no `usuario_sucursal` rows of its own -- `/yo`'s own
# `sucursales` field is always empty for that role. Branches on `/yo`'s own
# `role` field instead of the (always-empty) `sucursales` field.


async def test_iniciar_admin_with_no_sucursales_shows_full_picker_not_error(monkeypatch):
    """The old ASESOR_MOSTRADOR-only path would dead-end here with "no tenés
    ninguna sucursal asignada" -- wrong for an ADMIN, who never has any
    `usuario_sucursal` row by design, not by misconfiguration."""
    fake_client = FakeClient()
    fake_client.yo.return_value = {"sucursales": [], "role": "ADMIN"}
    fake_client.sucursales.return_value = [
        {"id": _S1, "nombre": "Bogotá"},
        {"id": _S2, "nombre": "Medellín"},
    ]
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context()
    result = await captura.iniciar(update, context)

    assert result == CapturaEstado.SUCURSAL
    assert set(context.user_data[captura._SUCURSALES_KEY].keys()) == {_S1, _S2}


async def test_iniciar_admin_single_active_sucursal_still_shows_picker_no_auto_select(monkeypatch):
    """For an ASESOR_MOSTRADOR, exactly-one-assigned-sucursal auto-selects
    (no real choice to make). For an ADMIN, picking WHICH sucursal to charge
    is the whole point of asking -- auto-select must NOT apply even if only
    one sucursal happens to be active system-wide."""
    fake_client = FakeClient()
    fake_client.yo.return_value = {"sucursales": [], "role": "ADMIN"}
    fake_client.sucursales.return_value = [{"id": _S1, "nombre": "Bogotá"}]
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context()
    result = await captura.iniciar(update, context)

    assert result == CapturaEstado.SUCURSAL
    assert set(context.user_data[captura._SUCURSALES_KEY].keys()) == {_S1}


async def test_iniciar_admin_no_active_sucursales_ends_conversation(monkeypatch):
    fake_client = FakeClient()
    fake_client.yo.return_value = {"sucursales": [], "role": "ADMIN"}
    fake_client.sucursales.return_value = []
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    result = await captura.iniciar(update, _make_context())

    assert result == ConversationHandler.END


async def test_iniciar_asesor_behavior_unchanged_when_role_present(monkeypatch):
    """Regression proof: adding the ADMIN branch must not disturb the
    ASESOR_MOSTRADOR path even when `/yo` now also returns an explicit
    `role` field (it always did in production; only these unit tests'
    fixtures omitted it before this change)."""
    fake_client = FakeClient()
    fake_client.yo.return_value = {"sucursales": [_S1], "role": "ASESOR_MOSTRADOR"}
    fake_client.sucursales.return_value = [{"id": _S1, "nombre": "Bogotá"}]
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update()
    context = _make_context()
    result = await captura.iniciar(update, context)

    assert result == CapturaEstado.METODO
    assert str(context.user_data[captura._DRAFT_KEY].sucursal_id) == _S1


# --- _obtener_sucursales_propias / _obtener_sucursales_todas ---------------
# Approval tests for CURRENT behavior (Fix-up finding #4, pre-refactor
# safety net): neither helper had direct coverage of its `client.sucursales()`
# BackendCaido/LoreApiError branches before extracting the shared
# `_fetch_sucursales_o_avisar` helper — written here BEFORE the refactor so
# it must still pass, unchanged, AFTER it.


async def test_obtener_sucursales_propias_backend_caido_shows_conexion_message(monkeypatch):
    fake_client = FakeClient()
    fake_client.sucursales.side_effect = BackendCaido("boom")
    update = _make_update()

    result = await captura._obtener_sucursales_propias(fake_client, update, {_S1})

    assert result is None
    text = update.message.reply_text.call_args.args[0]
    assert "problema" in text.lower()


async def test_obtener_sucursales_propias_lore_api_error_shows_conexion_message(monkeypatch):
    fake_client = FakeClient()
    fake_client.sucursales.side_effect = LoreApiError("unmapped")
    update = _make_update()

    result = await captura._obtener_sucursales_propias(fake_client, update, {_S1})

    assert result is None
    text = update.message.reply_text.call_args.args[0]
    assert "problema" in text.lower()


async def test_obtener_sucursales_todas_backend_caido_shows_conexion_message(monkeypatch):
    fake_client = FakeClient()
    fake_client.sucursales.side_effect = BackendCaido("boom")
    update = _make_update()

    result = await captura._obtener_sucursales_todas(fake_client, update)

    assert result is None
    text = update.message.reply_text.call_args.args[0]
    assert "problema" in text.lower()


async def test_obtener_sucursales_todas_lore_api_error_shows_conexion_message(monkeypatch):
    fake_client = FakeClient()
    fake_client.sucursales.side_effect = LoreApiError("unmapped")
    update = _make_update()

    result = await captura._obtener_sucursales_todas(fake_client, update)

    assert result is None
    text = update.message.reply_text.call_args.args[0]
    assert "problema" in text.lower()


# --- recibir_sucursal / recibir_metodo --------------------------------------


async def test_recibir_sucursal_unknown_id_ends_conversation():
    update = _make_update(callback_data="lore_cap_suc:stale")
    context = _make_context(user_data={captura._SUCURSALES_KEY: {_S1: "Bogotá"}})

    result = await captura.recibir_sucursal(update, context)

    assert result == ConversationHandler.END


async def test_recibir_sucursal_known_id_moves_to_metodo():
    update = _make_update(callback_data=f"lore_cap_suc:{_S1}")
    context = _make_context(
        user_data={
            captura._DRAFT_KEY: captura.Borrador(),
            captura._SUCURSALES_KEY: {_S1: "Bogotá"},
        }
    )

    result = await captura.recibir_sucursal(update, context)

    assert result == CapturaEstado.METODO


async def test_recibir_metodo_sets_manual_and_moves_to_manual_state():
    update = _make_update(callback_data="lore_cap_metodo:MANUAL")
    context = _make_context(user_data={captura._DRAFT_KEY: captura.Borrador()})

    result = await captura.recibir_metodo(update, context)

    assert result == CapturaEstado.MANUAL
    assert context.user_data[captura._DRAFT_KEY].metodo == "MANUAL"


# --- recibir_codigos ---------------------------------------------------------


_R1 = "44444444-4444-4444-4444-444444444444"


async def test_recibir_codigos_all_resolved_moves_to_seleccion(monkeypatch):
    fake_client = FakeClient()
    fake_client.resolver_referencias.return_value = {
        "resueltas": [{"entrada": "ABC", "referencia_id": _R1, "codigo": "ABC", "nombre": "Filtro"}],
        "no_resueltas": [],
    }
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="ABC")
    context = _make_context(user_data={captura._DRAFT_KEY: captura.Borrador()})

    result = await captura.recibir_codigos(update, context)

    assert result == CapturaEstado.SELECCION
    draft = context.user_data[captura._DRAFT_KEY]
    assert len(draft.lineas) == 1
    assert draft.lineas[0].codigo == "ABC"
    assert draft.lineas[0].seleccionada is False  # spec: toggles start OFF


async def test_recibir_codigos_splits_comma_and_newline():
    codigos, descartados = captura._parsear_codigos("ABC, DEF\nGHI")
    assert codigos == ["ABC", "DEF", "GHI"]
    assert descartados == 0


async def test_recibir_codigos_dedupes_case_insensitively():
    codigos, descartados = captura._parsear_codigos("abc\nABC\nAbc")
    assert codigos == ["abc"]
    assert descartados == 0


async def test_parsear_codigos_over_cap_reports_how_many_were_dropped():
    """Phase 10 fix-up finding #4: codes beyond the 30-per-message cap used
    to be dropped with zero signal to the advisor."""
    texto = ",".join(f"COD{i}" for i in range(35))
    codigos, descartados = captura._parsear_codigos(texto)
    assert len(codigos) == captura._MAX_CODIGOS_POR_LOTE
    assert descartados == 5


async def test_recibir_codigos_with_over_30_codes_warns_about_truncation(monkeypatch):
    fake_client = FakeClient()
    codigos_enviados = [f"COD{i}" for i in range(35)]
    resueltas = [
        {
            "entrada": codigo,
            "referencia_id": str(uuid.uuid4()),
            "codigo": codigo,
            "nombre": None,
        }
        for codigo in codigos_enviados[:30]
    ]
    fake_client.resolver_referencias.return_value = {"resueltas": resueltas, "no_resueltas": []}
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text=",".join(codigos_enviados))
    context = _make_context(user_data={captura._DRAFT_KEY: captura.Borrador()})

    result = await captura.recibir_codigos(update, context)

    assert result == CapturaEstado.SELECCION
    mensajes = [call.args[0] for call in update.message.reply_text.call_args_list]
    assert any("ignoraron 5 código" in m.lower() for m in mensajes)


async def test_recibir_codigos_with_unresolved_shows_no_resueltas(monkeypatch):
    fake_client = FakeClient()
    fake_client.resolver_referencias.return_value = {
        "resueltas": [],
        "no_resueltas": ["ZZZ"],
    }
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="ZZZ")
    context = _make_context(user_data={captura._DRAFT_KEY: captura.Borrador()})

    result = await captura.recibir_codigos(update, context)

    assert result == CapturaEstado.NO_RESUELTAS
    text = update.message.reply_text.call_args.args[0]
    assert "ZZZ" in text
    assert "no encontré" in text.lower()


async def test_recibir_codigos_empty_input_reprompts():
    update = _make_update(text="   ")
    context = _make_context(user_data={captura._DRAFT_KEY: captura.Borrador()})

    result = await captura.recibir_codigos(update, context)

    assert result == CapturaEstado.MANUAL


async def test_recibir_codigos_backend_caido_keeps_draft(monkeypatch):
    fake_client = FakeClient()
    fake_client.resolver_referencias.side_effect = BackendCaido("boom")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    update = _make_update(text="ABC")
    context = _make_context(user_data={captura._DRAFT_KEY: captura.Borrador()})

    result = await captura.recibir_codigos(update, context)

    assert result == CapturaEstado.MANUAL
    assert captura._DRAFT_KEY in context.user_data


# --- recibir_correccion_no_resueltas -----------------------------------------


async def test_recibir_correccion_no_resueltas_with_over_30_codes_warns_about_truncation(monkeypatch):
    fake_client = FakeClient()
    codigos_enviados = [f"COD{i}" for i in range(35)]
    resueltas = [
        {
            "entrada": codigo,
            "referencia_id": str(uuid.uuid4()),
            "codigo": codigo,
            "nombre": None,
        }
        for codigo in codigos_enviados[:30]
    ]
    fake_client.resolver_referencias.return_value = {"resueltas": resueltas, "no_resueltas": []}
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = captura.Borrador()
    draft.no_resueltas = list(codigos_enviados)
    update = _make_update(text=",".join(codigos_enviados))
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.recibir_correccion_no_resueltas(update, context)

    # The 5 dropped-by-the-cap codes are never sent to the resolver, so they
    # correctly remain in `no_resueltas` (never silently lost) — the flow
    # stays in NO_RESUELTAS to surface them, same as any other unresolved code.
    assert result == CapturaEstado.NO_RESUELTAS
    mensajes = [call.args[0] for call in update.message.reply_text.call_args_list]
    assert any("ignoraron 5 código" in m.lower() for m in mensajes)


# --- descartar_no_resuelta ---------------------------------------------------


async def test_descartar_no_resuelta_removes_entry_and_returns_to_manual_when_empty():
    draft = captura.Borrador()
    draft.no_resueltas = ["ZZZ"]
    update = _make_update(callback_data=f"lore_cap_descartar:{captura._clave_descarte('ZZZ')}")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.descartar_no_resuelta(update, context)

    assert result == CapturaEstado.MANUAL
    assert draft.no_resueltas == []


async def test_descartar_no_resuelta_removes_entry_and_moves_to_seleccion_when_lineas_exist():
    draft = captura.Borrador()
    draft.no_resueltas = ["ZZZ"]
    draft.lineas.append(
        captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC", nombre="Filtro")
    )
    update = _make_update(callback_data=f"lore_cap_descartar:{captura._clave_descarte('ZZZ')}")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.descartar_no_resuelta(update, context)

    assert result == CapturaEstado.SELECCION


async def test_descartar_no_resuelta_stale_key_redisplays_list():
    """A malformed or no-longer-matching key (stale/duplicate tap) must never
    guess — it must redisplay the current list untouched.

    gga finding: Telegram allows only ONE `answer()` per callback query, and
    rejects an `edit_message_text` whose content/keyboard is unchanged with
    `BadRequest: message is not modified` — this stale-key path must answer
    exactly once and must NOT re-edit the message (content is identical)."""
    draft = captura.Borrador()
    draft.no_resueltas = ["ZZZ"]
    update = _make_update(callback_data="lore_cap_descartar:deadbeefdeadbeef")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.descartar_no_resuelta(update, context)

    assert result == CapturaEstado.NO_RESUELTAS
    assert draft.no_resueltas == ["ZZZ"]  # untouched
    update.callback_query.answer.assert_awaited_once()
    update.callback_query.edit_message_text.assert_not_awaited()


async def test_descartar_no_resuelta_multi_entry_removes_correct_middle_entry_by_value_not_position():
    """Phase 10 fix-up finding #2: keying by raw list position breaks under a
    double-tap/stale button once the list has already shrunk — key by the
    CODE's stable hash instead (mirrors `alternar_seleccion`'s `referencia_id`
    keying), immune to reordering."""
    draft = captura.Borrador()
    draft.no_resueltas = ["AAA", "BBB", "CCC"]
    update = _make_update(callback_data=f"lore_cap_descartar:{captura._clave_descarte('BBB')}")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.descartar_no_resuelta(update, context)

    assert result == CapturaEstado.NO_RESUELTAS
    assert draft.no_resueltas == ["AAA", "CCC"]


async def test_descartar_no_resuelta_stale_tap_on_already_discarded_code_never_drops_a_different_entry():
    """A stale/duplicate tap for a code that a PRIOR tap already discarded
    (list already shrunk) must redisplay the current list, never silently
    discard a different, unintended entry."""
    draft = captura.Borrador()
    draft.no_resueltas = ["AAA", "CCC"]  # "BBB" was already discarded earlier
    update = _make_update(callback_data=f"lore_cap_descartar:{captura._clave_descarte('BBB')}")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.descartar_no_resuelta(update, context)

    assert result == CapturaEstado.NO_RESUELTAS
    assert draft.no_resueltas == ["AAA", "CCC"]  # untouched — nothing else silently dropped


# --- alternar_seleccion / continuar_seleccion -------------------------------


async def test_alternar_seleccion_toggles_on_then_off():
    referencia_id = uuid.uuid4()
    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=referencia_id, codigo="ABC"))
    update = _make_update(callback_data=f"lore_cap_toggle:{referencia_id}")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    await captura.alternar_seleccion(update, context)
    assert draft.lineas[0].seleccionada is True

    await captura.alternar_seleccion(update, context)
    assert draft.lineas[0].seleccionada is False


async def test_alternar_seleccion_with_multiple_lines_only_affects_the_toggled_one():
    """Phase 10 fix-up finding #11(b): toggling one entry among 3+ must never
    affect the others' selection state."""

    ref1, ref2, ref3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=ref1, codigo="AAA"))
    draft.lineas.append(captura.LineaBorrador(referencia_id=ref2, codigo="BBB"))
    draft.lineas.append(captura.LineaBorrador(referencia_id=ref3, codigo="CCC"))
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    update = _make_update(callback_data=f"lore_cap_toggle:{ref2}")
    await captura.alternar_seleccion(update, context)

    assert draft.lineas[0].seleccionada is False
    assert draft.lineas[1].seleccionada is True
    assert draft.lineas[2].seleccionada is False

    # toggling ref2 again flips ONLY ref2 back off, still leaving ref1/ref3 untouched
    await captura.alternar_seleccion(update, context)
    assert draft.lineas[0].seleccionada is False
    assert draft.lineas[1].seleccionada is False
    assert draft.lineas[2].seleccionada is False


async def test_alternar_seleccion_unknown_referencia_id_does_not_reedit_or_answer_twice():
    """gga finding: when nothing changed (unknown/stale referencia_id), a
    second `edit_message_reply_markup` call with the SAME keyboard raises
    `BadRequest: message is not modified`, and `answer()` (already sent
    unconditionally at the top of the function) must never be called again."""
    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC"))
    update = _make_update(callback_data=f"lore_cap_toggle:{__import__('uuid').uuid4()}")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.alternar_seleccion(update, context)

    assert result == CapturaEstado.SELECCION
    assert draft.lineas[0].seleccionada is False  # untouched
    update.callback_query.answer.assert_awaited_once()
    update.callback_query.edit_message_reply_markup.assert_not_awaited()


async def test_continuar_seleccion_blocks_commit_with_nothing_selected():
    """gga finding: Telegram allows only ONE `answer()` per callback query --
    this path must answer exactly once (with the alert), never an empty
    `answer()` first followed by a second alert `answer()`."""
    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC"))
    update = _make_update(callback_data="lore_cap_continuar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.continuar_seleccion(update, context)

    assert result == CapturaEstado.SELECCION
    assert draft.lineas[0].cantidad is None
    update.callback_query.answer.assert_awaited_once()
    _, kwargs = update.callback_query.answer.call_args
    assert kwargs.get("show_alert") is True


async def test_continuar_seleccion_moves_to_cantidad_when_selected():
    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC"))
    draft.lineas[0].seleccionada = True
    update = _make_update(callback_data="lore_cap_continuar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.continuar_seleccion(update, context)

    assert result == CapturaEstado.CANTIDAD
    _, kwargs = update.callback_query.edit_message_text.call_args
    assert kwargs.get("parse_mode") == "Markdown"  # fix #12: consistent with recibir_cantidad's later prompts


# --- recibir_cantidad ---------------------------------------------------------


async def test_recibir_cantidad_invalid_reprompts():
    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC"))
    draft.lineas[0].seleccionada = True
    update = _make_update(text="0")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.recibir_cantidad(update, context)

    assert result == CapturaEstado.CANTIDAD
    assert draft.lineas[0].cantidad is None


async def test_recibir_cantidad_boundary_9999_accepted():
    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC"))
    draft.lineas[0].seleccionada = True
    update = _make_update(text="9999")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.recibir_cantidad(update, context)

    assert result == CapturaEstado.CONFIRMAR
    assert draft.lineas[0].cantidad == 9999


async def test_recibir_cantidad_boundary_10000_rejected():
    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC"))
    draft.lineas[0].seleccionada = True
    update = _make_update(text="10000")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.recibir_cantidad(update, context)

    assert result == CapturaEstado.CANTIDAD


async def test_recibir_cantidad_asks_next_pending_line_before_confirming():

    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC"))
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="DEF"))
    draft.lineas[0].seleccionada = True
    draft.lineas[1].seleccionada = True
    update = _make_update(text="5")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.recibir_cantidad(update, context)

    assert result == CapturaEstado.CANTIDAD
    assert draft.lineas[0].cantidad == 5
    assert draft.lineas[1].cantidad is None
    text = update.message.reply_text.call_args.args[0]
    assert "DEF" in text


async def test_cap_seleccion_to_cap_cantidad_walks_3_selected_references_in_order():
    """Phase 10 fix-up finding #11(a): 3 selected references walked through 3
    sequential quantity prompts — each prompt must show the CORRECT
    reference's code, never a skipped/repeated/wrong one."""

    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="AAA"))
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="BBB"))
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="CCC"))
    for linea in draft.lineas:
        linea.seleccionada = True
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    # CAP_SELECCION -> CAP_CANTIDAD: first prompt must be for AAA (first pending).
    update_continuar = _make_update(callback_data="lore_cap_continuar")
    result = await captura.continuar_seleccion(update_continuar, context)
    assert result == CapturaEstado.CANTIDAD
    primer_texto = update_continuar.callback_query.edit_message_text.call_args.args[0]
    assert "AAA" in primer_texto
    assert "BBB" not in primer_texto
    assert "CCC" not in primer_texto

    # Answer AAA -> next prompt must be BBB, not CCC or a repeat of AAA.
    update_1 = _make_update(text="5")
    result = await captura.recibir_cantidad(update_1, context)
    assert result == CapturaEstado.CANTIDAD
    assert draft.lineas[0].cantidad == 5
    segundo_texto = update_1.message.reply_text.call_args.args[0]
    assert "BBB" in segundo_texto
    assert "AAA" not in segundo_texto
    assert "CCC" not in segundo_texto

    # Answer BBB -> next prompt must be CCC.
    update_2 = _make_update(text="7")
    result = await captura.recibir_cantidad(update_2, context)
    assert result == CapturaEstado.CANTIDAD
    assert draft.lineas[1].cantidad == 7
    tercer_texto = update_2.message.reply_text.call_args.args[0]
    assert "CCC" in tercer_texto
    assert "AAA" not in tercer_texto
    assert "BBB" not in tercer_texto

    # Answer CCC -> nothing left pending, moves to CONFIRMAR.
    update_3 = _make_update(text="9")
    result = await captura.recibir_cantidad(update_3, context)
    assert result == CapturaEstado.CONFIRMAR
    assert draft.lineas[2].cantidad == 9


async def test_commit_is_blocked_until_every_selected_reference_has_a_quantity():
    """Spec: 'commit MUST be blocked until a quantity has been provided for
    each one'. Proven end-to-end: 2 selected lines, only 1 answered — the
    state machine must still be in CANTIDAD, never CONFIRMAR."""

    draft = captura.Borrador()
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC"))
    draft.lineas.append(captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="DEF"))
    draft.lineas[0].seleccionada = True
    draft.lineas[1].seleccionada = True
    update = _make_update(text="5")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.recibir_cantidad(update, context)

    assert result != CapturaEstado.CONFIRMAR


# --- confirmar ---------------------------------------------------------------


def _draft_listo():

    draft = captura.Borrador()
    draft.sucursal_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    draft.metodo = "MANUAL"
    linea = captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC", nombre="Filtro")
    linea.seleccionada = True
    linea.cantidad = 3
    draft.lineas.append(linea)
    return draft


async def test_confirmar_cancelar_clears_draft_and_ends():
    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_cancelar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data


async def test_confirmar_success_sends_idempotency_key_equal_to_registro_id(monkeypatch):
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.return_value = {"carga_id": "c1"}
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data
    _, kwargs = fake_client.registrar_demanda_perdida.call_args
    assert kwargs["idempotency_key"] == str(draft.registro_id)
    assert kwargs["sucursal_id"] == str(draft.sucursal_id)
    assert kwargs["metodo"] == "MANUAL"
    assert kwargs["lineas"] == [{"referencia_id": str(draft.lineas[0].referencia_id), "cantidad": 3}]


async def test_confirmar_only_sends_selected_lines(monkeypatch):

    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.return_value = {"carga_id": "c1"}
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    no_seleccionada = captura.LineaBorrador(referencia_id=uuid.uuid4(), codigo="XYZ")
    no_seleccionada.seleccionada = False  # never toggled ON — must be excluded from the payload
    draft.lineas.append(no_seleccionada)
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    await captura.confirmar(update, context)

    _, kwargs = fake_client.registrar_demanda_perdida.call_args
    assert len(kwargs["lineas"]) == 1
    assert kwargs["lineas"][0]["referencia_id"] == str(draft.lineas[0].referencia_id)


async def test_confirmar_sucursal_no_autorizada_ends_and_clears_draft(monkeypatch):
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.side_effect = SucursalNoAutorizada("nope")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "sucursal ya no está autorizada" in text.lower()


async def test_confirmar_referencia_no_encontrada_ends_and_clears_draft(monkeypatch):
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.side_effect = ReferenciaNoEncontrada("nope")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data


async def test_confirmar_sucursal_no_encontrada_ends_and_clears_draft(monkeypatch):
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.side_effect = SucursalNoEncontrada("nope")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data


async def test_confirmar_idempotency_key_en_uso_ends_and_clears_draft(monkeypatch):
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.side_effect = IdempotencyKeyEnUso("dup")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data


async def test_confirmar_registro_inconsistente_ends_and_clears_draft(monkeypatch):
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.side_effect = RegistroInconsistente("weird")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data


async def test_confirmar_backend_caido_stays_in_confirmar_and_keeps_draft_for_retry(monkeypatch):
    """Phase 10 fix-up finding #1 (CRITICAL): ending the conversation here
    used to force any retry through a fresh /registrar, minting a NEW
    Idempotency-Key and losing the backend's own idempotent-replay safety
    net. Must stay in CONFIRMAR against the SAME draft instead."""
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.side_effect = BackendCaido("boom")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == CapturaEstado.CONFIRMAR
    assert captura._DRAFT_KEY in context.user_data
    assert context.user_data[captura._DRAFT_KEY] is draft
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "confirmar de nuevo" in text.lower() or "confirmar" in text.lower()


async def test_confirmar_unmapped_lore_api_error_stays_in_confirmar_for_retry(monkeypatch):
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.side_effect = LoreApiError("unmapped")
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    result = await captura.confirmar(update, context)

    assert result == CapturaEstado.CONFIRMAR
    assert captura._DRAFT_KEY in context.user_data
    assert context.user_data[captura._DRAFT_KEY] is draft


async def test_confirmar_retry_after_backend_caido_reuses_same_idempotency_key(monkeypatch):
    """Phase 10 fix-up finding #1: tapping Confirmar again after a
    BackendCaido must reuse the SAME registro_id/Idempotency-Key (not mint a
    fresh one), letting the backend's own idempotent replay handle a genuine
    duplicate-tap-after-timeout safely."""
    fake_client = FakeClient()
    fake_client.registrar_demanda_perdida.side_effect = [BackendCaido("boom"), {"carga_id": "c1"}]
    monkeypatch.setattr(captura, "_cliente", _fake_cliente(fake_client))

    draft = _draft_listo()
    update = _make_update(callback_data="lore_cap_confirmar")
    context = _make_context(user_data={captura._DRAFT_KEY: draft})

    primer_resultado = await captura.confirmar(update, context)
    assert primer_resultado == CapturaEstado.CONFIRMAR
    assert context.user_data[captura._DRAFT_KEY] is draft  # draft not cleared

    segundo_resultado = await captura.confirmar(update, context)
    assert segundo_resultado == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data

    llamadas = fake_client.registrar_demanda_perdida.call_args_list
    assert len(llamadas) == 2
    primera_key = llamadas[0].kwargs["idempotency_key"]
    segunda_key = llamadas[1].kwargs["idempotency_key"]
    assert primera_key == segunda_key == str(draft.registro_id)
