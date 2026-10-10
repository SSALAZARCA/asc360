"""
Inventario KPI summary tables: model registration and the static shape of the Alembic revision.
The real constraints are exercised in `pg_real/test_kpi_inventario_resumen_pg.py`.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import app.motored.models  # noqa: F401  (registers the models)
from app.motored.database import MotoredBase

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
_FILES = sorted(_VERSIONS_DIR.glob("*_kpi_inventario_resumen.py"))
TABLES = ("kpi_inventario_par", "kpi_costo_mes_referencia")


def _migration():
    assert len(_FILES) == 1, "expected exactly one kpi_inventario_resumen revision"
    spec = importlib.util.spec_from_file_location("kpi_inventario_resumen_migration", _FILES[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_models_register_the_two_tables_with_their_primary_keys():
    tablas = MotoredBase.metadata.tables
    assert set(TABLES) <= set(tablas)
    assert [c.name for c in tablas["kpi_inventario_par"].primary_key.columns] == [
        "fecha_corte", "sucursal_id", "referencia_id"]
    assert [c.name for c in tablas["kpi_costo_mes_referencia"].primary_key.columns] == [
        "anio_mes", "sucursal_id", "referencia_id"]


def test_the_cost_table_only_holds_first_days_of_a_month():
    checks = {c.name for c in MotoredBase.metadata.tables["kpi_costo_mes_referencia"].constraints}
    assert "ck_kpi_costo_mes_referencia_dia_1" in checks


def test_migration_chains_on_the_traslados_head_and_creates_both_tables():
    migration = _migration()
    assert migration.down_revision == "b2f6d9a4c718"
    with patch.object(migration, "op") as op_mock:
        migration.upgrade()

    assert [c.args[0] for c in op_mock.create_table.call_args_list] == list(TABLES)


def test_migration_downgrade_drops_both_tables():
    migration = _migration()
    with patch.object(migration, "op") as op_mock:
        migration.downgrade()

    assert sorted(c.args[0] for c in op_mock.drop_table.call_args_list) == sorted(TABLES)


def test_migration_flags_the_summaries_dirty_because_the_new_tables_start_empty():
    migration = _migration()
    with patch.object(migration, "op") as op_mock:
        migration.upgrade()

    sentencias = [str(c.args[0]) for c in op_mock.execute.call_args_list]
    assert sentencias == ["UPDATE kpi_resumen_estado SET sucio = true"]
