"""
Motored `motored-referencia-identidad` (R1): una referencia se identifica por
su CODIGO. `services/maestros.py::upsert_referencia` busca por codigo y, si la
referencia existe bajo OTRO proveedor, la MUEVE (mismo id, historial intacto)
en vez de duplicarla. Mantiene el invariante "la sustituta es del mismo
proveedor": un vinculo que el movimiento deja cruzado se quita CON aviso.

`FakeAsyncSession` encola el resultado de cada `execute` en el orden en que
el servicio emite sus queries: [referencia por codigo] y, solo si hubo
movimiento, [sustituta guardada] (cuando el archivo no trae sustituta) y
[referencias que la tienen como sustituta].
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.motored.models.auditoria_maestro import AuditoriaMaestro
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


# --- upsert: mover el proveedor -------------------------------------------------


async def test_upsert_con_otro_proveedor_mueve_la_referencia_y_conserva_el_id():
    existente = _ref("R-1", HMCL, precio_normal=100)
    db = FakeAsyncSession(execute_queue=[[existente], []])  # por codigo; referencias que la apuntan
    data = ReferenciaCreate(codigo="R-1", proveedor_id=OTRO, precio_normal=120)
    id_original = existente.id

    referencia, _, created = await maestros.upsert_referencia(db, data)

    assert referencia is existente and created is False
    assert referencia.id == id_original and referencia.proveedor_id == OTRO
    assert referencia.precio_normal == 120
    assert db.added_of_type(Referencia) == []  # no se creo un duplicado
    cambios = [a for a in db.added_of_type(AuditoriaMaestro) if a.campo == "proveedor_id"]
    assert len(cambios) == 1


async def test_upsert_con_el_mismo_proveedor_no_hace_queries_de_movimiento():
    existente = _ref("R-1", HMCL)
    db = FakeAsyncSession(execute_queue=[[existente]])  # solo la busqueda por codigo

    await maestros.upsert_referencia(db, ReferenciaCreate(codigo="R-1", proveedor_id=HMCL))

    assert len(db.executed_statements) == 1


async def test_al_mover_se_quitan_con_aviso_los_vinculos_que_apuntaban_a_ella():
    movida = _ref("NUEVA", HMCL)
    vieja = _ref("VIEJA", HMCL, sustituida_por=movida.id)
    vieja.activa = False
    db = FakeAsyncSession(execute_queue=[[movida], [vieja]])
    avisos = []

    await maestros.upsert_referencia(
        db, ReferenciaCreate(codigo="NUEVA", proveedor_id=OTRO), avisos=avisos)

    assert vieja.sustituida_por is None
    assert len(avisos) == 1 and "VIEJA" in avisos[0] and "NUEVA" in avisos[0]
    assert any(a.campo == "sustituida_por" and a.entidad_id == vieja.id
               for a in db.added_of_type(AuditoriaMaestro))


async def test_al_mover_se_quita_con_aviso_la_sustituta_guardada_que_quedo_en_otro_proveedor():
    sustituta = _ref("SUST", HMCL)
    movida = _ref("R-1", HMCL, sustituida_por=sustituta.id)
    # por codigo; sustituta guardada (el archivo no trae sustituta); referencias que apuntan a R-1
    db = FakeAsyncSession(execute_queue=[[movida], [sustituta], []])
    avisos = []

    await maestros.upsert_referencia(
        db, ReferenciaCreate(codigo="R-1", proveedor_id=OTRO), avisos=avisos)

    assert movida.sustituida_por is None
    assert len(avisos) == 1 and "SUST" in avisos[0]


async def test_al_mover_con_sustituta_en_el_archivo_no_revisa_la_guardada():
    sustituta_nueva = _ref("S2", OTRO)
    movida = _ref("R-1", HMCL)
    db = FakeAsyncSession(execute_queue=[[movida], []])  # por codigo; apuntadoras
    data = ReferenciaCreate(codigo="R-1", proveedor_id=OTRO, sustituida_por=sustituta_nueva.id)

    await maestros.upsert_referencia(db, data, avisos=[])

    assert movida.sustituida_por == sustituta_nueva.id


async def test_un_vinculo_que_sigue_siendo_del_mismo_proveedor_se_conserva():
    movida = _ref("R-1", HMCL)
    otra_de_otro = _ref("X", OTRO, sustituida_por=movida.id)  # ya cruzada: no se toca el invariante aca
    db = FakeAsyncSession(execute_queue=[[movida], [otra_de_otro]])
    avisos = []

    await maestros.upsert_referencia(
        db, ReferenciaCreate(codigo="R-1", proveedor_id=OTRO), avisos=avisos)

    assert otra_de_otro.sustituida_por == movida.id and avisos == []


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
