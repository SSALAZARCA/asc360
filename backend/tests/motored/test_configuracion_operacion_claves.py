"""
Motored "Configuración", T3 (Avisos), T4 (período) and T5 (Limpieza): the
new keys, their defaults (the constants and env values they replace) and
their validation.
"""
import pytest

from app.config import settings
from app.motored.services import avisos_antiguedad as av
from app.motored.services import parametros_claves as pc
from app.motored.services.corridas import codigos

AVISOS = ("aviso_hora_vispera", "aviso_hora_dia", "aviso_roles_destino")
LIMPIEZA = (
    "retencion_inventario_habilitada", "retencion_inventario_dias",
    "retencion_corridas_habilitada", "retencion_corridas_dias")


def _acepta(clave, valor):
    pc.validar_escritura(clave, valor)


def _rechaza(clave, valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura(clave, valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO
    return error.value.mensaje


@pytest.mark.parametrize("clave", AVISOS + LIMPIEZA)
def test_key_is_a_global_non_snapshotted_operation_key(clave):
    espec = pc.REGISTRO[clave]
    assert espec.grupo == pc.GRUPO_OPERACION
    assert espec.ambito == pc.AMBITO_GLOBAL
    assert pc.es_snapshotted(clave) is False
    assert clave not in pc.claves_motor()


def test_each_key_lives_in_its_tab():
    assert {pc.seccion_de(pc.REGISTRO[c]) for c in AVISOS} == {"avisos"}
    assert {pc.seccion_de(pc.REGISTRO[c]) for c in LIMPIEZA} == {"limpieza"}
    espec = pc.REGISTRO["periodo_tolerancia_pct"]
    assert pc.seccion_de(espec) == "cargas"
    assert pc.es_snapshotted("periodo_tolerancia_pct") is False


def test_aviso_defaults_are_the_constants_the_loop_used():
    reg = pc.REGISTRO
    assert reg["aviso_hora_vispera"].default == av.HORA_VISPERA.strftime(
        "%H:%M") == "16:30"
    assert reg["aviso_hora_dia"].default == av.HORA_DIA.strftime(
        "%H:%M") == "08:30"
    assert reg["aviso_roles_destino"].default == [
        r.value for r in av.ROLES_DESTINO] == ["COMPRAS"]


def test_limpieza_and_periodo_defaults_come_from_the_env_settings():
    reg = pc.REGISTRO
    assert reg["retencion_inventario_habilitada"].default is (
        settings.MOTORED_RETENCION_ENABLED)
    assert reg["retencion_inventario_dias"].default == (
        settings.MOTORED_RETENCION_DIAS)
    assert reg["retencion_corridas_habilitada"].default is (
        settings.MOTORED_CORRIDA_RETENCION_ENABLED)
    assert reg["retencion_corridas_dias"].default == (
        settings.MOTORED_CORRIDA_RETENCION_DIAS)
    assert reg["periodo_tolerancia_pct"].default == (
        settings.MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT) == 0.5


@pytest.mark.parametrize("valor", ["00:00", "08:30", "16:30", "23:59"])
def test_hours_accept_hh_mm(valor):
    _acepta("aviso_hora_vispera", valor)
    _acepta("aviso_hora_dia", valor)


@pytest.mark.parametrize("valor", [
    "24:00", "8:30", "08:60", "0830", "08:30:00", "", None, 830, "ab:cd"])
def test_hours_reject_anything_else(valor):
    _rechaza("aviso_hora_dia", valor)


@pytest.mark.parametrize("valor", [
    ["COMPRAS"], ["ADMIN"], ["ADMIN", "COMPRAS"]])
def test_roles_accept_the_web_roles_that_link_telegram(valor):
    _acepta("aviso_roles_destino", valor)


@pytest.mark.parametrize("valor", [
    [], ["SUCURSAL"], ["COMPRAS", "COMPRAS"], ["compras"], "COMPRAS",
    ["COMPRAS", 3], None])
def test_roles_reject_empty_unknown_or_repeated(valor):
    _rechaza("aviso_roles_destino", valor)


def test_roles_expose_their_options_to_the_page():
    ficha = pc.ficha(pc.REGISTRO["aviso_roles_destino"])
    assert ficha["tipo"] == "lista_opciones"
    assert ficha["opciones"] == ["ADMIN", "COMPRAS"]


@pytest.mark.parametrize("clave", [
    "retencion_inventario_habilitada", "retencion_corridas_habilitada"])
def test_retention_switches_are_booleans(clave):
    _acepta(clave, True)
    _acepta(clave, False)
    _rechaza(clave, "si")


@pytest.mark.parametrize("clave,minimo", [
    ("retencion_inventario_dias", 30), ("retencion_corridas_dias", 7)])
def test_retention_days_have_a_sane_minimum_explained_in_spanish(
        clave, minimo):
    _acepta(clave, minimo)
    _acepta(clave, 365)
    mensaje = _rechaza(clave, minimo - 1)
    assert str(minimo) in mensaje and "días" in mensaje
    _rechaza(clave, 0)
    _rechaza(clave, "90")
    _rechaza(clave, True)
    _rechaza(clave, 100000)


@pytest.mark.parametrize("valor", [0, 0.5, "2", 10, 100])
def test_period_tolerance_accepts_a_percentage(valor):
    _acepta("periodo_tolerancia_pct", valor)


@pytest.mark.parametrize("valor", [-1, 101, "x", None, True])
def test_period_tolerance_rejects_non_percentages(valor):
    _rechaza("periodo_tolerancia_pct", valor)


def test_the_four_ingesta_keys_of_the_cargas_tab_are_registered():
    for clave in ("tipos_inventario_incluidos", "estados_backorder_vigentes",
                  "dias_ventana_ingresos", "tolerancia_ingreso_pct"):
        assert pc.seccion_de(pc.REGISTRO[clave]) == "cargas"
    assert pc.REGISTRO["tipos_inventario_incluidos"].default == [
        "REPUESTOS", "ACCESORIOS", "LUBRICANTES", "LLANTAS", "BATERIAS",
        "CASCOS", "GPS"]
