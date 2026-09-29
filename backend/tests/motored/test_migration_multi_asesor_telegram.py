"""
Migration `a3f7c91d2e58` (odd/tasks/lore-multi-asesor-telegram.md, T1): lets
several `usuario` rows share one `telegram_id`.

Same approach as `test_migration_lore_bot_schema.py`: loaded by path and
exercised against a mocked `op`, plus a model/DDL agreement check.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import Index, UniqueConstraint

from app.motored.models.usuario import Usuario

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"


def _load():
    spec = importlib.util.spec_from_file_location(
        "sdd_multi_asesor_telegram_migration",
        _VERSIONS_DIR / "a3f7c91d2e58_multi_asesor_telegram.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load()


def _run(direction: str):
    with patch.object(migration, "op") as op_mock:
        getattr(migration, direction)()
    return op_mock


def _indexes(op_mock) -> dict:
    return {c.args[0]: c for c in op_mock.create_index.call_args_list}


def test_revision_chains_onto_the_current_head():
    assert migration.revision == "a3f7c91d2e58"
    assert migration.down_revision == "5c2e8a1f9b47"


def test_upgrade_sets_a_lock_timeout_before_touching_the_table():
    op_mock = _run("upgrade")

    primero = op_mock.execute.call_args_list[0].args[0]
    assert "lock_timeout" in str(primero)


def test_upgrade_drops_the_unique_constraint_on_telegram_id():
    op_mock = _run("upgrade")

    op_mock.drop_constraint.assert_called_once_with(
        "uq_usuario_telegram_id", "usuario", type_="unique"
    )


def test_upgrade_adds_a_plain_index_on_telegram_id():
    indices = _indexes(_run("upgrade"))

    plain = indices["ix_usuario_telegram_id"]
    assert plain.args[1] == "usuario"
    assert list(plain.args[2]) == ["telegram_id"]
    assert not plain.kwargs.get("unique")


def test_upgrade_adds_a_partial_unique_index_on_telegram_and_phone_excluding_rejected():
    indices = _indexes(_run("upgrade"))

    parcial = indices["uq_usuario_telegram_phone_activo"]
    assert list(parcial.args[2]) == ["telegram_id", "phone"]
    assert parcial.kwargs["unique"] is True
    assert "rejected" in str(parcial.kwargs["postgresql_where"])
    assert "<>" in str(parcial.kwargs["postgresql_where"])


def test_upgrade_keeps_admins_from_sharing_a_telegram_with_another_admin():
    indices = _indexes(_run("upgrade"))

    admin = indices["uq_usuario_telegram_admin"]
    assert list(admin.args[2]) == ["telegram_id"]
    assert admin.kwargs["unique"] is True
    assert "ADMIN" in str(admin.kwargs["postgresql_where"])


def test_downgrade_is_the_inverse_and_restores_the_unique_constraint():
    op_mock = _run("downgrade")

    dropped = {c.args[0] for c in op_mock.drop_index.call_args_list}
    assert dropped == {
        "uq_usuario_telegram_admin", "uq_usuario_telegram_phone_activo", "ix_usuario_telegram_id",
    }
    op_mock.create_unique_constraint.assert_called_once_with(
        "uq_usuario_telegram_id", "usuario", ["telegram_id"]
    )


def test_model_no_longer_declares_the_unique_constraint_on_telegram_id():
    unicas = [c for c in Usuario.__table__.constraints if isinstance(c, UniqueConstraint)]
    assert not [c for c in unicas if {col.name for col in c.columns} == {"telegram_id"}]


def test_model_declares_the_same_indexes_as_the_migration():
    por_nombre = {i.name: i for i in Usuario.__table__.indexes if isinstance(i, Index)}

    assert {"ix_usuario_telegram_id", "uq_usuario_telegram_phone_activo", "uq_usuario_telegram_admin"} <= set(por_nombre)
    assert por_nombre["ix_usuario_telegram_id"].unique is False
    assert por_nombre["uq_usuario_telegram_phone_activo"].unique is True
    assert [c.name for c in por_nombre["uq_usuario_telegram_phone_activo"].columns] == [
        "telegram_id", "phone",
    ]
