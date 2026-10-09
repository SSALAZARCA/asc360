"""
Inventory counts, public pair access (odd/motored-conteos-inventario, WU7;
design §6.2, §5.3, §8.1-§8.3, §8.6).

`POST /publico/conteos/{slug}/unirse` with no user account: the 6-digit
code plus 2-3 members. Same `FakeAsyncSession` queue convention as
`test_publico_informe.py`: the leading `[]` is the DB probe, then the
locked `(conteo, store name)` lookup, then the client's attempt row.
"""
import datetime
import hashlib
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.limiter import limiter
from app.main import app
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_acceso_intento import ConteoAccesoIntento
from app.motored.models.conteo_sesion import ConteoIntegrante, ConteoSesion
from app.motored.services.conteos import acceso, sesiones
from tests.motored.conftest import FakeAsyncSession, override_motored_db

BASE = "/api/motored/publico/conteos"
SLUG = "SlugDePrueba1234"
CODIGO = "482913"
GENERICO = {
    "code": "ACCESO_INVALIDO", "mensaje": "Código o enlace no válidos."}
CEDULAS = ("1130124821", "79123193")
TOKEN = "token-de-dispositivo-" + "x" * 30
UTC = datetime.timezone.utc


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "conteos-publico")
    monkeypatch.setattr(settings, "SECRET_KEY", "conteos-publico-asc360")
    limiter.reset()
    yield
    limiter.reset()
    app.dependency_overrides.clear()


def _ahora():
    return datetime.datetime.now(UTC)


def _conteo(estado="EN_CONTEO"):
    conteo = Conteo(
        id=uuid.uuid4(), tipo="TOTAL", estado=estado, origen="MANUAL",
        sucursal_id=uuid.uuid4(), lider_id=uuid.uuid4(),
        fecha_programada=_ahora().date(), enlace_slug=SLUG,
        acceso_fallidos_hora=0, umbral_reconteo_pesos=Decimal("1"),
        umbral_critico_pesos=Decimal("2"))
    conteo.codigo_hash = acceso.hash_codigo(conteo.id, CODIGO)
    return conteo


def _intento(conteo, fallidos=0, bloqueado_hasta=None):
    return ConteoAccesoIntento(
        conteo_id=conteo.id, cliente="c" * 64, fallidos=fallidos,
        ventana_inicio=_ahora(), bloqueado_hasta=bloqueado_hasta)


def _cuerpo(codigo=CODIGO, **extra):
    cuerpo = {"codigo": codigo, "dispositivo": "MOVIL", "integrantes": [
        {"nombre": "Ana Ruiz", "cedula": "1.130.124.821"},
        {"nombre": "Luis Gil", "cedula": CEDULAS[1]}]}
    cuerpo.update(extra)
    return cuerpo


def _unirse(filas, cuerpo=None, slug=SLUG):
    sesion = FakeAsyncSession(execute_queue=[[]] + list(filas))
    override_motored_db(sesion)
    respuesta = TestClient(app).post(
        f"{BASE}/{slug}/unirse", json=cuerpo or _cuerpo())
    return respuesta, sesion


def _cabeceras(r):
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-robots-tag"] == "noindex, nofollow"


def _sin_cedulas(r):
    for cedula in CEDULAS:
        assert cedula not in r.text
    assert "cedula" not in r.text


# --- unirse ------------------------------------------------------------------


def test_the_right_code_creates_a_session_with_its_members():
    conteo = _conteo()

    r, sesion = _unirse([[(conteo, "Quilichao")], [], [2]])

    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["etiqueta"] == "Pareja 3 · Ana R. y Luis G."
    assert cuerpo["integrantes"] == ["Ana Ruiz", "Luis Gil"]
    assert cuerpo["sucursal"] == "Quilichao"
    assert cuerpo["estado_conteo"] == "EN_CONTEO"
    creada = sesion.added_of_type(ConteoSesion)[0]
    assert creada.token_hash == hashlib.sha256(
        cuerpo["sesion_token"].encode()).hexdigest()
    assert (creada.estado, creada.dispositivo) == ("CONECTADA", "MOVIL")
    personas = sesion.added_of_type(ConteoIntegrante)
    assert [(p.orden, p.cedula) for p in personas] == [
        (1, CEDULAS[0]), (2, CEDULAS[1])]
    assert sesion.committed
    _sin_cedulas(r)
    _cabeceras(r)


def test_three_members_are_allowed():
    cuerpo = _cuerpo()
    cuerpo["integrantes"].append({"nombre": "Sofía", "cedula": "5551234"})

    r, sesion = _unirse([[(_conteo(), "Q")], [], [0]], cuerpo)

    assert r.status_code == 201, r.text
    assert r.json()["etiqueta"] == "Pareja 1 · Ana R., Luis G. y Sofía"
    assert len(sesion.added_of_type(ConteoIntegrante)) == 3


@pytest.mark.parametrize("caso", [
    "slug", "codigo", "programado", "cerrado", "anulado", "formato"])
def test_every_failure_is_the_same_generic_401(caso):
    estados = {"programado": "PROGRAMADO", "cerrado": "CERRADO",
               "anulado": "ANULADO"}
    conteo = _conteo(estados.get(caso, "EN_CONTEO"))
    filas = [[]] if caso == "slug" else [[(conteo, "Q")], []]
    codigo = {"codigo": "000000", "formato": "12ab"}.get(caso, CODIGO)

    r, sesion = _unirse(filas, _cuerpo(codigo=codigo))

    assert (r.status_code, r.json()) == (401, {"detail": GENERICO})
    assert not sesion.added_of_type(ConteoSesion)
    _cabeceras(r)


def test_a_wrong_code_is_counted_and_committed_before_the_401():
    conteo = _conteo()

    r, sesion = _unirse([[(conteo, "Q")], []], _cuerpo(codigo="000000"))

    assert r.status_code == 401
    intento = sesion.added_of_type(ConteoAccesoIntento)[0]
    assert intento.fallidos == 1 and intento.bloqueado_hasta is None
    assert intento.cliente == hashlib.sha256(b"testclient").hexdigest()
    assert conteo.acceso_fallidos_hora == 1
    assert sesion.committed


def test_five_failures_lock_the_client_for_15_minutes():
    conteo = _conteo()
    intento = _intento(conteo)

    for _ in range(5):
        r, sesion = _unirse(
            [[(conteo, "Q")], [intento]], _cuerpo(codigo="000000"))
        assert r.status_code == 401
        assert sesion.committed

    falta = intento.bloqueado_hasta - _ahora()
    assert datetime.timedelta(minutes=14) < falta
    assert falta <= datetime.timedelta(minutes=15)
    r, sesion = _unirse([[(conteo, "Q")], [intento]])
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "DEMASIADOS_INTENTOS"
    assert not sesion.added_of_type(ConteoSesion)
    _cabeceras(r)


def test_an_expired_lock_lets_the_right_code_in_and_resets_it():
    conteo = _conteo()
    intento = _intento(
        conteo, fallidos=3,
        bloqueado_hasta=_ahora() - datetime.timedelta(seconds=1))

    r, _ = _unirse([[(conteo, "Q")], [intento], [0]])

    assert r.status_code == 201, r.text
    assert (intento.fallidos, intento.bloqueado_hasta) == (0, None)


@pytest.mark.parametrize("integrantes", [
    [{"nombre": "Ana", "cedula": "1130124821"}],
    [{"nombre": "Ana", "cedula": "1130124821"},
     {"nombre": "Luis", "cedula": "1.130.124.821"}],
    [{"nombre": "Ana", "cedula": "11301abc"},
     {"nombre": "Luis", "cedula": "79123193"}],
    [{"nombre": " ", "cedula": "1130124821"},
     {"nombre": "Luis", "cedula": "79123193"}],
    [{"nombre": f"P{i}", "cedula": f"10{i}0000"} for i in range(4)],
])
def test_bad_members_are_a_422_that_never_echoes_the_input(integrantes):
    r, sesion = _unirse([], _cuerpo(integrantes=integrantes))

    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "DATOS_INGRESO_INVALIDOS"
    assert "1130124821" not in r.text and "11301abc" not in r.text
    assert not sesion.committed
    _cabeceras(r)


def test_a_body_that_is_not_json_is_a_422():
    sesion = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(sesion)

    r = TestClient(app).post(f"{BASE}/{SLUG}/unirse", content=b"nada")

    assert r.status_code == 422


# --- the attempt counters (pure rules) ---------------------------------------


def test_the_client_window_restarts_after_15_minutes():
    conteo = _conteo()
    intento = _intento(conteo, fallidos=4)
    despues = _ahora() + datetime.timedelta(minutes=16)

    sesiones.registrar_fallo_cliente(intento, despues)

    assert (intento.fallidos, intento.ventana_inicio) == (1, despues)
    assert intento.bloqueado_hasta is None


def test_30_failures_in_an_hour_rotate_the_code():
    conteo = _conteo()
    ahora = _ahora()
    anterior = conteo.codigo_hash

    rotados = [sesiones.registrar_fallo_conteo(conteo, ahora)
               for _ in range(30)]

    assert rotados == [False] * 29 + [True]
    assert conteo.codigo_hash != anterior
    assert conteo.codigo_rotado_en == ahora
    assert conteo.acceso_fallidos_hora == 0
    assert not acceso.verificar_codigo(conteo.id, CODIGO, conteo.codigo_hash)


def test_the_conteo_window_restarts_after_an_hour():
    conteo = _conteo()
    ahora = _ahora()
    conteo.acceso_fallidos_hora = 29
    conteo.acceso_ventana_inicio = ahora - datetime.timedelta(minutes=61)

    assert sesiones.registrar_fallo_conteo(conteo, ahora) is False
    assert conteo.acceso_fallidos_hora == 1
    assert conteo.acceso_ventana_inicio == ahora


# --- the device session ------------------------------------------------------


def _pareja(estado="CONECTADA", conteo=None):
    conteo = conteo or _conteo()
    sesion = ConteoSesion(
        id=uuid.uuid4(), conteo_id=conteo.id, tipo="PAREJA",
        token_hash=hashlib.sha256(TOKEN.encode()).hexdigest(),
        estado=estado, dispositivo="ESCRITORIO", conectada_en=_ahora(),
        ultima_actividad_en=_ahora())
    return sesion, conteo


def _con_token(metodo, ruta, filas, token=TOKEN):
    sesion = FakeAsyncSession(execute_queue=[[]] + list(filas))
    override_motored_db(sesion)
    cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
    respuesta = TestClient(app).request(
        metodo, f"{BASE}/{SLUG}{ruta}", headers=cabeceras)
    return respuesta, sesion


@pytest.fixture
def describir(monkeypatch):
    async def _describir(db, sesion):
        integrantes = [
            ConteoIntegrante(orden=1, nombre="Ana Ruiz", cedula=CEDULAS[0]),
            ConteoIntegrante(orden=2, nombre="Luis Gil", cedula=CEDULAS[1])]
        return sesiones.FilaSesion(sesion, 2, integrantes, None)
    monkeypatch.setattr(sesiones, "describir", _describir)


def test_who_am_i_returns_names_and_location_only(describir):
    sesion, conteo = _pareja()

    r, _ = _con_token("GET", "/sesion", [[(sesion, conteo, "Quilichao")]])

    assert r.status_code == 200, r.text
    assert r.json() == {
        "sesion_id": str(sesion.id), "etiqueta": "Pareja 2 · Ana R. y Luis G.",
        "integrantes": ["Ana Ruiz", "Luis Gil"], "sucursal": "Quilichao",
        "estado_conteo": "EN_CONTEO", "ubicacion_actual": None}
    _sin_cedulas(r)
    _cabeceras(r)


@pytest.mark.parametrize("caso", [
    "sin_token", "desconocido", "desconectada", "cerrada", "conteo_cerrado",
    "otro_slug"])
def test_anything_but_an_active_session_is_a_401(describir, caso):
    sesion, conteo = _pareja(
        estado={"desconectada": "DESCONECTADA",
                "cerrada": "CERRADA"}.get(caso, "CONECTADA"))
    if caso == "conteo_cerrado":
        conteo.estado = "CERRADO"
    if caso == "otro_slug":
        conteo.enlace_slug = "OtroSlug12345678"
    filas = [] if caso == "sin_token" else (
        [[]] if caso == "desconocido" else [[(sesion, conteo, "Q")]])

    r, _ = _con_token(
        "GET", "/sesion", filas, token=None if caso == "sin_token" else TOKEN)

    assert r.status_code == 401, r.text
    assert r.json()["detail"]["code"] == "SESION_INACTIVA"
    _cabeceras(r)


def test_rotating_the_code_keeps_connected_pairs_counting(describir):
    sesion, conteo = _pareja()
    for _ in range(30):
        sesiones.registrar_fallo_conteo(conteo, _ahora())

    r, _ = _con_token("GET", "/sesion", [[(sesion, conteo, "Q")]])

    assert r.status_code == 200, r.text


def test_salir_disconnects_the_device():
    sesion, conteo = _pareja()

    r, db = _con_token("POST", "/salir", [[(sesion, conteo, "Q")]])

    assert r.status_code == 204, r.text
    assert sesion.estado == "DESCONECTADA"
    assert sesion.desconectada_en is not None
    assert sesion.desconectada_por is None
    assert db.committed
    _cabeceras(r)


def test_activity_is_touched_at_most_every_20_seconds(monkeypatch):
    sesion, conteo = _pareja()
    viejo = _ahora() - datetime.timedelta(seconds=30)
    sesion.ultima_actividad_en = viejo
    monkeypatch.setattr(sesiones, "describir", AsyncMock(
        return_value=sesiones.FilaSesion(sesion, 1, [], None)))

    r, db = _con_token("GET", "/sesion", [[(sesion, conteo, "Q")]])

    assert r.status_code == 200, r.text
    assert sesion.ultima_actividad_en > viejo
    assert db.committed


# --- blind guard -------------------------------------------------------------

PROHIBIDOS = (
    "existencia", "costo", "diferencia", "valor", "sistema")


def _campos(esquema, componentes, vistos):
    if isinstance(esquema, list):
        for item in esquema:
            yield from _campos(item, componentes, vistos)
        return
    if not isinstance(esquema, dict):
        return
    ref = esquema.get("$ref")
    if ref and ref not in vistos:
        vistos.add(ref)
        yield from _campos(
            componentes[ref.rsplit("/", 1)[-1]], componentes, vistos)
    for nombre in esquema.get("properties", {}):
        yield nombre
    for valor in esquema.values():
        yield from _campos(valor, componentes, vistos)


def test_no_public_response_carries_expected_quantities_or_money():
    documento = app.openapi()
    componentes = documento["components"]["schemas"]
    rutas = {p: v for p, v in documento["paths"].items()
             if p.startswith(BASE)}
    assert len(rutas) >= 9
    campos = set()
    for operaciones in rutas.values():
        for operacion in operaciones.values():
            campos.update(_campos(
                operacion.get("responses", {}), componentes, set()))
    assert {"etiqueta", "integrantes", "aceptadas", "desconocidos",
            "referencias", "resumen_ubicacion", "creada"} <= campos
    prohibidos = {c for c in campos
                  if any(p in c.lower() for p in PROHIBIDOS)}
    assert prohibidos == set()
