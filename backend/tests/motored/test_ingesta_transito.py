"""
Fase 2 "Ingesta", Phase 8 "FACTURAS/INGRESOS + Tránsito" (PR8)
(sdd/motored-pedidos-ingesta, task 8.2) — `services/ingesta/transito.py`
(design ADR-9, spec "Tránsito cruce by RH document identity", H3/H4).

No live Postgres: same `FakeAsyncSession` convention as
`test_ingesta_backorder.py`. Statement-construction is asserted at the
SQL level, never against a real engine.

H3: the RH regex `^([A-Z]{2})(\\d+)$` is compared as (prefijo, entero),
NEVER a fixed-width substring -- this is the whole point of H3 (source
spec §5.5's own callout that a fixed-width `MID(...)` extraction breaks
silently once a supplier emits a longer consecutive number).
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from tests.motored.conftest import FakeAsyncSession

from app.motored.services.ingesta import transito

CARGA_ID = uuid.uuid4()
FECHA_CORTE = date(2026, 9, 15)


# ---------------------------------------------------------------------------
# 8.2 — extraer_prefijo_numero_rh (H3: regex, never fixed-width) (RED)
# ---------------------------------------------------------------------------


def test_extrae_prefijo_y_numero_de_6_digitos():
    assert transito.extraer_prefijo_numero_rh("RH194067") == ("RH", 194067)


def test_extrae_prefijo_y_numero_de_mas_de_6_digitos():
    # H3 — un consecutivo más largo que el ancho fijo históricamente usado
    # (8 en facturas, 6 en ingresos) debe seguir cruzando correctamente.
    assert transito.extraer_prefijo_numero_rh("RH12345678") == ("RH", 12345678)


def test_extrae_prefijo_distinto_de_rh():
    assert transito.extraer_prefijo_numero_rh("FE15892") == ("FE", 15892)


def test_documento_con_guion_no_matchea_el_regex():
    # Formato real encontrado en "ingreso facturas ultimo 45 dias": "CH-70752".
    assert transito.extraer_prefijo_numero_rh("CH-70752") is None


def test_documento_vacio_o_ausente_no_matchea():
    assert transito.extraer_prefijo_numero_rh(None) is None
    assert transito.extraer_prefijo_numero_rh("") is None


def test_documento_en_minuscula_matchea_tolerando_case():
    assert transito.extraer_prefijo_numero_rh("rh194067") == ("RH", 194067)


def test_documento_con_espacios_matchea_tras_trim():
    assert transito.extraer_prefijo_numero_rh("  RH194067  ") == ("RH", 194067)


# ---------------------------------------------------------------------------
# 8.2 — calcular_veredicto (H4: ventana de tránsito + sospecha de parcial) (RED)
# ---------------------------------------------------------------------------


def _documento(valor_total=Decimal("100000"), fecha_factura=date(2026, 8, 25)):
    return transito.DocumentoFactura(valor_total=valor_total, fecha_factura=fecha_factura)


def test_sin_ingreso_y_dentro_de_la_ventana_no_esta_vencido():
    # 20 días antes del corte, ventana default 45 -- spec "A factura within
    # the window counts as tránsito".
    documento = _documento(fecha_factura=date(2026, 8, 26))  # 20 días antes de FECHA_CORTE
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=None, fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.ingresada is False
    assert veredicto.transito_vencido is False
    assert veredicto.ingreso_parcial_sospechoso is False


def test_sin_ingreso_y_fuera_de_la_ventana_esta_vencido():
    # 60 días antes del corte -- spec "A factura past the window is vencido
    # and excluded".
    documento = _documento(fecha_factura=FECHA_CORTE - timedelta(days=60))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=None, fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.transito_vencido is True


def test_limite_exacto_de_la_ventana_no_esta_vencido():
    # spec: `fecha_factura < fecha_corte - dias_ventana_ingresos` -- el
    # límite exacto NO es estrictamente menor, así que no vence todavía.
    documento = _documento(fecha_factura=FECHA_CORTE - timedelta(days=45))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=None, fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.transito_vencido is False


def test_un_dia_mas_alla_del_limite_si_esta_vencido():
    documento = _documento(fecha_factura=FECHA_CORTE - timedelta(days=46))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=None, fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.transito_vencido is True


def test_ingreso_matcheado_marca_ingresada_y_nunca_vencido():
    documento = _documento(fecha_factura=FECHA_CORTE - timedelta(days=60))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=Decimal("100000"), fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.ingresada is True
    assert veredicto.transito_vencido is False


def test_valor_neto_dentro_de_tolerancia_no_es_sospechoso():
    documento = _documento(valor_total=Decimal("100000"))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=Decimal("101000"), fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.ingreso_parcial_sospechoso is False


def test_valor_neto_justo_en_el_limite_de_tolerancia_no_es_sospechoso():
    documento = _documento(valor_total=Decimal("100000"))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=Decimal("102000"), fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.ingreso_parcial_sospechoso is False


def test_valor_neto_mas_alla_de_la_tolerancia_es_sospechoso():
    documento = _documento(valor_total=Decimal("100000"))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=Decimal("150000"), fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.ingreso_parcial_sospechoso is True


def test_sin_ingreso_nunca_es_sospechoso():
    documento = _documento(fecha_factura=FECHA_CORTE - timedelta(days=60))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=None, fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.ingreso_parcial_sospechoso is False


def test_valor_total_cero_no_crashea_al_evaluar_sospecha():
    documento = _documento(valor_total=Decimal("0"))
    veredicto = transito.calcular_veredicto(
        documento, valor_ingreso_neto=Decimal("500"), fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )
    assert veredicto.ingreso_parcial_sospechoso is False


# ---------------------------------------------------------------------------
# 8.2 — calcular_veredictos (orquestación por documento) (RED)
# ---------------------------------------------------------------------------


def test_calcular_veredictos_evalua_cada_documento_de_facturas():
    facturas_por_documento = {
        ("RH", 194067): _documento(valor_total=Decimal("100000"), fecha_factura=FECHA_CORTE),
        ("RH", 194078): _documento(
            valor_total=Decimal("50000"), fecha_factura=FECHA_CORTE - timedelta(days=60)
        ),
    }
    ingresos_por_documento = {("RH", 194067): Decimal("100000")}

    veredictos = transito.calcular_veredictos(
        facturas_por_documento, ingresos_por_documento, fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )

    assert veredictos[("RH", 194067)].ingresada is True
    assert veredictos[("RH", 194078)].ingresada is False
    assert veredictos[("RH", 194078)].transito_vencido is True


def test_calcular_veredictos_ignora_ingresos_de_otro_prefijo():
    # Un ingreso "FE"/"CH" jamás puede cruzar contra una factura "RH" --
    # las claves de dict ya lo garantizan sin filtro adicional.
    facturas_por_documento = {
        ("RH", 15892): _documento(valor_total=Decimal("1000"), fecha_factura=FECHA_CORTE),
    }
    ingresos_por_documento = {("FE", 15892): Decimal("1000")}

    veredictos = transito.calcular_veredictos(
        facturas_por_documento, ingresos_por_documento, fecha_corte=FECHA_CORTE,
        dias_ventana_ingresos=45, tolerancia_ingreso_pct=2.0,
    )

    assert veredictos[("RH", 15892)].ingresada is False


# ---------------------------------------------------------------------------
# 8.2 — construir_statements_actualizacion + aplicar (set-based UPDATE) (RED)
# ---------------------------------------------------------------------------


def test_construir_statements_actualizacion_una_sentencia_por_documento():
    veredictos = {
        ("RH", 194067): transito.VeredictoTransito(True, False, False),
        ("RH", 194078): transito.VeredictoTransito(False, True, False),
    }

    statements = transito.construir_statements_actualizacion(veredictos)

    assert len(statements) == 2


def test_construir_statements_actualizacion_vacio_retorna_lista_vacia():
    assert transito.construir_statements_actualizacion({}) == []


async def test_aplicar_ejecuta_una_sentencia_por_documento():
    veredictos = {
        ("RH", 194067): transito.VeredictoTransito(True, False, False),
        ("RH", 194078): transito.VeredictoTransito(False, True, False),
    }
    session = FakeAsyncSession(execute_queue=[[], []])

    await transito.aplicar(session, veredictos)

    assert len(session.executed_statements) == 2


async def test_aplicar_no_ejecuta_nada_sin_veredictos():
    session = FakeAsyncSession(execute_queue=[])

    await transito.aplicar(session, {})

    assert session.executed_statements == []
