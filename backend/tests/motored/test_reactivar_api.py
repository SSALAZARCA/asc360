"""
POST /maestros/{entidad}/{id}/reactivar and POST /usuarios/{id}/reactivar
(odd/motored-acciones-con-iconos, T5): the counterpart of the soft-delete
endpoints. Only the active flag changes and one audit row records it.
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
from app.motored.models.usuario import Usuario
from app.motored.services import auditoria
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

ALL_ROLES = ["ADMIN", "COMPRAS", "SUCURSAL", "CONSULTA"]
MAESTROS_URL = "/api/motored/maestros"
USUARIOS_URL = "/api/motored/usuarios"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "reactivar-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "reactivar-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _client_as(role, obj) -> tuple:
    """A leading `[]` feeds `get_motored_db_or_503`'s connectivity probe."""
    session = FakeAsyncSession(execute_queue=[[], [obj]])
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(session)
    return TestClient(app), session


def _proveedor(**kw):
    return Proveedor(id=uuid.uuid4(), codigo="P1", nombre="Prov", es_principal=False, activa=False, **kw)


def _sucursal(**kw):
    return Sucursal(id=uuid.uuid4(), nombre="Norte", dias_seguridad=1, activa=False, **kw)


def _bodega(**kw):
    return Bodega(id=uuid.uuid4(), codigo="B1", sucursal_id=uuid.uuid4(), activa=False, **kw)


def _referencia(**kw):
    base = dict(
        id=uuid.uuid4(), codigo="R1", proveedor_id=uuid.uuid4(), unidad_empaque=1,
        unidad_empaque_advertencia=False, activa=False, homologados=[],
    )
    base.update(kw)
    return Referencia(**base)


def _usuario(**kw):
    base = dict(
        id=uuid.uuid4(), nombre="Ana", email="ana@motoredcolombia.com.co",
        hashed_password="hash", role="ADMIN", activo=False, status="approved",
    )
    base.update(kw)
    return Usuario(**base)


def _audit_rows(session):
    return [o for o in session.added if getattr(o, "accion", None) is not None]


@pytest.mark.parametrize("entidad,factory", [
    ("proveedores", _proveedor), ("sucursales", _sucursal),
    ("bodegas", _bodega), ("referencias", _referencia),
])
def test_reactivar_maestro_sets_activa_true_and_audits(entidad, factory):
    obj = factory()
    client, session = _client_as("COMPRAS", obj)

    response = client.post(f"{MAESTROS_URL}/{entidad}/{obj.id}/reactivar")

    assert response.status_code == 200, response.text
    assert response.json()["activa"] is True
    assert obj.activa is True
    assert session.committed
    (row,) = _audit_rows(session)
    assert (row.accion, row.campo, row.valor_anterior, row.valor_nuevo) == ("reactivate", "activa", "False", "True")


@pytest.mark.parametrize("role", ALL_ROLES)
def test_reactivar_maestro_is_restricted_to_admin_and_compras(role):
    obj = _proveedor()
    client, _ = _client_as(role, obj)

    response = client.post(f"{MAESTROS_URL}/proveedores/{obj.id}/reactivar")

    assert response.status_code == (200 if role in ("ADMIN", "COMPRAS") else 403)


def test_reactivar_maestro_unknown_id_is_404():
    session = FakeAsyncSession(execute_queue=[[], []])
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    override_motored_db(session)

    response = TestClient(app).post(f"{MAESTROS_URL}/sucursales/{uuid.uuid4()}/reactivar")

    assert response.status_code == 404


def test_reactivar_referencia_keeps_sustituida_por_unchanged():
    sustituta_id = uuid.uuid4()
    obj = _referencia(sustituida_por=sustituta_id)
    client, _ = _client_as("ADMIN", obj)

    response = client.post(f"{MAESTROS_URL}/referencias/{obj.id}/reactivar")

    assert response.status_code == 200, response.text
    assert obj.activa is True
    assert obj.sustituida_por == sustituta_id


def test_reactivar_already_active_is_a_no_op_without_audit():
    obj = _sucursal()
    obj.activa = True
    client, session = _client_as("ADMIN", obj)

    response = client.post(f"{MAESTROS_URL}/sucursales/{obj.id}/reactivar")

    assert response.status_code == 200
    assert _audit_rows(session) == []


@pytest.mark.parametrize("role", ALL_ROLES)
def test_reactivar_usuario_is_restricted_to_admin(role):
    usuario = _usuario()
    client, _ = _client_as(role, usuario)

    response = client.post(f"{USUARIOS_URL}/{usuario.id}/reactivar")

    assert response.status_code == (200 if role == "ADMIN" else 403)


@pytest.mark.parametrize("status", ["approved", "pending", "rejected"])
def test_reactivar_usuario_only_changes_activo_never_status(status):
    usuario = _usuario(status=status)
    client, session = _client_as("ADMIN", usuario)

    response = client.post(f"{USUARIOS_URL}/{usuario.id}/reactivar")

    assert response.status_code == 200, response.text
    assert usuario.activo is True
    assert usuario.status == status
    assert response.json()["status"] == status
    (row,) = _audit_rows(session)
    assert (row.entidad, row.accion, row.valor_nuevo) == ("usuario", "reactivate", "True")


def test_reactivar_usuario_unknown_id_is_404():
    session = FakeAsyncSession(execute_queue=[[], []])
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    override_motored_db(session)

    assert TestClient(app).post(f"{USUARIOS_URL}/{uuid.uuid4()}/reactivar").status_code == 404


def test_audit_reactivate_records_activa_transition():
    row = auditoria.audit_reactivate(FakeAsyncSession(), "proveedor", uuid.uuid4())

    assert (row.accion, row.campo, row.valor_anterior, row.valor_nuevo) == ("reactivate", "activa", "False", "True")
