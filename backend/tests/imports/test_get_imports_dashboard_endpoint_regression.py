"""
RED regression tests for `get_imports_dashboard`
(`GET /api/v1/imports/dashboard`) capturing CURRENT (pre-refactor) behavior —
Phase 2 of `sdd/imports-oversized-functions-refactor-tier1`.

These exercise the endpoint via the HTTP harness (`make_test_client`) +
`FakeAsyncSession` and MUST keep passing unchanged after the extraction
(delegates to `_query_status_counts`/`_resolve_status_map`/
`_query_backorder_totals`/`_query_by_cycle`/`_build_upcoming_etas`) — same
file, same assertions, only the endpoint's internals change.

Locked-in behaviors (read directly off the pre-refactor source,
`backend/app/api/v1/imports.py` lines 2053-2186, before writing any test):
  - `motos_st_map`/`sp_st_map` status-count queries ALWAYS both run,
    regardless of `is_spare_part` — `moto_orders`/`sp_orders` in the
    response are therefore always computed from BOTH maps, independent of
    the `is_spare_part` filter.
  - `status_map` (the KPI counters) is: `motos_st_map` when
    `is_spare_part=False`, `sp_st_map` when `is_spare_part=True`, and a
    per-key SUM of both maps when `is_spare_part` is omitted (`None`).
  - The backorder block (3 extra DB calls) is entirely SKIPPED when
    `is_spare_part=False` — `active_backorders`/`total_backorder_units`/
    `total_declared_value_usd` are hardcoded to `0`/`0`/`0.0`.
  - `total_declared_value_usd`'s query sums `SparePartLot.total_declared_value`
    with NO filter on `is_spare_part` at all (pre-existing behavior, not this
    change's concern — preserved byte-for-byte).
  - The "by cycle" query switches between a `DISTINCT pi_number` count (when
    `is_spare_part=False`) and a plain `COUNT(*)` (otherwise), the latter
    filtered by `is_spare_part` only when it is not `None`.
  - The "upcoming ETAs" query ALWAYS runs (independent of `is_spare_part`
    short-circuits above), excludes `computed_status == "completado"`, is
    windowed to the next 60 days, and limited to 10 rows.

Call-count-per-branch is locked in structurally: `FakeAsyncSession` raises
if `execute()` is called more times than queued, so an execute_queue with
the wrong number of entries for a given `is_spare_part` value fails loudly
— this is intentional and doubles as a regression signal for the
extraction's DB-call ordering.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_actor,
    make_imports_editor,
)


def test_non_editor_role_gets_403():
    """`make_actor()` (role=jefe_taller) is not an imports editor -> 403, no DB call."""
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/dashboard")

    assert response.status_code == 403
    assert response.json()["detail"] == "Sin permisos para el módulo de importaciones"
    assert fake_db.executed_statements == []


def test_is_spare_part_none_merges_status_maps_and_includes_backorders():
    """
    Default (`is_spare_part` omitted): status_map is the per-key SUM of
    motos+sp maps; backorder block runs (3 extra calls); cycle branch uses
    the plain COUNT(*) query (else-branch); 7 total execute() calls.
    """
    fake_db = FakeAsyncSession(execute_queue=[
        [SimpleNamespace(computed_status="en_preparacion", cnt=2), SimpleNamespace(computed_status="completado", cnt=5)],
        [SimpleNamespace(computed_status="en_preparacion", cnt=3), SimpleNamespace(computed_status="backorder", cnt=1)],
        [4],
        [10],
        [1234.5],
        [SimpleNamespace(cycle="2026-01", cnt=6)],
        [],
    ])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["en_preparacion"] == 5  # 2 (motos) + 3 (sp)
    assert body["completado"] == 5      # 5 (motos) + 0 (sp, key absent)
    assert body["backorder"] == 1       # 0 (motos, key absent) + 1 (sp)
    assert body["total_active"] == 6    # en_preparacion(5) + backorder(1), completado excluded
    assert body["moto_orders"] == 2     # motos map excluding completado, ALWAYS both maps
    assert body["sp_orders"] == 4       # sp map excluding completado: en_preparacion(3)+backorder(1)
    assert body["active_backorders"] == 4
    assert body["total_backorder_units"] == 10
    assert body["total_declared_value_usd"] == 1234.5
    assert body["by_cycle"] == [{"cycle": "2026-01", "count": 6}]
    assert body["upcoming_etas"] == []
    assert len(fake_db.executed_statements) == 7


def test_is_spare_part_true_uses_sp_status_map_only():
    """`is_spare_part=True`: status_map == sp map only; backorder block still runs (not False)."""
    fake_db = FakeAsyncSession(execute_queue=[
        [SimpleNamespace(computed_status="en_preparacion", cnt=2)],
        [SimpleNamespace(computed_status="en_transito", cnt=7)],
        [0],
        [0],
        [0.0],
        [],
        [],
    ])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/dashboard", params={"is_spare_part": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body["en_preparacion"] == 0   # sp map has no "en_preparacion" key
    assert body["en_transito"] == 7      # taken purely from sp map
    assert body["moto_orders"] == 2      # still computed from motos map regardless of filter
    assert body["sp_orders"] == 7
    assert len(fake_db.executed_statements) == 7


def test_is_spare_part_false_skips_backorder_queries_and_uses_distinct_cycle_branch():
    """
    `is_spare_part=False`: status_map == motos map only; backorder block is
    SKIPPED entirely (hardcoded zeros, no extra DB calls); only 4 total
    execute() calls (2 status maps + cycle + eta).
    """
    fake_db = FakeAsyncSession(execute_queue=[
        [SimpleNamespace(computed_status="en_transito", cnt=9)],
        [SimpleNamespace(computed_status="en_transito", cnt=100)],
        [SimpleNamespace(cycle="2025-12", cnt=3)],
        [],
    ])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/dashboard", params={"is_spare_part": "false"})

    assert response.status_code == 200
    body = response.json()
    assert body["en_transito"] == 9  # motos map only, sp map's 100 ignored
    assert body["moto_orders"] == 9
    assert body["sp_orders"] == 100  # always computed from sp map, independent of the filter
    assert body["active_backorders"] == 0
    assert body["total_backorder_units"] == 0
    assert body["total_declared_value_usd"] == 0.0
    assert body["by_cycle"] == [{"cycle": "2025-12", "count": 3}]
    assert len(fake_db.executed_statements) == 4


def test_upcoming_etas_are_serialized_with_expected_fields():
    """Locks in the exact upcoming_etas serialization shape."""
    order_id = uuid.uuid4()
    eta_dt = datetime(2026, 8, 1, 12, 0, 0)
    eta_row = SimpleNamespace(
        id=order_id,
        pi_number="PI-1",
        model="MODEL-X",
        eta=eta_dt,
        eta_raw="01/08/2026",
        qty=10,
        is_spare_part=False,
        computed_status="en_transito",
        cycle="2026-Q3",
    )
    fake_db = FakeAsyncSession(execute_queue=[[], [], [0], [0], [0.0], [], [eta_row]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/dashboard")

    assert response.status_code == 200
    assert response.json()["upcoming_etas"] == [{
        "id": str(order_id),
        "pi_number": "PI-1",
        "model": "MODEL-X",
        "eta": eta_dt.isoformat(),
        "eta_raw": "01/08/2026",
        "qty": 10,
        "is_spare_part": False,
        "computed_status": "en_transito",
        "cycle": "2026-Q3",
    }]


def test_upcoming_etas_query_excludes_completado_and_limits_to_10():
    """
    Locks in the 60-day-ETA-window query's structural shape: excludes
    `completado` (NOT IN clause) and caps results at 10 rows (LIMIT bind).
    """
    fake_db = FakeAsyncSession(execute_queue=[[], [], [0], [0], [0.0], [], []])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/dashboard")

    assert response.status_code == 200
    eta_stmt = fake_db.executed_statements[-1]
    sql = str(eta_stmt)
    assert "NOT IN" in sql
    compiled = eta_stmt.compile()
    assert 10 in compiled.params.values()
