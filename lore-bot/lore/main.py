"""Lore's process entrypoint.

Phase 8 (this file) only constructs the `Application` object — no handlers
are registered yet (Phase 9's job: `/start`, `/vincular`, the capture and
correction conversation handlers). Running this module for real, via the
Dockerfile's `CMD`, would call `run_polling()` and needs a live bot token;
nothing in this skeleton phase requires that to import or unit-test (see
`tests/test_main.py`, which never calls `main()`).
"""
from __future__ import annotations

from telegram.ext import Application

from lore import config


def build_application() -> Application:
    """Construct, but do not start, the python-telegram-bot `Application`."""
    return Application.builder().token(config.LORE_BOT_TOKEN).build()


def main() -> None:  # pragma: no cover — exercised only by the real process
    application = build_application()
    application.run_polling()


if __name__ == "__main__":  # pragma: no cover
    main()
