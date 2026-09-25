"""
Phase 6 "Demanda perdida — bot write path" (sdd/motored-ventas-perdidas-bot,
task 6.14; design D1) — HTTP-layer coverage for `GET /api/motored/
demanda-perdida/cobertura-bot`.

Real `motored_client` + `override_motored_db`/`override_motored_user`
convention (same as `test_cargas_api.py`'s SUCURSAL-scoping tests). The
SUCURSAL-scoping assertions use statement introspection (compiled bind
values), not a `_FilteringFakeSession`, because the aggregation query
returns plain `(sucursal_id, fecha)` tuples -- a real `.in_()` filter is
applied by Postgres, not by row-level Python filtering.
"""
import uuid
from datetime import date

import pytest

from app.config import settings
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

URL = "/api/motored/demanda-perdida/cobertura-bot"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "cobertura-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "cobertura-test-asc360-secret")


def _in_clause_values(stmt) -> list:
    """Extracts the bound values of an `.in_()` clause from a compiled
    `WHERE`, if present -- proves REAL scoping, not just "some rows came
    back". Only matches a clause whose operator is `in_op` (a plain
    equality clause like `estado == 'ACTIVA'` also has a `right.value`,
    but it's a scalar string, not an "in" list)."""
    whereclause = getattr(stmt, "whereclause", None)
    if whereclause is None:
        return []
    for clausula in getattr(whereclause, "clauses", [whereclause]):
        operador = getattr(clausula, "operator", None)
        if getattr(operador, "__name__", "") != "in_op":
            continue
        right = getattr(clausula, "right", None)
        if right is not None and hasattr(right, "value"):
            return list(right.value)
    return []


def test_cobertura_bot_admin_sees_all_sucursales_unscoped(motored_client):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    sucursal_a, sucursal_b = uuid.uuid4(), uuid.uuid4()
    session = FakeAsyncSession(
        execute_queue=[[], [(sucursal_a, date(2026, 9, 20)), (sucursal_b, date(2026, 9, 22))]]
    )
    override_motored_db(session)

    response = motored_client.get(URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert {row["sucursal_id"] for row in body} == {str(sucursal_a), str(sucursal_b)}
    # No sucursal_id IN (...) filter was applied for a non-SUCURSAL role.
    stmt = session.executed_statements[-1]
    assert _in_clause_values(stmt) == []


def test_cobertura_bot_sucursal_role_scoped_to_own_sucursales(motored_client):
    propia = uuid.uuid4()
    override_motored_user(
        MotoredUser(user_id=str(uuid.uuid4()), role="SUCURSAL", sucursal_ids=[str(propia)])
    )
    session = FakeAsyncSession(execute_queue=[[], [(propia, date(2026, 9, 24))]])
    override_motored_db(session)

    response = motored_client.get(URL)

    assert response.status_code == 200, response.text
    assert response.json() == [{"sucursal_id": str(propia), "ultima_fecha_bot": "2026-09-24"}]
    stmt = session.executed_statements[-1]
    assert _in_clause_values(stmt) == [propia]


def test_cobertura_bot_sucursal_role_with_no_own_sucursales_returns_empty_without_querying(
    motored_client,
):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="SUCURSAL", sucursal_ids=[]))
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    response = motored_client.get(URL)

    assert response.status_code == 200, response.text
    assert response.json() == []
    assert len(session.executed_statements) == 1  # only the readiness probe
