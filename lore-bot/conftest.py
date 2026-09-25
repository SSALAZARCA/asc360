"""Root conftest: inject dummy env vars before any `lore.*` module is imported.

`lore/config.py` calls `validar_config(os.environ)` at import time (fail-closed
at process startup — see its own docstring for the ADR-4 reasoning). Without
this, pytest would crash on collection the moment any test module does
`from lore import config` (directly or transitively via `lore.api`/`lore.main`)
in an environment where the real `LORE_*` secrets are not set.

These are dummy values, not real secrets, and are only used by the tests
below that do NOT already provide their own crafted env dict — most of
`test_config.py` calls `validar_config()` directly with its own dicts and
never touches `os.environ`.
"""
import os

os.environ.setdefault("LORE_BOT_TOKEN", "test-lore-token")
os.environ.setdefault("LORE_BOT_SECRET", "test-lore-secret")
os.environ.setdefault("LORE_OPENAI_API_KEY", "test-lore-openai-key")
