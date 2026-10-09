"""
Inventory counts, pair readings (odd/motored-conteos-inventario, WU8;
design §6.2, §7, ADR-5, ADR-6, §9.5).

Public routes behind the device token: the referencia catalogue (ETag),
the store's locations, setting the current location, the reading batches
(idempotent, set-based), voiding and the recent readings.

Same `FakeAsyncSession` queue convention as `test_publico_conteos.py`:
the leading `[]` is the DB probe, then the `(session, conteo, store)` row
of `sesion_de_pareja`, then the service's own queries in order.
"""
import datetime
import gzip
import hashlib
import json
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Insert

from app.config import settings
from app.core.limiter import limiter
from app.main import app
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_lectura import ConteoLectura
from app.motored.models.conteo_sesion import ConteoSesion
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import (
    catalogo, errores, lecturas, ubicaciones,
)
from tests.motored.conftest import FakeAsyncSession, override_motored_db

BASE = "/api/motored/publico/conteos"
SLUG = "SlugDePrueba1234"
TOKEN = "token-de-dispositivo-" + "y" * 30
UTC = datetime.timezone.utc
PROHIBIDOS = ("existencia", "costo", "diferencia", "valor", "sistema")
REF_A, REF_B = uuid.uuid4(), uuid.uuid4()


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "conteos-lect")
    monkeypatch.setattr(settings, "SECRET_KEY", "conteos-lect-asc360")
    limiter.reset()
    catalogo.limpiar_cache()
    yield
    catalogo.limpiar_cache()
    limiter.reset()
    app.dependency_overrides.clear()


def _ahora():
    return datetime.datetime.now(UTC)


def _ubicacion(codigo="A3", activa=True, sucursal_id=None):
    return UbicacionInventario(
        id=uuid.uuid4(), sucursal_id=sucursal_id or uuid.uuid4(),
        codigo=codigo, nombre=f"Estante {codigo}", activa=activa,
        origen="LIDER")


def _pareja(estado_conteo="EN_CONTEO", ubicacion=None, estado="CONECTADA"):
    conteo = Conteo(
        id=uuid.uuid4(), tipo="TOTAL", estado=estado_conteo,
        origen="MANUAL", sucursal_id=uuid.uuid4(), lider_id=uuid.uuid4(),
        fecha_programada=_ahora().date(), enlace_slug=SLUG,
        umbral_reconteo_pesos=Decimal("1"),
        umbral_critico_pesos=Decimal("2"))
    sesion = ConteoSesion(
        id=uuid.uuid4(), conteo_id=conteo.id, tipo="PAREJA",
        token_hash=hashlib.sha256(TOKEN.encode()).hexdigest(),
        estado=estado, dispositivo="ESCRITORIO", conectada_en=_ahora(),
        ultima_actividad_en=_ahora(),
        ubicacion_actual_id=None if ubicacion is None else ubicacion.id)
    return sesion, conteo


def _llamar(metodo, ruta, filas, pareja=None, **kwargs):
    sesion, conteo = pareja or _pareja()
    db = FakeAsyncSession(
        execute_queue=[[], [(sesion, conteo, "Quilichao")]] + list(filas))
    override_motored_db(db)
    cabeceras = {"Authorization": f"Bearer {TOKEN}"}
    cabeceras.update(kwargs.pop("headers", {}))
    respuesta = TestClient(app).request(
        metodo, f"{BASE}/{SLUG}{ruta}", headers=cabeceras, **kwargs)
    return respuesta, db


def _claves(valor):
    if isinstance(valor, dict):
        for clave, hijo in valor.items():
            yield clave
            yield from _claves(hijo)
    elif isinstance(valor, list):
        for hijo in valor:
            yield from _claves(hijo)


def _ciego(r):
    """The answer carries no expected quantity, cost or difference."""
    assert r.headers["cache-control"] == "no-store"
    if r.status_code == 304 or not r.content:
        return
    claves = set(_claves(r.json()))
    assert not {c for c in claves
                if any(p in c.lower() for p in PROHIBIDOS)}, claves


def _item(codigo="ABC-1", **extra):
    item = {"id": str(uuid.uuid4()), "codigo_leido": codigo,
            "leida_en": _ahora().isoformat(), "metodo": "ESCANER"}
    item.update(extra)
    return item


def _inserciones(db):
    return [s for s in db.executed_statements if isinstance(s, Insert)]


# --- normalization (pure) ----------------------------------------------------


@pytest.mark.parametrize("crudo, esperado", [
    (" abc-123 ", "ABC-123"), ("Abc-123", "ABC-123"),
    ("\tabc-123\n", "ABC-123")])
def test_a_scanned_code_is_trimmed_and_upper_cased(crudo, esperado):
    assert lecturas.normalizar_codigo(crudo) == esperado


@pytest.mark.parametrize("crudo, esperado", [
    ("UBI-A3", "A3"), (" ubi-a3 ", "A3"), ("estante  a3", "ESTANTE A3"),
    ("B2", "B2")])
def test_a_location_code_drops_the_label_prefix(crudo, esperado):
    assert ubicaciones.codigo_ubicacion(crudo) == esperado


@pytest.mark.parametrize("crudo", ["", "   ", "UBI-", "UBI-  ", "X" * 31])
def test_an_empty_or_long_location_code_is_invalid(crudo):
    with pytest.raises(errores.UbicacionInvalida):
        ubicaciones.codigo_ubicacion(crudo)


def test_only_a_ubi_prefix_marks_a_location_label():
    assert ubicaciones.es_etiqueta(" ubi-a3")
    assert not ubicaciones.es_etiqueta("ABC-UBI-1")


def _entrada(codigo, cantidad="1", forzar=False, ident=None):
    return lecturas.Entrada(
        id=ident or uuid.uuid4(), codigo_leido=codigo,
        cantidad=Decimal(cantidad), leida_en=_ahora(), metodo="MANUAL",
        forzar_desconocido=forzar)


def test_classify_splits_known_unknown_forced_and_invalid():
    resueltas = {"ABC-1": (REF_A, "Pastilla")}
    repetida = uuid.uuid4()
    items = [
        _entrada(" abc-1 ", "2", ident=repetida), _entrada("ABC-1"),
        _entrada("abc-1", ident=repetida), _entrada("ZZZ"),
        _entrada("yyy", forzar=True), _entrada("UBI-B2", forzar=True),
        _entrada("ABC-1", "0"), _entrada("ABC-1", "100000"),
        _entrada("ABC-1", "1.005"), _entrada("   ")]

    lote = lecturas.clasificar(items, resueltas)

    assert [(f["codigo_leido"], f["referencia_id"], f["cantidad"])
            for f in lote.filas] == [
        ("ABC-1", REF_A, Decimal("2")), ("ABC-1", REF_A, Decimal("1")),
        ("YYY", None, Decimal("1"))]
    assert lote.repetidas == [repetida]
    assert lote.desconocidos == [(items[3].id, "ZZZ")]
    assert [m for _, m in lote.rechazadas] == [
        "ES_UBICACION", "CANTIDAD_INVALIDA", "CANTIDAD_INVALIDA",
        "CANTIDAD_INVALIDA", "CODIGO_INVALIDO"]


# --- catalogue (ADR-6) -------------------------------------------------------

FILAS_CATALOGO = [("ABC-1", "Pastilla freno"), ("R-1", None)]


def test_the_catalogue_lists_every_code_with_an_etag():
    r, _ = _llamar("GET", "/catalogo", [FILAS_CATALOGO])

    assert r.status_code == 200, r.text
    assert r.json()["referencias"] == [
        ["ABC-1", "Pastilla freno"], ["R-1", ""]]
    assert r.headers["etag"].startswith('"')
    _ciego(r)


def test_the_catalogue_answers_304_when_the_etag_matches():
    r, _ = _llamar("GET", "/catalogo", [FILAS_CATALOGO])
    etag = r.headers["etag"]

    r2, db = _llamar(
        "GET", "/catalogo", [], headers={"If-None-Match": etag})

    assert r2.status_code == 304, r2.text
    assert r2.headers["etag"] == etag
    assert len(db.executed_statements) == 2
    _ciego(r2)


def test_a_stale_etag_gets_the_full_catalogue_again():
    r, _ = _llamar(
        "GET", "/catalogo", [FILAS_CATALOGO],
        headers={"If-None-Match": '"viejo"'})

    assert r.status_code == 200
    assert len(r.json()["referencias"]) == 2


def test_the_catalogue_is_gzipped_when_the_client_accepts_it():
    cat = catalogo.armar(FILAS_CATALOGO)

    assert json.loads(gzip.decompress(cat.comprimido)) == json.loads(
        cat.cuerpo)
    r, _ = _llamar(
        "GET", "/catalogo", [FILAS_CATALOGO],
        headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in r.headers["vary"]


# --- locations ---------------------------------------------------------------


def test_the_pair_lists_the_active_locations_of_its_store():
    ubicacion = _ubicacion()

    r, _ = _llamar("GET", "/ubicaciones", [[ubicacion]])

    assert r.status_code == 200, r.text
    assert r.json() == [{"id": str(ubicacion.id), "codigo": "A3",
                         "nombre": "Estante A3"}]
    _ciego(r)


def test_a_scanned_label_sets_an_existing_location():
    ubicacion = _ubicacion()
    pareja = _pareja()

    r, db = _llamar(
        "PUT", "/ubicacion", [[ubicacion]], pareja,
        json={"codigo": " ubi-a3 "})

    assert r.status_code == 200, r.text
    assert r.json() == {"creada": False, "ubicacion": {
        "id": str(ubicacion.id), "codigo": "A3", "nombre": "Estante A3"}}
    assert pareja[0].ubicacion_actual_id == ubicacion.id
    assert db.committed
    _ciego(r)


def test_an_unknown_location_is_created_by_the_pair():
    pareja = _pareja()
    nueva = uuid.uuid4()

    r, db = _llamar(
        "PUT", "/ubicacion", [[], [], [nueva]], pareja,
        json={"codigo": "pasillo 2", "nombre": "Pasillo dos"})

    assert r.status_code == 200, r.text
    assert r.json() == {"creada": True, "ubicacion": {
        "id": str(nueva), "codigo": "PASILLO 2", "nombre": "Pasillo dos"}}
    assert pareja[0].ubicacion_actual_id == nueva
    assert len(_inserciones(db)) == 1


def test_a_new_location_without_name_is_named_after_its_code():
    r, _ = _llamar(
        "PUT", "/ubicacion", [[], [], [uuid.uuid4()]],
        json={"codigo": "b7"})

    assert r.json()["ubicacion"]["nombre"] == "B7"


def test_an_inactive_location_cannot_be_used():
    r, db = _llamar(
        "PUT", "/ubicacion", [[_ubicacion(activa=False)]],
        json={"codigo": "A3"})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "UBICACION_INACTIVA"
    assert not db.committed


def test_a_location_whose_label_is_a_referencia_code_is_refused():
    r, db = _llamar(
        "PUT", "/ubicacion", [[], [REF_A]], json={"codigo": "A3"})

    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UBICACION_CHOCA_REFERENCIA"
    assert not _inserciones(db)


# --- readings ----------------------------------------------------------------


def test_a_reading_without_a_location_is_a_409():
    r, db = _llamar("POST", "/lecturas", [], json={"lecturas": [_item()]})

    assert r.status_code == 409
    assert r.json()["detail"] == {
        "code": "SIN_UBICACION",
        "mensaje": "Primero indique la ubicación."}
    assert not _inserciones(db)


def test_more_than_100_readings_is_a_422():
    pareja = _pareja(ubicacion=_ubicacion())
    lote = [_item() for _ in range(101)]

    r, _ = _llamar("POST", "/lecturas", [], pareja, json={"lecturas": lote})

    assert r.status_code == 422


def test_an_empty_batch_is_a_422():
    r, _ = _llamar("POST", "/lecturas", [], json={"lecturas": []})

    assert r.status_code == 422


def test_a_batch_is_one_insert_and_unknowns_are_not_stored():
    pareja = _pareja(ubicacion=_ubicacion())
    conocida = _item(" abc-1 ")
    minuscula = _item("r-1", cantidad="3")
    desconocida = _item("ZZZ")
    previa = _item("ABC-1")
    filas = [["EN_CONTEO"], [(REF_A, "ABC-1", "Pastilla")],
             [(REF_B, "r-1", "Filtro")],
             [uuid.UUID(conocida["id"]), uuid.UUID(minuscula["id"])]]

    r, db = _llamar(
        "POST", "/lecturas", filas, pareja,
        json={"lecturas": [conocida, minuscula, desconocida, previa]})

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["aceptadas"] == [conocida["id"], minuscula["id"]]
    assert cuerpo["duplicadas"] == [previa["id"]]
    assert cuerpo["desconocidos"] == [
        {"id": desconocida["id"], "codigo": "ZZZ"}]
    assert cuerpo["rechazadas"] == []
    assert cuerpo["referencias"] == {"ABC-1": "Pastilla", "R-1": "Filtro"}
    assert len(_inserciones(db)) == 1
    assert db.committed
    _ciego(r)


def test_a_forced_unknown_code_is_stored_without_referencia():
    pareja = _pareja(ubicacion=_ubicacion())
    forzada = _item("zzz", forzar_desconocido=True)

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], [], [], [uuid.UUID(forzada["id"])]],
        pareja, json={"lecturas": [forzada]})

    assert r.status_code == 200, r.text
    assert r.json()["aceptadas"] == [forzada["id"]]
    assert r.json()["desconocidos"] == []
    assert len(_inserciones(db)) == 1


def test_a_batch_with_nothing_storable_runs_no_insert():
    pareja = _pareja(ubicacion=_ubicacion())

    r, db = _llamar(
        "POST", "/lecturas", [["EN_CONTEO"], [], []], pareja,
        json={"lecturas": [_item("ZZZ"), _item("UBI-A3"),
                           _item("ABC-1", cantidad="0")]})

    assert r.status_code == 200, r.text
    assert [m["motivo"] for m in r.json()["rechazadas"]] == [
        "ES_UBICACION", "CANTIDAD_INVALIDA"]
    assert not _inserciones(db)


def test_readings_after_round_one_closed_are_refused():
    pareja = _pareja("EN_RECONTEO", ubicacion=_ubicacion())
    item = _item()

    r, db = _llamar("POST", "/lecturas", [["EN_RECONTEO"]], pareja,
                    json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert r.json()["rechazadas"] == [
        {"id": item["id"], "motivo": "RONDA_CERRADA"}]
    assert not _inserciones(db)


def test_a_bad_metodo_is_a_422():
    pareja = _pareja(ubicacion=_ubicacion())

    r, _ = _llamar("POST", "/lecturas", [], pareja,
                   json={"lecturas": [_item(metodo="LASER")]})

    assert r.status_code == 422


# --- voiding -----------------------------------------------------------------


def _lectura(sesion, conteo, anulada_en=None):
    return ConteoLectura(
        id=uuid.uuid4(), conteo_id=conteo.id, sesion_id=sesion.id,
        ubicacion_id=uuid.uuid4(), referencia_id=REF_A,
        codigo_leido="ABC-1", cantidad=Decimal("1"), ronda=1,
        metodo="ESCANER", leida_en=_ahora(), anulada_en=anulada_en)


def test_a_pair_voids_its_own_reading():
    pareja = _pareja()
    lectura = _lectura(*pareja)

    r, db = _llamar(
        "POST", f"/lecturas/{lectura.id}/anular", [[lectura]], pareja)

    assert r.status_code == 200, r.text
    assert lectura.anulada_en is not None
    assert r.json()["id"] == str(lectura.id)
    assert db.committed
    _ciego(r)


def test_voiding_twice_keeps_the_first_time():
    pareja = _pareja()
    antes = _ahora() - datetime.timedelta(minutes=3)
    lectura = _lectura(*pareja, anulada_en=antes)

    r, _ = _llamar(
        "POST", f"/lecturas/{lectura.id}/anular", [[lectura]], pareja)

    assert r.status_code == 200
    assert lectura.anulada_en == antes


def test_another_sessions_reading_is_not_found():
    r, db = _llamar("POST", f"/lecturas/{uuid.uuid4()}/anular", [[]])

    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "LECTURA_NO_ENCONTRADA"
    assert "sesion_id" in str(db.executed_statements[-1])


def test_a_round_one_reading_cannot_be_voided_in_reconteo():
    pareja = _pareja("EN_RECONTEO")
    lectura = _lectura(*pareja)

    r, _ = _llamar(
        "POST", f"/lecturas/{lectura.id}/anular", [[lectura]], pareja)

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "RONDA_CERRADA"
    assert lectura.anulada_en is None


# --- recent readings ---------------------------------------------------------


def test_recent_readings_and_the_location_summary():
    ubicacion = _ubicacion()
    pareja = _pareja(ubicacion=ubicacion)
    ident = uuid.uuid4()
    reciente = (ident, "ABC-1", "Pastilla", Decimal("2"), "ESCANER",
                "A3", "Estante A3", _ahora(), None)
    resumen = [("ABC-1", "Pastilla", Decimal("5"), 3),
               ("ZZZ", None, Decimal("1"), 1)]

    r, db = _llamar(
        "GET", "/lecturas/recientes?limite=10",
        [[ubicacion], [reciente], resumen], pareja)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ubicacion_actual"]["codigo"] == "A3"
    assert cuerpo["lecturas"][0]["id"] == str(ident)
    assert cuerpo["lecturas"][0]["ubicacion"] == {
        "codigo": "A3", "nombre": "Estante A3"}
    assert cuerpo["resumen_ubicacion"] == [
        {"codigo": "ABC-1", "descripcion": "Pastilla", "cantidad": "5",
         "lecturas": 3},
        {"codigo": "ZZZ", "descripcion": None, "cantidad": "1",
         "lecturas": 1}]
    assert "LIMIT" in str(db.executed_statements[-2])
    _ciego(r)


def test_recent_readings_without_a_location_have_no_summary():
    r, _ = _llamar("GET", "/lecturas/recientes", [[]])

    assert r.status_code == 200, r.text
    assert r.json() == {
        "ubicacion_actual": None, "lecturas": [], "resumen_ubicacion": []}


@pytest.mark.parametrize("limite", [0, 201])
def test_the_recent_limit_is_bounded(limite):
    r, _ = _llamar("GET", f"/lecturas/recientes?limite={limite}", [])

    assert r.status_code == 422


# --- sessions that are not active --------------------------------------------

RUTAS = [
    ("GET", "/catalogo", None), ("GET", "/ubicaciones", None),
    ("PUT", "/ubicacion", {"codigo": "A3"}),
    ("POST", "/lecturas", {"lecturas": [_item()]}),
    ("POST", f"/lecturas/{uuid.uuid4()}/anular", None),
    ("GET", "/lecturas/recientes", None)]


@pytest.mark.parametrize("metodo, ruta, cuerpo", RUTAS)
@pytest.mark.parametrize("caso", ["desconectada", "conteo_cerrado"])
def test_every_reading_route_needs_an_active_session(
        metodo, ruta, cuerpo, caso):
    estado = "DESCONECTADA" if caso == "desconectada" else "CONECTADA"
    pareja = _pareja(
        "CERRADO" if caso == "conteo_cerrado" else "EN_CONTEO",
        estado=estado)

    r, db = _llamar(metodo, ruta, [], pareja, json=cuerpo)

    assert r.status_code == 401, r.text
    assert r.json()["detail"]["code"] == "SESION_INACTIVA"
    assert not db.committed
