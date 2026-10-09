"""
Inventory counts, the pure rules of scheduling and Iniciar
(odd/motored-conteos-inventario, WU5; design §4.10, §5.1, ADR-9): the
staleness verdict, the state guards, the reason guard and the frozen
thresholds. The SQL side runs against a real Postgres in
`pg_real/test_conteos_snapshot_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services.conteos import errores, snapshot

UTC = datetime.timezone.utc
AHORA = datetime.datetime(2026, 10, 9, 23, 0, tzinfo=UTC)
CORTE = datetime.date(2026, 10, 9)
USUARIO = uuid.uuid4()


def _fuente(aplicado_en, fecha_corte=CORTE):
    return snapshot.FuenteSnapshot(
        carga_id=uuid.uuid4(), fecha_corte=fecha_corte,
        aplicado_en=aplicado_en, lineas=10)


# --- staleness --------------------------------------------------------------


def test_age_counts_from_the_apply_time():
    aplicado = AHORA - datetime.timedelta(hours=7, minutes=30)
    assert snapshot.antiguedad_horas(_fuente(aplicado), AHORA) == (
        Decimal("7.5"))


def test_age_without_apply_time_counts_from_the_cut_date_in_bogota():
    fuente = _fuente(None, datetime.date(2026, 10, 9))
    # 2026-10-09 00:00 Bogotá = 05:00 UTC; 18 hours before 23:00 UTC.
    assert snapshot.antiguedad_horas(fuente, AHORA) == Decimal("18")


def test_a_fresh_inventory_gives_no_warning():
    fuente = _fuente(AHORA - datetime.timedelta(hours=6))
    assert snapshot.revisar_antiguedad(
        fuente, 6, AHORA, False, USUARIO) is None


def test_a_stale_inventory_is_refused_with_the_carga_facts():
    aplicado = AHORA - datetime.timedelta(hours=6, minutes=6)
    fuente = _fuente(aplicado)

    with pytest.raises(errores.InventarioAntiguo) as error:
        snapshot.revisar_antiguedad(fuente, 6, AHORA, False, USUARIO)

    assert error.value.codigo == "INVENTARIO_ANTIGUO"
    assert error.value.datos["fecha_corte"] == "2026-10-09"
    assert error.value.datos["aplicado_en"] == aplicado.isoformat()
    assert error.value.datos["antiguedad_horas"] == "6.1"
    assert error.value.datos["vigencia_horas"] == 6
    assert "09/10/2026" in error.value.mensaje


def test_a_confirmed_stale_inventory_is_recorded():
    fuente = _fuente(AHORA - datetime.timedelta(hours=30))

    advertencia = snapshot.revisar_antiguedad(
        fuente, 6, AHORA, True, USUARIO)

    assert advertencia == {
        "antiguedad_horas": "30.0", "vigencia_horas": 6,
        "confirmada_por": str(USUARIO)}


# --- state guards ---------------------------------------------------------


@pytest.mark.parametrize("accion, estado", [
    ("reprogramar", "EN_CONTEO"), ("reprogramar", "CERRADO"),
    ("reprogramar", "ANULADO"), ("iniciar", "EN_CONTEO"),
    ("iniciar", "EN_RECONTEO"), ("iniciar", "CERRADO"),
    ("iniciar", "ANULADO"), ("anular", "CERRADO"), ("anular", "ANULADO"),
])
def test_transitions_are_refused_from_wrong_states(accion, estado):
    conteo = SimpleNamespace(estado=estado)
    with pytest.raises(errores.EstadoInvalido) as error:
        snapshot.exigir_estado(conteo, accion)
    assert error.value.datos["estado"] == estado


@pytest.mark.parametrize("accion, estado", [
    ("reprogramar", "PROGRAMADO"), ("iniciar", "PROGRAMADO"),
    ("anular", "PROGRAMADO"), ("anular", "EN_CONTEO"),
    ("anular", "EN_RECONTEO"),
])
def test_transitions_are_allowed_from_their_states(accion, estado):
    snapshot.exigir_estado(SimpleNamespace(estado=estado), accion)


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_annulling_needs_a_reason(motivo):
    with pytest.raises(errores.MotivoRequerido):
        snapshot.limpiar_motivo(motivo)


def test_the_reason_is_trimmed():
    assert snapshot.limpiar_motivo("  bodega inundada ") == "bodega inundada"


# --- frozen thresholds ----------------------------------------------------


def test_thresholds_come_from_the_configured_values():
    umbrales = snapshot.umbrales_desde({
        pc.CLAVE_CONTEO_UMBRAL_RECONTEO: 80000,
        pc.CLAVE_CONTEO_UMBRAL_CRITICO: 900000,
        pc.CLAVE_CONTEO_VIGENCIA_HORAS: 12,
    })
    assert umbrales == snapshot.Umbrales(
        Decimal("80000"), Decimal("900000"), 12)


def test_inconsistent_saved_thresholds_refuse_to_start():
    with pytest.raises(errores.UmbralesInvalidos):
        snapshot.umbrales_desde({
            pc.CLAVE_CONTEO_UMBRAL_RECONTEO: 600000,
            pc.CLAVE_CONTEO_UMBRAL_CRITICO: 500000,
            pc.CLAVE_CONTEO_VIGENCIA_HORAS: 6,
        })


def test_every_domain_error_has_a_code_and_a_spanish_message():
    for clase in errores.ErrorConteo.__subclasses__():
        error = clase()
        assert error.codigo and error.codigo == error.codigo.upper()
        assert error.mensaje and str(error) == error.mensaje
