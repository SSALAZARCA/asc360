"""
sdd/reception-email-notification (Phase 10, design ADR 6): mandatory
cross-runtime copy-parity guard.

The Telegram bot (`telegram-bot/bot/handlers/reception.py`) is the
canonical source of the email-capture copy for the ASKING_CLIENT_EMAIL
step; the Mini App (`frontend/app/tg/reception/page.js`) copies the same
five constants verbatim, per the exact precedent already in this repo for
CLIENT_FIELDS / _build_client_summary. This is a STATIC TEXT-PARITY guard,
not a red-first TDD unit -- there's no runtime behavior to unit-test here
(pure text extraction from both files), so it's written once, run GREEN,
and left as the closing verification of the whole 3-slice feature.

It reads both files as plain text (no bot/frontend runtime import needed
for either), regex-extracts the five constants from both, and asserts
byte-for-byte equality between the two files' values AND against the
pinned values from the design doc. This test MUST fail if either file
drifts.
"""
import re
from pathlib import Path

# backend/tests/reception_email/test_bot_miniapp_copy_parity.py
#   parents[0] = reception_email/
#   parents[1] = tests/
#   parents[2] = backend/
#   parents[3] = repo root (siblings: backend/, frontend/, telegram-bot/)
REPO_ROOT = Path(__file__).resolve().parents[3]
BOT_FILE = REPO_ROOT / "telegram-bot" / "bot" / "handlers" / "reception.py"
MINIAPP_FILE = REPO_ROOT / "frontend" / "app" / "tg" / "reception" / "page.js"

# Pinned verbatim from the design doc (sdd/reception-email-notification,
# ADR 6 "Normative copy" table) -- the source of truth both files must
# match, independent of each other.
PINNED_VALUES = {
    "EMAIL_PROMPT": (
        "¿Me das el *email del cliente*? Le mandamos el comprobante de "
        "recepción en PDF. Si no tiene, tocá *Sin email*."
    ),
    "EMAIL_INVALID": "Ese email no parece válido. ¿Me lo escribís de nuevo? O tocá *Sin email*.",
    "EMAIL_SKIP_LABEL": "Sin email",
    "EMAIL_OK": "Email *{email}* registrado. ✅",
    "EMAIL_RE": r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
}

STRING_CONSTANTS = ("EMAIL_PROMPT", "EMAIL_INVALID", "EMAIL_SKIP_LABEL", "EMAIL_OK")


def _extract_bot_constants(text: str) -> dict:
    """Bot syntax: `NAME = "..."` (plain strings) and `EMAIL_RE = r"..."` (raw string)."""
    values = {}
    for name in STRING_CONSTANTS:
        m = re.search(rf'^{name}\s*=\s*"((?:[^"\\]|\\.)*)"', text, re.MULTILINE)
        assert m, f"Could not find bot constant {name} in {BOT_FILE}"
        values[name] = m.group(1)
    m = re.search(r'^EMAIL_RE\s*=\s*r"((?:[^"\\]|\\.)*)"', text, re.MULTILINE)
    assert m, f"Could not find bot constant EMAIL_RE in {BOT_FILE}"
    values["EMAIL_RE"] = m.group(1)
    return values


def _extract_miniapp_constants(text: str) -> dict:
    """Mini App syntax: `const NAME = '...';` (single-quoted strings) and
    `const EMAIL_RE = /.../;` (regex literal)."""
    values = {}
    for name in STRING_CONSTANTS:
        m = re.search(rf"const {name}\s*=\s*'((?:[^'\\]|\\.)*)'", text)
        assert m, f"Could not find Mini App constant {name} in {MINIAPP_FILE}"
        values[name] = m.group(1)
    m = re.search(r"const EMAIL_RE\s*=\s*/((?:[^/\\]|\\.)*)/", text)
    assert m, f"Could not find Mini App constant EMAIL_RE in {MINIAPP_FILE}"
    values["EMAIL_RE"] = m.group(1)
    return values


def test_bot_and_miniapp_email_copy_match_each_other_and_pinned_spec():
    assert BOT_FILE.exists(), f"Bot reception handler not found at {BOT_FILE}"
    assert MINIAPP_FILE.exists(), f"Mini App reception page not found at {MINIAPP_FILE}"

    bot_text = BOT_FILE.read_text(encoding="utf-8")
    miniapp_text = MINIAPP_FILE.read_text(encoding="utf-8")

    bot_values = _extract_bot_constants(bot_text)
    miniapp_values = _extract_miniapp_constants(miniapp_text)

    for name, pinned in PINNED_VALUES.items():
        assert bot_values[name] == pinned, (
            f"Bot's {name} drifted from the pinned design spec value.\n"
            f"  bot:    {bot_values[name]!r}\n"
            f"  pinned: {pinned!r}"
        )
        assert miniapp_values[name] == pinned, (
            f"Mini App's {name} drifted from the pinned design spec value.\n"
            f"  miniapp: {miniapp_values[name]!r}\n"
            f"  pinned:  {pinned!r}"
        )
        assert bot_values[name] == miniapp_values[name], (
            f"{name} differs between the bot and the Mini App.\n"
            f"  bot:     {bot_values[name]!r}\n"
            f"  miniapp: {miniapp_values[name]!r}"
        )
