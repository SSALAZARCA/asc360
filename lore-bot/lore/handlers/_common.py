"""Shared constants/helpers used by both `handlers/registro.py` and
`handlers/admin.py`.

Hoisted here (Phase 9 fix-up, finding #9) because `_MSG_CONEXION` used to be
defined independently in both modules with slightly different wording (one
mentioned "/start", the other didn't) — a drift risk with zero test coverage
to catch it. Wording chosen: WITHOUT "/start", because `admin.py`'s
`vincular_command` can hit this exact failure mode outside any conversation
context, where telling an admin to "mandá /start" would be misleading
recovery advice (that command starts the self-registration flow, not the
admin-linking one).
"""
from __future__ import annotations

import re

from telegram import ReplyKeyboardMarkup

_MSG_CONEXION = "⚠️ Tuve un problema para hablar con el sistema. Probá de nuevo en unos segundos."

_MSG_SESION_EXPIRADA = (
    "⚠️ Tu sesión anterior expiró. Volvé a mandar el comando que estabas usando."
)
# Deliberately generic (Phase 10 fix-up, finding #3): `registro.callback_huerfano`
# is a single fallback shared by every `lore_*` callback prefix (`lore_sucursal:`,
# `lore_apr:`/`lore_rej:`, and — since Phase 10 — `lore_cap_*`/`lore_cor_*` too).
# Naming a specific command here (it used to say "Mandá /start de nuevo") gave
# wrong recovery guidance for 2 of the 3 flows it covers: an advisor stuck
# mid-capture or mid-correction needs /registrar or /correcciones, not /start.

# Telegram's legacy Markdown (parse_mode="Markdown", NOT MarkdownV2) only
# treats these four characters as special: `_ * `` [`. A caller-supplied
# string interpolated unescaped into a Markdown-mode message can otherwise
# make the Bot API reject the whole message with a 400 "can't parse
# entities" error (Phase 9 fix-up, finding #2).
_MARKDOWN_SPECIAL_CHARS = re.compile(r"([_*`\[])")


def _escapar_markdown(texto: str) -> str:
    """Escape Telegram legacy Markdown v1 special characters in `texto`.

    Safe to call on any user-supplied string headed into a
    `parse_mode="Markdown"` message — does nothing to strings that contain
    none of `_ * `` [`.
    """
    return _MARKDOWN_SPECIAL_CHARS.sub(r"\\\1", texto)


# Phase 10 fix-up, finding #6: hoisted from `captura.py`/`correccion.py`,
# which each defined these two constants and the same `isdigit()`+bounds
# check byte-for-byte. Only the validation logic and the numbers moved here
# — each call site keeps its own user-facing error message wording as-is.
_CANTIDAD_MINIMA = 1
_CANTIDAD_MAXIMA = 9999


def _validar_cantidad(texto: str) -> int | None:
    """Parses a raw quantity string, returning the int if it's a valid
    quantity (`_CANTIDAD_MINIMA` to `_CANTIDAD_MAXIMA`), or `None` if not
    (non-digit text, empty string, or out of bounds)."""
    if not texto.isdigit():
        return None
    valor = int(texto)
    if not (_CANTIDAD_MINIMA <= valor <= _CANTIDAD_MAXIMA):
        return None
    return valor


# Persistent Reply Keyboard (UX shortcut) — lets an approved advisor TAP a
# button instead of typing `/registrar`/`/correcciones`. Wiring detail: the
# exact label strings below are ALSO used, byte-for-byte, as the
# `filters.Text([...])` match in `main.py`'s extra `MessageHandler` entry
# points for the `captura`/`correccion` `ConversationHandler`s -- both must
# stay in sync, which is exactly why they live here as shared constants
# instead of being duplicated as string literals in each file.
BOTON_REGISTRAR = "📝 Registrar venta perdida"
BOTON_CORRECCIONES = "🧾 Mis correcciones de hoy"

# `resize_keyboard=True` shrinks the keyboard to fit just these 2 rows
# instead of Telegram's oversized default. Deliberately NOT
# `one_time_keyboard=True`: that flag hides the keyboard again after a single
# tap, which is the opposite of "persistent" here.
#
# Send-site judgment call: this is attached to exactly ONE message per role --
# `registro.py::start()`'s approved-welcome-back reply. A Telegram
# `ReplyKeyboardMarkup` is a client-side UI attachment to the CHAT, not to
# one message: once sent, it stays in force for that chat until the bot
# explicitly replaces it with another `reply_markup` (a different keyboard or
# `ReplyKeyboardRemove()`). Nothing later in the capture/correction flows
# sends either of those, so re-attaching this keyboard again after every
# capture/correction completion would be redundant, not more "persistent".
# (Known, accepted gap: a user already-approved BEFORE this feature shipped
# only gets the keyboard once they type `/start` again -- there is no other
# trigger to backfill it, and this task's scope is additive UX, not an
# existing-user migration.)
#
# Renamed from `TECLADO_ASESOR` -> `TECLADO_CAPTURA` (ad-hoc, post-Phase-10):
# an ADMIN can now also drive `/registrar`/`/correcciones` (see
# `deps_bot.py::require_bot_asesor_o_admin` on the backend side), so a name
# implying "advisor-only" would be actively misleading. Only 2 non-test call
# sites (this module + `registro.py`) plus `test_handlers_registro.py`
# reference the old name -- small enough blast radius that a rename beats
# leaving a stale, role-specific name on a now-role-generic constant.
TECLADO_CAPTURA = ReplyKeyboardMarkup(
    [[BOTON_REGISTRAR], [BOTON_CORRECCIONES]],
    resize_keyboard=True,
)
