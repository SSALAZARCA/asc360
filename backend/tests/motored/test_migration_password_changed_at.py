"""Static checks for the `usuario.password_changed_at` migration (T3)."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[2]
_FILE = _ROOT / "alembic_motored" / "versions" / "b8d2f4a61c93_usuario_password_changed_at.py"


def _load():
    spec = importlib.util.spec_from_file_location("pwd_changed_at", _FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain_and_single_head():
    module = _load()
    assert module.revision == "b8d2f4a61c93"
    assert module.down_revision == "a7c3e91d5b20"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic_motored.ini")))
    # One linear chain that contains this revision; later migrations may sit on top.
    assert len(script.get_heads()) == 1
    assert script.get_revision("b8d2f4a61c93") is not None


def test_upgrade_adds_a_nullable_datetime_column_without_backfill():
    module = _load()
    with patch.object(module, "op") as op:
        module.upgrade()
    table, column = op.add_column.call_args.args
    assert table == "usuario"
    assert column.name == "password_changed_at"
    assert column.nullable is True
    assert not op.execute.called


def test_downgrade_drops_the_column():
    module = _load()
    with patch.object(module, "op") as op:
        module.downgrade()
    op.drop_column.assert_called_once_with("usuario", "password_changed_at")
