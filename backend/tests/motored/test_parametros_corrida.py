"""
Motored Pedidos F3 "Motor", S4b (sdd/motored-pedidos-motor, ADR-7, decisión
#16): parámetros congelados de una corrida y su snapshot con la fuente de
cada valor.

Todo es puro salvo `cargar_parametros_corrida`, que hace UNA lectura.
"""
import datetime
import json
import uuid
from fractions import Fraction

import pytest

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros, parametros_claves as pc
from app.motored.services.corridas import parametros_corrida as pcorr
from app.motored.services.motor.tipos import ParametrosMotor
from tests.motored.conftest import FakeAsyncSession

CORTE = datetime.date(2026, 10, 5)
SUC_A = uuid.uuid4()
SUC_B = uuid.uuid4()
SUCURSALES = [SUC_A, SUC_B]


def _fila(clave, valor, sucursal_id=None, desde=datetime.date(2026, 10, 1)):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=desde,
        sucursal_id=sucursal_id,
    )


def _construir(filas=(), overrides=None):
    vigentes = parametros.VigentesMotor.desde_filas(
        filas, CORTE, overrides=overrides)
    return pcorr.construir_parametros_corrida(vigentes, SUCURSALES)


# --- Preset legacy por defecto ---------------------------------------------


def test_without_rows_the_engine_gets_the_legacy_preset():
    resultado = _construir()

    assert resultado.motor == ParametrosMotor()


def test_without_rows_every_source_is_default():
    resultado = _construir()

    fuentes = {
        e["fuente"] for e in resultado.snapshot["parametros"].values()
    }
    assert fuentes == {"DEFAULT"}


def test_without_rows_dias_entre_pedidos_is_30_per_sucursal():
    resultado = _construir()

    assert resultado.dias_entre_pedidos == {SUC_A: 30, SUC_B: 30}


def test_without_rows_the_four_staleness_limits_are_7():
    resultado = _construir()

    assert resultado.limites_antiguedad == {
        "inventario": 7, "backorder": 7, "facturas": 7, "ingresos": 7,
    }


# --- Precedencia por sucursal ----------------------------------------------


def test_sucursal_override_beats_global_beats_default():
    filas = [
        _fila("dias_entre_pedidos", 15),
        _fila("dias_entre_pedidos", 7, SUC_A),
    ]

    resultado = _construir(filas)

    assert resultado.dias_entre_pedidos == {SUC_A: 7, SUC_B: 15}
    por_suc = resultado.snapshot["dias_entre_pedidos_por_sucursal"]
    assert por_suc[str(SUC_A)]["fuente"] == "SUCURSAL"
    assert por_suc[str(SUC_B)]["fuente"] == "GLOBAL"


def test_each_sucursal_snapshot_entry_records_row_id_and_version():
    fila = _fila("dias_entre_pedidos", 7, SUC_A)

    resultado = _construir([fila])

    entrada = resultado.snapshot["dias_entre_pedidos_por_sucursal"]
    assert entrada[str(SUC_A)]["parametro_id"] == str(fila.id)
    assert entrada[str(SUC_A)]["vigente_desde"] == "2026-10-01"
    assert entrada[str(SUC_B)]["fuente"] == "DEFAULT"
    assert entrada[str(SUC_B)]["valor"] == 30


# --- Traducción al motor ---------------------------------------------------


def test_stored_values_map_into_the_engine_parameters():
    filas = [
        _fila("incluir_demanda_perdida_en_ponderada", True),
        _fila("factor_demanda_perdida", "1.5"),
        _fila("consolidar_sustituidas", True),
        _fila("modo_redondeo_empaque", "ARRIBA"),
        _fila("corte_abc_a", "0.70"),
        _fila("corte_abc_b", "0.90"),
        _fila("umbral_f", 3),
        _fila("umbral_m", 2),
        _fila("k_fms", {"F": "4", "M": "2", "S": "1"}),
        _fila("tolerancia_sobrestock", "0.5"),
        _fila("meses_inventario_muerto", 4),
    ]

    motor = _construir(filas).motor

    assert motor.incluir_demanda_perdida is True
    assert motor.factor_demanda_perdida == Fraction(3, 2)
    assert motor.consolidar_sustituidas is True
    assert motor.modo_redondeo == "ARRIBA"
    assert (motor.corte_abc_a, motor.corte_abc_b) == (
        Fraction(7, 10), Fraction(9, 10))
    assert (motor.umbral_f, motor.umbral_m) == (3, 2)
    assert dict(motor.k_fms) == {
        "F": Fraction(4), "M": Fraction(2), "S": Fraction(1)}
    assert motor.tolerancia_sobrestock == Fraction(1, 2)
    assert motor.meses_inventario_muerto == 4


def test_mes_en_curso_and_transito_switches_are_exposed_for_the_preflight():
    filas = [
        _fila("modo_mes_en_curso", "PONDERADO"),
        _fila("tope_proyeccion_mes_actual", "2.5"),
        _fila("min_dias_mes_actual", 8),
        _fila("excluir_transito_vencido", True),
    ]

    resultado = _construir(filas)

    assert resultado.modo_mes_en_curso == "PONDERADO"
    assert resultado.tope_mes_en_curso == Fraction(5, 2)
    assert resultado.min_dias_mes_en_curso == 8
    assert resultado.excluir_transito_vencido is True
    assert resultado.motor.mes_en_curso is None


def test_mes_en_curso_defaults_are_the_legacy_values():
    resultado = _construir()

    assert resultado.modo_mes_en_curso == "EXCLUIDO"
    assert resultado.tope_mes_en_curso == Fraction(3)
    assert resultado.min_dias_mes_en_curso == 5
    assert resultado.excluir_transito_vencido is False


def test_a_stored_value_that_is_invalid_is_a_coded_error():
    with pytest.raises(pc.ErrorParametro) as info:
        _construir([_fila("dias_entre_pedidos", "abc", SUC_A)])

    assert info.value.codigo == "E-PARAM-002"


# --- Escenarios (overrides) ------------------------------------------------


def test_override_replaces_the_value_with_source_override():
    filas = [_fila("consolidar_sustituidas", False)]

    resultado = _construir(filas, {"consolidar_sustituidas": True})

    assert resultado.motor.consolidar_sustituidas is True
    entrada = resultado.snapshot["parametros"]["consolidar_sustituidas"]
    assert entrada["fuente"] == "OVERRIDE"
    assert entrada["parametro_id"] is None


def test_override_of_dias_entre_pedidos_applies_to_every_sucursal():
    filas = [_fila("dias_entre_pedidos", 7, SUC_A)]

    resultado = _construir(filas, {"dias_entre_pedidos": 15})

    assert resultado.dias_entre_pedidos == {SUC_A: 15, SUC_B: 15}


def test_overrides_never_mutate_the_stored_rows():
    fila = _fila("factor_demanda_perdida", "1")

    _construir([fila], {"factor_demanda_perdida": "2"})

    assert fila.valor == "1"


@pytest.mark.parametrize("overrides", [
    {"clave_que_no_existe": 1},
    {"dias_entre_pedidos": 0},
    {"consolidar_sustituidas": "si"},
    {"dias_ventana_ingresos": 30},
])
def test_invalid_or_non_engine_overrides_are_e_corrida_010(overrides):
    with pytest.raises(pc.ErrorParametro) as info:
        pcorr.validar_overrides(overrides)

    assert info.value.codigo == "E-CORRIDA-010"


def test_valid_overrides_are_accepted_and_none_means_no_scenario():
    assert pcorr.validar_overrides({"consolidar_sustituidas": True}) is None
    assert pcorr.validar_overrides(None) is None
    assert pcorr.validar_overrides({}) is None


# --- Snapshot --------------------------------------------------------------


def test_snapshot_records_every_engine_parameter_with_its_source():
    resultado = _construir()

    registrados = set(resultado.snapshot["parametros"])
    assert registrados == set(pc.claves_motor())
    entrada = resultado.snapshot["parametros"]["k_fms"]
    assert set(entrada) == {
        "valor", "fuente", "parametro_id", "vigente_desde"}


def test_snapshot_records_each_staleness_limit_with_its_source():
    filas = [_fila("max_dias_antiguedad_facturas", 15)]

    resultado = _construir(filas)

    limites = resultado.snapshot["limites_antiguedad"]
    assert limites["facturas"] == {
        "clave": "max_dias_antiguedad_facturas",
        "dias": 15, "fuente": "GLOBAL",
    }
    assert limites["inventario"]["fuente"] == "DEFAULT"
    assert set(limites) == {"inventario", "backorder", "facturas", "ingresos"}


def test_snapshot_is_plain_json_and_carries_the_corte():
    filas = [_fila("factor_demanda_perdida", "1.5")]

    snapshot = _construir(filas).snapshot

    assert json.loads(json.dumps(snapshot)) == snapshot
    assert snapshot["parametros_en_fecha"] == "2026-10-05"


def test_raising_one_staleness_limit_changes_only_the_gate_value():
    base = _construir()

    elevado = _construir([_fila("max_dias_antiguedad_facturas", 15)])

    assert elevado.motor == base.motor
    assert elevado.dias_entre_pedidos == base.dias_entre_pedidos
    assert elevado.limites_antiguedad["facturas"] == 15
    assert elevado.limites_antiguedad["inventario"] == 7
    diferencias = _diferencias(base.snapshot, elevado.snapshot)
    assert diferencias == {
        "parametros.max_dias_antiguedad_facturas.valor",
        "parametros.max_dias_antiguedad_facturas.fuente",
        "parametros.max_dias_antiguedad_facturas.parametro_id",
        "parametros.max_dias_antiguedad_facturas.vigente_desde",
        "limites_antiguedad.facturas.dias",
        "limites_antiguedad.facturas.fuente",
    }


def _diferencias(a, b, ruta=""):
    if not isinstance(a, dict):
        return set() if a == b else {ruta}
    encontradas = set()
    for clave in a.keys() | b.keys():
        sub = f"{ruta}.{clave}" if ruta else str(clave)
        encontradas |= _diferencias(a.get(clave), b.get(clave), sub)
    return encontradas


# --- Lectura desde la base -------------------------------------------------


async def test_cargar_parametros_corrida_reads_once_and_builds():
    filas = [_fila("dias_entre_pedidos", 7, SUC_A)]
    db = FakeAsyncSession(execute_queue=[filas])

    resultado = await pcorr.cargar_parametros_corrida(
        db, CORTE, SUCURSALES, overrides={"consolidar_sustituidas": True},
    )

    assert len(db.executed_statements) == 1
    assert resultado.dias_entre_pedidos == {SUC_A: 7, SUC_B: 30}
    assert resultado.motor.consolidar_sustituidas is True


async def test_cargar_rejects_bad_overrides_before_reading():
    db = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(pc.ErrorParametro):
        await pcorr.cargar_parametros_corrida(
            db, CORTE, SUCURSALES, overrides={"nope": 1},
        )

    assert db.executed_statements == []
