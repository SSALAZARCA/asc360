"""
Role-gate tests for `GET /api/v1/imports/shipment-orders/export`
(`export_shipment_orders`, `imports.py`) -- the Pedidos tab's "Exportar
Excel" button.

2026-08-24 business decision: this endpoint was widened from
`_require_superadmin` to `_require_imports_editor` (superadmin | proveedor |
administrativo) -- the Pedidos tab itself is already visible to all three
via `ALL_TABS`' `roles: null` in `ImportsTabs.js`, so this reuses the shared
helper instead of a narrower inline check (matching what the frontend
already exposes, per the task's own decision rule).

No prior test file covered this endpoint's role gate at all.
"""
from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor


def test_technician_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_imports_editor(role="technician"), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/shipment-orders/export")

    assert response.status_code == 403
    assert response.json()["detail"] == "Sin permisos para el módulo de importaciones"
    assert fake_db.executed_statements == []


def test_client_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_imports_editor(role="client"), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/shipment-orders/export")

    assert response.status_code == 403
    assert fake_db.executed_statements == []


def test_administrativo_now_gets_200():
    """2026-08-24 business decision: administrativo now matches superadmin
    on this Excel export (previously blocked)."""
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(role="administrativo"), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/shipment-orders/export")

    assert response.status_code == 200


def test_proveedor_still_gets_200_unchanged():
    """Regression guard: `proveedor` already had access via
    `_require_imports_editor` at other imports endpoints (e.g. the
    reconciliation export) -- this widening must not have narrowed that."""
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(role="proveedor"), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/shipment-orders/export")

    assert response.status_code == 200


def test_superadmin_still_gets_200_unchanged():
    fake_db = FakeAsyncSession(execute_queue=[[]])

    with make_test_client(current_user=make_imports_editor(role="superadmin"), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/shipment-orders/export")

    assert response.status_code == 200
