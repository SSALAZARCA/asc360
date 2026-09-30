"""The container start script must also apply the Motored Alembic chain.

Deploys are automatic on push to main (Coolify rebuilds the backend and runs
`scripts/start.sh`). Until now the script only ran the asc360 chain, so
Motored schema changes never reached production on their own. These static
checks pin the contract: the Motored chain runs on every start, only when
Motored is configured, and a Motored failure never stops the shared backend
(asc360 and Motored share one container).
"""
from pathlib import Path

_START_SH = Path(__file__).resolve().parents[2] / "scripts" / "start.sh"


def _script() -> str:
    return _START_SH.read_text(encoding="utf-8")


def test_start_script_runs_the_motored_chain():
    assert "alembic -c alembic_motored.ini upgrade head" in _script()


def test_motored_chain_runs_after_asc360_chain_and_before_server():
    script = _script()
    asc360 = script.index("alembic upgrade head")
    motored = script.index("alembic -c alembic_motored.ini upgrade head")
    server = script.index("exec uvicorn")
    assert asc360 < motored < server


def test_motored_chain_is_skipped_when_motored_is_not_configured():
    assert "settings.MOTORED_DATABASE_URL" in _script()


def test_motored_failure_does_not_abort_the_shared_backend():
    line = next(
        line for line in _script().splitlines()
        if "alembic -c alembic_motored.ini upgrade head" in line
    )
    assert "||" in line


def test_start_script_never_echoes_the_raw_database_url():
    """The URL carries the DB password and would land in every deploy log."""
    for line in _script().splitlines():
        if line.lstrip().startswith("#"):
            continue
        if "echo" in line or "printf" in line:
            assert "$DATABASE_URL" not in line and "${DATABASE_URL" not in line, line
