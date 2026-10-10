"""
Inventory counts -- the leader panel's "Contadas" filter, the reference
search and the per-reference detail
(odd/tasks/motored-conteo-panel-busqueda.md).

Pure rules (matching, ordering, combining with a chip) and the HTTP
contract over a fake session; the real SQL is proven in
`pg_real/test_conteos_busqueda_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.motored.services.conteos import busqueda, diferencias, sesiones
from tests.motored.test_conteos_reconteos import (  # noqa: F401
    CRITICO, OTRO_LIDER_ID, _conteo, _listo, _llamar,
)

D = Decimal
UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


def _cruda(codigo, nombre, sistema, ronda1, minuto=None, costo="1000",
           reconteo=None, ronda2=None):
    ultima = None if minuto is None else T0 + datetime.timedelta(
        minutes=minuto)
    return diferencias.FilaCruda(
        referencia_id=uuid.uuid4(), codigo=codigo, nombre=nombre,
        sistema=None if sistema is None else D(sistema),
        ronda1=None if ronda1 is None else D(ronda1),
        costo_unitario=D(costo), costo_fuente="BODEGA",
        ubicaciones=["Estante A3"],
        reconteo_id=uuid.uuid4() if reconteo else None,
        reconteo_estado=reconteo,
        reconteo_origen="UMBRAL" if reconteo else None,
        reconteo_sesion_id=None, misma_pareja_autorizada=False,
        ronda2=None if ronda2 is None else D(ronda2),
        ultima_lectura_en=ultima)


def _filas(*crudas):
    return [diferencias.calcular(c, CRITICO) for c in crudas]


ESCENA = (
    _cruda("94109-12000S", "Pastilla de freno", "4", "4", minuto=5),
    _cruda("AB.77 10", "Filtro de aceite", "10", "2", minuto=30),
    _cruda("CX-1", "Bujía", "3", None),
    _cruda("DX-9", "Filtro de aire", "1", "900", minuto=10,
           costo="1000"),
    _cruda("EX-2", "Cadena", "5", None, reconteo="TERMINADO",
           ronda2="5", minuto=40),
)


# --- matching ----------------------------------------------------------------


@pytest.mark.parametrize("q", [
    "9410912000S", "94109 12000s", "94109-12000S", "12000", "pastilla",
    "DE FRENO"])
def test_a_code_matches_by_key_and_a_name_by_part(q):
    fila = _filas(ESCENA[0])[0]

    assert busqueda.coincide(fila, q) is True


@pytest.mark.parametrize("q", ["94109-13", "embrague", "  ", "--"])
def test_what_does_not_match(q):
    fila = _filas(ESCENA[0])[0]

    assert busqueda.coincide(fila, q) is False


def test_a_hyphen_less_code_finds_a_dotted_one():
    filas = _filas(*ESCENA)

    hallados = busqueda.elegir(filas, "todas", "ab7710")

    assert [f.codigo for f in hallados] == ["AB.77 10"]


# --- the "contadas" chip -----------------------------------------------------


def test_counted_keeps_contado_above_zero_latest_reading_first():
    filas = _filas(*ESCENA)

    hallados = busqueda.elegir(filas, "contadas", None)

    # CX-1 was never read; EX-2 counts through its finished reconteo.
    assert [f.codigo for f in hallados] == [
        "EX-2", "AB.77 10", "DX-9", "94109-12000S"]


def test_counted_rows_with_no_time_go_last():
    filas = _filas(
        _cruda("Z-1", "Uno", "1", "1"), _cruda("Y-1", "Dos", "1", "2",
                                               minuto=1))

    hallados = busqueda.elegir(filas, "contadas", None)

    assert [f.codigo for f in hallados] == ["Y-1", "Z-1"]


def test_the_count_of_counted_references():
    assert busqueda.cuenta_contadas(_filas(*ESCENA)) == 4


# --- combining the search with a chip ----------------------------------------


def test_search_combines_with_the_counted_chip():
    filas = _filas(*ESCENA)

    hallados = busqueda.elegir(filas, "contadas", "filtro")

    assert [f.codigo for f in hallados] == ["AB.77 10", "DX-9"]


def test_search_combines_with_the_critical_chip():
    filas = _filas(*ESCENA)

    # DX-9: +899 x 1000 is critical; AB.77 10 (-8000) is not.
    hallados = busqueda.elegir(filas, "criticas", "filtro")

    assert [f.codigo for f in hallados] == ["DX-9"]


def test_search_under_todas_reaches_rows_with_no_difference():
    filas = _filas(*ESCENA)

    hallados = busqueda.elegir(filas, "todas", "pastilla")

    assert [f.codigo for f in hallados] == ["94109-12000S"]


def test_search_under_todas_keeps_the_value_order():
    filas = _filas(*ESCENA)

    hallados = busqueda.elegir(filas, "todas", "filtro")

    assert [f.codigo for f in hallados] == ["DX-9", "AB.77 10"]


def test_the_global_counts_ignore_the_search():
    cuentas = busqueda.cuentas(_filas(*ESCENA))

    # Differences: AB.77 10, CX-1, DX-9, EX-2 (reconteo).
    assert cuentas == {"total": 4, "criticas": 1, "en_reconteo": 1,
                       "contadas": 4}


# --- the detail --------------------------------------------------------------


def test_the_detail_labels_the_pair_and_keeps_the_latest():
    sid = uuid.uuid4()
    lineas = busqueda.armar_detalle(
        [("Estante A3", 1, sid, D("5"), T0),
         ("Estante B1", 1, sid, D("3"), T0 + datetime.timedelta(hours=1))],
        {sid: "Pareja 1 · Ana R. y Luis G."})

    assert lineas["ultima_lectura_en"] == T0 + datetime.timedelta(hours=1)
    assert lineas["lineas"][0] == {
        "ubicacion": "Estante A3", "ronda": 1,
        "sesion": {"id": sid, "etiqueta": "Pareja 1 · Ana R. y Luis G."},
        "cantidad": D("5"), "ultima_lectura_en": T0}


def test_an_unread_code_has_an_empty_detail():
    assert busqueda.armar_detalle([], {}) == {
        "lineas": [], "ultima_lectura_en": None}


# --- HTTP --------------------------------------------------------------------


@pytest.fixture
def sin_parejas(monkeypatch):
    monkeypatch.setattr(sesiones, "listar", AsyncMock(return_value=[]))


def test_the_search_runs_on_every_reference_of_the_count(
        monkeypatch, sin_parejas):
    conteo = _conteo()
    filas = AsyncMock(return_value=list(ESCENA))
    monkeypatch.setattr(diferencias, "filas", filas)

    r, _ = _llamar(
        "GERENCIA", "GET", f"/{conteo.id}/diferencias?filtro=todas"
        "&q=pastilla", conteo)

    assert r.status_code == 200, r.text
    assert filas.await_args.kwargs == {"solo_diferencias": False}
    cuerpo = r.json()
    assert [i["codigo"] for i in cuerpo["items"]] == ["94109-12000S"]
    assert (cuerpo["total"], cuerpo["contadas"]) == (4, 4)
    assert cuerpo["items"][0]["ultima_lectura_en"].startswith("2026-10-10")


def test_the_counted_chip_answers_most_recent_first(
        monkeypatch, sin_parejas):
    conteo = _conteo()
    monkeypatch.setattr(
        diferencias, "filas", AsyncMock(return_value=list(ESCENA)))

    r, _ = _llamar(
        "LIDER_INVENTARIOS", "GET",
        f"/{conteo.id}/diferencias?filtro=contadas", conteo)

    assert r.status_code == 200, r.text
    assert [i["codigo"] for i in r.json()["items"]] == [
        "EX-2", "AB.77 10", "DX-9", "94109-12000S"]


@pytest.mark.parametrize("ruta", [
    "/diferencias?filtro=contadas", "/diferencias?q=abc",
    "/diferencias/detalle?codigo=A-1"])
def test_another_leaders_conteo_is_a_404(ruta):
    conteo = _conteo(lider_id=OTRO_LIDER_ID)

    r, _ = _llamar(
        "LIDER_INVENTARIOS", "GET", f"/{conteo.id}{ruta}", conteo)

    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "CONTEO_NO_ENCONTRADO"


def test_the_detail_needs_a_code():
    conteo = _conteo()

    r, _ = _llamar("ADMIN", "GET", f"/{conteo.id}/diferencias/detalle",
                   conteo)

    assert r.status_code == 422


def test_the_detail_answers_per_location_and_pair(monkeypatch):
    conteo = _conteo()
    sid = uuid.uuid4()
    leer = AsyncMock(return_value=[("Estante A3", 1, sid, D("5"), T0)])
    monkeypatch.setattr(busqueda, "lineas_de", leer)
    monkeypatch.setattr(sesiones, "listar", AsyncMock(return_value=[
        sesiones.FilaSesion(type("S", (), {"id": sid})(), 3, [], None)]))

    r, _ = _llamar(
        "GERENCIA", "GET",
        f"/{conteo.id}/diferencias/detalle?codigo=94109-12000S", conteo)

    assert r.status_code == 200, r.text
    assert leer.await_args.args[1:] == (conteo.id, "94109-12000S")
    cuerpo = r.json()
    assert cuerpo["codigo"] == "94109-12000S"
    linea = cuerpo["lineas"][0]
    assert (linea["ubicacion"], linea["ronda"], linea["cantidad"]) == (
        "Estante A3", 1, "5")
    assert linea["sesion"]["etiqueta"] == "Pareja 3 · "
