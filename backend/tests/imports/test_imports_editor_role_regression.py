"""
Regression test locking in the imports-editor role gotcha (see design.md for
`sdd/imports-oversized-functions-refactor-tier1`): `_require_imports_editor`
requires `role in ("superadmin", "proveedor", "administrativo")`. The
generic `make_actor()` helper (used by non-imports tests) defaults to
role=`jefe_taller`, which is NOT an editor and 403s on every imports
endpoint. Future Tier 1/2/3 tests MUST use `make_imports_editor()` instead
of `make_actor()` when hitting imports HTTP endpoints — this test proves
that difference is real behavior, not just documentation.

Uses `list_spare_part_lots` (`GET /api/v1/imports/spare-part-lots`) as the
representative endpoint since it is the first one covered by Phase 1.
"""
from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_actor, make_imports_editor


def test_default_actor_role_gets_403_on_spare_part_lots():
    """`make_actor()` (role=jefe_taller) is NOT an imports editor -> 403."""
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/spare-part-lots")

    assert response.status_code == 403
    assert response.json()["detail"] == "Sin permisos para el módulo de importaciones"


def test_imports_editor_role_does_not_get_403_on_spare_part_lots():
    """`make_imports_editor()` (role=administrativo) passes the editor gate."""
    # One `select(SparePartLot)...` execute call; no lots -> no follow-up
    # rotation_map query (list_spare_part_lots skips it when `all_part_numbers`
    # is empty), so a single empty-list queue entry is enough.
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/spare-part-lots")

    assert response.status_code == 200
    assert response.json() == []
