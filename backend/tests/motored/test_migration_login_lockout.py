"""Static checks for the login lockout columns + `login_evento` migration (T9/T10)."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[2]
_FILE = _ROOT / "alembic_motored" / "versions" / "d9a2b6e04f71_login_lockout_and_events.py"


def _load():
    spec = importlib.util.spec_from_file_location("login_lockout_mig", _FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chains_onto_must_change_password_with_a_single_head():
    module = _load()
    assert module.revision == "d9a2b6e04f71"
    assert module.down_revision == "c4e7a19b3d58"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic_motored.ini")))
    assert len(script.get_heads()) == 1
    assert script.get_revision("d9a2b6e04f71") is not None


def test_upgrade_is_additive_only():
    module = _load()
    with patch.object(module, "op") as op:
        module.upgrade()
    columns = {c.args[1].name: c.args[1] for c in op.add_column.call_args_list}
    assert columns["login_fallidos"].nullable is False
    assert str(columns["login_fallidos"].server_default.arg) == "0"
    assert columns["login_ventana_inicio"].nullable and columns["bloqueado_hasta"].nullable
    assert op.create_table.call_args.args[0] == "login_evento"
    assert not op.drop_table.called and not op.drop_column.called and not op.execute.called


def test_downgrade_reverses_everything():
    module = _load()
    with patch.object(module, "op") as op:
        module.downgrade()
    op.drop_table.assert_called_once_with("login_evento")
    dropped = {c.args[1] for c in op.drop_column.call_args_list}
    assert dropped == {"login_fallidos", "login_ventana_inicio", "bloqueado_hasta"}
