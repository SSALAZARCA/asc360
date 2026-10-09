"""
Inventory counts, per-reading location (odd/motored-conteos-inventario,
WU13b; design §7).

A pair keeps counting offline, moving shelves included: each reading may
carry the location code in effect when it was scanned (`ubicacion_codigo`,
`UBI-` accepted). The server files it there, creating a missing location
as 'PAREJA' like `PUT /ubicacion`; without a code it falls back to the
session's current location, and with neither the batch is the old 409.
The session's current location follows the newest stored reading.

Same `FakeAsyncSession` queue convention as `test_publico_conteos_
lecturas.py`: the leading `[]` is the DB probe, then the `(session,
conteo, store)` row of `sesion_de_pareja`, then the service's queries:
conteo estado, referencia lookup, the locations (one set-based SELECT;
for missing codes the referencia clash check and one INSERT), then the
readings INSERT.
"""
import datetime
import uuid

from sqlalchemy.dialects import postgresql

from app.motored.models.ubicacion_inventario import UbicacionInventario
from tests.motored.test_publico_conteos_lecturas import (  # noqa: F401
    REF_A, _ahora, _ciego, _inserciones, _item, _listo, _llamar, _pareja,
    _ubicacion,
)

RID = uuid.uuid4()
CONOCIDA = [(REF_A, "ABC-1", "Pastilla")]


def _params(insercion):
    return insercion.compile(dialect=postgresql.dialect()).params


def _lecturas_insert(db):
    """The readings INSERT (the last INSERT of the request)."""
    return _inserciones(db)[-1]


def _en(minutos):
    instante = _ahora() + datetime.timedelta(minutes=minutos)
    return instante.isoformat()


def _fila(ubicacion):
    return (ubicacion.id, ubicacion.codigo, ubicacion.activa)


def test_a_stamped_reading_lands_in_its_own_location():
    a3, b2 = _ubicacion("A3"), _ubicacion("B2")
    pareja = _pareja(ubicacion=a3)
    item = _item(ubicacion_codigo="B2")

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [_fila(b2)], [uuid.UUID(item["id"])]],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert r.json()["aceptadas"] == [item["id"]]
    assert _params(_lecturas_insert(db))["ubicacion_id_m0"] == b2.id
    assert pareja[0].ubicacion_actual_id == b2.id
    _ciego(r)


def test_an_unstamped_reading_falls_back_to_the_session_location():
    a3 = _ubicacion("A3")
    pareja = _pareja(ubicacion=a3)
    item = _item()

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [uuid.UUID(item["id"])]],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert _params(_lecturas_insert(db))["ubicacion_id_m0"] == a3.id
    assert pareja[0].ubicacion_actual_id == a3.id


def test_a_stamped_batch_needs_no_session_location():
    b2 = _ubicacion("B2")
    pareja = _pareja()
    item = _item(ubicacion_codigo="B2")

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [_fila(b2)], [uuid.UUID(item["id"])]],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert pareja[0].ubicacion_actual_id == b2.id


def test_an_unstamped_reading_without_session_location_is_a_409():
    pareja = _pareja()
    lote = [_item(ubicacion_codigo="B2"), _item()]

    r, db = _llamar("POST", "/lecturas", [], pareja, json={"lecturas": lote})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SIN_UBICACION"
    assert not _inserciones(db)


def test_an_inactive_location_rejects_only_its_readings():
    b2, c1 = _ubicacion("B2"), _ubicacion("C1", activa=False)
    pareja = _pareja(ubicacion=_ubicacion("A3"))
    apagada = _item(ubicacion_codigo="C1")
    buena = _item(ubicacion_codigo="B2")

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [_fila(b2), _fila(c1)],
         [uuid.UUID(buena["id"])]],
        pareja, json={"lecturas": [apagada, buena]})

    assert r.status_code == 200, r.text
    assert r.json()["aceptadas"] == [buena["id"]]
    assert r.json()["rechazadas"] == [
        {"id": apagada["id"], "motivo": "UBICACION_INACTIVA"}]
    params = _params(_lecturas_insert(db))
    assert params["ubicacion_id_m0"] == b2.id
    assert "ubicacion_id_m1" not in params


def test_a_ubi_prefix_in_the_stamp_is_normalized():
    b2 = _ubicacion("B2")
    pareja = _pareja(ubicacion=_ubicacion("A3"))
    item = _item(ubicacion_codigo=" ubi-b2 ")

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [_fila(b2)], [uuid.UUID(item["id"])]],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert _params(_lecturas_insert(db))["ubicacion_id_m0"] == b2.id


def test_one_batch_with_two_locations_resolves_them_in_one_query():
    b2, c1 = _ubicacion("B2"), _ubicacion("C1")
    pareja = _pareja(ubicacion=_ubicacion("A3"))
    lote = [_item(ubicacion_codigo="B2"), _item(ubicacion_codigo="c1"),
            _item(ubicacion_codigo="B2")]
    filas = [["EN_CONTEO"], CONOCIDA, [_fila(b2), _fila(c1)],
             [uuid.UUID(i["id"]) for i in lote]]

    r, db = _llamar("POST", "/lecturas", filas, pareja,
                    json={"lecturas": lote})

    assert r.status_code == 200, r.text
    assert len(r.json()["aceptadas"]) == 3
    params = _params(_lecturas_insert(db))
    assert [params[f"ubicacion_id_m{n}"] for n in range(3)] == [
        b2.id, c1.id, b2.id]
    # probe, session, estado, referencias, locations, readings INSERT
    assert len(db.executed_statements) == 6
    assert len(_inserciones(db)) == 1


def test_the_session_follows_the_newest_reading():
    b2, c1 = _ubicacion("B2"), _ubicacion("C1")
    pareja = _pareja(ubicacion=_ubicacion("A3"))
    nueva = _item(ubicacion_codigo="C1", leida_en=_en(5))
    vieja = _item(ubicacion_codigo="B2", leida_en=_en(1))

    r, _ = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [_fila(b2), _fila(c1)],
         [uuid.UUID(nueva["id"]), uuid.UUID(vieja["id"])]],
        pareja, json={"lecturas": [nueva, vieja]})

    assert r.status_code == 200, r.text
    assert pareja[0].ubicacion_actual_id == c1.id


def test_a_resent_batch_does_not_move_the_session():
    a3, b2 = _ubicacion("A3"), _ubicacion("B2")
    pareja = _pareja(ubicacion=a3)
    item = _item(ubicacion_codigo="B2")

    r, _ = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [_fila(b2)], []],
        pareja, json={"lecturas": [item]})

    assert r.json()["duplicadas"] == [item["id"]]
    assert pareja[0].ubicacion_actual_id == a3.id


def test_a_missing_location_is_created_by_the_pair():
    pareja = _pareja(ubicacion=_ubicacion("A3"))
    nueva = uuid.uuid4()
    item = _item(ubicacion_codigo="pasillo  9")

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [], [], [(nueva, "PASILLO 9")],
         [uuid.UUID(item["id"])]],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    creacion, insercion = _inserciones(db)
    assert creacion.table.name == UbicacionInventario.__tablename__
    alta = _params(creacion)
    assert alta["codigo_m0"] == "PASILLO 9"
    assert alta["nombre_m0"] == "PASILLO 9"
    assert alta["origen_m0"] == "PAREJA"
    assert _params(insercion)["ubicacion_id_m0"] == nueva
    assert pareja[0].ubicacion_actual_id == nueva


def test_a_location_created_meanwhile_is_read_back():
    otra = _ubicacion("P9")
    pareja = _pareja(ubicacion=_ubicacion("A3"))
    item = _item(ubicacion_codigo="P9")

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [], [], [], [_fila(otra)],
         [uuid.UUID(item["id"])]],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert _params(_lecturas_insert(db))["ubicacion_id_m0"] == otra.id


def test_a_stamp_that_clashes_with_a_referencia_is_rejected():
    pareja = _pareja(ubicacion=_ubicacion("A3"))
    item = _item(ubicacion_codigo="X1")

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_CONTEO"], CONOCIDA, [], ["UBI-X1"]],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert r.json()["rechazadas"] == [
        {"id": item["id"], "motivo": "UBICACION_CHOCA_REFERENCIA"}]
    assert not _inserciones(db)


def test_an_invalid_stamp_is_rejected():
    pareja = _pareja(ubicacion=_ubicacion("A3"))
    item = _item(ubicacion_codigo="UBI-")

    r, db = _llamar(
        "POST", "/lecturas", [["EN_CONTEO"], CONOCIDA],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert r.json()["rechazadas"] == [
        {"id": item["id"], "motivo": "UBICACION_INVALIDA"}]
    assert not _inserciones(db)


def test_a_round_two_reading_follows_the_same_rule():
    b2 = _ubicacion("B2")
    pareja = _pareja("EN_RECONTEO", ubicacion=_ubicacion("A3"))
    item = _item("abc-1", reconteo_id=str(RID), ubicacion_codigo="B2")

    r, db = _llamar(
        "POST", "/lecturas",
        [["EN_RECONTEO"], [(RID, "ABC-1", REF_A)], CONOCIDA, [_fila(b2)],
         [uuid.UUID(item["id"])]],
        pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    params = _params(_lecturas_insert(db))
    assert params["ronda_m0"] == 2
    assert params["ubicacion_id_m0"] == b2.id
    _ciego(r)
