"""Owner rule (2026-10-03): a proveedor's codigo can be edited only while no
referencia is loaded under it. The codigo is the key that bulk uploads use, so
changing it once referencias exist would split them from future files.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.schemas.proveedor import ProveedorUpdate
from app.motored.services import maestros
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)


def _proveedor(codigo="OTRO"):
    return Proveedor(id=uuid.uuid4(), codigo=codigo, nombre="Otros", activa=True)


def _referencia(proveedor):
    return Referencia(
        id=uuid.uuid4(), codigo="R1", proveedor_id=proveedor.id, unidad_empaque=1,
    )


class TestCambioDeCodigo:
    async def test_changes_codigo_when_no_referencia_uses_it(self):
        proveedor = _proveedor()
        db = FakeAsyncSession(execute_queue=[[], []])  # no refs, no duplicate

        await maestros.update_proveedor(db, proveedor, ProveedorUpdate(codigo="OTROS"))

        assert proveedor.codigo == "OTROS"

    async def test_trims_the_new_codigo(self):
        proveedor = _proveedor()
        db = FakeAsyncSession(execute_queue=[[], []])

        await maestros.update_proveedor(db, proveedor, ProveedorUpdate(codigo="  OTROS "))

        assert proveedor.codigo == "OTROS"

    async def test_rejects_change_when_referencias_are_loaded(self):
        proveedor = _proveedor()
        db = FakeAsyncSession(execute_queue=[[_referencia(proveedor).id]])

        with pytest.raises(maestros.CodigoProveedorBloqueadoError) as exc:
            await maestros.update_proveedor(db, proveedor, ProveedorUpdate(codigo="OTROS"))

        assert proveedor.codigo == "OTRO"
        assert "referencias" in str(exc.value)

    async def test_rejects_a_codigo_already_used_by_another_proveedor(self):
        proveedor = _proveedor()
        otro = _proveedor(codigo="OTROS")
        db = FakeAsyncSession(execute_queue=[[], [otro]])

        with pytest.raises(maestros.CodigoProveedorBloqueadoError) as exc:
            await maestros.update_proveedor(db, proveedor, ProveedorUpdate(codigo="OTROS"))

        assert proveedor.codigo == "OTRO"
        assert "OTROS" in str(exc.value)

    async def test_rejects_an_empty_codigo(self):
        proveedor = _proveedor()
        db = FakeAsyncSession()

        with pytest.raises(maestros.CodigoProveedorBloqueadoError):
            await maestros.update_proveedor(db, proveedor, ProveedorUpdate(codigo="   "))

        assert proveedor.codigo == "OTRO"

    async def test_same_codigo_needs_no_check(self):
        proveedor = _proveedor()
        db = FakeAsyncSession()  # any query would fail: the queue is empty

        await maestros.update_proveedor(
            db, proveedor, ProveedorUpdate(codigo="OTRO", nombre="Otros proveedores"),
        )

        assert proveedor.codigo == "OTRO"
        assert proveedor.nombre == "Otros proveedores"

    async def test_editing_other_fields_never_checks_referencias(self):
        proveedor = _proveedor()
        db = FakeAsyncSession()

        await maestros.update_proveedor(db, proveedor, ProveedorUpdate(nombre="Nuevo"))

        assert proveedor.nombre == "Nuevo"


def test_api_answers_409_when_the_proveedor_has_referencias(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "codigo-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "codigo-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    proveedor = _proveedor()
    session = FakeAsyncSession(execute_queue=[
        [],  # readiness probe
        [proveedor],  # _get_or_404
        [uuid.uuid4()],  # a referencia uses it
    ])
    override_motored_db(session)
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/motored/maestros/proveedores/{proveedor.id}",
                json={"codigo": "OTROS"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409, response.text
    assert "referencias" in response.json()["detail"]
    assert proveedor.codigo == "OTRO"
