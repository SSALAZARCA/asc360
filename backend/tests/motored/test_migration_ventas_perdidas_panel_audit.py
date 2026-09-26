"""
Tests for Phase 1 "Migration + Model" (sdd/motored-ventas-perdidas-panel,
task 1.1): the new revision on the `alembic_motored` chain that adds the
edit/anular audit columns plus a `fecha` index to `demanda_perdida_bot_linea`.

Same approach as `test_migration_lore_bot_schema.py`: no live test
DATABASE_URL exists for this Alembic chain in this repo -- the migration is
loaded directly by file path (`alembic_motored/versions/` is a script-
location, not an importable package) and exercised against a mocked `op`,
asserting the exact DDL calls issued and that upgrade/downgrade are inverses
of each other. Model/DDL agreement is asserted separately in
`test_models_bot.py`.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"


def _load_migration(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, _VERSIONS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration(
    "43191272c816_ventas_perdidas_panel_audit.py", "sdd_ventas_perdidas_panel_audit_migration",
)


def _added_columns(op_mock) -> dict:
    return {
        c.args[1].name: c.args[1]
        for c in op_mock.add_column.call_args_list
        if c.args[0] == "demanda_perdida_bot_linea"
    }


class TestRevisionChain:
    def test_chains_onto_current_head(self):
        assert migration.revision == "43191272c816"
        assert migration.down_revision == "8611c3e463ac"


class TestUpgrade:
    def test_adds_editado_and_anulado_columns_nullable(self):
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()

        added = _added_columns(op_mock)
        assert added["editado_por"].nullable is True
        assert added["editado_en"].nullable is True
        assert added["anulado_por"].nullable is True
        assert added["anulado_en"].nullable is True

    def test_creates_foreign_keys_for_editado_por_and_anulado_por(self):
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()

        op_mock.create_foreign_key.assert_any_call(
            "fk_demanda_perdida_bot_linea_editado_por_usuario",
            "demanda_perdida_bot_linea", "usuario", ["editado_por"], ["id"],
        )
        op_mock.create_foreign_key.assert_any_call(
            "fk_demanda_perdida_bot_linea_anulado_por_usuario",
            "demanda_perdida_bot_linea", "usuario", ["anulado_por"], ["id"],
        )

    def test_creates_fecha_index(self):
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()

        op_mock.create_index.assert_any_call(
            "ix_demanda_perdida_bot_linea_fecha",
            "demanda_perdida_bot_linea", ["fecha"], unique=False,
        )


class TestDowngrade:
    def test_drops_index_before_foreign_keys_before_columns(self):
        with patch.object(migration, "op") as op_mock:
            migration.downgrade()

        order = [name for name, _args, _kwargs in op_mock.method_calls]
        index_pos = order.index("drop_index")
        fk_positions = [i for i, name in enumerate(order) if name == "drop_constraint"]
        column_positions = [i for i, name in enumerate(order) if name == "drop_column"]

        assert index_pos < min(fk_positions)
        assert max(fk_positions) < min(column_positions)

    def test_drops_the_fecha_index(self):
        with patch.object(migration, "op") as op_mock:
            migration.downgrade()

        op_mock.drop_index.assert_any_call(
            "ix_demanda_perdida_bot_linea_fecha", table_name="demanda_perdida_bot_linea",
        )

    def test_drops_both_foreign_keys(self):
        with patch.object(migration, "op") as op_mock:
            migration.downgrade()

        op_mock.drop_constraint.assert_any_call(
            "fk_demanda_perdida_bot_linea_editado_por_usuario",
            "demanda_perdida_bot_linea", type_="foreignkey",
        )
        op_mock.drop_constraint.assert_any_call(
            "fk_demanda_perdida_bot_linea_anulado_por_usuario",
            "demanda_perdida_bot_linea", type_="foreignkey",
        )

    def test_drops_all_four_columns(self):
        with patch.object(migration, "op") as op_mock:
            migration.downgrade()

        for column_name in ("editado_por", "editado_en", "anulado_por", "anulado_en"):
            op_mock.drop_column.assert_any_call("demanda_perdida_bot_linea", column_name)
