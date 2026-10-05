"""
KPI summary tables (R1): model registration and the static shape of the Alembic
revision. The real constraints are exercised in `pg_real/test_kpi_resumen_migration_pg.py`.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import Index

import app.motored.models  # noqa: F401  (registers the models)
from app.motored.database import MotoredBase

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
_FILES = sorted(_VERSIONS_DIR.glob("*_kpi_resumen.py"))
TABLES = (
    "kpi_venta_mes", "kpi_factura_firma", "kpi_cliente_mes", "kpi_costo_referencia", "kpi_inventario_corte",
    "kpi_resumen_estado",
)


def _migration():
    assert len(_FILES) == 1, "expected exactly one kpi_resumen revision"
    spec = importlib.util.spec_from_file_location("kpi_resumen_migration", _FILES[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_models_register_the_six_tables_and_their_unique_indexes():
    assert set(TABLES) <= set(MotoredBase.metadata.tables)
    unicos = {i.name for t in MotoredBase.metadata.tables.values() for i in t.indexes if i.unique}
    assert {"uq_kpi_venta_mes_llave", "uq_kpi_factura_firma_llave"} <= unicos
    assert all(isinstance(i, Index) for i in MotoredBase.metadata.tables["kpi_venta_mes"].indexes)


def test_estado_table_is_a_single_row_table():
    checks = {c.name for c in MotoredBase.metadata.tables["kpi_resumen_estado"].constraints}
    assert "ck_kpi_resumen_estado_fila_unica" in checks


def test_migration_chains_on_the_budgets_head_and_creates_the_tables_in_fk_order():
    migration = _migration()
    assert migration.down_revision == "d7a2f4b8c915"
    with patch.object(migration, "op") as op_mock:
        migration.upgrade()

    assert [c.args[0] for c in op_mock.create_table.call_args_list] == list(TABLES)


def test_migration_downgrade_drops_every_table():
    migration = _migration()
    with patch.object(migration, "op") as op_mock:
        migration.downgrade()

    assert sorted(c.args[0] for c in op_mock.drop_table.call_args_list) == sorted(TABLES)
