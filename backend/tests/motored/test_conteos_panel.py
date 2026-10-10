"""
Inventory counts, the leader's live panel (odd/motored-conteos-inventario,
WU12b; design ADR-8, §6.1, §9.3).

HTTP-layer tests on the real mounted router with the usual seams: the
user (`override_motored_user`) and a `FakeAsyncSession` whose leading
`[]` is `get_motored_db_or_503`'s probe. The version lookup and the full
payload are stubbed: the pg_real file runs them for real. What a fake
can prove is the routing: who may read, and that an unchanged version
answers from the version lookup alone (no conteo load, no aggregates).
Pure rules of the payload (the differences summary, the counted lines)
are tested directly.
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
from app.motored.services.auth import MotoredUser
from app.motored.services.conteos import diferencias, panel
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

BASE = "/api/motored/conteos"
UTC = datetime.timezone.utc
AHORA = datetime.datetime(2026, 10, 9, 13, 0, tzinfo=UTC)
LIDER_ID = uuid.uuid4()
D = Decimal


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "conteos-panel")
    monkeypatch.setattr(settings, "SECRET_KEY", "conteos-panel-asc360")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def stubs(monkeypatch):
    huella = AsyncMock(return_value=panel.Huella(LIDER_ID, 42))
    armar = AsyncMock(return_value={
        "version": 43, "sin_cambios": False, "estado": "EN_CONTEO",
        "progreso": {"refs_universo": 4, "refs_contadas": 3,
                     "lecturas_total": 6, "ultima_lectura_en": AHORA},
        "exactitud_parcial": None, "parejas": [],
        "unidades": {"total_contado": D("0"), "dentro_esperado": D("0"),
                     "sobrantes": D("0"), "sistema_total": D("9")},
        "diferencias_resumen": {"criticas": 0, "en_reconteo": 0,
                                "total": 5}})
    monkeypatch.setattr(panel, "huella", huella)
    monkeypatch.setattr(panel, "armar", armar)
    return huella, armar


def _conteo(lider_id=LIDER_ID):
    return Conteo(
        id=uuid.uuid4(), tipo="TOTAL", estado="EN_CONTEO",
        origen="MANUAL", sucursal_id=uuid.uuid4(), lider_id=lider_id,
        fecha_programada=AHORA.date(), created_at=AHORA,
        umbral_reconteo_pesos=D("100000"),
        umbral_critico_pesos=D("500000"))


def _usuario(rol, user_id=None):
    if user_id is None:
        user_id = LIDER_ID if rol == "LIDER_INVENTARIOS" else uuid.uuid4()
    return MotoredUser(user_id=str(user_id), role=rol)


def _pedir(rol, conteo_id, version=None, conteo=None, user_id=None):
    override_motored_user(_usuario(rol, user_id))
    sesion = FakeAsyncSession(
        execute_queue=[[]], get_queue=[conteo] if conteo else [])
    override_motored_db(sesion)
    ruta = f"{BASE}/{conteo_id}/panel"
    if version is not None:
        ruta += f"?version={version}"
    return TestClient(app).get(ruta), sesion


# --- who reads ---------------------------------------------------------------


@pytest.mark.parametrize("rol", ["ADMIN", "LIDER_INVENTARIOS", "GERENCIA"])
def test_readers_get_the_full_panel(stubs, rol):
    conteo = _conteo()

    r, _ = _pedir(rol, conteo.id, conteo=conteo)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["version"] == 43 and cuerpo["sin_cambios"] is False
    assert cuerpo["progreso"]["refs_contadas"] == 3
    assert stubs[1].await_args.args[1] is conteo


def test_another_leaders_conteo_is_a_404(stubs):
    r, _ = _pedir(
        "LIDER_INVENTARIOS", uuid.uuid4(), user_id=uuid.uuid4())

    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "CONTEO_NO_ENCONTRADO"
    stubs[1].assert_not_awaited()


def test_a_missing_conteo_is_a_404(stubs):
    stubs[0].return_value = None

    r, _ = _pedir("ADMIN", uuid.uuid4(), version=42)

    assert r.status_code == 404, r.text
    stubs[1].assert_not_awaited()


@pytest.mark.parametrize("rol", ["COMPRAS", "SUCURSAL"])
def test_other_roles_get_403(stubs, rol):
    r, _ = _pedir(rol, uuid.uuid4())

    assert r.status_code == 403, r.text
    stubs[0].assert_not_awaited()


# --- the version short-circuit (ADR-8) ---------------------------------------


def test_the_same_version_answers_from_the_version_lookup_alone(stubs):
    r, sesion = _pedir("LIDER_INVENTARIOS", uuid.uuid4(), version=42)

    assert r.status_code == 200, r.text
    assert r.json() == {"version": 42, "sin_cambios": True}
    stubs[0].assert_awaited_once()
    stubs[1].assert_not_awaited()
    # Only the session probe ran; the conteo itself was never loaded
    # (an empty get_queue fails the test if `db.get` is called).
    assert len(sesion.executed_statements) == 1


def test_another_version_loads_the_conteo_and_the_payload(stubs):
    conteo = _conteo()

    r, _ = _pedir("ADMIN", conteo.id, version=41, conteo=conteo)

    assert r.status_code == 200, r.text
    assert r.json()["sin_cambios"] is False
    assert stubs[1].await_args.args[2] == 42


# --- pure rules of the payload -----------------------------------------------


def _cruda(codigo, sistema, ronda1, costo="1000", reconteo=None,
           ronda2=None, referencia=True):
    return diferencias.FilaCruda(
        referencia_id=uuid.uuid4() if referencia else None,
        codigo=codigo, nombre=codigo,
        sistema=None if sistema is None else D(sistema),
        ronda1=None if ronda1 is None else D(ronda1),
        costo_unitario=None if costo is None else D(costo),
        costo_fuente=None if sistema is None else "BODEGA",
        ubicaciones=None, reconteo_id=uuid.uuid4() if reconteo else None,
        reconteo_estado=reconteo, reconteo_origen=(
            "UMBRAL" if reconteo else None),
        reconteo_sesion_id=None, misma_pareja_autorizada=None,
        ronda2=None if ronda2 is None else D(ronda2))


def test_the_summary_counts_like_the_differences_list():
    crudas = [
        _cruda("A", "10", "8"), _cruda("B", "10", "1", costo="60000"),
        _cruda("D", "3", "3"), _cruda("E", "5", None),
        _cruda("F", "2", "2", reconteo="PENDIENTE"),
        _cruda("Z", None, "1", costo=None, referencia=False),
    ]

    resumen = panel.resumen_diferencias(crudas, D("500000"))

    assert resumen == {"criticas": 1, "en_reconteo": 1, "total": 5}


def test_the_summary_is_empty_without_thresholds():
    assert panel.resumen_diferencias([_cruda("A", "1", "2")], None) == {
        "criticas": 0, "en_reconteo": 0, "total": 0}


def test_counted_lines_are_round_one_reads_or_finished_reconteos():
    crudas = [
        _cruda("A", "10", "8"), _cruda("E", "5", None),
        _cruda("G", "4", None, reconteo="TERMINADO", ronda2="4"),
        _cruda("H", "4", None, reconteo="ASIGNADO"),
    ]

    assert [c.codigo for c in panel.contadas(crudas)] == ["A", "G"]


# --- units counted (owner decision 2026-10-10) -------------------------------


def _unidades(*crudas):
    return panel.unidades(list(crudas))


def test_units_inside_and_surplus_by_case():
    crudas = [
        _cruda("EXACTO", "4", "4"),
        _cruda("FALTA", "10", "7"),
        _cruda("SOBRA", "3", "5"),
        _cruda("CERO", "0", "2"),
        _cruda("NEGATIVO", "-3", "2"),
        _cruda("SIN_LEER", "6", None),
        _cruda("FUERA", None, "1", costo=None),
        _cruda("DESCONOCIDO", None, "2", costo=None, referencia=False),
    ]

    u = panel.unidades(crudas)

    # dentro: 4 + 7 + 3 + 0 + 0 + 0; sobrantes: 2 + 2 + 2 + 1 + 2.
    assert u == {"total_contado": D("23"), "dentro_esperado": D("14"),
                 "sobrantes": D("9"), "sistema_total": D("23")}


def test_negative_system_counts_as_zero_expected():
    u = _unidades(_cruda("N", "-5", None))

    assert u == {"total_contado": D("0"), "dentro_esperado": D("0"),
                 "sobrantes": D("0"), "sistema_total": D("0")}


def test_a_finished_reconteo_replaces_round_one_in_the_units():
    u = _unidades(
        _cruda("R", "5", "2", reconteo="TERMINADO", ronda2="6"),
        _cruda("P", "5", "2", reconteo="ASIGNADO", ronda2="9"))

    assert u["total_contado"] == D("8")
    assert (u["dentro_esperado"], u["sobrantes"]) == (D("7"), D("1"))


@pytest.mark.parametrize("sistema,ronda1", [
    ("0", "3"), ("-2", "1.5"), ("4", "4"), ("4", "9"), ("8", "2"),
    (None, "2"), ("5", None)])
def test_total_is_inside_plus_surplus(sistema, ronda1):
    u = _unidades(_cruda("X", sistema, ronda1), _cruda("Y", "1", "1"))

    assert u["total_contado"] == u["dentro_esperado"] + u["sobrantes"]


def test_units_use_the_differences_table_contado():
    """Parity: the card adds up exactly the `contado` that
    `diferencias.calcular` puts in the table's Contado column."""
    crudas = [
        _cruda("A", "10", "8"), _cruda("B", "0", "2"),
        _cruda("G", "4", None, reconteo="TERMINADO", ronda2="3"),
        _cruda("H", "4", "1", reconteo="ASIGNADO", ronda2="7"),
        _cruda("Z", None, "1", costo=None, referencia=False),
    ]

    tabla = [diferencias.calcular(c, D("500000")).contado for c in crudas]

    assert [diferencias.contado_de(c) for c in crudas] == tabla
    assert panel.unidades(crudas)["total_contado"] == sum(tabla)


def test_no_rows_means_zero_units():
    assert panel.unidades([]) == {
        "total_contado": D("0"), "dentro_esperado": D("0"),
        "sobrantes": D("0"), "sistema_total": D("0")}


def test_the_version_is_a_stable_js_safe_integer():
    partes = (7, 6, "EN_CONTEO", "abc", "def")

    version = panel.version_de(partes)

    assert version == panel.version_de(partes)
    assert 0 <= version < 2 ** 53
    assert version != panel.version_de((8, 6, "EN_CONTEO", "abc", "def"))
