"""
Fase 2 "Ingesta", Phase 7 "BACKORDER + DEMANDA_PERDIDA Transform" (PR7)
(sdd/motored-pedidos-ingesta, task 7.2) — `services/ingesta/
demanda_perdida.py` (design ADR-8/ADR-9, spec "DEMANDA_PERDIDA silent
discard of incomplete rows").

No live Postgres: same `FakeAsyncSession` convention as the rest of
`tests/motored/`.

Columns (`sucursal`, `sucursal Drive`, `Referencia`, `Cantidad Solicitada`)
verified against the real production workbook (`PLANTILLA PEDIDO
SEPTIEMBRE.xlsx`, hoja "Ventas perdidas"): exact header casing confirmed
with openpyxl. In THIS month's real export the sheet has 710 data rows and
ALL 710 are blank/`#N/A` formula remnants (zero rows carry both a
`Referencia` and a `Cantidad Solicitada` > 0) -- confirming the spec's own
description verbatim ("El archivo trae muchas filas vacías y `#N/A` de
fórmulas") rather than a hypothetical edge case. Because no row in the real
file is actually usable this cycle, the shape of a POPULATED `sucursal`
column could not be verified end-to-end against real data -- flagged in the
apply-progress report for the orchestrator to re-check once the owner has a
month with real lost-demand rows.

The silent-discard rule is THE ONE documented exception to per-row-tolerant
error reporting: unlike VENTAS/INVENTARIO/BACKORDER, a row here that fails
resolution or quantity NEVER produces a `carga_error` -- confirmed against
`sdd/motored-pedidos-ingesta/proposal` (§5.7, "descartar filas sin
referencia o sin cantidad > 0, sin reportarlas como error"). The exception
is scoped EXACTLY to those two conditions: an unresolved `sucursal` on an
otherwise-valid row (resolvable referencia + `cantidad_solicitada > 0`)
still follows the general per-row-tolerant rule and DOES produce a
`SUCURSAL_NO_ENCONTRADA` `carga_error`, staging the row with
`sucursal_id = None` for Fase 9 to re-resolve later -- same contract as
every other movement type.
"""
import uuid
from datetime import date
from decimal import Decimal

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import columnas, demanda_perdida
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()

_MAPA_COLUMNAS = {
    "sucursal": 0,
    "sucursal Drive": 1,
    "Referencia": 2,
    "Cantidad Solicitada": 3,
}


def _cache(sucursales=(), referencias=()) -> CacheResolucion:
    return CacheResolucion(
        sucursal_por_texto={texto: sid for texto, sid in sucursales},
        referencia_por_codigo_proveedor={clave: rid for clave, rid in referencias},
    )


def _fila(sucursal="CALI NORTE", sucursal_drive=None, referencia="REF1", cantidad_solicitada=5):
    return (sucursal, sucursal_drive, referencia, cantidad_solicitada)


def _cache_resuelta():
    return _cache(
        sucursales=[("CALI NORTE", SUCURSAL_ID)],
        referencias=[(("REF1", PROVEEDOR_ID), REFERENCIA_ID)],
    )


def _procesar(fila_raw, **overrides):
    kwargs = dict(
        numero_fila=2,
        lote=1,
        mapa_columnas=_MAPA_COLUMNAS,
        cache=_cache_resuelta(),
        carga_id=CARGA_ID,
        proveedor_id=PROVEEDOR_ID,
    )
    kwargs.update(overrides)
    return demanda_perdida.procesar_fila(fila_raw, **kwargs)


# ---------------------------------------------------------------------------
# 7.2 — descarte silencioso (única excepción documentada) + mapeo (RED)
# ---------------------------------------------------------------------------


def test_fila_completamente_vacia_se_descarta_en_silencio():
    # Reproduce las 710 filas #N/A/en blanco del sheet real.
    fila_staging, errores = _procesar(_fila(referencia=None, cantidad_solicitada=None))

    assert fila_staging is None
    assert errores == []


def test_sin_referencia_se_descarta_en_silencio_sin_importar_la_cantidad():
    fila_staging, errores = _procesar(_fila(referencia=None, cantidad_solicitada=99))

    assert fila_staging is None
    assert errores == []


def test_referencia_no_resuelta_se_descarta_en_silencio_sin_carga_error():
    # La ÚNICA excepción documentada a la tolerancia por-fila: a diferencia
    # de VENTAS/INVENTARIO/BACKORDER, acá NO se genera REFERENCIA_NO_
    # ENCONTRADA.
    fila_staging, errores = _procesar(_fila(referencia="NO-EXISTE"))

    assert fila_staging is None
    assert errores == []


def test_cantidad_cero_se_descarta_en_silencio():
    fila_staging, errores = _procesar(_fila(cantidad_solicitada=0))

    assert fila_staging is None
    assert errores == []


def test_cantidad_negativa_se_descarta_en_silencio():
    fila_staging, errores = _procesar(_fila(cantidad_solicitada=-1))

    assert fila_staging is None
    assert errores == []


def test_cantidad_ausente_se_descarta_en_silencio():
    fila_staging, errores = _procesar(_fila(cantidad_solicitada=None))

    assert fila_staging is None
    assert errores == []


def test_cantidad_no_numerica_se_descarta_en_silencio_sin_carga_error():
    # A diferencia de VENTAS/INVENTARIO/BACKORDER (que SÍ emiten un error
    # tipado para un valor no-numérico), DEMANDA_PERDIDA colapsa este caso
    # al mismo descarte silencioso que "ausente"/"cero" -- spec §5.7,
    # literal: "sin reportarlas como error".
    fila_staging, errores = _procesar(_fila(cantidad_solicitada="#N/A"))

    assert fila_staging is None
    assert errores == []


def test_fila_aplicable_conserva_cantidad_solicitada_en_el_payload():
    fila_staging, errores = _procesar(_fila(cantidad_solicitada=7))

    assert errores == []
    assert Decimal(fila_staging.payload["cantidad_solicitada"]) == Decimal("7")
    assert fila_staging.sucursal_id == SUCURSAL_ID
    assert fila_staging.referencia_id == REFERENCIA_ID


def test_sucursal_drive_es_respaldo_cuando_sucursal_esta_vacia():
    cache = _cache(
        sucursales=[("BOGOTA CENTRO", SUCURSAL_ID)],
        referencias=[(("REF1", PROVEEDOR_ID), REFERENCIA_ID)],
    )
    fila_staging, errores = _procesar(
        _fila(sucursal="", sucursal_drive="Bogota Centro"), cache=cache
    )

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_sucursal_no_resuelta_SI_genera_carga_error_a_diferencia_de_referencia():
    # La excepción de descarte silencioso está ACOTADA a referencia/cantidad
    # -- una sucursal sin resolver en una fila POR LO DEMÁS válida sigue la
    # regla general de tolerancia por-fila (carga_error + staging con NULL).
    fila_staging, errores = _procesar(_fila(sucursal="NO EXISTE", sucursal_drive=None))

    assert fila_staging is not None
    assert fila_staging.sucursal_id is None
    assert fila_staging.referencia_id == REFERENCIA_ID
    assert len(errores) == 1
    assert errores[0].codigo_error == "SUCURSAL_NO_ENCONTRADA"


def test_una_fila_descartada_no_afecta_una_fila_valida_del_mismo_lote():
    descartada, errores_descartada = _procesar(_fila(referencia=None))
    valida, errores_valida = _procesar(_fila())

    assert descartada is None and errores_descartada == []
    assert valida is not None and errores_valida == []


def test_columnas_esperadas_mapean_por_nombre_via_columnas_modulo():
    encabezado = ("sucursal", "sucursal Drive", "Referencia", "Cantidad Solicitada")
    mapa = columnas.construir_mapa_columnas(encabezado, demanda_perdida.COLUMNAS_ESPERADAS)

    esperado = dict(
        zip(demanda_perdida.COLUMNAS_ESPERADAS, range(len(demanda_perdida.COLUMNAS_ESPERADAS)))
    )
    assert mapa == esperado


# ---------------------------------------------------------------------------
# 7.2 — agregación + upsert REPLACE-not-sum (RED)
# ---------------------------------------------------------------------------


def _fila_staging(sucursal_id, referencia_id, cantidad_solicitada, fila=1, lote=1):
    return CargaFilaStaging(
        carga_id=CARGA_ID,
        fila=fila,
        lote=lote,
        payload={"cantidad_solicitada": str(cantidad_solicitada)},
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )


def test_agregar_cantidad_solicitada_suma_instancias_de_demanda_perdida():
    # A diferencia de BACKORDER (una línea puntual por pedido), cada fila
    # acá es una INSTANCIA separada de demanda perdida para la misma
    # sucursal/referencia -- sumarlas es correcto (mismo criterio aditivo
    # que VENTAS usa para unidades vendidas).
    filas = [
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 5, fila=1),
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 3, fila=2),
    ]

    totales = demanda_perdida.agregar_cantidad_solicitada(filas)

    assert totales[(SUCURSAL_ID, REFERENCIA_ID)] == Decimal("8")


def test_agregar_cantidad_solicitada_excluye_filas_sin_clave_resuelta():
    filas = [
        _fila_staging(None, REFERENCIA_ID, 5),
        _fila_staging(SUCURSAL_ID, None, 5, fila=2),
    ]

    assert demanda_perdida.agregar_cantidad_solicitada(filas) == {}


def test_construir_statement_upsert_setea_cantidad_a_excluded_nunca_suma():
    totales = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("8")}

    stmt = demanda_perdida.construir_statement_upsert(totales, date(2026, 9, 15), CARGA_ID)

    set_clause = stmt._post_values_clause.update_values_to_set
    valores_set = {
        (col if isinstance(col, str) else col.name): expr for col, expr in set_clause
    }
    assert "cantidad_solicitada" in valores_set
    columna_referenciada = valores_set["cantidad_solicitada"]
    assert columna_referenciada.table.name == "excluded"
    assert columna_referenciada.name == "cantidad_solicitada"


def test_construir_statement_upsert_retorna_none_sin_totales():
    assert demanda_perdida.construir_statement_upsert({}, date(2026, 9, 15), CARGA_ID) is None


async def test_aplicar_ejecuta_una_sola_sentencia_set_based():
    totales = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("8")}
    session = FakeAsyncSession(execute_queue=[[]])

    await demanda_perdida.aplicar(session, totales, date(2026, 9, 15), CARGA_ID)

    assert len(session.executed_statements) == 1


async def test_aplicar_no_ejecuta_nada_sin_totales():
    session = FakeAsyncSession(execute_queue=[])

    await demanda_perdida.aplicar(session, {}, date(2026, 9, 15), CARGA_ID)

    assert session.executed_statements == []


async def test_una_recarga_de_la_misma_fecha_reemplaza_no_acumula():
    totales_corregidos = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("12")}
    session = FakeAsyncSession(execute_queue=[[]])

    await demanda_perdida.aplicar(session, totales_corregidos, date(2026, 9, 15), CARGA_ID)

    insert_values = session.executed_statements[0].compile().construct_params()
    assert Decimal("12") in insert_values.values()


# ---------------------------------------------------------------------------
# Phase 2 (sdd/motored-ventas-perdidas-bot, task 2.1) — el upsert EXCEL debe
# escribir/matchear `origen='EXCEL'` explícitamente ahora que la unique key
# de `demanda_perdida` se ensanchó a 4 columnas (Fase 1, schema). Byte a
# byte: el REPLACE-not-sum de arriba (líneas ~244-275) queda intacto, esto
# solo agrega la columna `origen` a las VALUES y al conflict target.
# ---------------------------------------------------------------------------


def test_construir_statement_upsert_incluye_origen_excel_en_los_valores():
    totales = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("8")}

    stmt = demanda_perdida.construir_statement_upsert(totales, date(2026, 9, 15), CARGA_ID)

    valores_compilados = stmt.compile().construct_params()
    assert "EXCEL" in valores_compilados.values()


def test_construir_statement_upsert_conflict_target_incluye_origen():
    totales = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("8")}

    stmt = demanda_perdida.construir_statement_upsert(totales, date(2026, 9, 15), CARGA_ID)

    conflict_target = list(stmt._post_values_clause.inferred_target_elements)
    assert conflict_target == ["fecha", "sucursal_id", "referencia_id", "origen"]
