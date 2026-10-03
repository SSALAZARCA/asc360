"""
Motored `motored-referencia-identidad` (R1): una referencia se identifica por
su CODIGO. El codigo se guarda recortado, se busca solo por codigo, crear uno
repetido es 409 y "crear como OTROS" no duplica un codigo de otro proveedor.
Mover una referencia de proveedor (mismo id) lo hace la carga masiva de
reemplazo: ver `test_reemplazo_referencias.py`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.schemas.referencia import ReferenciaCreate
from app.motored.services import maestros
from tests.motored.conftest import FakeAsyncSession, override_motored_db

HMCL, OTRO = uuid.uuid4(), uuid.uuid4()


def _ref(codigo, proveedor=HMCL, **extra):
    return Referencia(id=uuid.uuid4(), codigo=codigo, proveedor_id=proveedor,
                      unidad_empaque=1, activa=True, homologados=[], **extra)


# --- el codigo se guarda con trim -----------------------------------------------


def test_el_schema_guarda_el_codigo_sin_espacios_sobrantes():
    assert ReferenciaCreate(codigo="  AB-1 \t", proveedor_id=HMCL).codigo == "AB-1"


def test_el_schema_conserva_mayusculas_y_minusculas():
    assert ReferenciaCreate(codigo="aB-1", proveedor_id=HMCL).codigo == "aB-1"


def test_un_codigo_en_blanco_se_rechaza():
    with pytest.raises(ValidationError):
        ReferenciaCreate(codigo="   ", proveedor_id=HMCL)


# --- la busqueda es por codigo --------------------------------------------------


def test_ya_no_existe_la_busqueda_por_codigo_y_proveedor():
    assert hasattr(maestros, "get_referencia_by_codigo")
    assert not hasattr(maestros, "get_referencia_by_codigo_proveedor")


async def test_get_referencia_by_codigo_filtra_solo_por_codigo():
    existente = _ref("R-1")
    db = FakeAsyncSession(execute_queue=[[existente]])

    assert await maestros.get_referencia_by_codigo(db, " R-1 ") is existente
    sql = str(db.executed_statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "proveedor_id" not in sql.split("WHERE")[1]


# --- crear con un codigo que ya existe (otro proveedor) -> 409, no 500 ----------


def test_crear_una_referencia_con_un_codigo_existente_es_409(monkeypatch):
    from app.config import settings
    from app.motored.services.auth import MotoredUser
    from tests.motored.conftest import override_motored_user

    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "identidad-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "identidad-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    session = FakeAsyncSession(
        execute_queue=[[]],  # readiness probe
        raise_integrity_error=IntegrityError("COMMIT", {}, Exception("uq_referencia_codigo")))
    override_motored_db(session)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/motored/maestros/referencias",
                json={"codigo": "R-1", "proveedor_id": str(OTRO)})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409, response.text
    assert "R-1" in response.json()["detail"]
    assert session.rolled_back is True


def _post_con_error_de_integridad(error):
    from app.config import settings
    from app.motored.services.auth import MotoredUser
    from tests.motored.conftest import override_motored_user

    settings.MOTORED_ENABLED = True
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    session = FakeAsyncSession(execute_queue=[[]], raise_integrity_error=error)
    override_motored_db(session)
    try:
        with TestClient(app) as client:
            return client.post(
                "/api/motored/maestros/referencias", json={"codigo": "R-1", "proveedor_id": str(OTRO)})
    finally:
        app.dependency_overrides.clear()


def test_una_violacion_de_llave_foranea_no_se_reporta_como_codigo_duplicado(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "identidad-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "identidad-test-asc360-secret")
    error = IntegrityError(
        "COMMIT", {}, Exception('insert or update on table "referencia" violates foreign key constraint '
                                '"referencia_proveedor_id_fkey"'))

    response = _post_con_error_de_integridad(error)

    assert response.status_code == 422, response.text
    assert "Ya existe" not in response.json()["detail"]
    assert "inexistente" in response.json()["detail"]


def test_la_violacion_unica_del_codigo_leida_del_diag_sigue_siendo_409(monkeypatch):
    from types import SimpleNamespace

    from app.config import settings

    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "identidad-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "identidad-test-asc360-secret")
    orig = Exception("duplicate key")
    orig.diag = SimpleNamespace(constraint_name="uq_referencia_codigo")

    response = _post_con_error_de_integridad(IntegrityError("COMMIT", {}, orig))

    assert response.status_code == 409, response.text
    assert "R-1" in response.json()["detail"]


def test_editar_una_referencia_con_una_fk_inexistente_es_422_no_500(monkeypatch):
    from app.config import settings
    from app.motored.services.auth import MotoredUser
    from tests.motored.conftest import override_motored_user

    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "identidad-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "identidad-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    existente = _ref("R-1", HMCL)
    error = IntegrityError("COMMIT", {}, Exception('violates foreign key constraint "referencia_proveedor_id_fkey"'))
    session = FakeAsyncSession(execute_queue=[[], [existente]], raise_integrity_error=error)
    override_motored_db(session)
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/motored/maestros/referencias/{existente.id}", json={"proveedor_id": str(OTRO)})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422, response.text
    assert session.rolled_back is True


# --- el alta de "referencia desconocida" tambien busca solo por codigo ----------


async def test_crear_referencia_desconocida_no_duplica_un_codigo_de_otro_proveedor():
    from types import SimpleNamespace

    from app.motored.api import cargas

    otros = Proveedor(id=uuid.uuid4(), codigo="OTROS", nombre="Otros")
    existente_en_hmcl = _ref("DESC-1", HMCL)
    db = FakeAsyncSession(execute_queue=[[otros], [existente_en_hmcl]])

    aplicada = await cargas._aplicar_creacion_referencia(
        db, SimpleNamespace(valor=" DESC-1 "))

    assert aplicada is False and db.added_of_type(Referencia) == []
    sql = str(db.executed_statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "proveedor_id" not in sql.split("WHERE")[1]


async def test_una_referencia_creada_como_otros_resuelve_al_reaplicar_la_carga():
    from types import SimpleNamespace

    from app.motored.api import cargas
    from app.motored.services.ingesta.resolucion import construir_cache, resolver_referencia

    otros = Proveedor(id=uuid.uuid4(), codigo="OTROS", nombre="Otros")
    db = FakeAsyncSession(execute_queue=[[otros], []])
    assert await cargas._aplicar_creacion_referencia(db, SimpleNamespace(valor="DESC-9")) is True
    [creada] = db.added_of_type(Referencia)

    cache = await construir_cache(FakeAsyncSession(execute_queue=[
        [], [], [], [(creada.codigo, creada.proveedor_id, creada.id)]]))

    assert resolver_referencia(cache, "DESC-9") == creada.id and creada.proveedor_id == otros.id
