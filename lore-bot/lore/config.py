"""Lore's own process configuration — fail-closed at startup.

This is the standalone bot PROCESS (not the shared `backend`). Per this
change's ADR-4 distinction, `backend` must never crash for a Motored
misconfiguration (it fails closed per-request instead — see
`backend/app/motored/deps_bot.py::lore_bot_secret_is_safe`/
`require_lore_ready`). `lore-bot` has no such constraint: it is allowed,
and expected, to refuse to start at all with an unsafe configuration.

This module mirrors the INTENT of `lore_bot_secret_is_safe` (refuse an
empty or shared secret) as its own independent check — it does not import
anything from `backend/` or `telegram-bot/` (see `tests/test_isolation.py`).
"""
from __future__ import annotations

import os
from typing import Mapping

_REQUIRED_VARS = ("LORE_BOT_TOKEN", "LORE_BOT_SECRET", "LORE_OPENAI_API_KEY")


class ConfigError(Exception):
    """Raised when the current environment is unsafe for lore-bot to start."""


def validar_config(env: Mapping[str, str]) -> None:
    """Raise `ConfigError` if `env` is not safe for this process to start.

    Checks, in order:
    1. Every var in `_REQUIRED_VARS` is present and non-empty.
    2. `LORE_OPENAI_API_KEY` does not equal Sonia's own `OPENAI_API_KEY`
       (absence of either side is never treated as a match).
    3. `LORE_BOT_SECRET` does not equal Sonia's own `SONIA_BOT_SECRET`.

    Pure function: takes an explicit mapping instead of reading `os.environ`
    directly, so it can be unit-tested with crafted dicts without touching
    real process state.
    """
    for var in _REQUIRED_VARS:
        if not env.get(var):
            raise ConfigError(
                f"{var} must be set via environment variable — no default allowed"
            )

    lore_openai_key = env.get("LORE_OPENAI_API_KEY")
    sonia_openai_key = env.get("OPENAI_API_KEY")
    if sonia_openai_key is not None and lore_openai_key == sonia_openai_key:
        raise ConfigError(
            "LORE_OPENAI_API_KEY must not equal OPENAI_API_KEY (Sonia's own key)"
        )

    lore_bot_secret = env.get("LORE_BOT_SECRET")
    sonia_bot_secret = env.get("SONIA_BOT_SECRET")
    if sonia_bot_secret is not None and lore_bot_secret == sonia_bot_secret:
        raise ConfigError(
            "LORE_BOT_SECRET must not equal SONIA_BOT_SECRET (Sonia's own secret)"
        )


# Fails at import time — the standalone process crashes on invalid config
# instead of starting in a broken/insecure state.
validar_config(os.environ)

LORE_BOT_TOKEN: str = os.environ["LORE_BOT_TOKEN"]
LORE_BOT_SECRET: str = os.environ["LORE_BOT_SECRET"]
LORE_OPENAI_API_KEY: str = os.environ["LORE_OPENAI_API_KEY"]
LORE_API_URL: str = os.environ.get(
    "LORE_API_URL", "http://backend:8000/api/motored/bot"
)
LORE_USER_CACHE_TTL_SECONDS: int = int(
    os.environ.get("LORE_USER_CACHE_TTL_SECONDS", "60")
)
LORE_OPENAI_MAX_RETRIES: int = int(os.environ.get("LORE_OPENAI_MAX_RETRIES", "2"))
