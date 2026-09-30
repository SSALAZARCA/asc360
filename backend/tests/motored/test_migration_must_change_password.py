"""Static checks for the `usuario.must_change_password` migration (T8)."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[2]
_FILE = _ROOT / "alembic_motored" / "versions" / "c4e7a19b3d58_usuario_must_change_password.py"


def _load():
    spec = importlib.util.spec_from_file_location("must_change_pwd", _FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chains_onto_password_changed_at_with_a_single_head():
    module = _load()
    assert module.revision == "c4e7a19b3d58"
    assert module.down_revision == "b8d2f4a61c93"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic_motored.ini")))
    assert len(script.get_heads()) == 1
    assert script.get_revision("c4e7a19b3d58") is not None


def test_upgrade_adds_a_not_null_boolean_defaulting_to_false():
    module = _load()
    with patch.object(module, "op") as op:
        module.upgrade()
    table, column = op.add_column.call_args.args
    assert table == "usuario"
    assert column.name == "must_change_password"
    assert column.nullable is False
    assert str(column.server_default.arg) == "false"
    assert not op.execute.called


def test_downgrade_drops_the_column():
    module = _load()
    with patch.object(module, "op") as op:
        module.downgrade()
    op.drop_column.assert_called_once_with("usuario", "must_change_password")
