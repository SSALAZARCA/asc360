"""
Fase 2 "Ingesta", Phase 7 "BACKORDER + DEMANDA_PERDIDA Transform" (PR7)
(sdd/motored-pedidos-ingesta, task 7.1) — `services/ingesta/backorder.py`
(design ADR-8/ADR-9, spec "BACKORDER pending-quantity filter").

No live Postgres: same `FakeAsyncSession` convention as
`test_ingesta_ventas.py`/`test_ingesta_inventario.py`. Upsert semantics are
asserted at the SQL-construction level.

Columns (`SIC`, `Sucursal`, `Número del pedido`, `Estado del pedido`,
`Referencia Parte`, `Cantidad Pendiente`) were verified against the real
production workbook (`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`, hoja "backorder"):
2 430 rows, exact header casing confirmed with openpyxl (`data_only=True`).
814 rows carry `Estado del pedido = 'BACKORDER'`; the remaining 1 615 are a
block of fully-blank trailing rows (same "Excel formula remnants past the
real data" shape already found in Phase 6's INVENTARIO sheet) -- here they
need NO special-case discard, unlike INVENTARIO's blank-`Referencia` fix:
a blank `Estado del pedido` already fails `estados_backorder_vigentes`
membership and a blank `Cantidad Pendiente` already fails `> 0`, so both
business filters exclude them naturally, the same way VENTAS's
`_pasa_filtros_negocio` excludes non-`Aprobada` rows before ever touching
key resolution.

`SIC` resolves via `resolucion.resolver_sucursal_por_sic` (a NEW cache
lookup this phase adds, see `test_ingesta_resolucion.py`) -- BACKORDER is
the only file type keyed to the proveedor's own SIC code rather than a
sucursal name/bodega code. `Sucursal` is the fallback when SIC doesn't
resolve (verificación cruzada, spec §5.3), mirroring the primary+fallback
shape VENTAS/INVENTARIO already use for `Desc.bodega`/`Bodega`.
"""
import uuid
from datetime import date
from decimal import Decimal

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import backorder, columnas
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()

_MAPA_COLUMNAS = {
    "SIC": 0,
    "Sucursal": 1,
    "Número del pedido": 2,
    "Estado del pedido": 3,
    "Referencia Parte": 4,
    "Cantidad Pendiente": 5,
}


def _cache(sucursales_por_sic=(), sucursales_por_texto=(), referencias=()):
    return CacheResolucion(
        sucursal_por_texto={texto: sid for texto, sid in sucursales_por_texto},
        referencia_por_codigo_proveedor={clave: rid for clave, rid in referencias},
        sucursal_por_sic={sic: sid for sic, sid in sucursales_por_sic},
    )


def _fila(
    sic="1779",
    sucursal="MR SOACHA EL DORADO",
    numero_pedido=74,
    estado="BACKORDER",
    referencia="REF1",
    cantidad_pendiente=48,
):
    return (sic, sucursal, numero_pedido, estado, referencia, cantidad_pendiente)


def _cache_resuelta():
    return _cache(
        sucursales_por_sic=[("1779", SUCURSAL_ID)],
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
        estados_backorder_vigentes=["BACKORDER"],
    )
    kwargs.update(overrides)
    return backorder.procesar_fila(fila_raw, **kwargs)


# ---------------------------------------------------------------------------
# 7.1 — filtros de negocio (estado + cantidad_pendiente > 0) y mapeo (RED)
# ---------------------------------------------------------------------------


def test_estado_no_vigente_se_descarta_en_silencio():
    fila_staging, errores = _procesar(_fila(estado="CANCELADO"))

    assert fila_staging is None
    assert errores == []


def test_estado_ausente_se_descarta_en_silencio_como_fila_de_relleno():
    # Reproduce el bloque de 1 615 filas en blanco al final del sheet real.
    fila_staging, errores = _procesar(_fila(estado=None, cantidad_pendiente=None))

    assert fila_staging is None
    assert errores == []


def test_cantidad_pendiente_cero_se_descarta_en_silencio():
    fila_staging, errores = _procesar(_fila(cantidad_pendiente=0))

    assert fila_staging is None
    assert errores == []


def test_cantidad_pendiente_negativa_se_descarta_en_silencio():
    fila_staging, errores = _procesar(_fila(cantidad_pendiente=-3))

    assert fila_staging is None
    assert errores == []


def test_cantidad_pendiente_ausente_se_trata_como_cero_y_se_descarta():
    fila_staging, errores = _procesar(_fila(cantidad_pendiente=None))

    assert fila_staging is None
    assert errores == []


def test_cantidad_pendiente_no_numerica_emite_error_y_no_genera_staging():
    fila_staging, errores = _procesar(_fila(cantidad_pendiente="N/D"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == backorder.CODIGO_CANTIDAD_PENDIENTE_INVALIDA


def test_fila_aplicable_conserva_cantidad_pendiente_y_numero_pedido_en_el_payload():
    fila_staging, errores = _procesar(_fila(cantidad_pendiente=48, numero_pedido=74))

    assert errores == []
    assert Decimal(fila_staging.payload["cantidad_pendiente"]) == Decimal("48")
    assert fila_staging.payload["numero_pedido"] == "74"


def test_sucursal_resuelve_por_sic_primero():
    fila_staging, errores = _procesar(_fila(sic="1779", sucursal="TEXTO QUE NO MATCHEA"))

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_sucursal_cae_a_texto_cuando_sic_no_resuelve():
    cache = _cache(
        sucursales_por_texto=[("SOACHA EL DORADO", SUCURSAL_ID)],
        referencias=[(("REF1", PROVEEDOR_ID), REFERENCIA_ID)],
    )
    fila_staging, errores = _procesar(
        _fila(sic="9999", sucursal="MR Soacha El Dorado"), cache=cache
    )

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_sucursal_no_resuelta_por_ningun_camino_genera_staging_con_null_y_carga_error():
    fila_staging, errores = _procesar(_fila(sic="9999", sucursal="NO EXISTE"))

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


def test_columnas_esperadas_mapean_por_nombre_via_columnas_modulo():
    encabezado = (
        "SIC", "Sucursal", "Número del pedido", "Estado del pedido",
        "Referencia Parte", "Cantidad Pendiente",
    )
    mapa = columnas.construir_mapa_columnas(encabezado, backorder.COLUMNAS_ESPERADAS)

    esperado = dict(zip(backorder.COLUMNAS_ESPERADAS, range(len(backorder.COLUMNAS_ESPERADAS))))
    assert mapa == esperado


# ---------------------------------------------------------------------------
# 7.1 — consolidación por clave natural + upsert REPLACE-not-sum (RED)
# ---------------------------------------------------------------------------


def _fila_staging(sucursal_id, referencia_id, cantidad_pendiente, numero_pedido, fila=1, lote=1):
    return CargaFilaStaging(
        carga_id=CARGA_ID,
        fila=fila,
        lote=lote,
        payload={"cantidad_pendiente": str(cantidad_pendiente), "numero_pedido": numero_pedido},
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )


def test_consolidar_lineas_mantiene_pedidos_distintos_separados():
    filas = [
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 48, "74", fila=1),
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 1, "80", fila=2),
    ]

    consolidado = backorder.consolidar_lineas(filas)

    assert consolidado[(SUCURSAL_ID, REFERENCIA_ID, "74")] == Decimal("48")
    assert consolidado[(SUCURSAL_ID, REFERENCIA_ID, "80")] == Decimal("1")


def test_consolidar_lineas_excluye_filas_sin_clave_resuelta():
    filas = [
        _fila_staging(None, REFERENCIA_ID, 10, "74"),
        _fila_staging(SUCURSAL_ID, None, 10, "80", fila=2),
    ]

    assert backorder.consolidar_lineas(filas) == {}


def test_construir_statement_upsert_setea_cantidad_pendiente_a_excluded_nunca_suma():
    consolidado = {(SUCURSAL_ID, REFERENCIA_ID, "74"): Decimal("48")}

    stmt = backorder.construir_statement_upsert(consolidado, date(2026, 9, 15), CARGA_ID)

    set_clause = stmt._post_values_clause.update_values_to_set
    valores_set = {
        (col if isinstance(col, str) else col.name): expr for col, expr in set_clause
    }
    assert "cantidad_pendiente" in valores_set
    columna_referenciada = valores_set["cantidad_pendiente"]
    assert columna_referenciada.table.name == "excluded"
    assert columna_referenciada.name == "cantidad_pendiente"


def test_construir_statement_upsert_retorna_none_sin_consolidado():
    assert backorder.construir_statement_upsert({}, date(2026, 9, 15), CARGA_ID) is None


async def test_aplicar_ejecuta_una_sola_sentencia_set_based():
    consolidado = {(SUCURSAL_ID, REFERENCIA_ID, "74"): Decimal("48")}
    session = FakeAsyncSession(execute_queue=[[]])

    await backorder.aplicar(session, consolidado, date(2026, 9, 15), CARGA_ID)

    assert len(session.executed_statements) == 1


async def test_aplicar_no_ejecuta_nada_sin_consolidado():
    session = FakeAsyncSession(execute_queue=[])

    await backorder.aplicar(session, {}, date(2026, 9, 15), CARGA_ID)

    assert session.executed_statements == []


async def test_una_recarga_del_mismo_fecha_corte_reemplaza_no_acumula():
    consolidado_corregido = {(SUCURSAL_ID, REFERENCIA_ID, "74"): Decimal("50")}
    session = FakeAsyncSession(execute_queue=[[]])

    await backorder.aplicar(session, consolidado_corregido, date(2026, 9, 15), CARGA_ID)

    insert_values = session.executed_statements[0].compile().construct_params()
    assert Decimal("50") in insert_values.values()


# ---------------------------------------------------------------------------
# Fase 9, task 9.6 (owner decision 2026-09-22) — cross-check "PARCIAL" de
# ADR-9: advertir (nunca rechazar) si alguna `Fecha Creación` es posterior
# al `fecha_corte` declarado. `Fecha Creación` es OPCIONAL (no forma parte
# de `COLUMNAS_ESPERADAS`): su ausencia nunca dispara el chequeo
# "columna obligatoria faltante" del orquestador (Fase 9.4).
# ---------------------------------------------------------------------------

_MAPA_COLUMNAS_CON_FECHA_CREACION = dict(_MAPA_COLUMNAS, **{"Fecha Creación": 6})


def _fila_con_fecha_creacion(fecha_creacion, **overrides):
    base = _fila(**overrides)
    return base + (fecha_creacion,)


def test_fecha_creacion_se_captura_en_el_payload_cuando_la_columna_esta_presente():
    fila_staging, errores = _procesar(
        _fila_con_fecha_creacion(date(2026, 9, 10)),
        mapa_columnas=_MAPA_COLUMNAS_CON_FECHA_CREACION,
    )

    assert errores == []
    assert fila_staging.payload["fecha_creacion"] == "2026-09-10"


def test_fecha_creacion_ausente_de_la_columna_no_rompe_el_procesamiento():
    # `_MAPA_COLUMNAS` (sin "Fecha Creación") es el mapa REAL de un archivo
    # que no trae esa columna opcional -- `procesar_fila` no debe romper ni
    # exigirla.
    fila_staging, errores = _procesar(_fila())

    assert errores == []
    assert "fecha_creacion" not in fila_staging.payload


def test_fecha_creacion_no_interpretable_se_ignora_sin_error():
    fila_staging, errores = _procesar(
        _fila_con_fecha_creacion("no-es-una-fecha"),
        mapa_columnas=_MAPA_COLUMNAS_CON_FECHA_CREACION,
    )

    assert errores == []
    assert "fecha_creacion" not in fila_staging.payload


def test_evaluar_corte_declarado_advierte_si_alguna_fecha_creacion_es_posterior_al_corte():
    filas = [
        CargaFilaStaging(
            carga_id=CARGA_ID, fila=5, lote=1,
            payload={"cantidad_pendiente": "10", "numero_pedido": "1",
                     "fecha_creacion": "2026-09-20"},
            sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        ),
        CargaFilaStaging(
            carga_id=CARGA_ID, fila=6, lote=1,
            payload={"cantidad_pendiente": "5", "numero_pedido": "2",
                     "fecha_creacion": "2026-09-10"},
            sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        ),
    ]

    veredicto = backorder.evaluar_corte_declarado(filas, date(2026, 9, 15))

    assert veredicto.advertencia is True
    assert veredicto.filas_posteriores == (5,)


def test_evaluar_corte_declarado_no_advierte_si_fechas_son_anteriores_o_iguales_al_corte():
    filas = [
        CargaFilaStaging(
            carga_id=CARGA_ID, fila=1, lote=1,
            payload={"cantidad_pendiente": "10", "numero_pedido": "1",
                     "fecha_creacion": "2026-09-15"},
            sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        ),
    ]

    veredicto = backorder.evaluar_corte_declarado(filas, date(2026, 9, 15))

    assert veredicto.advertencia is False
    assert veredicto.filas_posteriores == ()


def test_evaluar_corte_declarado_ignora_filas_sin_fecha_creacion_capturada():
    filas = [
        CargaFilaStaging(
            carga_id=CARGA_ID, fila=1, lote=1,
            payload={"cantidad_pendiente": "10", "numero_pedido": "1"},
            sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        ),
    ]

    veredicto = backorder.evaluar_corte_declarado(filas, date(2026, 9, 15))

    assert veredicto.advertencia is False
    assert veredicto.filas_posteriores == ()
