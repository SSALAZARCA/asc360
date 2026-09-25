import os
import subprocess
import sys
from pathlib import Path

import pytest

from lore.config import ConfigError, validar_config

_REQUIRED_VARS = ("LORE_BOT_TOKEN", "LORE_BOT_SECRET", "LORE_OPENAI_API_KEY")


def _env(**overrides):
    base = {
        "LORE_BOT_TOKEN": "token-123",
        "LORE_BOT_SECRET": "lore-secret-abc",
        "LORE_OPENAI_API_KEY": "sk-lore-xyz",
    }
    base.update(overrides)
    return base


class TestValidarConfigHappyPath:
    def test_does_not_raise_when_all_required_vars_are_set_and_distinct(self):
        validar_config(_env())  # no raise

    def test_does_not_raise_when_sonia_vars_are_simply_absent(self):
        # In production lore-bot's own container never has SONIA_BOT_SECRET
        # or OPENAI_API_KEY set at all — absence must never be a false match.
        env = _env()
        assert "SONIA_BOT_SECRET" not in env
        assert "OPENAI_API_KEY" not in env
        validar_config(env)  # no raise


class TestValidarConfigRequiredVars:
    @pytest.mark.parametrize("missing", _REQUIRED_VARS)
    def test_raises_when_required_var_is_empty_string(self, missing):
        env = _env(**{missing: ""})
        with pytest.raises(ConfigError):
            validar_config(env)

    @pytest.mark.parametrize("missing", _REQUIRED_VARS)
    def test_raises_when_required_var_is_absent(self, missing):
        env = _env()
        del env[missing]
        with pytest.raises(ConfigError):
            validar_config(env)


class TestValidarConfigCrossProcessCollisions:
    def test_raises_when_lore_openai_key_equals_sonia_openai_key(self):
        env = _env(LORE_OPENAI_API_KEY="shared-key", OPENAI_API_KEY="shared-key")
        with pytest.raises(ConfigError):
            validar_config(env)

    def test_raises_when_lore_bot_secret_equals_sonia_bot_secret(self):
        env = _env(LORE_BOT_SECRET="shared-secret", SONIA_BOT_SECRET="shared-secret")
        with pytest.raises(ConfigError):
            validar_config(env)

    def test_does_not_raise_when_openai_keys_differ(self):
        env = _env(LORE_OPENAI_API_KEY="lore-key", OPENAI_API_KEY="sonia-key")
        validar_config(env)  # no raise

    def test_does_not_raise_when_bot_secrets_differ(self):
        env = _env(LORE_BOT_SECRET="lore-secret", SONIA_BOT_SECRET="sonia-secret")
        validar_config(env)  # no raise


class TestProcessStartupFailsClosed:
    """Proves the module-level guard actually runs at import time, in a real
    subprocess — not just that the pure `validar_config()` function raises.

    Uses a subprocess (not `monkeypatch.setattr(os, "environ", ...)`) on
    purpose: Phase 5 of this same change found that mutating shared process
    state (there: `monkeypatch.setattr(settings, ...)` vs. bare `setattr`)
    leaked secrets across unrelated tests when the full suite ran together.
    A subprocess with its own env dict cannot leak into this test process.
    """

    def _run_import_lore_config(self, env_overrides):
        lore_bot_dir = Path(__file__).resolve().parent.parent
        env = {"PATH": os.environ.get("PATH", "")}
        env.update(_env())
        env.update(env_overrides)
        return subprocess.run(
            [sys.executable, "-c", "import lore.config"],
            cwd=str(lore_bot_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_process_exits_nonzero_when_lore_bot_secret_is_empty(self):
        result = self._run_import_lore_config({"LORE_BOT_SECRET": ""})
        assert result.returncode != 0
        assert "ConfigError" in result.stderr

    def test_process_exits_nonzero_when_lore_bot_secret_equals_sonia_bot_secret(self):
        result = self._run_import_lore_config(
            {"LORE_BOT_SECRET": "shared", "SONIA_BOT_SECRET": "shared"}
        )
        assert result.returncode != 0
        assert "ConfigError" in result.stderr

    def test_process_starts_clean_with_a_safe_config(self):
        result = self._run_import_lore_config({})
        assert result.returncode == 0, result.stderr
