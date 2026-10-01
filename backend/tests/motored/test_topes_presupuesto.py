"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5a,
ADR-6, decisiones F4-7 y F4-16, spec TP-02..TP-05): los endpoints del tope
de presupuesto en `/api/motored/parametros/topes-presupuesto`.

- GET: ADMIN y COMPRAS (SUCURSAL, CONSULTA y el resto reciben 403).
- POST: sólo ADMIN; 1 a 200 topes, una versión por tienda que CAMBIA, todo
  en una transacción. Nada se escribe si una entrada es inválida.

La sesión es la doble `FakeAsyncSession`; la cola de `execute` lleva primero
la sonda de disponibilidad de Motored y después las consultas del servicio,
en el orden en que las emite.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services.auth import MotoredUser
from app.motored.services.reloj import hoy_bogota
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

URL = "/api/motored/parametros/topes-presupuesto"
MODO = "modo_tope_presupuesto"
TOPE = "presupuesto_maximo_pedido"
USUARIO = uuid.UUID(int=900)
CALI = uuid.UUID(int=1)
PEREIRA = uuid.UUID(int=2)
MANIZALES = uuid.UUID(int=3)
DESDE = datetime.date(2026, 9, 28)
OTROS = ["CONSULTA", "SUCURSAL", "SERVICIO_CLIENTE", "ASESOR_MOSTRADOR"]


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "topes-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "topes-asc360")
    yield
    app.dependency_overrides.clear()


def _fila(clave, valor, sucursal_id=None, desde=DESDE):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=desde,
        sucursal_id=sucursal_id,
    )


def _como(rol, consultas=()):
    """Cliente con ese rol; `consultas` van detrás de la sonda."""
    override_motored_user(MotoredUser(user_id=str(USUARIO), role=rol))
    db = FakeAsyncSession(execute_queue=[[]] + [list(c) for c in consultas])
    override_motored_db(db)
    return TestClient(app), db


def _leer(rol="ADMIN", filas=(), sucursales=((CALI, "Cali"),)):
    return _como(rol, [filas, sucursales])


def _cuerpo(*topes):
    return {"topes": [
        {"sucursal_id": str(sid), "valor": valor} for sid, valor in topes]}


def _escribir(topes, existentes=None, filas=(), rol="ADMIN"):
    ids = [sid for sid, _ in topes] if existentes is None else existentes
    cliente, db = _como(rol, [ids, filas])
    return cliente.post(URL, json=_cuerpo(*topes)), db


# --- GET: lectura (TP-02, F4-16) -------------------------------------------


def test_the_switch_reads_off_with_no_rows():
    cliente, _db = _leer()

    cuerpo = cliente.get(URL).json()

    assert cuerpo["modo_activo"] is False
    assert cuerpo["modo_vigente_desde"] is None


def test_a_written_switch_reads_on_with_its_effective_date():
    cliente, _db = _leer(filas=[_fila(MODO, True)])

    cuerpo = cliente.get(URL).json()

    assert cuerpo["modo_activo"] is True
    assert cuerpo["modo_vigente_desde"] == "2026-09-28"


def test_a_switch_written_off_reads_off_with_its_date():
    cliente, _db = _leer(filas=[_fila(MODO, False)])

    cuerpo = cliente.get(URL).json()

    assert cuerpo["modo_activo"] is False
    assert cuerpo["modo_vigente_desde"] == "2026-09-28"


@pytest.mark.parametrize("basura", ["false", "true", 1, "si", []])
def test_a_stored_switch_that_is_not_a_boolean_reads_as_off(basura):
    cliente, _db = _leer(filas=[_fila(MODO, basura)])

    assert cliente.get(URL).json()["modo_activo"] is False


def test_every_active_tienda_is_listed_with_its_cap_or_null():
    filas = [_fila(TOPE, "80000000", CALI)]
    cliente, _db = _leer(
        filas=filas, sucursales=[(CALI, "Cali"), (PEREIRA, "Pereira")])

    topes = cliente.get(URL).json()["topes"]

    assert [t["nombre"] for t in topes] == ["Cali", "Pereira"]
    assert topes[0]["sucursal_id"] == str(CALI)
    assert Decimal(topes[0]["valor"]) == Decimal("80000000")
    assert topes[0]["vigente_desde"] == "2026-09-28"
    assert topes[1]["valor"] is None and topes[1]["vigente_desde"] is None


def test_a_cap_with_decimals_is_returned_exactly():
    filas = [_fila(TOPE, "80000000.50", CALI)]
    cliente, _db = _leer(filas=filas)

    topes = cliente.get(URL).json()["topes"]

    assert Decimal(topes[0]["valor"]) == Decimal("80000000.50")


def test_a_cap_removed_with_null_reads_as_no_cap_but_keeps_its_date():
    filas = [_fila(TOPE, None, CALI, DESDE)]
    cliente, _db = _leer(filas=filas)

    topes = cliente.get(URL).json()["topes"]

    assert topes[0]["valor"] is None
    assert topes[0]["vigente_desde"] == "2026-09-28"


def test_the_newest_version_of_a_cap_wins():
    nueva = _fila(TOPE, "90000000", CALI, datetime.date(2026, 10, 1))
    vieja = _fila(TOPE, "80000000", CALI, DESDE)
    cliente, _db = _leer(filas=[nueva, vieja])

    topes = cliente.get(URL).json()["topes"]

    assert Decimal(topes[0]["valor"]) == Decimal("90000000")
    assert topes[0]["vigente_desde"] == "2026-10-01"


def test_a_global_row_for_the_cap_is_not_a_cap_of_any_tienda():
    """El tope sólo existe por tienda: una fila global (jamás escrita por la
    API, que la rechaza con E-PARAM-004) no cuenta."""
    cliente, _db = _leer(filas=[_fila(TOPE, "1", None)])

    assert cliente.get(URL).json()["topes"][0]["valor"] is None


def test_another_tiendas_cap_is_not_inherited():
    cliente, _db = _leer(
        filas=[_fila(TOPE, "70", PEREIRA)],
        sucursales=[(CALI, "Cali"), (PEREIRA, "Pereira")])

    topes = {t["nombre"]: t["valor"] for t in cliente.get(URL).json()["topes"]}

    assert topes["Cali"] is None
    assert Decimal(topes["Pereira"]) == 70


def test_a_corrupt_stored_cap_reads_as_no_cap_instead_of_failing():
    cliente, _db = _leer(filas=[_fila(TOPE, "abc", CALI)])

    respuesta = cliente.get(URL)

    assert respuesta.status_code == 200
    assert respuesta.json()["topes"][0]["valor"] is None


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS"])
def test_admin_and_compras_can_read_the_caps(rol):
    cliente, _db = _leer(rol)

    assert cliente.get(URL).status_code == 200


@pytest.mark.parametrize("rol", OTROS)
def test_every_other_role_is_refused_on_the_read(rol):
    cliente, db = _como(rol, [[], []])

    respuesta = cliente.get(URL)

    assert respuesta.status_code == 403
    assert len(db.executed_statements) == 1   # sólo la sonda


def test_the_read_without_credentials_is_a_401():
    app.dependency_overrides.clear()
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 4))

    assert TestClient(app).get(URL).status_code == 401


# --- POST: escritura (TP-02, TP-05) ----------------------------------------


def test_admin_writes_one_version_for_a_new_cap():
    respuesta, db = _escribir([(CALI, 80000000)])

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json() == {
        "actualizados": [str(CALI)], "sin_cambios": []}
    (fila,) = db.added_of_type(ParametroMetodologia)
    assert (fila.clave, fila.sucursal_id) == (TOPE, CALI)
    assert Decimal(fila.valor) == Decimal("80000000")
    assert fila.created_by == USUARIO
    assert fila.vigente_desde == hoy_bogota()
    assert db.committed is True


@pytest.mark.parametrize("valor, esperado", [
    (80000000, "80000000"), ("80000000", "80000000"),
    (80000000.5, "80000000.5"), ("1250.75", "1250.75"),
    (" 90 ", "90"),
    ("12345678901234567890123456789012.34",
     "12345678901234567890123456789012.34"),
])
def test_the_cap_is_stored_as_exact_decimal_text(valor, esperado):
    _respuesta, db = _escribir([(CALI, valor)])

    assert db.added[0].valor == esperado


def test_a_null_cap_removes_the_cap_with_a_new_version():
    filas = [_fila(TOPE, "80000000", CALI)]

    respuesta, db = _escribir([(CALI, None)], filas=filas)

    assert respuesta.json()["actualizados"] == [str(CALI)]
    assert db.added[0].valor is None


def test_one_version_per_changed_tienda_in_one_transaction():
    topes = [(CALI, 10), (PEREIRA, 20), (MANIZALES, 30)]

    respuesta, db = _escribir(topes)

    assert respuesta.json()["actualizados"] == [
        str(CALI), str(PEREIRA), str(MANIZALES)]
    assert [f.sucursal_id for f in db.added] == [CALI, PEREIRA, MANIZALES]
    assert [f.valor for f in db.added] == ["10", "20", "30"]
    assert db.committed is True


def test_a_tienda_whose_cap_does_not_change_gets_no_new_version():
    filas = [_fila(TOPE, "80000000.00", CALI)]
    topes = [(CALI, 80000000), (PEREIRA, 5)]

    respuesta, db = _escribir(topes, filas=filas)

    assert respuesta.json() == {
        "actualizados": [str(PEREIRA)], "sin_cambios": [str(CALI)]}
    assert [f.sucursal_id for f in db.added] == [PEREIRA]


def test_null_over_no_cap_is_not_a_change():
    respuesta, db = _escribir([(CALI, None)])

    assert respuesta.json() == {
        "actualizados": [], "sin_cambios": [str(CALI)]}
    assert db.added == []


def test_null_over_a_null_cap_is_not_a_change():
    respuesta, db = _escribir(
        [(CALI, None)], filas=[_fila(TOPE, None, CALI)])

    assert respuesta.json()["sin_cambios"] == [str(CALI)]
    assert db.added == []


def test_another_tiendas_cap_does_not_hide_a_change():
    filas = [_fila(TOPE, "10", PEREIRA)]

    respuesta, db = _escribir([(CALI, 10)], existentes=[CALI], filas=filas)

    assert respuesta.json()["actualizados"] == [str(CALI)]
    assert len(db.added) == 1


@pytest.mark.parametrize("valor", [0, -5, "abc", "", True, "NaN", [], {}])
def test_an_invalid_cap_is_a_coded_422_and_writes_nothing(valor):
    respuesta, db = _escribir([(CALI, valor)])

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == [] and db.committed is False


def test_one_invalid_entry_rejects_the_whole_request():
    respuesta, db = _escribir([(CALI, 10), (PEREIRA, -1)])

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert str(PEREIRA) in respuesta.json()["detail"]["message"]
    assert db.added == [] and db.committed is False


def test_an_unknown_sucursal_is_a_coded_422_and_writes_nothing():
    respuesta, db = _escribir(
        [(CALI, 10), (PEREIRA, 20)], existentes=[CALI])

    assert respuesta.status_code == 422
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "E-PARAM-002"
    assert str(PEREIRA) in detalle["message"]
    assert db.added == [] and db.committed is False


def test_the_same_tienda_twice_in_one_request_is_a_coded_422():
    respuesta, db = _escribir([(CALI, 10), (CALI, 20)])

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


def test_an_empty_list_is_a_coded_422():
    cliente, db = _como("ADMIN", [[], []])

    respuesta = cliente.post(URL, json={"topes": []})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


def test_more_than_200_entries_is_a_coded_422():
    topes = [(uuid.UUID(int=1000 + i), 1) for i in range(201)]

    respuesta, db = _escribir(topes, existentes=[])

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert db.added == []


def test_exactly_200_entries_are_accepted():
    topes = [(uuid.UUID(int=1000 + i), i + 1) for i in range(200)]

    respuesta, db = _escribir(topes)

    assert respuesta.status_code == 201, respuesta.text
    assert len(db.added) == 200


def test_an_entry_without_a_value_is_a_validation_error_not_a_removal():
    cliente, db = _como("ADMIN", [[CALI], []])

    respuesta = cliente.post(
        URL, json={"topes": [{"sucursal_id": str(CALI)}]})

    assert respuesta.status_code == 422
    assert db.added == []


def test_extra_fields_are_rejected():
    cliente, db = _como("ADMIN", [[CALI], []])

    respuesta = cliente.post(URL, json={"topes": [
        {"sucursal_id": str(CALI), "valor": 10, "global": True}]})

    assert respuesta.status_code == 422
    assert db.added == []


@pytest.mark.parametrize("rol", ["COMPRAS"] + OTROS)
def test_only_admin_can_write_the_caps(rol):
    respuesta, db = _escribir([(CALI, 10)], rol=rol)

    assert respuesta.status_code == 403
    assert db.added == [] and db.committed is False
    assert len(db.executed_statements) == 1   # sólo la sonda


def test_the_write_without_credentials_is_a_401():
    app.dependency_overrides.clear()
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 4))

    respuesta = TestClient(app).post(URL, json=_cuerpo((CALI, 10)))

    assert respuesta.status_code == 401
