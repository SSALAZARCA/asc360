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

_MSG_CONEXION = "⚠️ Tuve un problema para hablar con el sistema. Probá de nuevo en unos segundos."

_MSG_SESION_EXPIRADA = "⚠️ Tu sesión anterior expiró. Mandá /start de nuevo."

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
