"""
Static checks for the detractor "responsable" backfill migration: it chains
after the current head, keeps a single head and runs the expected UPDATE.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[2]
_FILE = _ROOT / "alembic_motored" / "versions" / "a7c3e91d5b20_caso_detractor_responsable_backfill.py"


def _load():
    spec = importlib.util.spec_from_file_location("detractor_backfill", _FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain_and_single_head():
    module = _load()
    assert module.revision == "a7c3e91d5b20"
    assert module.down_revision == "f2a6d83b9e14"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic_motored.ini")))
    assert script.get_heads() == ["a7c3e91d5b20"]


def test_upgrade_runs_the_idempotent_backfill_update():
    module = _load()
    with patch.object(module, "op") as op:
        module.upgrade()
    sql = " ".join(str(call.args[0]) for call in op.execute.call_args_list)
    assert "UPDATE caso_detractor" in sql
    assert "asignado_a IS NULL" in sql
    assert "usuario_id IS NOT NULL" in sql
    assert "ORDER BY a.created_at, a.id" in sql


def test_downgrade_is_a_documented_noop():
    module = _load()
    with patch.object(module, "op") as op:
        module.downgrade()
    op.execute.assert_not_called()
