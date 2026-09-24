"""
Tests for Phase 1 "Schema" (sdd/motored-ventas-perdidas-bot, tasks 1.1-1.6):
the two new revisions on the `alembic_motored` chain -- `lore_role_enum`
(`d0f33eb07f78`) and `lore_bot_schema` (`8611c3e463ac`).

Same approach as `tests/test_migration_suggestion_dismissed_at.py`: no live
test DATABASE_URL exists for either Alembic chain in this repo (see that
file's docstring) -- migrations are loaded directly by file path (`alembic_
motored/versions/` is a script-location, not an importable package) and
exercised against a mocked `op`, asserting the exact DDL calls issued and
that upgrade/downgrade are inverses of each other. Model/DDL agreement is
asserted separately in `test_models_bot.py` and `test_models_movimientos.py`.
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import sqlalchemy as sa

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"


def _load_migration(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, _VERSIONS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


role_enum_migration = _load_migration(
    "d0f33eb07f78_lore_role_enum.py", "sdd_lore_role_enum_migration"
)
bot_schema_migration = _load_migration(
    "8611c3e463ac_lore_bot_schema.py", "sdd_lore_bot_schema_migration"
)


def _added_columns(op_mock, table_name: str) -> dict:
    return {
        c.args[1].name: c.args[1]
        for c in op_mock.add_column.call_args_list
        if c.args[0] == table_name
    }


def _check_constraint_names(op_mock, table_name: str) -> dict:
    return {
        c.args[0]: c.args[2]
        for c in op_mock.create_check_constraint.call_args_list
        if c.args[1] == table_name
    }


class TestRevisionChain:
    def test_lore_role_enum_revision_ids(self):
        assert role_enum_migration.revision == "d0f33eb07f78"
        assert role_enum_migration.down_revision == "3956c0ebd69c"

    def test_lore_bot_schema_chains_onto_lore_role_enum(self):
        assert bot_schema_migration.revision == "8611c3e463ac"
        assert bot_schema_migration.down_revision == "d0f33eb07f78"


class TestLoreRoleEnumUpgrade:
    def test_adds_asesor_mostrador_inside_autocommit_block(self):
        with patch.object(role_enum_migration, "op") as op_mock:
            role_enum_migration.upgrade()

        op_mock.get_context.return_value.autocommit_block.assert_called_once()
        op_mock.execute.assert_called_once()
        (executed_arg,), _ = op_mock.execute.call_args
        assert (
            "ALTER TYPE motored_role ADD VALUE IF NOT EXISTS 'ASESOR_MOSTRADOR'"
            in str(executed_arg)
        )


class TestLoreRoleEnumDowngrade:
    def test_downgrade_is_a_documented_no_op(self):
        with patch.object(role_enum_migration, "op") as op_mock:
            role_enum_migration.downgrade()
        op_mock.execute.assert_not_called()
        op_mock.get_context.assert_not_called()


class TestLoreBotSchemaUpgradeUsuario:
    def test_adds_telegram_id_phone_status_and_resolution_columns(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        added = _added_columns(op_mock, "usuario")
        assert added["telegram_id"].nullable is True
        assert isinstance(added["telegram_id"].type, sa.BigInteger)
        assert added["phone"].nullable is True
        assert added["status"].nullable is False
        assert added["status"].server_default.arg == "approved"
        assert added["resuelto_por"].nullable is True
        assert added["resuelto_en"].nullable is True
        assert added["codigo_vinculacion_hash"].nullable is True
        assert added["codigo_vinculacion_expira"].nullable is True

    def test_creates_unique_constraint_on_telegram_id(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        calls = [
            c for c in op_mock.create_unique_constraint.call_args_list
            if c.args[1] == "usuario"
        ]
        assert len(calls) == 1
        assert calls[0].args[0] == "uq_usuario_telegram_id"
        assert list(calls[0].args[2]) == ["telegram_id"]

    def test_creates_foreign_key_for_resuelto_por(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        op_mock.create_foreign_key.assert_any_call(
            "fk_usuario_resuelto_por_usuario", "usuario", "usuario", ["resuelto_por"], ["id"],
        )

    def test_makes_email_and_hashed_password_nullable(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        op_mock.alter_column.assert_any_call("usuario", "email", nullable=True)
        op_mock.alter_column.assert_any_call("usuario", "hashed_password", nullable=True)

    def test_adds_status_and_credenciales_web_checks(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        checks = _check_constraint_names(op_mock, "usuario")
        assert "pending" in checks["ck_usuario_status"]
        assert "approved" in checks["ck_usuario_status"]
        assert "rejected" in checks["ck_usuario_status"]
        assert "ASESOR_MOSTRADOR" in checks["ck_usuario_credenciales_web"]
        assert "hashed_password IS NOT NULL" in checks["ck_usuario_credenciales_web"]


class TestLoreBotSchemaUpgradeCargaArchivo:
    def test_adds_origen_defaulting_to_excel(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        added = _added_columns(op_mock, "carga_archivo")
        assert added["origen"].nullable is False
        assert added["origen"].server_default.arg == "EXCEL"

    def test_file_columns_become_nullable(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        for column_name in ("nombre_archivo", "hash_sha256", "ruta_objeto", "bytes"):
            op_mock.alter_column.assert_any_call("carga_archivo", column_name, nullable=True)

    def test_adds_origin_and_bot_tipo_checks(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        checks = _check_constraint_names(op_mock, "carga_archivo")
        assert "EXCEL" in checks["ck_carga_archivo_origen"]
        assert "BOT" in checks["ck_carga_archivo_origen"]
        assert "nombre_archivo IS NOT NULL" in checks["ck_carga_archivo_archivo_por_origen"]
        assert "DEMANDA_PERDIDA" in checks["ck_carga_archivo_bot_tipo"]

    def test_creates_origen_tipo_created_at_index(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        op_mock.create_index.assert_any_call(
            "ix_carga_archivo_origen_tipo_created_at",
            "carga_archivo", ["origen", "tipo", "created_at"], unique=False,
        )


class TestLoreBotSchemaUpgradeDemandaPerdida:
    def test_adds_origen_defaulting_to_excel(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        added = _added_columns(op_mock, "demanda_perdida")
        assert added["origen"].nullable is False
        assert added["origen"].server_default.arg == "EXCEL"

    def test_widens_unique_constraint_to_include_origen(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        op_mock.drop_constraint.assert_any_call(
            "uq_demanda_perdida_fecha_sucursal_referencia", "demanda_perdida", type_="unique",
        )
        create_calls = [
            c for c in op_mock.create_unique_constraint.call_args_list
            if c.args[1] == "demanda_perdida"
        ]
        assert len(create_calls) == 1
        assert create_calls[0].args[0] == "uq_demanda_perdida_fecha_sucursal_referencia_origen"
        assert list(create_calls[0].args[2]) == [
            "fecha", "sucursal_id", "referencia_id", "origen",
        ]


class TestLoreBotSchemaUpgradeBotLinea:
    def test_creates_demanda_perdida_bot_linea_table(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        table_calls = [
            c for c in op_mock.create_table.call_args_list
            if c.args[0] == "demanda_perdida_bot_linea"
        ]
        assert len(table_calls) == 1

        # Bind the captured column/constraint definitions to a real Table so
        # string-named constraints (e.g. UniqueConstraint("carga_id", ...))
        # resolve their `.columns` the same way a live `op.create_table` call
        # would -- they stay unbound/empty otherwise.
        table = sa.Table(
            "demanda_perdida_bot_linea", sa.MetaData(), *table_calls[0].args[1:],
        )

        for name in (
            "id", "carga_id", "usuario_id", "fecha", "sucursal_id",
            "referencia_id", "cantidad", "estado", "created_at", "updated_at",
        ):
            assert name in table.c
        assert table.c.cantidad.nullable is False
        assert table.c.estado.nullable is False
        assert table.c.estado.server_default.arg == "ACTIVA"

        unique = [c for c in table.constraints if isinstance(c, sa.UniqueConstraint)]
        assert len(unique) == 1
        assert {col.name for col in unique[0].columns} == {"carga_id", "referencia_id"}

        checks = {
            c.name: str(c.sqltext)
            for c in table.constraints if isinstance(c, sa.CheckConstraint)
        }
        assert "cantidad > 0" in checks.values()
        assert any("ACTIVA" in text and "ANULADA" in text for text in checks.values())

    def test_creates_usuario_and_sucursal_fecha_indexes(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.upgrade()

        op_mock.create_index.assert_any_call(
            "ix_demanda_perdida_bot_linea_usuario_id_fecha",
            "demanda_perdida_bot_linea", ["usuario_id", "fecha"], unique=False,
        )
        op_mock.create_index.assert_any_call(
            "ix_demanda_perdida_bot_linea_sucursal_id_fecha",
            "demanda_perdida_bot_linea", ["sucursal_id", "fecha"], unique=False,
        )


class TestLoreBotSchemaDowngrade:
    def test_deletes_bot_data_in_fk_order_before_dropping_the_ledger_table(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.downgrade()

        executed = [str(c.args[0]) for c in op_mock.execute.call_args_list]
        demanda_idx = next(i for i, s in enumerate(executed) if "DELETE FROM demanda_perdida " in s)
        ledger_idx = next(i for i, s in enumerate(executed) if "demanda_perdida_bot_linea" in s)
        carga_idx = next(i for i, s in enumerate(executed) if "DELETE FROM carga_archivo" in s)
        usuario_sucursal_idx = next(i for i, s in enumerate(executed) if "usuario_sucursal" in s)
        usuario_idx = next(
            i for i, s in enumerate(executed)
            if s.strip().startswith("DELETE FROM usuario ")
        )
        assert demanda_idx < ledger_idx < carga_idx < usuario_sucursal_idx < usuario_idx

    def test_drops_bot_linea_table(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.downgrade()

        op_mock.drop_table.assert_any_call("demanda_perdida_bot_linea")

    def test_restores_old_demanda_perdida_unique_constraint(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.downgrade()

        op_mock.create_unique_constraint.assert_any_call(
            "uq_demanda_perdida_fecha_sucursal_referencia",
            "demanda_perdida", ["fecha", "sucursal_id", "referencia_id"],
        )
        op_mock.drop_column.assert_any_call("demanda_perdida", "origen")

    def test_restores_not_null_on_carga_archivo_file_columns(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.downgrade()

        for column_name in ("nombre_archivo", "hash_sha256", "ruta_objeto", "bytes"):
            op_mock.alter_column.assert_any_call("carga_archivo", column_name, nullable=False)
        op_mock.drop_column.assert_any_call("carga_archivo", "origen")

    def test_restores_not_null_on_usuario_credentials_and_drops_new_columns(self):
        with patch.object(bot_schema_migration, "op") as op_mock:
            bot_schema_migration.downgrade()

        op_mock.alter_column.assert_any_call("usuario", "email", nullable=False)
        op_mock.alter_column.assert_any_call("usuario", "hashed_password", nullable=False)
        for column_name in (
            "telegram_id", "phone", "status", "resuelto_por", "resuelto_en",
            "codigo_vinculacion_hash", "codigo_vinculacion_expira",
        ):
            op_mock.drop_column.assert_any_call("usuario", column_name)
