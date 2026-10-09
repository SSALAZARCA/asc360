"""
Inventory counts, the parts coordinator as a count leader
(odd/motored-conteos-inventario, owner decision 2026-10-09).

COORDINADOR_REPUESTOS gets exactly the LIDER_INVENTARIOS powers in the
counts module: it may be assigned as leader, it reaches
`/api/motored/conteos`, and it only sees and acts on the conteos it leads
(another's answers 404). Any other non-leader role still cannot lead.
"""
import datetime
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.auth import MotoredUser
from app.motored.services.conteos import (
    cierre, consultas, errores, reconteos, snapshot,
)
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

BASE = "/api/motored/conteos"
ROL = "COORDINADOR_REPUESTOS"
UTC = datetime.timezone.utc
AHORA = datetime.datetime(2026, 10, 9, 13, 0, tzinfo=UTC)
COORDINADOR_ID = uuid.uuid4()
OTRO_LIDER_ID = uuid.uuid4()
RID, SID = uuid.uuid4(), uuid.uuid4()
HASH = "f" * 64


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "conteos-coord")
    monkeypatch.setattr(settings, "SECRET_KEY", "conteos-coord-asc360")
    monkeypatch.setattr(
        settings, "MOTORED_PUBLIC_URL", "https://motored.test/")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def datos(monkeypatch):
    monkeypatch.setattr(consultas, "datos_conteo", AsyncMock(
        return_value=consultas.DatosConteo("Quilichao", "Coord", None)))


def _conteo(estado="EN_CONTEO", lider_id=COORDINADOR_ID):
    abierto = estado in ("EN_CONTEO", "EN_RECONTEO")
    return Conteo(
        id=uuid.uuid4(), tipo="TOTAL", estado=estado, origen="MANUAL",
        sucursal_id=uuid.uuid4(), lider_id=lider_id,
        fecha_programada=AHORA.date(), created_at=AHORA,
        enlace_slug="SlugDePrueba1234" if abierto else None,
        codigo_hash=HASH if abierto else None,
        codigo_rotado_en=AHORA if abierto else None,
        snapshot_tomado_en=AHORA if abierto else None,
        snapshot_fecha_corte=AHORA.date() if abierto else None,
        umbral_reconteo_pesos=Decimal("100000.00"),
        umbral_critico_pesos=Decimal("500000.00"))


def _llamar(metodo, ruta, conteo=None, json=None):
    override_motored_user(
        MotoredUser(user_id=str(COORDINADOR_ID), role=ROL))
    db = FakeAsyncSession(
        execute_queue=[[]],
        get_queue=[conteo] if conteo is not None else [None])
    override_motored_db(db)
    return TestClient(app).request(metodo, BASE + ruta, json=json), db


# --- leader validation (schedule / reschedule) ------------------------------


def _usuario(rol, activo=True):
    return Usuario(
        id=uuid.uuid4(), nombre=rol.value, email="u@x.com",
        hashed_password="h", role=rol, activo=activo, status="approved")


def _tienda():
    return Sucursal(id=uuid.uuid4(), nombre="S", activa=True)


async def test_a_coordinator_can_be_scheduled_as_leader():
    lider = _usuario(MotoredRole.COORDINADOR_REPUESTOS)
    db = FakeAsyncSession(get_queue=[_tienda(), lider])

    conteo = await snapshot.programar_conteo(
        db, uuid.uuid4(), lider.id, AHORA.date(), uuid.uuid4())

    assert conteo.lider_id == lider.id


@pytest.mark.parametrize("rol", [MotoredRole.COMPRAS, MotoredRole.GERENCIA])
async def test_a_non_leader_role_still_cannot_lead(rol):
    db = FakeAsyncSession(get_queue=[_tienda(), _usuario(rol)])

    with pytest.raises(errores.LiderInvalido):
        await snapshot.programar_conteo(
            db, uuid.uuid4(), uuid.uuid4(), AHORA.date(), uuid.uuid4())


async def test_an_inactive_coordinator_cannot_lead():
    lider = _usuario(MotoredRole.COORDINADOR_REPUESTOS, activo=False)
    db = FakeAsyncSession(get_queue=[_tienda(), lider])

    with pytest.raises(errores.LiderInvalido):
        await snapshot.programar_conteo(
            db, uuid.uuid4(), lider.id, AHORA.date(), uuid.uuid4())


def test_both_roles_lead_and_others_do_not():
    assert set(snapshot.ROLES_LIDER_CONTEO) == {
        MotoredRole.LIDER_INVENTARIOS, MotoredRole.COORDINADOR_REPUESTOS}
    for rol in ("LIDER_INVENTARIOS", ROL):
        assert consultas.es_lider(MotoredUser(user_id="x", role=rol))
    for rol in ("ADMIN", "GERENCIA", "COMPRAS"):
        assert not consultas.es_lider(MotoredUser(user_id="x", role=rol))


def test_admin_is_assignable_but_not_scoped():
    assert set(snapshot.ROLES_ASIGNABLES_LIDER) == {
        MotoredRole.LIDER_INVENTARIOS, MotoredRole.COORDINADOR_REPUESTOS,
        MotoredRole.ADMIN}
    assert MotoredRole.ADMIN not in snapshot.ROLES_LIDER_CONTEO
    admin = MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN")
    assert consultas.ve_lider(admin, uuid.uuid4())


# --- HTTP: scoping -----------------------------------------------------------


def test_the_coordinator_reaches_the_counts_list_scoped_to_itself(
        monkeypatch):
    conteo = _conteo(estado="PROGRAMADO")
    listar = AsyncMock(return_value=[(conteo, "Quilichao", "Coord")])
    monkeypatch.setattr(consultas, "listar", listar)

    r, _ = _llamar("GET", "")

    assert r.status_code == 200, r.text
    assert [c["id"] for c in r.json()] == [str(conteo.id)]
    assert str(listar.await_args.kwargs["lider_id"]) == str(COORDINADOR_ID)


def test_the_coordinator_sees_its_own_conteo_with_the_access(datos):
    conteo = _conteo()

    r, _ = _llamar("GET", f"/{conteo.id}", conteo)

    assert r.status_code == 200, r.text
    assert r.json()["acceso"]["slug"] == conteo.enlace_slug


@pytest.mark.parametrize("metodo, ruta, cuerpo", [
    ("GET", "", None), ("POST", "/iniciar", {}),
    ("POST", f"/reconteos/{RID}/asignar", {"sesion_id": str(SID)}),
    ("POST", "/cerrar", {}),
])
def test_another_leaders_conteo_is_a_404(datos, metodo, ruta, cuerpo):
    conteo = _conteo(lider_id=OTRO_LIDER_ID)

    r, db = _llamar(metodo, f"/{conteo.id}{ruta}", conteo, json=cuerpo)

    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "CONTEO_NO_ENCONTRADO"
    assert not db.committed


def test_the_coordinator_still_cannot_schedule():
    r, _ = _llamar("GET", "/lideres")

    assert r.status_code == 403, r.text


# --- HTTP: the leader's actions on its own conteo ----------------------------


def test_the_coordinator_starts_its_own_conteo(monkeypatch, datos):
    conteo = _conteo()
    fuente = snapshot.FuenteSnapshot(uuid.uuid4(), AHORA.date(), AHORA, 3)
    iniciar = AsyncMock(return_value=snapshot.InicioConteo(
        conteo, "048213", fuente, None))
    monkeypatch.setattr(snapshot, "iniciar_conteo", iniciar)

    r, db = _llamar("POST", f"/{conteo.id}/iniciar", conteo, json={})

    assert r.status_code == 200, r.text
    assert r.json()["codigo"] == "048213"
    assert db.committed


def test_the_coordinator_assigns_a_reconteo(monkeypatch):
    conteo = _conteo(estado="EN_RECONTEO")
    asignado = ConteoReconteo(
        id=RID, conteo_id=conteo.id, codigo="R-1", estado="ASIGNADO",
        origen="LIDER", sesion_id=SID, misma_pareja_autorizada=False,
        asignado_en=AHORA, diferencia_ronda1=Decimal("-2"),
        valor_ronda1=Decimal("-2000.00"))
    monkeypatch.setattr(
        reconteos, "asignar", AsyncMock(return_value=asignado))

    r, db = _llamar(
        "POST", f"/{conteo.id}/reconteos/{RID}/asignar", conteo,
        json={"sesion_id": str(SID)})

    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(RID)
    assert db.committed


def test_the_coordinator_closes_its_own_conteo(monkeypatch):
    conteo = _conteo(estado="EN_RECONTEO")
    kpi = cierre.calcular_kpi([])
    monkeypatch.setattr(cierre, "cerrar", AsyncMock(
        return_value=cierre.Cierre(conteo, kpi, 0)))

    r, db = _llamar("POST", f"/{conteo.id}/cerrar", conteo, json={})

    assert r.status_code == 200, r.text
    assert r.json()["reconteos_cancelados"] == 0
    assert db.committed


# --- the leaders list --------------------------------------------------------


def test_the_leaders_list_carries_both_roles(monkeypatch):
    filas = [
        consultas.OpcionLider(uuid.uuid4(), "Ana", "a@x.com",
                              "COORDINADOR_REPUESTOS"),
        consultas.OpcionLider(uuid.uuid4(), "Lina", None,
                              "LIDER_INVENTARIOS"),
    ]
    monkeypatch.setattr(
        consultas, "lideres_activos", AsyncMock(return_value=filas))
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()),
                                      role="ADMIN"))
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))

    r = TestClient(app).get(BASE + "/lideres")

    assert r.status_code == 200, r.text
    assert [(x["nombre"], x["rol"]) for x in r.json()] == [
        ("Ana", "COORDINADOR_REPUESTOS"), ("Lina", "LIDER_INVENTARIOS")]


async def test_the_leaders_query_includes_admin_but_no_other_role():
    db = FakeAsyncSession(execute_queue=[[]])

    await consultas.lideres_activos(db)

    sql = str(db.executed_statements[0].compile(
        compile_kwargs={"literal_binds": True}))
    for rol in ("LIDER_INVENTARIOS", "COORDINADOR_REPUESTOS", "ADMIN"):
        assert f"'{rol}'" in sql
    for rol in ("GERENCIA", "COMPRAS"):
        assert f"'{rol}'" not in sql


# --- ADMIN as leader (owner decision 2026-10-09) -----------------------------


async def test_an_admin_can_be_scheduled_as_leader():
    lider = _usuario(MotoredRole.ADMIN)
    db = FakeAsyncSession(get_queue=[_tienda(), lider])

    conteo = await snapshot.programar_conteo(
        db, uuid.uuid4(), lider.id, AHORA.date(), uuid.uuid4())

    assert conteo.lider_id == lider.id


async def test_an_admin_can_be_reassigned_as_leader(monkeypatch):
    conteo = _conteo(estado="PROGRAMADO")
    lider = _usuario(MotoredRole.ADMIN)
    db = FakeAsyncSession(get_queue=[lider])
    monkeypatch.setattr(snapshot.acceso, "bloquear_conteo",
                        AsyncMock(return_value=conteo))

    await snapshot.reprogramar_conteo(
        db, conteo.id, AHORA.date(), lider.id)

    assert conteo.lider_id == lider.id


def test_the_leaders_list_carries_an_admin(monkeypatch):
    fila = consultas.OpcionLider(uuid.uuid4(), "Adri", None, "ADMIN")
    monkeypatch.setattr(
        consultas, "lideres_activos", AsyncMock(return_value=[fila]))
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()),
                                      role="ADMIN"))
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))

    r = TestClient(app).get(BASE + "/lideres")

    assert r.status_code == 200, r.text
    assert [(x["nombre"], x["rol"]) for x in r.json()] == [
        ("Adri", "ADMIN")]


def _como_otro_admin(metodo, ruta, conteo, json=None):
    override_motored_user(
        MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    db = FakeAsyncSession(execute_queue=[[]], get_queue=[conteo])
    override_motored_db(db)
    return TestClient(app).request(metodo, BASE + ruta, json=json), db


def test_another_admin_sees_an_admin_led_conteo(datos):
    conteo = _conteo(lider_id=uuid.uuid4())

    r, _ = _como_otro_admin("GET", f"/{conteo.id}", conteo)

    assert r.status_code == 200, r.text


def test_another_admin_closes_an_admin_led_conteo(monkeypatch):
    conteo = _conteo(estado="EN_RECONTEO", lider_id=uuid.uuid4())
    kpi = cierre.calcular_kpi([])
    monkeypatch.setattr(cierre, "cerrar", AsyncMock(
        return_value=cierre.Cierre(conteo, kpi, 0)))

    r, db = _como_otro_admin("POST", f"/{conteo.id}/cerrar", conteo, {})

    assert r.status_code == 200, r.text
    assert db.committed


def test_a_leader_is_still_scoped_away_from_an_admin_led_conteo(datos):
    conteo = _conteo(lider_id=uuid.uuid4())
    for rol in ("LIDER_INVENTARIOS", ROL):
        override_motored_user(
            MotoredUser(user_id=str(uuid.uuid4()), role=rol))
        override_motored_db(
            FakeAsyncSession(execute_queue=[[]], get_queue=[conteo]))

        r = TestClient(app).get(f"{BASE}/{conteo.id}")

        assert r.status_code == 404, (rol, r.text)
