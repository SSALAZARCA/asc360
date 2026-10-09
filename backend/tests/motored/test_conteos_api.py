"""
Inventory counts, leader API (odd/motored-conteos-inventario, WU6/WU7;
design §6.1, §5.1, §8.1, §8.3).

HTTP-layer tests on the real mounted router. The user and the DB are the
usual seams (`override_motored_user`, `FakeAsyncSession`); the leading
`[]` of every execute queue is `get_motored_db_or_503`'s probe and the
conteo itself comes from `get_queue` (the scoping lookup). The services
are stubbed here; the pg_real files run them for real.

Scoping (owner decision): ADMIN does everything; a LIDER_INVENTARIOS only
sees and acts on its own conteos (another's answers 404, never 403);
GERENCIA reads everything and every write answers 403.
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
from app.motored.models.conteo_sesion import ConteoIntegrante, ConteoSesion
from app.motored.services.auth import MotoredUser
from app.motored.services.conteos import (
    acceso, consultas, errores, panel, sesiones, snapshot,
)
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

BASE = "/api/motored/conteos"
PUBLICA = "https://motored.test"
UTC = datetime.timezone.utc
AHORA = datetime.datetime(2026, 10, 9, 13, 0, tzinfo=UTC)
ADMIN_ID = uuid.uuid4()
LIDER_ID = uuid.uuid4()
OTRO_LIDER_ID = uuid.uuid4()
CEDULA = "1130124821"
HASH = "f" * 64


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "conteos-api")
    monkeypatch.setattr(settings, "SECRET_KEY", "conteos-api-asc360")
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", PUBLICA + "/")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def datos(monkeypatch):
    resumen = consultas.ResumenSnapshot(
        nombre_archivo="inv.xlsx", lineas=3, valor_sistema=Decimal("90.00"),
        sin_costo=1)
    mock = AsyncMock(return_value=consultas.DatosConteo(
        "Quilichao", "Lina Líder", resumen))
    monkeypatch.setattr(consultas, "datos_conteo", mock)
    return mock


def _usuario(rol):
    ids = {"ADMIN": ADMIN_ID, "LIDER_INVENTARIOS": LIDER_ID}
    return MotoredUser(
        user_id=str(ids.get(rol, uuid.uuid4())), role=rol)


def _conteo(estado="EN_CONTEO", lider_id=LIDER_ID):
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


def _llamar(rol, metodo, ruta, conteo=None, cola=None, json=None):
    override_motored_user(_usuario(rol))
    sesion = FakeAsyncSession(
        execute_queue=[[]] + list(cola or []),
        get_queue=[conteo] if conteo is not None else [None])
    override_motored_db(sesion)
    respuesta = TestClient(app).request(
        metodo, BASE + ruta, json=json)
    return respuesta, sesion


def _detalle(respuesta, codigo):
    assert respuesta.json()["detail"]["code"] == codigo, respuesta.text


# --- scoping and RBAC --------------------------------------------------------


@pytest.mark.parametrize("rol", ["ADMIN", "LIDER_INVENTARIOS", "GERENCIA"])
def test_readers_see_the_detail_of_a_visible_conteo(datos, rol):
    conteo = _conteo()

    r, _ = _llamar(rol, "GET", f"/{conteo.id}", conteo)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["id"] == str(conteo.id)
    assert cuerpo["sucursal"]["nombre"] == "Quilichao"
    assert cuerpo["lider"] == {"id": str(LIDER_ID), "nombre": "Lina Líder"}
    assert cuerpo["snapshot"]["lineas"] == 3
    assert cuerpo["umbrales"] == {
        "reconteo": "100000.00", "critico": "500000.00"}
    assert "codigo_hash" not in r.text and HASH not in r.text


def test_the_leader_and_admin_see_the_access_but_gerencia_does_not(datos):
    conteo = _conteo()
    url = f"{PUBLICA}/motored/c/{conteo.enlace_slug}"

    lider, _ = _llamar("LIDER_INVENTARIOS", "GET", f"/{conteo.id}", conteo)
    gerencia, _ = _llamar("GERENCIA", "GET", f"/{conteo.id}", conteo)

    assert lider.json()["acceso"]["url"] == url
    assert lider.json()["acceso"]["qr_url"] == f"{BASE}/{conteo.id}/qr.png"
    assert gerencia.json()["acceso"] is None


def test_another_leaders_conteo_is_a_404_never_a_403(datos):
    conteo = _conteo(lider_id=OTRO_LIDER_ID)

    for metodo, ruta in [
            ("GET", ""), ("GET", "/sesiones"), ("POST", "/iniciar"),
            ("POST", "/codigo/rotar"), ("GET", "/qr.png")]:
        r, _ = _llamar(
            "LIDER_INVENTARIOS", metodo, f"/{conteo.id}{ruta}", conteo)
        assert r.status_code == 404, (ruta, r.text)
        _detalle(r, "CONTEO_NO_ENCONTRADO")


def test_a_missing_conteo_is_a_404_for_admin(datos):
    r, _ = _llamar("ADMIN", "GET", f"/{uuid.uuid4()}")

    assert r.status_code == 404
    assert r.json()["detail"] == {
        "code": "CONTEO_NO_ENCONTRADO", "mensaje": "El conteo no existe."}


ESCRITURAS = [
    ("POST", "", {"sucursal_id": str(uuid.uuid4()),
                  "lider_id": str(uuid.uuid4()),
                  "fecha_programada": "2026-10-12"}),
    ("PATCH", "/{id}", {"fecha_programada": "2026-10-13"}),
    ("POST", "/{id}/anular", {"motivo": "x"}),
    ("POST", "/{id}/iniciar", {}),
    ("POST", "/{id}/codigo/rotar", None),
    ("GET", "/{id}/qr.png", None),
    ("POST", "/{id}/sesiones/{sid}/desconectar", None),
    ("GET", "/lideres", None),
]


@pytest.mark.parametrize("metodo,ruta,cuerpo", ESCRITURAS)
def test_gerencia_gets_403_on_every_write(metodo, ruta, cuerpo):
    ruta = ruta.format(id=uuid.uuid4(), sid=uuid.uuid4())

    r, _ = _llamar("GERENCIA", metodo, ruta, json=cuerpo)

    assert r.status_code == 403, r.text


@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    e for e in ESCRITURAS
    if e[1] in ("", "/{id}", "/{id}/anular", "/lideres")])
def test_scheduling_is_admin_only(metodo, ruta, cuerpo):
    ruta = ruta.format(id=uuid.uuid4())

    r, _ = _llamar("LIDER_INVENTARIOS", metodo, ruta, json=cuerpo)

    assert r.status_code == 403, r.text


@pytest.mark.parametrize("rol,lider", [
    ("ADMIN", None), ("GERENCIA", None),
    ("LIDER_INVENTARIOS", str(LIDER_ID))])
def test_the_list_is_scoped_to_the_leader(monkeypatch, rol, lider):
    conteo = _conteo()
    listar = AsyncMock(return_value=[(conteo, "Quilichao", "Lina")])
    monkeypatch.setattr(consultas, "listar", listar)
    progreso = AsyncMock(
        return_value={conteo.id: panel.Progreso(4210, 1300)})
    monkeypatch.setattr(panel, "progreso", progreso)

    r, _ = _llamar(
        rol, "GET", f"?estado=EN_CONTEO&sucursal_id={conteo.sucursal_id}")

    assert r.status_code == 200, r.text
    assert [c["id"] for c in r.json()] == [str(conteo.id)]
    assert r.json()[0]["progreso"] == {
        "refs_universo": 4210, "refs_contadas": 1300}
    assert progreso.await_args.args[1] == [conteo.id]
    filtros = listar.await_args.kwargs
    assert filtros["estado"] == "EN_CONTEO"
    assert filtros["sucursal_id"] == conteo.sucursal_id
    assert (None if filtros["lider_id"] is None
            else str(filtros["lider_id"])) == lider
    assert HASH not in r.text


def test_closed_conteos_in_the_list_carry_no_progress(monkeypatch):
    conteo = _conteo(estado="CERRADO")
    monkeypatch.setattr(consultas, "listar", AsyncMock(
        return_value=[(conteo, "Quilichao", "Lina")]))
    progreso = AsyncMock(return_value={})
    monkeypatch.setattr(panel, "progreso", progreso)

    r, _ = _llamar("ADMIN", "GET", "")

    assert r.status_code == 200, r.text
    assert r.json()[0]["progreso"] is None
    assert progreso.await_args.args[1] == []


def test_an_unknown_estado_filter_is_a_422():
    r, _ = _llamar("ADMIN", "GET", "?estado=CUALQUIERA")

    assert r.status_code == 422


# --- schedule, reschedule, annul (ADMIN) -------------------------------------


def test_admin_schedules_a_conteo(monkeypatch, datos):
    conteo = _conteo(estado="PROGRAMADO")
    programar = AsyncMock(return_value=conteo)
    monkeypatch.setattr(snapshot, "programar_conteo", programar)
    cuerpo = {"sucursal_id": str(conteo.sucursal_id),
              "lider_id": str(LIDER_ID), "fecha_programada": "2026-10-12"}

    r, sesion = _llamar("ADMIN", "POST", "", json=cuerpo)

    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "PROGRAMADO"
    args = programar.await_args.args
    assert args[1:] == (
        conteo.sucursal_id, LIDER_ID, datetime.date(2026, 10, 12),
        ADMIN_ID)
    assert sesion.committed


@pytest.mark.parametrize("error,estado", [
    (errores.SucursalInvalida(), 422),
    (errores.LiderInvalido(), 422),
    (errores.MotivoRequerido(), 422),
    (errores.EstadoInvalido("No se puede.", estado="CERRADO"), 409),
    (errores.ConteoTotalAbierto(), 409),
    (errores.SinInventario(), 409),
    (errores.UmbralesInvalidos(), 409),
    (errores.ConteoNoEncontrado(), 404),
])
def test_domain_errors_map_to_http_with_their_spanish_message(
        monkeypatch, error, estado):
    monkeypatch.setattr(
        snapshot, "programar_conteo", AsyncMock(side_effect=error))
    cuerpo = {"sucursal_id": str(uuid.uuid4()),
              "lider_id": str(uuid.uuid4()),
              "fecha_programada": "2026-10-12"}

    r, sesion = _llamar("ADMIN", "POST", "", json=cuerpo)

    assert r.status_code == estado
    assert r.json()["detail"] == {
        "code": error.codigo, "mensaje": error.mensaje, **error.datos}
    assert not sesion.committed


def test_admin_reschedules_and_reassigns(monkeypatch, datos):
    conteo = _conteo(estado="PROGRAMADO")
    reprogramar = AsyncMock(return_value=conteo)
    monkeypatch.setattr(snapshot, "reprogramar_conteo", reprogramar)

    r, sesion = _llamar("ADMIN", "PATCH", f"/{conteo.id}", json={
        "fecha_programada": "2026-10-20", "lider_id": str(OTRO_LIDER_ID)})

    assert r.status_code == 200, r.text
    assert reprogramar.await_args.args[1:] == (
        conteo.id, datetime.date(2026, 10, 20), OTRO_LIDER_ID)
    assert sesion.committed


def test_admin_annuls_with_a_reason(monkeypatch, datos):
    conteo = _conteo(estado="ANULADO")
    anular = AsyncMock(return_value=conteo)
    monkeypatch.setattr(snapshot, "anular_conteo", anular)

    r, sesion = _llamar(
        "ADMIN", "POST", f"/{conteo.id}/anular", json={"motivo": "Lluvia"})

    assert r.status_code == 200, r.text
    assert anular.await_args.args[1:4] == (conteo.id, ADMIN_ID, "Lluvia")
    assert sesion.committed


def test_annul_without_a_reason_is_a_422(monkeypatch):
    monkeypatch.setattr(snapshot, "anular_conteo", AsyncMock(
        side_effect=errores.MotivoRequerido()))

    r, _ = _llamar("ADMIN", "POST", f"/{uuid.uuid4()}/anular", json={})

    assert r.status_code == 422
    _detalle(r, "MOTIVO_REQUERIDO")


# --- iniciar, code, QR -------------------------------------------------------


def _inicio(conteo, codigo="048213", advertencia=None):
    fuente = snapshot.FuenteSnapshot(
        uuid.uuid4(), AHORA.date(), AHORA, 3)
    return snapshot.InicioConteo(conteo, codigo, fuente, advertencia)


@pytest.mark.parametrize("rol", ["ADMIN", "LIDER_INVENTARIOS"])
def test_iniciar_returns_the_plain_code_once(monkeypatch, datos, rol):
    conteo = _conteo()
    iniciar = AsyncMock(return_value=_inicio(conteo))
    monkeypatch.setattr(snapshot, "iniciar_conteo", iniciar)

    r, sesion = _llamar(
        rol, "POST", f"/{conteo.id}/iniciar", conteo,
        json={"confirmar_antiguedad": True})

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["codigo"] == "048213"
    assert cuerpo["conteo"]["acceso"]["slug"] == conteo.enlace_slug
    assert cuerpo["conteo"]["acceso"]["url"].endswith(
        "/motored/c/" + conteo.enlace_slug)
    assert iniciar.await_args.kwargs["confirmar_inventario_viejo"] is True
    assert sesion.committed
    assert HASH not in r.text and "codigo_hash" not in r.text
    detalle, _ = _llamar(rol, "GET", f"/{conteo.id}", conteo)
    assert "048213" not in detalle.text


def test_a_stale_inventory_is_a_409_with_its_facts(monkeypatch):
    conteo = _conteo(estado="PROGRAMADO")
    error = errores.InventarioAntiguo(
        "Viejo.", fecha_corte="2026-10-05", antiguedad_horas="80.0",
        vigencia_horas=24)
    monkeypatch.setattr(
        snapshot, "iniciar_conteo", AsyncMock(side_effect=error))

    r, sesion = _llamar(
        "LIDER_INVENTARIOS", "POST", f"/{conteo.id}/iniciar", conteo)

    assert r.status_code == 409
    assert r.json()["detail"] == {
        "code": "INVENTARIO_ANTIGUO", "mensaje": "Viejo.",
        "fecha_corte": "2026-10-05", "antiguedad_horas": "80.0",
        "vigencia_horas": 24}
    assert not sesion.committed


def test_rotating_returns_the_new_code_once(monkeypatch):
    conteo = _conteo()
    rotar = AsyncMock(return_value="000417")
    monkeypatch.setattr(acceso, "rotar_codigo", rotar)

    r, sesion = _llamar(
        "LIDER_INVENTARIOS", "POST", f"/{conteo.id}/codigo/rotar", conteo)

    assert r.status_code == 200, r.text
    assert r.json()["codigo"] == "000417"
    assert rotar.await_args.args[1] == conteo.id
    assert sesion.committed


def test_the_qr_is_a_png_of_the_public_url(monkeypatch):
    conteo = _conteo()

    r, _ = _llamar("ADMIN", "GET", f"/{conteo.id}/qr.png", conteo)

    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store"
    assert r.content.startswith(b"\x89PNG")


def test_the_qr_of_a_conteo_not_running_is_a_409():
    conteo = _conteo(estado="PROGRAMADO")

    r, _ = _llamar("ADMIN", "GET", f"/{conteo.id}/qr.png", conteo)

    assert r.status_code == 409
    _detalle(r, "ESTADO_INVALIDO")


def test_without_a_public_url_the_qr_is_a_409(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", "")
    conteo = _conteo()

    r, _ = _llamar("ADMIN", "GET", f"/{conteo.id}/qr.png", conteo)

    assert r.status_code == 409
    _detalle(r, "ENLACE_SIN_CONFIGURAR")


# --- helper lists ------------------------------------------------------------


def test_admin_lists_the_active_leaders(monkeypatch):
    fila = consultas.OpcionLider(
        LIDER_ID, "Lina", "l@x.com", "LIDER_INVENTARIOS")
    monkeypatch.setattr(
        consultas, "lideres_activos", AsyncMock(return_value=[fila]))

    r, _ = _llamar("ADMIN", "GET", "/lideres")

    assert r.status_code == 200, r.text
    assert r.json() == [
        {"id": str(LIDER_ID), "nombre": "Lina", "email": "l@x.com",
         "rol": "LIDER_INVENTARIOS"}]


def test_admin_lists_the_stores_with_their_latest_inventory(monkeypatch):
    fila = {"id": uuid.uuid4(), "nombre": "Quilichao", "inventario": {
        "carga_id": uuid.uuid4(), "fecha_corte": AHORA.date(),
        "aplicado_en": AHORA, "antiguedad_horas": Decimal("2.5")},
        "vigencia_horas": 24}
    monkeypatch.setattr(
        consultas, "sucursales", AsyncMock(return_value=[fila]))

    r, _ = _llamar("ADMIN", "GET", "/sucursales")

    assert r.status_code == 200, r.text
    assert r.json()[0]["inventario"]["antiguedad_horas"] == "2.5"


# --- pair sessions (leader side) ---------------------------------------------


def _fila_sesion(conteo, estado="CONECTADA"):
    sesion = ConteoSesion(
        id=uuid.uuid4(), conteo_id=conteo.id, tipo="PAREJA",
        token_hash="a" * 64, estado=estado, dispositivo="MOVIL",
        conectada_en=AHORA, ultima_actividad_en=AHORA)
    integrantes = [
        ConteoIntegrante(orden=1, nombre="Ana Ruiz", cedula=CEDULA),
        ConteoIntegrante(orden=2, nombre="Luis Gil", cedula="79123193")]
    return sesiones.FilaSesion(sesion, 1, integrantes, None)


@pytest.mark.parametrize("rol", ["ADMIN", "LIDER_INVENTARIOS", "GERENCIA"])
def test_the_sessions_list_never_carries_a_cedula(monkeypatch, rol):
    conteo = _conteo()
    fila = _fila_sesion(conteo)
    monkeypatch.setattr(sesiones, "listar", AsyncMock(return_value=[fila]))

    r, _ = _llamar(rol, "GET", f"/{conteo.id}/sesiones", conteo)

    assert r.status_code == 200, r.text
    item = r.json()[0]
    assert item["etiqueta"] == "Pareja 1 · Ana R. y Luis G."
    assert item["integrantes"] == ["Ana Ruiz", "Luis Gil"]
    assert CEDULA not in r.text and "79123193" not in r.text
    assert "cedula" not in r.text and "token" not in r.text


def test_the_leader_disconnects_a_pair(monkeypatch):
    conteo = _conteo()
    fila = _fila_sesion(conteo, estado="DESCONECTADA")
    desconectar = AsyncMock(return_value=fila)
    monkeypatch.setattr(sesiones, "desconectar", desconectar)

    r, sesion = _llamar(
        "LIDER_INVENTARIOS", "POST",
        f"/{conteo.id}/sesiones/{fila.sesion.id}/desconectar", conteo)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "DESCONECTADA"
    assert desconectar.await_args.args[1:4] == (
        conteo.id, fila.sesion.id, LIDER_ID)
    assert sesion.committed


def test_the_router_answers_503_while_motored_is_off(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", False)

    r, _ = _llamar("ADMIN", "GET", "")

    assert r.status_code == 503
