"""Unit tests for `lore.handlers._asesor` — the shared "who is acting?" rules
for a Telegram account that several advisors share."""
from unittest.mock import AsyncMock, MagicMock

from lore.api import BackendCaido, NoRegistrado, Pendiente, Rechazado
from lore.handlers import _asesor


def _a(id, nombre="Ana", status="approved", activo=True, role="ASESOR_MOSTRADOR", sucursales=()):
    return {
        "id": id, "nombre": nombre, "role": role, "status": status,
        "activo": activo, "sucursales": list(sucursales),
    }


def _yo(*asesores):
    return {"asesores": list(asesores)}


def test_utilizables_keeps_only_approved_and_active():
    yo = _yo(_a("1"), _a("2", status="pending"), _a("3", status="rejected"), _a("4", activo=False))

    assert [a["id"] for a in _asesor.asesores_utilizables(yo)] == ["1"]


def test_utilizables_of_a_legacy_single_actor_body_is_that_actor():
    legacy = {"id": "1", "nombre": "Ana", "role": "ASESOR_MOSTRADOR", "sucursales": ["s1"]}

    assert _asesor.asesores_utilizables(legacy) == [legacy]


def test_ninguno_habilitado_only_when_several_registered_and_none_usable():
    assert _asesor.ninguno_habilitado(_yo(_a("1", status="pending"), _a("2", status="rejected")))
    assert not _asesor.ninguno_habilitado(_yo(_a("1"), _a("2", status="pending")))
    assert not _asesor.ninguno_habilitado(_yo(_a("1", status="pending")))  # single: old flow
    assert not _asesor.ninguno_habilitado({"id": "1"})


def test_actor_automatico_single_advisor_sends_no_usuario_id():
    yo = _yo(_a("1"))

    assert _asesor.actor_automatico(yo) == (yo["asesores"][0], None)


def test_actor_automatico_legacy_body_uses_the_body_itself_and_no_usuario_id():
    legacy = {"id": "1", "role": "ASESOR_MOSTRADOR", "sucursales": []}

    assert _asesor.actor_automatico(legacy) == (legacy, None)


def test_actor_automatico_one_usable_among_several_names_that_advisor():
    ana = _a("1")
    yo = _yo(_a("2", status="pending"), ana)

    assert _asesor.actor_automatico(yo) == (ana, "1")


def test_teclado_asesores_has_one_button_per_advisor_then_cancelar():
    kb = _asesor.teclado_asesores("lore_cap_ase:", [_a("1", "Ana"), _a("2", "Beto")])

    filas = kb.inline_keyboard
    assert [(f[0].text, f[0].callback_data) for f in filas[:2]] == [
        ("Ana", "lore_cap_ase:1"), ("Beto", "lore_cap_ase:2"),
    ]
    assert filas[2][0].callback_data == "lore_cancelar"


def test_buscar_asesor_only_returns_offered_options():
    opciones = {"1": _a("1")}

    assert _asesor.buscar_asesor(opciones, "1") == opciones["1"]
    assert _asesor.buscar_asesor(opciones, "999") is None
    assert _asesor.buscar_asesor({}, "1") is None


async def _verificar(excepcion):
    client = MagicMock()
    client.yo = AsyncMock(side_effect=excepcion)
    update = MagicMock()
    update.callback_query = None
    update.message.reply_text = AsyncMock()
    resultado = await _asesor.verificar_actor(client, update)
    return resultado, update.message.reply_text.call_args.args[0]


async def test_verificar_actor_replies_and_returns_none_for_each_blocked_state():
    for excepcion, fragmento in [
        (NoRegistrado("x"), "registrado"),
        (Pendiente("x"), "pendiente"),
        (Rechazado("x"), "rechazada"),
        (BackendCaido("x"), "problema"),
    ]:
        resultado, texto = await _verificar(excepcion)
        assert resultado is None
        assert fragmento in texto.lower()


async def test_verificar_actor_returns_the_yo_body_on_success():
    client = MagicMock()
    client.yo = AsyncMock(return_value={"id": "1"})

    assert await _asesor.verificar_actor(client, MagicMock()) == {"id": "1"}
