"""Captura when several advisors share one Telegram: "¿Quién registra?" at the
start of every conversation, the choice kept only in that conversation's
`user_data`, and the chosen usuario sent on every backend call of it."""
from unittest.mock import AsyncMock, MagicMock

from telegram.ext import ConversationHandler

from lore.estados import Borrador, CapturaEstado
from lore.handlers import captura

_S1 = "11111111-1111-1111-1111-111111111111"
_S2 = "22222222-2222-2222-2222-222222222222"
_ANA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_BETO = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


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


def _cliente_registrado(fake_client):
    """Returns `(factory, llamadas)`; `llamadas` records `(telegram_id, usuario_id)`."""
    llamadas = []

    def fabrica(telegram_id, usuario_id=None):
        llamadas.append((telegram_id, usuario_id))
        return fake_client

    return fabrica, llamadas


def _asesor(id, nombre, sucursales, status="approved", activo=True):
    return {
        "id": id, "nombre": nombre, "role": "ASESOR_MOSTRADOR", "status": status,
        "activo": activo, "sucursales": sucursales,
    }


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


def _preparar(monkeypatch, yo, sucursales=None):
    fake = FakeClient()
    fake.yo.return_value = yo
    fake.sucursales.return_value = sucursales or [
        {"id": _S1, "nombre": "Bogotá"}, {"id": _S2, "nombre": "Medellín"},
    ]
    fabrica, llamadas = _cliente_registrado(fake)
    monkeypatch.setattr(captura, "_cliente", fabrica)
    return fake, llamadas


def _dos_asesores():
    return {"asesores": [_asesor(_ANA, "Ana", [_S1]), _asesor(_BETO, "Beto", [_S1, _S2])]}


def _botones(llamada):
    return [fila[0] for fila in llamada.kwargs["reply_markup"].inline_keyboard]


# --- the question ------------------------------------------------------------


async def test_iniciar_with_two_usable_advisors_asks_who_registers(monkeypatch):
    fake, _ = _preparar(monkeypatch, _dos_asesores())
    update, context = _make_update(), _make_context()

    result = await captura.iniciar(update, context)

    assert result == CapturaEstado.ASESOR
    llamada = update.message.reply_text.call_args
    assert "¿Quién registra?" in llamada.args[0]
    botones = _botones(llamada)
    assert [(b.text, b.callback_data) for b in botones[:2]] == [
        ("Ana", f"lore_cap_ase:{_ANA}"), ("Beto", f"lore_cap_ase:{_BETO}"),
    ]
    assert botones[2].callback_data == "lore_cancelar"
    fake.sucursales.assert_not_awaited()
    assert captura._DRAFT_KEY not in context.user_data


async def test_iniciar_asks_again_every_time_never_remembering_a_previous_choice(monkeypatch):
    _preparar(monkeypatch, _dos_asesores())
    previo = Borrador(usuario_id=_ANA)
    context = _make_context(user_data={captura._DRAFT_KEY: previo})

    result = await captura.iniciar(_make_update(), context)

    assert result == CapturaEstado.ASESOR
    assert captura._DRAFT_KEY not in context.user_data or context.user_data[captura._DRAFT_KEY].usuario_id is None


async def test_iniciar_does_not_offer_pending_rejected_or_inactive_advisors(monkeypatch):
    yo = {"asesores": [
        _asesor(_ANA, "Ana", [_S1]), _asesor(_BETO, "Beto", [_S1]),
        _asesor("c", "Caro", [_S1], status="pending"),
        _asesor("d", "Dani", [_S1], status="rejected"),
        _asesor("e", "Eva", [_S1], activo=False),
    ]}
    _preparar(monkeypatch, yo)
    update = _make_update()

    await captura.iniciar(update, _make_context())

    nombres = [b.text for b in _botones(update.message.reply_text.call_args)[:-1]]
    assert nombres == ["Ana", "Beto"]


async def test_iniciar_single_advisor_asks_nothing_and_sends_no_usuario_id(monkeypatch):
    yo = {**_asesor(_ANA, "Ana", [_S1]), "asesores": [_asesor(_ANA, "Ana", [_S1])]}
    _, llamadas = _preparar(monkeypatch, yo)
    context = _make_context()

    result = await captura.iniciar(_make_update(), context)

    assert result == CapturaEstado.METODO
    assert context.user_data[captura._DRAFT_KEY].usuario_id is None
    assert all(usuario_id is None for _, usuario_id in llamadas)


async def test_iniciar_one_usable_among_several_uses_it_and_names_it(monkeypatch):
    yo = {"asesores": [_asesor("c", "Caro", [_S2], status="pending"), _asesor(_ANA, "Ana", [_S1])]}
    _preparar(monkeypatch, yo)
    context = _make_context()

    result = await captura.iniciar(_make_update(), context)

    assert result == CapturaEstado.METODO
    borrador = context.user_data[captura._DRAFT_KEY]
    assert str(borrador.sucursal_id) == _S1  # Ana's sucursal, not Caro's
    assert borrador.usuario_id == _ANA


async def test_iniciar_several_registered_but_none_usable_ends_with_a_message(monkeypatch):
    yo = {"asesores": [_asesor(_ANA, "Ana", [_S1], status="pending"), _asesor(_BETO, "Beto", [_S1], status="rejected")]}
    _preparar(monkeypatch, yo)
    update = _make_update()

    result = await captura.iniciar(update, _make_context())

    assert result == ConversationHandler.END
    assert "habilitado" in update.message.reply_text.call_args.args[0]


# --- the answer ---------------------------------------------------------------


async def test_recibir_asesor_stores_the_choice_and_uses_that_advisors_sucursales(monkeypatch):
    _, llamadas = _preparar(monkeypatch, _dos_asesores())
    context = _make_context()
    await captura.iniciar(_make_update(), context)

    update = _make_update(callback_data=f"lore_cap_ase:{_BETO}")
    result = await captura.recibir_asesor(update, context)

    assert result == CapturaEstado.SUCURSAL
    assert context.user_data[captura._DRAFT_KEY].usuario_id == _BETO
    assert set(context.user_data[captura._SUCURSALES_KEY]) == {_S1, _S2}  # Beto's two
    assert (123, _BETO) in llamadas


async def test_recibir_asesor_with_one_sucursal_skips_the_picker(monkeypatch):
    _preparar(monkeypatch, _dos_asesores())
    context = _make_context()
    await captura.iniciar(_make_update(), context)

    update = _make_update(callback_data=f"lore_cap_ase:{_ANA}")
    result = await captura.recibir_asesor(update, context)

    assert result == CapturaEstado.METODO
    borrador = context.user_data[captura._DRAFT_KEY]
    assert borrador.usuario_id == _ANA
    assert str(borrador.sucursal_id) == _S1
    update.callback_query.edit_message_text.assert_awaited()


async def test_recibir_asesor_rejects_an_advisor_that_was_not_offered(monkeypatch):
    _preparar(monkeypatch, _dos_asesores())
    context = _make_context()
    await captura.iniciar(_make_update(), context)

    update = _make_update(callback_data="lore_cap_ase:ffffffff-ffff-ffff-ffff-ffffffffffff")
    result = await captura.recibir_asesor(update, context)

    assert result == ConversationHandler.END
    assert captura._DRAFT_KEY not in context.user_data
    assert "no está disponible" in update.callback_query.edit_message_text.call_args.args[0]


async def test_recibir_asesor_without_a_pending_question_ends(monkeypatch):
    _preparar(monkeypatch, _dos_asesores())
    update = _make_update(callback_data=f"lore_cap_ase:{_ANA}")

    result = await captura.recibir_asesor(update, _make_context())

    assert result == ConversationHandler.END


# --- the choice travels with the whole conversation ------------------------------


async def test_recibir_codigos_sends_the_chosen_usuario(monkeypatch):
    fake, llamadas = _preparar(monkeypatch, _dos_asesores())
    fake.resolver_referencias.return_value = {"resueltas": [], "no_resueltas": ["X1"]}
    context = _make_context(user_data={captura._DRAFT_KEY: Borrador(usuario_id=_BETO)})

    await captura.recibir_codigos(_make_update(text="X1"), context)

    assert llamadas == [(123, _BETO)]


async def test_confirmar_sends_the_chosen_usuario(monkeypatch):
    fake, llamadas = _preparar(monkeypatch, _dos_asesores())
    fake.registrar_demanda_perdida.return_value = {}
    borrador = Borrador(usuario_id=_BETO)
    context = _make_context(user_data={captura._DRAFT_KEY: borrador})

    await captura.confirmar(_make_update(callback_data="lore_cap_confirmar"), context)

    assert llamadas == [(123, _BETO)]


async def test_cancelar_clears_the_pending_question(monkeypatch):
    _preparar(monkeypatch, _dos_asesores())
    context = _make_context()
    await captura.iniciar(_make_update(), context)

    await captura.cancelar(_make_update(), context)

    assert captura._ASESORES_KEY not in context.user_data
