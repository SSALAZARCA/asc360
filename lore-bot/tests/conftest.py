"""Shared test helpers for lore-bot."""
import pytest


def _termina_en_cancelar(llamada) -> bool:
    """True when a `reply_text`/`edit_message_text` call's inline keyboard
    ends with the shared "✖️ Cancelar" row (`lore_cancelar`) on its own."""
    markup = llamada.kwargs.get("reply_markup")
    return markup is not None and [b.callback_data for b in markup.inline_keyboard[-1]] == ["lore_cancelar"]


@pytest.fixture
def termina_en_cancelar():
    return _termina_en_cancelar
