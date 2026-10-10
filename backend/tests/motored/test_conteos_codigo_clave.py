"""
Inventory counts -- a scanned code finds its master referencia even when
the label omits the hyphens, spaces or dots of the master code
(odd/tasks/motored-conteo-codigo-sin-guiones.md).

The match key is the code upper-cased with every character outside
`A-Z0-9` removed. A key shared by two or more master codes is ambiguous
and resolves to nothing, unless the reading equals one master code
under `upper(btrim)`. `UBI-` labels are never matched by key. The same
examples are checked on the device
(`frontend/__tests__/motored-conteo-codigo-clave.test.js`).
"""
import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.services.conteos import lecturas
from tests.motored.test_publico_conteos_lecturas import _ahora

REF_A = uuid.uuid4()
REF_B = uuid.uuid4()
REF_C = uuid.uuid4()
RID = uuid.uuid4()


# --- the key (same examples as the device) -----------------------------------


@pytest.mark.parametrize("crudo", [
    "94109-12000S", "9410912000S", " 94109 12000s ", "94109.12000S"])
def test_the_key_drops_everything_outside_a_z_and_digits(crudo):
    assert lecturas.clave_codigo(crudo) == "9410912000S"


@pytest.mark.parametrize("crudo, esperado", [
    ("", ""), (None, ""), ("--", ""), ("ABC-1/2", "ABC12"),
    ("UBI-B7", "UBIB7")])
def test_the_key_of_edge_cases(crudo, esperado):
    assert lecturas.clave_codigo(crudo) == esperado


# --- resolution over the referencia rows (pure) ------------------------------

FILAS = [
    (REF_A, "94109-12000S", "Tornillo"),
    (REF_B, "AB-12", "Buje"),
    (REF_C, "AB.12", "Buje largo"),
]


def test_a_hyphen_less_code_resolves_to_its_master_code():
    resueltas = lecturas.elegir_referencias(
        {"9410912000S", "94109 12000S"}, FILAS)

    assert resueltas == {
        "9410912000S": (REF_A, "Tornillo", "94109-12000S"),
        "94109 12000S": (REF_A, "Tornillo", "94109-12000S")}


def test_a_key_shared_by_two_master_codes_resolves_to_nothing():
    assert lecturas.elegir_referencias({"AB12", "AB 12"}, FILAS) == {}


def test_an_exact_master_code_wins_over_an_ambiguous_key():
    resueltas = lecturas.elegir_referencias({"AB.12"}, FILAS)

    assert resueltas == {"AB.12": (REF_C, "Buje largo", "AB.12")}


def test_a_location_label_is_never_matched_by_key():
    filas = [(REF_A, "UBIB7", "Raro")]

    assert lecturas.elegir_referencias({"UBI-B7"}, filas) == {}
    assert lecturas.elegir_referencias({"UBIB7"}, filas) == {
        "UBIB7": (REF_A, "Raro", "UBIB7")}


def test_two_master_codes_equal_under_upper_btrim_stay_unknown():
    filas = [(REF_A, "x-1", "a"), (REF_B, "X-1 ", "b")]

    assert lecturas.elegir_referencias({"X-1", "X1"}, filas) == {}


# --- a reading is stored under the master code -------------------------------


def _entrada(codigo, reconteo_id=None):
    return lecturas.Entrada(
        id=uuid.uuid4(), codigo_leido=codigo, cantidad=Decimal("1"),
        leida_en=_ahora(), metodo="ESCANER", reconteo_id=reconteo_id)


def test_a_hyphen_less_reading_is_stored_under_the_master_code():
    resueltas = {"9410912000S": (REF_A, "Tornillo", "94109-12000S")}

    lote = lecturas.clasificar([_entrada("9410912000s")], resueltas)

    assert [(f["codigo_leido"], f["referencia_id"]) for f in lote.filas] \
        == [("94109-12000S", REF_A)]
    assert lote.desconocidos == []


def test_an_ambiguous_reading_comes_back_unknown():
    entrada = _entrada("AB12")

    lote = lecturas.clasificar([entrada], {})

    assert lote.filas == []
    assert lote.desconocidos == [(entrada.id, "AB12")]


# --- round 2: the reconteo's code by key -------------------------------------


def test_a_hyphen_less_round_two_reading_passes_for_a_master_reconteo():
    lectura = _entrada("9410912000S", RID)

    aptas, cerradas = lecturas.por_ronda(
        [lectura], "EN_RECONTEO", {RID: ("94109-12000S", True)})

    assert (aptas, cerradas) == ([lectura], [])


def test_a_key_match_does_not_pass_for_a_code_not_in_the_master():
    lectura = _entrada("XQ1", RID)

    _, cerradas = lecturas.por_ronda(
        [lectura], "EN_RECONTEO", {RID: ("XQ-1", False)})

    assert cerradas == [(lectura.id, "RECONTEO_OTRO_CODIGO")]


def test_a_round_two_key_match_must_resolve_to_the_reconteos_code():
    propios = {RID: ("AB-12", True)}
    buena = _entrada("AB-12", RID)
    ambigua = _entrada("AB12", RID)
    otra = _entrada("AB.12", RID)
    resueltas = {
        "AB-12": (REF_B, "Buje", "AB-12"),
        "AB.12": (REF_C, "Buje largo", "AB.12")}

    aptas, cerradas = lecturas.confirmar_ronda_dos(
        [buena, ambigua, otra], propios, resueltas)

    assert aptas == [buena]
    assert cerradas == [(ambigua.id, "RECONTEO_OTRO_CODIGO"),
                        (otra.id, "RECONTEO_OTRO_CODIGO")]


def test_round_two_confirmation_keeps_round_one_and_resolved_readings():
    uno = _entrada("9410912000S")
    dos = _entrada("9410912000S", RID)
    resueltas = {"9410912000S": (REF_A, "Tornillo", "94109-12000S")}

    aptas, cerradas = lecturas.confirmar_ronda_dos(
        [uno, dos], {RID: ("94109-12000S", True)}, resueltas)

    assert (aptas, cerradas) == ([uno, dos], [])


# --- the SQL key matches the functional index --------------------------------


def _migracion():
    archivo = (Path(__file__).resolve().parents[2] / "alembic_motored"
               / "versions" / "b7d3e9a1c540_referencia_codigo_clave.py")
    spec = importlib.util.spec_from_file_location("codigo_clave", archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_the_lookup_expression_is_the_indexed_one():
    compilado = str(lecturas._CLAVE_SQL.compile(
        dialect=postgresql.dialect()))

    assert compilado.replace("referencia.codigo", "codigo") \
        == _migracion().CLAVE
    assert _migracion().down_revision == "f4b8d2a6c917"


def test_the_migration_creates_and_drops_the_index():
    modulo = _migracion()
    for direccion in ("upgrade", "downgrade"):
        with patch.object(modulo, "op") as op_mock:
            getattr(modulo, direccion)()
        sql = [str(c.args[0]) for c in op_mock.execute.call_args_list]
        assert sql[0] == "SET LOCAL lock_timeout = '5s'"
        assert "ix_referencia_codigo_clave" in sql[1]
