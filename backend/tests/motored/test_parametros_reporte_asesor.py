"""
The three Configuración keys of the asesor daily report send
(odd/motored-reporte-diario-asesor, T3b): the switch (OFF by default until
the owner approves a real sample), the deadline hour and the minimum hour.
They live in the Avisos tab and never enter a corrida snapshot.
"""
import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services import reporte_asesor_envio as envio

CLAVES = (
    "reporte_asesor_envio_activo",
    "reporte_asesor_hora_limite",
    "reporte_asesor_hora_minima",
)


def test_the_three_keys_are_registered_in_the_avisos_tab():
    for clave in CLAVES:
        espec = pc.REGISTRO[clave]
        assert espec.grupo == pc.GRUPO_OPERACION
        assert pc.seccion_de(espec) == "avisos"
        assert not pc.es_snapshotted(clave)


def test_defaults_switch_off_deadline_ten_minimum_six():
    assert pc.REGISTRO["reporte_asesor_envio_activo"].default is False
    assert pc.REGISTRO["reporte_asesor_hora_limite"].default == "10:00"
    assert pc.REGISTRO["reporte_asesor_hora_minima"].default == "06:00"


def test_the_service_constants_match_the_registry():
    assert envio.CLAVE_ACTIVO == CLAVES[0]
    assert envio.CLAVE_HORA_LIMITE == CLAVES[1]
    assert envio.CLAVE_HORA_MINIMA == CLAVES[2]
    respaldos = envio.respaldos()
    for clave in CLAVES:
        assert respaldos[clave] == pc.REGISTRO[clave].default


def test_types_are_bool_and_hour():
    assert pc.REGISTRO["reporte_asesor_envio_activo"].tipo == "bool"
    assert pc.REGISTRO["reporte_asesor_hora_limite"].tipo == "hora"
    assert pc.REGISTRO["reporte_asesor_hora_minima"].tipo == "hora"


@pytest.mark.parametrize("clave, valor", [
    ("reporte_asesor_envio_activo", True),
    ("reporte_asesor_hora_limite", "11:30"),
    ("reporte_asesor_hora_minima", "05:00"),
])
def test_valid_values_are_accepted(clave, valor):
    pc.validar_escritura(clave, valor)


@pytest.mark.parametrize("clave, valor", [
    ("reporte_asesor_envio_activo", "si"),
    ("reporte_asesor_hora_limite", "25:00"),
    ("reporte_asesor_hora_minima", 6),
])
def test_invalid_values_are_refused(clave, valor):
    with pytest.raises(pc.ErrorParametro):
        pc.validar_escritura(clave, valor)
