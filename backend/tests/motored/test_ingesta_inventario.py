"""
Fase 2 "Ingesta", Phase 6 "INVENTARIO Transform" (sdd/motored-pedidos-ingesta,
task 6.1) — `services/ingesta/inventario.py` (design ADR-3/ADR-8/ADR-9, spec
"INVENTARIO bodega-principal consolidation and 90-day retention").

No live Postgres: same `FakeAsyncSession` convention as
`test_ingesta_ventas.py`. Consolidation and the REPLACE-not-sum upsert are
asserted at the SQL-construction level, same as VENTAS's ADR-4 tests.

Column names (`Referencia`, `Bodega`, `Desc.bodega`, `Existencia`) and the
"empty trailing row" shape were verified against the real production
workbook (`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`, hoja "inventario actual"):
56 532 data rows, of which the LAST 795 are fully blank except for stray
`#N/A` formula remnants in unrelated columns -- `Referencia` is `None` on
every one of them. Treating a blank `Referencia` as
`REFERENCIA_NO_ENCONTRADA` would have produced 795 false errors on every
single real load, so a blank/padding row is discarded in silence instead
(same "not a real row" contract VENTAS already uses for its business
filters, `_pasa_filtros_negocio`) -- see `test_fila_sin_referencia_...`
below.
"""
import uuid
from datetime import date
from decimal import Decimal

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import columnas, inventario
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
SUCURSAL_ID_2 = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()

_MAPA_COLUMNAS = {
    "Referencia": 0,
    "Bodega": 1,
    "Desc.bodega": 2,
    "Existencia": 3,
}


def _cache(sucursales=(), referencias=()) -> CacheResolucion:
    sucursal_por_texto = {texto: sid for texto, sid in sucursales}
    referencia_por_codigo_proveedor = {clave: rid for clave, rid in referencias}
    return CacheResolucion(
        sucursal_por_texto=sucursal_por_texto,
        referencia_por_codigo_proveedor=referencia_por_codigo_proveedor,
    )


def _fila(referencia="REF1", bodega="BA061", desc_bodega="CALI NORTE", existencia=10):
    return (referencia, bodega, desc_bodega, existencia)


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
    return inventario.procesar_fila(fila_raw, **kwargs)


# ---------------------------------------------------------------------------
# 6.1 — mapeo, fila de relleno, existencia y resolución de claves (RED)
# ---------------------------------------------------------------------------


def test_fila_sin_referencia_se_descarta_en_silencio_como_relleno():
    # Reproduce el bloque de 795 filas en blanco al final del sheet real
    # (`Referencia is None`) -- no es un dato inválido, es la cola vacía de
    # un `.xlsx` exportado con fórmulas de más filas de las que tiene datos.
    fila_staging, errores = _procesar(_fila(referencia=None))

    assert fila_staging is None
    assert errores == []


def test_fila_aplicable_conserva_existencia_en_el_payload():
    fila_staging, errores = _procesar(_fila(existencia=25))

    assert errores == []
    assert Decimal(fila_staging.payload["existencia"]) == Decimal("25")


def test_existencia_ausente_se_trata_como_cero_no_como_error():
    fila_staging, errores = _procesar(_fila(existencia=None))

    assert errores == []
    assert Decimal(fila_staging.payload["existencia"]) == Decimal("0")


def test_existencia_no_numerica_emite_error_y_no_genera_staging():
    fila_staging, errores = _procesar(_fila(existencia="N/D"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == inventario.CODIGO_EXISTENCIA_INVALIDA


def test_sucursal_no_resuelta_genera_staging_con_null_y_carga_error():
    fila_staging, errores = _procesar(_fila(desc_bodega="SUCURSAL INEXISTENTE", bodega=""))

    assert fila_staging is not None
    assert fila_staging.sucursal_id is None
    assert fila_staging.referencia_id == REFERENCIA_ID
    assert len(errores) == 1
    assert errores[0].codigo_error == "SUCURSAL_NO_ENCONTRADA"


def test_referencia_no_resuelta_genera_staging_con_null_y_carga_error():
    fila_staging, errores = _procesar(_fila(referencia="NO-EXISTE"))

    assert fila_staging is not None
    assert fila_staging.referencia_id is None
    assert fila_staging.sucursal_id == SUCURSAL_ID
    assert len(errores) == 1
    assert errores[0].codigo_error == "REFERENCIA_NO_ENCONTRADA"


def test_una_fila_no_resuelta_no_aborta_el_resto_del_lote():
    mala, errores_mala = _procesar(_fila(referencia="NO-EXISTE"))
    buena, errores_buena = _procesar(_fila())

    assert mala is not None and errores_mala
    assert buena is not None and not errores_buena


def test_desc_bodega_vacio_usa_bodega_como_fallback():
    cache = _cache(
        sucursales=[("BA061", SUCURSAL_ID)],
        referencias=[(("REF1", PROVEEDOR_ID), REFERENCIA_ID)],
    )
    fila_staging, errores = _procesar(_fila(desc_bodega="", bodega="BA061"), cache=cache)

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_columnas_esperadas_mapean_por_nombre_via_columnas_modulo():
    encabezado = ("Referencia", "Bodega", "Desc.bodega", "Existencia")
    mapa = columnas.construir_mapa_columnas(encabezado, inventario.COLUMNAS_ESPERADAS)

    esperado = dict(zip(inventario.COLUMNAS_ESPERADAS, range(len(inventario.COLUMNAS_ESPERADAS))))
    assert mapa == esperado


# ---------------------------------------------------------------------------
# 6.1 — consolidación bodega-principal (T13) + upsert REPLACE-not-sum (RED)
# ---------------------------------------------------------------------------


def _fila_staging(sucursal_id, referencia_id, existencia, fila=1, lote=1):
    return CargaFilaStaging(
        carga_id=CARGA_ID,
        fila=fila,
        lote=lote,
        payload={"existencia": str(existencia)},
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )


def test_consolidar_existencias_suma_una_bodega_secundaria_en_la_principal():
    # BA066 (secundaria) y BA061 (principal) ya resolvieron, vía el cache de
    # ADR-8, a la MISMA `sucursal_id` -- este módulo no vuelve a mirar el
    # código de bodega, solo suma por la clave ya resuelta (design "A
    # secondary bodega's stock rolls into the principal").
    filas = [
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 30, fila=1),  # BA066
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 12, fila=2),  # BA061
    ]

    consolidado = inventario.consolidar_existencias(filas)

    assert consolidado[(SUCURSAL_ID, REFERENCIA_ID)] == Decimal("42")


def test_consolidar_existencias_mantiene_sucursales_distintas_separadas():
    filas = [
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 10, fila=1),
        _fila_staging(SUCURSAL_ID_2, REFERENCIA_ID, 5, fila=2),
    ]

    consolidado = inventario.consolidar_existencias(filas)

    assert consolidado[(SUCURSAL_ID, REFERENCIA_ID)] == Decimal("10")
    assert consolidado[(SUCURSAL_ID_2, REFERENCIA_ID)] == Decimal("5")


def test_consolidar_existencias_excluye_filas_sin_clave_resuelta():
    filas = [
        _fila_staging(None, REFERENCIA_ID, 10),
        _fila_staging(SUCURSAL_ID, None, 10, fila=2),
    ]

    assert inventario.consolidar_existencias(filas) == {}


def test_construir_statement_upsert_setea_existencias_a_excluded_nunca_suma():
    consolidado = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("42")}

    stmt = inventario.construir_statement_upsert(consolidado, date(2026, 9, 15), CARGA_ID)

    set_clause = stmt._post_values_clause.update_values_to_set
    valores_set = {
        (col if isinstance(col, str) else col.name): expr for col, expr in set_clause
    }
    assert "existencias" in valores_set
    columna_referenciada = valores_set["existencias"]
    assert columna_referenciada.table.name == "excluded"
    assert columna_referenciada.name == "existencias"


def test_construir_statement_upsert_retorna_none_sin_consolidado():
    assert inventario.construir_statement_upsert({}, date(2026, 9, 15), CARGA_ID) is None


async def test_aplicar_ejecuta_una_sola_sentencia_set_based():
    consolidado = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("42")}
    session = FakeAsyncSession(execute_queue=[[]])

    await inventario.aplicar(session, consolidado, date(2026, 9, 15), CARGA_ID)

    assert len(session.executed_statements) == 1


async def test_aplicar_no_ejecuta_nada_sin_consolidado():
    session = FakeAsyncSession(execute_queue=[])

    await inventario.aplicar(session, {}, date(2026, 9, 15), CARGA_ID)

    assert session.executed_statements == []


async def test_una_recarga_del_mismo_fecha_corte_reemplaza_no_acumula():
    # spec "A same-fecha_corte reload replaces, not accumulates".
    consolidado_original = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("42")}
    consolidado_corregido = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("50")}
    session = FakeAsyncSession(execute_queue=[[]])

    await inventario.aplicar(session, consolidado_corregido, date(2026, 9, 15), CARGA_ID)

    insert_values = session.executed_statements[0].compile().construct_params()
    assert Decimal("50") in insert_values.values()
    assert Decimal("42") not in insert_values.values()
    assert Decimal(str(consolidado_original[(SUCURSAL_ID, REFERENCIA_ID)])) == Decimal("42")


# ---------------------------------------------------------------------------
# 6.1 — E-CARGA-021, rechazo de `fecha_corte` fuera de la ventana de 90 días
# (ADR-3: la ventana se ancla a la `fecha_corte` MÁXIMA ya existente, nunca
# a `now()`; design "An INVENTARIO load whose declared fecha_corte is
# already outside the window is rejected at validation")
# ---------------------------------------------------------------------------


def test_sin_snapshot_previo_nunca_rechaza():
    # Primer load de la vida del sistema: no hay ventana contra la cual
    # comparar -- esta fecha_corte SE CONVERTIRÁ en la máxima.
    assert not inventario.fecha_corte_fuera_de_ventana(date(2026, 9, 15), None, dias_retencion=90)


def test_fecha_corte_dentro_de_la_ventana_no_rechaza():
    maxima = date(2026, 9, 15)
    declarada = date(2026, 7, 1)  # 76 días antes -- dentro de la ventana de 90.

    assert not inventario.fecha_corte_fuera_de_ventana(declarada, maxima, dias_retencion=90)


def test_fecha_corte_justo_en_el_limite_no_rechaza():
    maxima = date(2026, 9, 15)
    limite = date(2026, 6, 17)  # exactamente 90 días antes de la máxima.

    assert not inventario.fecha_corte_fuera_de_ventana(limite, maxima, dias_retencion=90)


def test_fecha_corte_fuera_de_la_ventana_rechaza():
    maxima = date(2026, 9, 15)
    declarada = date(2025, 1, 1)  # muy anterior a los 90 días.

    assert inventario.fecha_corte_fuera_de_ventana(declarada, maxima, dias_retencion=90)


def test_fecha_corte_usa_default_de_settings_si_no_se_pasa_dias_retencion(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MOTORED_RETENCION_DIAS", 90)
    maxima = date(2026, 9, 15)
    declarada = date(2025, 1, 1)

    assert inventario.fecha_corte_fuera_de_ventana(declarada, maxima)
