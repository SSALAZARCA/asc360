"""
Configuración tab "Conteos de inventario" (odd/motored-conteos-inventario,
WU4): the three registry keys, their rules and the cross-key rule
"reconteo amount < critical amount".
"""
import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services.corridas import codigos

RECONTEO = pc.CLAVE_CONTEO_UMBRAL_RECONTEO
CRITICO = pc.CLAVE_CONTEO_UMBRAL_CRITICO
VIGENCIA = pc.CLAVE_CONTEO_VIGENCIA_HORAS


def test_the_keys_have_the_owner_defaults():
    assert RECONTEO == "conteo_umbral_reconteo_pesos"
    assert CRITICO == "conteo_umbral_critico_pesos"
    assert VIGENCIA == "conteo_inventario_vigencia_horas"
    assert pc.REGISTRO[RECONTEO].default == 100000
    assert pc.REGISTRO[CRITICO].default == 500000
    assert pc.REGISTRO[VIGENCIA].default == 6


@pytest.mark.parametrize("clave", [RECONTEO, CRITICO, VIGENCIA])
def test_the_keys_live_in_the_conteos_tab_and_are_not_snapshotted(clave):
    ficha = pc.ficha(pc.REGISTRO[clave])
    assert ficha["seccion"] == "conteos"
    assert ficha["grupo"] == pc.GRUPO_OPERACION
    assert ficha["tipo"] == "entero"
    assert ficha["snapshotted"] is False
    assert ficha["minimo"] == 1


def test_conteos_is_a_known_tab():
    assert "conteos" in pc.SECCIONES


@pytest.mark.parametrize("clave", [RECONTEO, CRITICO, VIGENCIA])
@pytest.mark.parametrize("valor", [0, -1, "100", 1.5, None, True])
def test_the_keys_refuse_non_positive_or_non_integer_values(clave, valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura(clave, valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO


@pytest.mark.parametrize("clave", [RECONTEO, CRITICO, VIGENCIA])
def test_the_keys_accept_a_positive_integer(clave):
    pc.validar_escritura(clave, 1)


def test_the_keys_are_global_only():
    with pytest.raises(pc.ErrorParametro):
        pc.validar_escritura(RECONTEO, 10, sucursal_id="x")


def test_reconteo_must_be_below_critical():
    pc.validar_umbrales_conteo(100000, 500000)
    for reconteo, critico in ((500000, 500000), (600000, 500000)):
        with pytest.raises(pc.ErrorParametro) as error:
            pc.validar_umbrales_conteo(reconteo, critico)
        assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO
        assert "menor que" in error.value.mensaje


def test_relation_checks_the_written_key_against_the_other_one():
    vigentes = {RECONTEO: 100000, CRITICO: 500000}

    pc.validar_relaciones(RECONTEO, 400000, vigentes)
    pc.validar_relaciones(CRITICO, 200000, vigentes)
    pc.validar_relaciones(VIGENCIA, 1, vigentes)
    with pytest.raises(pc.ErrorParametro):
        pc.validar_relaciones(RECONTEO, 500000, vigentes)
    with pytest.raises(pc.ErrorParametro):
        pc.validar_relaciones(CRITICO, 90000, vigentes)


def test_relation_falls_back_to_the_defaults_when_nothing_is_saved():
    with pytest.raises(pc.ErrorParametro):
        pc.validar_relaciones(RECONTEO, 700000, {})
    pc.validar_relaciones(CRITICO, 100001, {})


def test_related_keys_are_the_other_threshold_only():
    assert pc.claves_relacionadas(RECONTEO) == (CRITICO,)
    assert pc.claves_relacionadas(CRITICO) == (RECONTEO,)
    assert pc.claves_relacionadas(VIGENCIA) == ()
