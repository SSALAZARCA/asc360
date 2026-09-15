"""
Phase 1 "Cimientos" — `app.motored.database`.

Two real behavioral contracts are under test here (per
sdd/motored-pedidos-cimientos design, ADR-4 and ADR-5):

1. The engine is built LAZILY. Importing `app.motored.database` (and by
   extension `app.main.app`, once a later slice mounts the Motored router)
   must never attempt to create an engine or connect to anything, even with
   `MOTORED_DATABASE_URL` empty. If this regresses, `tests/conftest.py`
   (which imports `app.main.app`) breaks for the entire existing suite.

2. `get_motored_db` does NOT auto-commit on clean exit — unlike
   `app.database.get_db`. A caller that opens a session, writes, and lets
   the generator exit cleanly without an explicit `commit()` must see that
   write rolled back. Later slices (the all-or-nothing bulk upload) depend
   on this being true.

No live Postgres exists yet for Motored, so behavior #2 is exercised
against a throwaway file-backed SQLite database via `aiosqlite` — enough to
prove the session/transaction contract of the generator itself, which is
independent of the SQL dialect.
"""
import sqlalchemy as sa

from app.config import settings
from app.motored import database as motored_database

# A minimal ad-hoc table — Phase 1 has no Motored models yet (those land in
# Phase 3), so this test only needs *some* table to prove commit semantics.
_metadata = sa.MetaData()
_demo_table = sa.Table(
    "motored_db_contract_demo",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("value", sa.String),
)


def test_import_does_not_build_or_connect_an_engine():
    """Importing the module must be a pure, side-effect-free declaration."""
    assert motored_database.get_motored_engine.cache_info().currsize == 0


async def test_get_motored_db_does_not_autocommit_on_clean_exit(tmp_path, monkeypatch):
    db_path = tmp_path / "motored_contract.db"
    monkeypatch.setattr(settings, "MOTORED_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    motored_database.get_motored_engine.cache_clear()

    engine = motored_database.get_motored_engine()
    async with engine.begin() as conn:
        await conn.run_sync(_metadata.create_all)

    try:
        gen = motored_database.get_motored_db()
        session = await gen.__anext__()
        await session.execute(sa.insert(_demo_table).values(id=1, value="uncommitted"))
        # Clean exit — the caller never called session.commit().
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

        # A fresh connection against the same engine must see NOTHING: the
        # write above must have been rolled back, not silently persisted.
        async with engine.connect() as conn:
            result = await conn.execute(sa.select(_demo_table))
            rows = result.fetchall()
        assert rows == []
    finally:
        await engine.dispose()
        motored_database.get_motored_engine.cache_clear()
