"""
Regression tests for the role guard on `list_moto_observations`
(`GET /api/v1/imports/moto-observations`, `imports.py`).

Bug fixed: this endpoint had no permission dependency at all — any
authenticated user, any role, could list predefined moto observations.
Its exact sibling `list_moto_locations` already requires
`_require_imports_editor` (superadmin/administrativo/proveedor); this
closes the same gate here for consistency.
"""
import uuid

from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_actor, make_imports_editor


def test_non_editor_role_gets_403():
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/moto-observations")

    assert response.status_code == 403
    assert fake_db.executed_statements == []


def test_imports_editor_can_list():
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/moto-observations")

    assert response.status_code == 200
    assert response.json() == []
