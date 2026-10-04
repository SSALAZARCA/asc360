"""
Motored budgets (T2): the Alembic revision creating `presupuesto_version` and
`presupuesto_linea`. Static checks with a mocked `op`; the real constraints
(CHECK day = 1, UNIQUE, cascade) are exercised in `pg_real/test_presupuestos_pg.py`.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
_FILES = sorted(_VERSIONS_DIR.glob("*_presupuestos.py"))


def _migration():
    assert len(_FILES) == 1, "expected exactly one presupuestos revision"
    spec = importlib.util.spec_from_file_location("presupuestos_migration", _FILES[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chains_onto_the_gerencia_role_revision():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == ("d7a2f4b8c915", "c4e8a1f6d903")


def test_upgrade_creates_both_tables_header_first():
    migration = _migration()
    with patch.object(migration, "op") as op_mock:
        migration.upgrade()

    assert [c.args[0] for c in op_mock.create_table.call_args_list] == [
        "presupuesto_version", "presupuesto_linea"]


def test_downgrade_drops_lines_before_header():
    migration = _migration()
    with patch.object(migration, "op") as op_mock:
        migration.downgrade()

    assert [c.args[0] for c in op_mock.drop_table.call_args_list] == [
        "presupuesto_linea", "presupuesto_version"]
