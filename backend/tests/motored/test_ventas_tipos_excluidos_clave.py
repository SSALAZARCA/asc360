"""The `ventas_tipos_excluidos` setting: ERP sale-type codes that the VENTAS
load discards (key, defaults and validation only; no ingest behavior)."""
import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services.corridas import codigos

CLAVE = "ventas_tipos_excluidos"


def _acepta(valor):
    pc.validar_escritura(CLAVE, valor)


def _rechaza(valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura(CLAVE, valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO


def test_key_is_a_global_operation_key_in_the_cargas_tab():
    espec = pc.REGISTRO[CLAVE]
    assert espec.grupo == pc.GRUPO_OPERACION
    assert espec.ambito == pc.AMBITO_GLOBAL
    assert pc.seccion_de(espec) == "cargas"
    assert pc.es_snapshotted(CLAVE) is False
    assert CLAVE not in pc.claves_motor()


def test_defaults_are_the_agreed_erp_codes():
    default = pc.REGISTRO[CLAVE].default
    assert {"codigo": "IM19", "modo": "prefijo"} in default
    exactos = {f["codigo"] for f in default if f["modo"] == "exacto"}
    assert exactos == {
        "VS12", "VS13", "G01", "OBS2", "RPGOGORO",
        *(f"ST00{n}" for n in range(1, 9))}
    assert len(default) == 1 + len(exactos)
    _acepta(default)


def test_page_gets_the_row_fields():
    ficha = pc.ficha(pc.REGISTRO[CLAVE])
    assert ficha["campos"] == ["codigo", "modo"]


@pytest.mark.parametrize("valor", [
    [], [{"codigo": "IM19", "modo": "prefijo"}],
    [{"codigo": "A", "modo": "prefijo"}, {"codigo": "A", "modo": "exacto"}]])
def test_accepts_valid_lists(valor):
    _acepta(valor)


@pytest.mark.parametrize("valor", [
    None, "IM19", [{"codigo": "", "modo": "exacto"}],
    [{"codigo": " IM19", "modo": "exacto"}],
    [{"codigo": "im19", "modo": "exacto"}],
    [{"codigo": "IM19", "modo": "contiene"}],
    [{"codigo": "IM19"}], [{"codigo": 3, "modo": "exacto"}],
    [{"codigo": "IM19", "modo": "exacto", "extra": 1}],
    ["IM19"],
    [{"codigo": "A", "modo": "exacto"}, {"codigo": "A", "modo": "exacto"}]])
def test_rejects_invalid_lists(valor):
    _rechaza(valor)
