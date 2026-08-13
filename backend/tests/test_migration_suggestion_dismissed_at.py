"""
Tests for the one migration in `sdd/parts-description-source-of-truth`
(design D18): `d1e2f3a4b5c6_add_suggestion_dismissed_at.py`.

No live test DATABASE_URL exists in this repo (see
`tests/remisiones/test_availability_view.py`'s docstring) -- these are NOT
a live `alembic upgrade head` / `downgrade -1` round trip against a real
Postgres. Instead they load the migration module directly by file path
(the `alembic/` directory is a script-location, not an importable package
-- `alembic.versions` would collide with the installed `alembic` pip
package) and assert the DDL calls it issues: nullable, no `server_default`
(so an upgrade changes zero existing rows), and that `upgrade`/`downgrade`
are exact inverses of each other on the same column. Also asserts the
model column (`app/models/parts_manual.py`) agrees with the migration's
DDL, per the Testing Strategy's "at minimum assert model/DDL agreement"
guidance for migrations in this repo.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.parts_manual import PartsReference

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "d1e2f3a4b5c6_add_suggestion_dismissed_at.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "sdd_suggestion_dismissed_at_migration", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


class TestMigrationRevisionChain:
    def test_revision_ids(self):
        assert migration.revision == "d1e2f3a4b5c6"

    def test_down_revision_is_current_alembic_head_at_design_time(self):
        # Re-verified live via `alembic heads` before writing this migration
        # (design D18 explicitly calls out the tree has had parallel heads
        # before) -- pins that this migration was chained onto the correct,
        # single head, not a stale one.
        assert migration.down_revision == "c9d0e1f2a3b4"


class TestMigrationUpgrade:
    def test_adds_nullable_column_with_no_server_default(self):
        """Nullable, no server_default -> zero existing rows change on
        deploy (the proposal's zero-migration-impact success criterion,
        satisfied for the one exception D18 carves out)."""
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()

        op_mock.add_column.assert_called_once()
        table_name, column = op_mock.add_column.call_args[0]
        assert table_name == "parts_references"
        assert column.name == "suggestion_dismissed_at"
        assert column.nullable is True
        assert column.server_default is None


class TestMigrationDowngrade:
    def test_drops_the_same_column_upgrade_added(self):
        with patch.object(migration, "op") as op_mock:
            migration.downgrade()

        op_mock.drop_column.assert_called_once_with(
            "parts_references", "suggestion_dismissed_at"
        )


class TestModelDDLAgreement:
    def test_model_column_matches_migration_column_shape(self):
        col = PartsReference.__table__.columns["suggestion_dismissed_at"]
        assert col.nullable is True
        assert col.server_default is None
        assert col.type.python_type is __import__("datetime").datetime
