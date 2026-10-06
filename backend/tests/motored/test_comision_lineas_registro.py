"""
Motored "Configuración", Comisiones: the per-line bonus keys (`comision_lineas`,
`comision_bono_umbral_pct`) -- registration, defaults and validation.
"""
import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services.corridas import codigos

CLAVES = ("comision_lineas", "comision_bono_umbral_pct")


def _acepta(clave, valor):
    pc.validar_escritura(clave, valor)


def _rechaza(clave, valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura(clave, valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO


def _linea(**cambios):
    base = {"linea": "CASCOS", "pct_meta": "6", "bono": "30000", "activo": True}
    return {**base, **cambios}


@pytest.mark.parametrize("clave", CLAVES)
def test_key_is_a_global_non_snapshotted_comisiones_key(clave):
    espec = pc.REGISTRO[clave]
    assert (espec.grupo, espec.ambito) == (pc.GRUPO_OPERACION, pc.AMBITO_GLOBAL)
    assert pc.seccion_de(espec) == "comisiones"
    assert pc.es_snapshotted(clave) is False


@pytest.mark.parametrize("clave", CLAVES)
def test_default_passes_its_own_validation(clave):
    _acepta(clave, pc.REGISTRO[clave].default)


def test_defaults_are_the_agreed_ones():
    assert pc.REGISTRO["comision_bono_umbral_pct"].default == "95"
    assert pc.REGISTRO["comision_lineas"].default == [
        {"linea": "LUBRICANTES", "pct_meta": "21", "bono": "35000", "activo": True},
        {"linea": "CASCOS", "pct_meta": "6", "bono": "30000", "activo": True},
        {"linea": "ACCESORIOS", "pct_meta": "3", "bono": "25000", "activo": True},
        {"linea": "LLANTAS", "pct_meta": "1", "bono": "25000", "activo": True},
        {"linea": "BATERIAS", "pct_meta": "1", "bono": "25000", "activo": True},
        {"linea": "TECNIRED", "pct_meta": "6", "bono": "25000", "activo": True},
    ]


def test_default_lines_are_commercial_lines_or_tecnired():
    from app.motored.services import tablero_asesores as t
    codigos_ = {x["linea"] for x in pc.REGISTRO["comision_lineas"].default}
    assert codigos_ <= set(t.LINEAS) | {"TECNIRED"}


# --- comision_lineas -------------------------------------------------------

def test_an_empty_list_is_valid():
    _acepta("comision_lineas", [])


def test_the_shape_the_editor_sends_is_accepted():
    _acepta("comision_lineas", [_linea(), _linea(linea="TECNIRED", pct_meta="6.5", bono="0", activo=False)])


def test_numbers_are_accepted_and_converted_to_strings():
    valor = [_linea(pct_meta=6, bono=30000.0)]
    _acepta("comision_lineas", valor)
    assert pc.parsear("comision_lineas", valor) == [
        {"linea": "CASCOS", "pct_meta": "6", "bono": "30000", "activo": True}]


@pytest.mark.parametrize("valor", [
    None, "x", {}, [1], [_linea(), _linea(pct_meta="2")],          # duplicate line
    [_linea(linea="cascos")], [_linea(linea=" CASCOS")], [_linea(linea="")],
    [_linea(linea="BATERÍAS")], [_linea(linea=3)],
])
def test_a_bad_list_or_line_is_rejected(valor):
    _rechaza("comision_lineas", valor)


@pytest.mark.parametrize("pct", ["0", 0, "-1", "100.01", "abc", None, True, "NaN"])
def test_pct_meta_must_be_above_zero_and_at_most_100(pct):
    _rechaza("comision_lineas", [_linea(pct_meta=pct)])


@pytest.mark.parametrize("pct", ["0.01", "100", 100, "21"])
def test_pct_meta_boundaries_are_accepted(pct):
    _acepta("comision_lineas", [_linea(pct_meta=pct)])


@pytest.mark.parametrize("bono", ["-1", -5, "1.5", 2.5, "abc", None, True, "1e3"])
def test_bono_must_be_whole_non_negative_pesos(bono):
    _rechaza("comision_lineas", [_linea(bono=bono)])


@pytest.mark.parametrize("activo", ["true", 1, None])
def test_activo_must_be_a_bool(activo):
    _rechaza("comision_lineas", [_linea(activo=activo)])


@pytest.mark.parametrize("cambio", [{"extra": 1}])
def test_unknown_fields_are_rejected(cambio):
    _rechaza("comision_lineas", [_linea(**cambio)])


def test_a_missing_field_is_rejected():
    fila = _linea()
    del fila["activo"]
    _rechaza("comision_lineas", [fila])


# --- comision_bono_umbral_pct ----------------------------------------------

@pytest.mark.parametrize("valor", ["0", "95", 95, "100.5", "200", 200.0])
def test_umbral_accepts_0_to_200(valor):
    _acepta("comision_bono_umbral_pct", valor)


@pytest.mark.parametrize("valor", ["-1", "200.01", "abc", None, True, [], "NaN"])
def test_umbral_rejects_out_of_range_or_non_numeric(valor):
    _rechaza("comision_bono_umbral_pct", valor)
