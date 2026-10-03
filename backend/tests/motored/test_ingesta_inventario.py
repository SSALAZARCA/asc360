"""
Fase 2 "Ingesta", Phase 6 "INVENTARIO Transform" (sdd/motored-pedidos-ingesta,
task 6.1) — `services/ingesta/inventario.py` (design ADR-3/ADR-8/ADR-9, spec
"INVENTARIO bodega-principal consolidation and 90-day retention").

No live Postgres: same `FakeAsyncSession` convention as
`test_ingesta_ventas.py`. Consolidation and the REPLACE-not-sum upsert are
asserted at the SQL-construction level, same as VENTAS's ADR-4 tests.

Column names (`Referencia`, `Bodega`, `Desc.bodega`, `Existencia`, `Costo prom. uni.`) and the
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

import pytest

from tests.motored.conftest import FakeAsyncSession
from tests.motored.sql_upsert import upsert_set_clause

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import columnas, inventario, numeros
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
    "Costo prom. uni.": 4,
}


def _cache(sucursales=(), referencias=()) -> CacheResolucion:
    sucursal_por_texto = {texto: sid for texto, sid in sucursales}
    referencia_por_codigo = {codigo: (rid, prov) for (codigo, prov), rid in referencias}
    return CacheResolucion(
        sucursal_por_texto=sucursal_por_texto,
        referencia_por_codigo=referencia_por_codigo,
    )


def _fila(referencia="REF1", bodega="BA061", desc_bodega="CALI NORTE", existencia=10, costo=1500):
    return (referencia, bodega, desc_bodega, existencia, costo)


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


@pytest.mark.parametrize("valor", [None, "", "#N/A", "#NAME?", "#VALUE!"])
def test_existencia_vacia_o_con_error_de_excel_es_error_de_fila_no_un_cero(valor):
    fila_staging, errores = _procesar(_fila(existencia=valor))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == numeros.CODIGO_VALOR_FALTANTE
    assert errores[0].columna == "Existencia" and errores[0].fila == 2
    assert "Existencia" in errores[0].mensaje and "corregí el archivo" in errores[0].mensaje


def test_existencia_cero_real_sigue_siendo_valida():
    fila_staging, errores = _procesar(_fila(existencia=0))

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


def test_codigo_resuelve_aunque_el_nombre_sea_desconocido():
    cache = _cache(
        sucursales=[("BA911", SUCURSAL_ID)],
        referencias=[(("REF1", PROVEEDOR_ID), REFERENCIA_ID)],
    )
    fila_staging, errores = _procesar(_fila(desc_bodega="CRA 1RA 2", bodega="BA911"), cache=cache)

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_codigo_gana_sobre_el_nombre_si_apuntan_a_sucursales_distintas():
    cache = _cache(
        sucursales=[("CALI NORTE", SUCURSAL_ID), ("BA911", SUCURSAL_ID_2)],
        referencias=[(("REF1", PROVEEDOR_ID), REFERENCIA_ID)],
    )
    fila_staging, errores = _procesar(_fila(desc_bodega="CALI NORTE", bodega="BA911"), cache=cache)

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID_2


def test_codigo_desconocido_cae_al_nombre():
    fila_staging, errores = _procesar(_fila(desc_bodega="CALI NORTE", bodega="ZZ999"))

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_codigo_vacio_con_nombre_conocido_resuelve():
    fila_staging, errores = _procesar(_fila(desc_bodega="CALI NORTE", bodega=""))

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_alias_del_nombre_sigue_funcionando_con_codigo_desconocido():
    # Los alias ya viven en `sucursal_por_texto` (misma clave normalizada).
    cache = _cache(
        sucursales=[("CRA 1RA 2", SUCURSAL_ID_2)],
        referencias=[(("REF1", PROVEEDOR_ID), REFERENCIA_ID)],
    )
    fila_staging, errores = _procesar(_fila(desc_bodega="CRA 1RA 2", bodega="ZZ999"), cache=cache)

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID_2


def test_nombre_y_codigo_desconocidos_generan_error_con_nombre_como_valor_y_codigo_en_mensaje():
    fila_staging, errores = _procesar(_fila(desc_bodega="CRA 1RA 2", bodega="ZZ999"))

    assert fila_staging.sucursal_id is None
    assert len(errores) == 1
    assert errores[0].codigo_error == "SUCURSAL_NO_ENCONTRADA"
    assert errores[0].valor == "CRA 1RA 2"
    assert "ZZ999" in errores[0].mensaje


def test_columnas_esperadas_mapean_por_nombre_via_columnas_modulo():
    encabezado = ("Referencia", "Bodega", "Desc.bodega", "Existencia", "Costo prom. uni.")
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

    valores_set = upsert_set_clause(stmt)
    assert "existencias" in valores_set
    assert valores_set["existencias"] == "excluded.existencias"


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


# ---------------------------------------------------------------------------
# INVENTARIO per-bodega detail (`inventario_detalle`): required cost column,
# row-level cost parsing that NEVER rejects the row, staging payload and the
# apply-time detail statements. `inventario_snapshot` behaviour above must not
# change.
# ---------------------------------------------------------------------------


def test_columnas_esperadas_incluye_el_costo_promedio_al_final():
    assert inventario.COLUMNAS_ESPERADAS == (
        "Referencia", "Bodega", "Desc.bodega", "Existencia", "Costo prom. uni."
    )


def test_payload_lleva_bodega_cruda_y_costo_sin_tocar_la_existencia():
    fila_staging, errores = _procesar(_fila(bodega="  BA066 ", existencia=25, costo=1500))

    assert errores == []
    assert Decimal(fila_staging.payload["existencia"]) == Decimal("25")
    assert fila_staging.payload["bodega"] == "BA066"
    assert Decimal(fila_staging.payload["costo"]) == Decimal("1500")


@pytest.mark.parametrize(
    "crudo, esperado",
    [
        ("$ 1.234.567", Decimal("1234567")),
        ("$1.234,50", Decimal("1234.50")),
        (1500.5, Decimal("1500.5")),
        (-500, Decimal("-500")),  # negativo: se guarda tal cual, el lector lo excluye
        (0, Decimal("0")),
    ],
)
def test_costo_se_interpreta_con_el_formato_de_dinero_colombiano(crudo, esperado):
    fila_staging, errores = _procesar(_fila(costo=crudo))

    assert errores == []
    assert Decimal(fila_staging.payload["costo"]) == esperado


@pytest.mark.parametrize("crudo", [None, "", "   ", "#N/A", "abc", "1.234", 10 ** 15])
def test_costo_vacio_o_invalido_nunca_rechaza_la_fila_ni_toca_la_existencia(crudo):
    fila_staging, errores = _procesar(_fila(existencia=7, costo=crudo))

    assert errores == []
    assert fila_staging is not None
    assert fila_staging.payload["costo"] is None
    assert Decimal(fila_staging.payload["existencia"]) == Decimal("7")
    assert fila_staging.sucursal_id == SUCURSAL_ID
    assert fila_staging.referencia_id == REFERENCIA_ID


def test_fila_sin_la_celda_de_costo_en_absoluto_igual_llega_al_staging():
    # Fila mas corta que el encabezado (la celda ni existe).
    fila_staging, errores = _procesar(("REF1", "BA061", "CALI NORTE", 10))

    assert errores == []
    assert fila_staging.payload["costo"] is None


def test_costo_en_blanco_deja_las_existencias_consolidadas_identicas_a_las_de_antes():
    con_costo, _ = _procesar(_fila(existencia=10, costo=1500))
    sin_costo, _ = _procesar(_fila(existencia=10, costo=None))
    legado = CargaFilaStaging(
        carga_id=CARGA_ID, fila=2, lote=1, payload={"existencia": "10"},
        sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
    )

    esperado = {(SUCURSAL_ID, REFERENCIA_ID): Decimal("10")}
    assert inventario.consolidar_existencias([sin_costo]) == esperado
    assert inventario.consolidar_existencias([con_costo]) == esperado
    assert inventario.consolidar_existencias([legado]) == esperado


def test_bodega_se_trunca_a_20_caracteres_y_vacia_queda_como_texto_vacio():
    larga, _ = _procesar(_fila(bodega="B" * 30))
    vacia, _ = _procesar(_fila(bodega=None))

    assert larga.payload["bodega"] == "B" * 20
    assert vacia.payload["bodega"] == ""


def _staging_detalle(sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID, bodega="BA061",
                     existencia="10", costo="1500", fila=1):
    return CargaFilaStaging(
        carga_id=CARGA_ID, fila=fila, lote=1,
        payload={"existencia": existencia, "bodega": bodega, "costo": costo},
        sucursal_id=sucursal_id, referencia_id=referencia_id,
    )


def test_construir_detalle_guarda_una_fila_por_bodega_aunque_consoliden_en_la_misma_sucursal():
    filas = [
        _staging_detalle(bodega="BA061", existencia="12", costo="1500", fila=1),
        _staging_detalle(bodega="BA066", existencia="30", costo=None, fila=2),
    ]

    detalle = inventario.construir_detalle(filas, date(2026, 9, 15), CARGA_ID)

    assert [(d["bodega"], d["existencia"], d["costo_unitario"]) for d in detalle] == [
        ("BA061", Decimal("12"), Decimal("1500")),
        ("BA066", Decimal("30"), None),
    ]
    assert all(
        d["carga_id"] == CARGA_ID and d["fecha_corte"] == date(2026, 9, 15)
        and d["sucursal_id"] == SUCURSAL_ID and d["referencia_id"] == REFERENCIA_ID
        for d in detalle
    )


def test_construir_detalle_excluye_lo_que_el_snapshot_tambien_excluye():
    filas = [
        _staging_detalle(sucursal_id=None),
        _staging_detalle(referencia_id=None, fila=2),
        CargaFilaStaging(  # staged por una version anterior: sin bodega ni costo
            carga_id=CARGA_ID, fila=3, lote=1, payload={"existencia": "5"},
            sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
        ),
    ]

    assert inventario.construir_detalle(filas, date(2026, 9, 15), CARGA_ID) == []


async def test_aplicar_detalle_borra_por_fecha_corte_y_sucursal_y_luego_inserta():
    session = FakeAsyncSession(execute_queue=[[], []])

    await inventario.aplicar_detalle(
        session, [_staging_detalle(), _staging_detalle(fila=2)], date(2026, 9, 15), CARGA_ID
    )

    borrado, insercion = session.executed_statements
    assert borrado.is_delete and borrado.table.name == "inventario_detalle"
    assert insercion.is_insert and insercion.table.name == "inventario_detalle"


async def test_aplicar_detalle_inserta_en_lotes():
    filas = [_staging_detalle(fila=i) for i in range(inventario.TAMANO_LOTE_DETALLE * 2 + 1)]
    session = FakeAsyncSession(execute_queue=[[]] * 4)

    await inventario.aplicar_detalle(session, filas, date(2026, 9, 15), CARGA_ID)

    assert len(session.executed_statements) == 1 + 3  # delete + 3 lotes


async def test_aplicar_detalle_sin_filas_resueltas_no_ejecuta_nada():
    session = FakeAsyncSession()

    await inventario.aplicar_detalle(
        session, [_staging_detalle(sucursal_id=None)], date(2026, 9, 15), CARGA_ID
    )

    assert session.executed_statements == []
