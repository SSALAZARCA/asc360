"""
Post-verify fix -- SUCURSAL branch scoping for `list_maestro`/`get_maestro`
(sdd/motored-pedidos-cimientos). Closes the CRITICAL gap found by
`sdd-verify` (`sdd/motored-pedidos-cimientos/verify-report`): the spec's
`motored-auth` capability, "Requirement: SUCURSAL branch scoping" (2 GWT
scenarios -- "SUCURSAL cannot read another branch's masters" / "SUCURSAL
can read their own branch's data"), the proposal's business-rules table
("Role `SUCURSAL` sees only its own branches ... test T19"), and the
proposal's Success Criteria ("SUCURSAL provably cannot read another
branch's masters") were never actually implemented.

Scope decision (mirrored in `app/motored/api/maestros.py`'s module
docstring): only `sucursal`/`bodega` are tied to a specific branch and are
therefore scoped for role SUCURSAL. `proveedor`/`referencia` are
branch-agnostic catalog data shared across all ~47 branches -- explicitly
NOT filtered, proven by `test_proveedor_list_is_not_filtered_for_sucursal_role`
/ `test_referencia_list_is_not_filtered_for_sucursal_role` below.

Uses the same real `TestClient(app)` + `override_motored_user`/
`override_motored_db` pattern as `test_rbac_matrix.py`. Filtering is applied
in Python over the full row set returned by the (fake) query -- not via a
SQL `WHERE` clause -- specifically so it is testable black-box: a queue
holding BOTH branches' rows lets these tests fail (RED) against the
original unfiltered code and pass (GREEN) once `list_maestro`/`get_maestro`
apply `_in_scope`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.bodega import Bodega
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

B1_ID = uuid.uuid4()
B2_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "sucursal-scoping-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "sucursal-scoping-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _sucursal(sucursal_id, nombre):
    return Sucursal(
        id=sucursal_id, nombre=nombre, sic="SIC-" + nombre, dias_seguridad="2.5", activa=True
    )


def _bodega(codigo, sucursal_id, bodega_id=None):
    return Bodega(
        id=bodega_id or uuid.uuid4(), codigo=codigo, sucursal_id=sucursal_id, activa=True
    )


def _client_scoped_to(*branch_ids, execute_queue) -> TestClient:
    user = MotoredUser(
        user_id=str(uuid.uuid4()), role="SUCURSAL", sucursal_ids=[str(b) for b in branch_ids]
    )
    override_motored_user(user)
    override_motored_db(FakeAsyncSession(execute_queue=execute_queue))
    return TestClient(app)


def _client_as(role: str, execute_queue) -> TestClient:
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(FakeAsyncSession(execute_queue=execute_queue))
    return TestClient(app)


# --- 1. SUCURSAL list is scoped to own branch (sucursales) -----------------


def test_sucursal_user_lists_only_own_branch_sucursales():
    rows = [_sucursal(B1_ID, "B1"), _sucursal(B2_ID, "B2")]
    # First queue slot is `get_motored_db_or_503`'s `SELECT 1` connectivity
    # probe (harmless empty result); the second is the real list query.
    client = _client_scoped_to(B1_ID, execute_queue=[[], rows])
    response = client.get("/api/motored/maestros/sucursales")
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert ids == {str(B1_ID)}


# --- 2. Direct GET of another branch's sucursal is a 404, not a 403 --------


def test_sucursal_user_get_other_branch_sucursal_is_404_not_403():
    other_branch = _sucursal(B2_ID, "B2")
    client = _client_scoped_to(B1_ID, execute_queue=[[], [other_branch]])
    response = client.get(f"/api/motored/maestros/sucursales/{B2_ID}")
    assert response.status_code == 404
    assert "B2" not in response.text


# --- 3. Same two behaviors mirrored for bodegas -----------------------------


def test_sucursal_user_lists_only_own_branch_bodegas():
    rows = [_bodega("BOD-B1", B1_ID), _bodega("BOD-B2", B2_ID)]
    client = _client_scoped_to(B1_ID, execute_queue=[[], rows])
    response = client.get("/api/motored/maestros/bodegas")
    assert response.status_code == 200
    codigos = {row["codigo"] for row in response.json()}
    assert codigos == {"BOD-B1"}


def test_sucursal_user_get_other_branch_bodega_is_404_not_403():
    other_bodega = _bodega("BOD-B2", B2_ID)
    client = _client_scoped_to(B1_ID, execute_queue=[[], [other_bodega]])
    response = client.get(f"/api/motored/maestros/bodegas/{other_bodega.id}")
    assert response.status_code == 404
    assert "BOD-B2" not in response.text


# --- 4. SUCURSAL user CAN see their own branch's data -----------------------


def test_sucursal_user_can_read_own_branch_sucursal_and_bodega():
    own_sucursal = _sucursal(B1_ID, "B1")
    own_bodega = _bodega("BOD-B1", B1_ID)
    client = _client_scoped_to(
        B1_ID, execute_queue=[[], [own_sucursal], [], [own_bodega]]
    )

    sucursal_response = client.get(f"/api/motored/maestros/sucursales/{B1_ID}")
    assert sucursal_response.status_code == 200
    assert sucursal_response.json()["nombre"] == "B1"

    bodega_response = client.get(f"/api/motored/maestros/bodegas/{own_bodega.id}")
    assert bodega_response.status_code == 200
    assert bodega_response.json()["codigo"] == "BOD-B1"


# --- 5. Empty sucursal_ids -> empty list, never an error, never every row --


def test_sucursal_user_with_no_assigned_branches_sees_empty_lists():
    sucursales = [_sucursal(B1_ID, "B1"), _sucursal(B2_ID, "B2")]
    bodegas = [_bodega("BOD-B1", B1_ID), _bodega("BOD-B2", B2_ID)]
    client = _client_scoped_to(execute_queue=[[], sucursales, [], bodegas])

    sucursal_response = client.get("/api/motored/maestros/sucursales")
    assert sucursal_response.status_code == 200
    assert sucursal_response.json() == []

    bodega_response = client.get("/api/motored/maestros/bodegas")
    assert bodega_response.status_code == 200
    assert bodega_response.json() == []


# --- 6. ADMIN/COMPRAS/CONSULTA are unaffected -- explicit regression check --


@pytest.mark.parametrize("role", ["ADMIN", "COMPRAS", "CONSULTA"])
def test_non_sucursal_roles_still_see_every_branch_unfiltered(role):
    rows = [_sucursal(B1_ID, "B1"), _sucursal(B2_ID, "B2")]
    client = _client_as(role, execute_queue=[[], rows])
    response = client.get("/api/motored/maestros/sucursales")
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert ids == {str(B1_ID), str(B2_ID)}


# --- 7. proveedor/referencia are branch-agnostic -- NOT filtered for SUCURSAL


def test_proveedor_list_is_not_filtered_for_sucursal_role():
    proveedores = [
        Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True, activa=True),
        Proveedor(id=uuid.uuid4(), codigo="OTRO", nombre="Otro", es_principal=False, activa=True),
    ]
    client = _client_scoped_to(B1_ID, execute_queue=[[], proveedores])
    response = client.get("/api/motored/maestros/proveedores")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_referencia_list_is_not_filtered_for_sucursal_role():
    proveedor_id = uuid.uuid4()
    referencias = [
        Referencia(
            id=uuid.uuid4(),
            codigo="REF1",
            proveedor_id=proveedor_id,
            unidad_empaque=1,
            unidad_empaque_advertencia=False,
            activa=True,
        ),
        Referencia(
            id=uuid.uuid4(),
            codigo="REF2",
            proveedor_id=proveedor_id,
            unidad_empaque=1,
            unidad_empaque_advertencia=False,
            activa=True,
        ),
    ]
    client = _client_scoped_to(B1_ID, execute_queue=[[], referencias])
    response = client.get("/api/motored/maestros/referencias")
    assert response.status_code == 200
    assert len(response.json()) == 2
