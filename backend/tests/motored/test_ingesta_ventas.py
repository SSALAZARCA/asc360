"""
Fase 2 "Ingesta", Phase 4 "VENTAS Transform" (sdd/motored-pedidos-ingesta,
tasks 4.1/4.2) — `services/ingesta/ventas.py` (design ADR-2/ADR-4/ADR-8,
spec "VENTAS net-signed aggregation preserving Módulo origin").

No live Postgres: same `FakeAsyncSession` convention as the rest of
`tests/motored/` (see `test_ingesta_resolucion.py`). `agregar_unidades`/
`construir_statement_upsert` are pure functions exercised directly --
REPLACE-not-sum (ADR-4) is asserted at the SQL-construction level (the SET
clause is a literal `EXCLUDED.unidades`, never an addition), which is what
makes idempotency (T17) and the overlapping-month case provable without a
real database.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import columnas, ventas
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()

_MAPA_COLUMNAS = {
    "Estado": 0,
    "Módulo": 1,
    "Fecha": 2,
    "Cantidad inv.": 3,
    "Tipo inventario": 4,
    "Desc.bodega": 5,
    "Bodega": 6,
    "Referencia": 7,
}

# 2026-09-15 as an Excel serial (days since 1899-12-30).
_SERIAL_2026_09_15 = 46280


def _cache(sucursales=(), referencias=()) -> CacheResolucion:
    sucursal_por_texto = {texto: sid for texto, sid in sucursales}
    referencia_por_codigo_proveedor = {clave: rid for clave, rid in referencias}
    return CacheResolucion(
        sucursal_por_texto=sucursal_por_texto,
        referencia_por_codigo_proveedor=referencia_por_codigo_proveedor,
    )


def _fila(
    estado="Aprobada",
    modulo="MOSTRADOR",
    fecha=_SERIAL_2026_09_15,
    cantidad=10,
    tipo_inventario="0002 - REPUESTOS",
    desc_bodega="CALI NORTE",
    bodega="BA061",
    referencia="REF1",
):
    return (estado, modulo, fecha, cantidad, tipo_inventario, desc_bodega, bodega, referencia)


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
        tipos_inventario_incluidos=["0002 - REPUESTOS"],
    )
    kwargs.update(overrides)
    return ventas.procesar_fila(fila_raw, **kwargs)


# ---------------------------------------------------------------------------
# 4.1 — filtros de negocio y mapeo (RED)
# ---------------------------------------------------------------------------


def test_estado_distinto_de_aprobada_se_descarta_en_silencio():
    fila_staging, errores = _procesar(_fila(estado="Pendiente"))

    assert fila_staging is None
    assert errores == []


def test_tipo_inventario_no_incluido_se_descarta_en_silencio():
    fila_staging, errores = _procesar(
        _fila(tipo_inventario="0005 - ACCESORIOS"),
        tipos_inventario_incluidos=["0002 - REPUESTOS"],
    )

    assert fila_staging is None
    assert errores == []


def test_fila_aplicable_conserva_modulo_como_origen():
    fila_staging, errores = _procesar(_fila(modulo="TALLER"))

    assert errores == []
    assert fila_staging.payload["origen"] == "TALLER"


def test_anio_mes_se_derivan_de_fecha_no_de_una_etiqueta():
    fila_staging, _ = _procesar(_fila(fecha=_SERIAL_2026_09_15))

    assert fila_staging.payload["anio"] == 2026
    assert fila_staging.payload["mes"] == 9


def test_cantidad_negativa_se_conserva_con_signo_sin_clasificar_devolucion():
    fila_staging, _ = _procesar(_fila(cantidad=-2))

    assert Decimal(fila_staging.payload["cantidad"]) == Decimal("-2")


def test_cantidad_no_numerica_emite_error_y_no_genera_staging():
    # decimal.InvalidOperation nunca debe propagar crudo -- mismo contrato
    # de tolerancia por-fila que una Fecha implausible.
    fila_staging, errores = _procesar(_fila(cantidad="N/D"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == ventas.CODIGO_CANTIDAD_INVALIDA


def test_cantidad_ausente_se_trata_como_cero_no_como_error():
    fila_staging, errores = _procesar(_fila(cantidad=None))

    assert errores == []
    assert Decimal(fila_staging.payload["cantidad"]) == Decimal("0")


def test_fecha_implausible_emite_error_y_no_genera_staging():
    fila_staging, errores = _procesar(_fila(fecha=1))  # serial 1 -> año 1900

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == ventas.CODIGO_FECHA_INVALIDA


def test_fecha_como_datetime_real_se_interpreta_igual_que_un_serial():
    # Caso REAL, no hipotético: openpyxl con data_only=True entrega un
    # `datetime.datetime` cuando la celda tiene formato de fecha -- así
    # llega en el workbook real de producción (confirmado contra
    # "PLANTILLA PEDIDO SEPTIEMBRE.xlsx", hoja "BD ventas ultimos 6
    # meses"). Si esto no se soportara, TODA fila de un archivo real caería
    # en FECHA_INVALIDA.
    fila_staging, errores = _procesar(_fila(fecha=datetime(2026, 9, 15)))

    assert errores == []
    assert fila_staging.payload["anio"] == 2026
    assert fila_staging.payload["mes"] == 9


def test_fecha_como_date_real_se_interpreta_igual_que_un_datetime():
    fila_staging, errores = _procesar(_fila(fecha=date(2026, 9, 15)))

    assert errores == []
    assert fila_staging.payload["anio"] == 2026
    assert fila_staging.payload["mes"] == 9


def test_fecha_datetime_implausible_tambien_emite_error():
    fila_staging, errores = _procesar(_fila(fecha=datetime(1900, 1, 1)))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == ventas.CODIGO_FECHA_INVALIDA


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
    # spec "Per-row tolerance for movement loads": una fila mala no bloquea el resto.
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
    encabezado = (
        "Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
        "Desc.bodega", "Bodega", "Referencia",
    )
    mapa = columnas.construir_mapa_columnas(encabezado, ventas.COLUMNAS_ESPERADAS)

    assert mapa == dict(zip(ventas.COLUMNAS_ESPERADAS, range(len(ventas.COLUMNAS_ESPERADAS))))


# ---------------------------------------------------------------------------
# 4.2 — agregación neta-firmada + upsert REPLACE-not-sum (RED)
# ---------------------------------------------------------------------------


def _fila_staging(sucursal_id, referencia_id, anio, mes, origen, cantidad, fila=1, lote=1):
    return CargaFilaStaging(
        carga_id=CARGA_ID,
        fila=fila,
        lote=lote,
        payload={"anio": anio, "mes": mes, "origen": origen, "cantidad": str(cantidad)},
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )


def test_agregar_unidades_suma_signed_sin_clasificar_devolucion():
    # 10 unidades de venta normal + 1 nota de crédito de -2 -> 8 neto (evidencia del proposal).
    filas = [
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR", 10),
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR", -2, fila=2),
    ]

    totales = ventas.agregar_unidades(filas)

    assert totales[(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR")] == Decimal("8")


def test_agregar_unidades_mantiene_modulo_como_dimension_separada():
    filas = [
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR", 5),
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "TALLER", 3, fila=2),
    ]

    totales = ventas.agregar_unidades(filas)

    assert totales[(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR")] == Decimal("5")
    assert totales[(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "TALLER")] == Decimal("3")
    assert sum(totales.values()) == Decimal("8")


def test_agregar_unidades_excluye_filas_sin_clave_resuelta():
    filas = [
        _fila_staging(None, REFERENCIA_ID, 2026, 9, "MOSTRADOR", 10),
        _fila_staging(SUCURSAL_ID, None, 2026, 9, "MOSTRADOR", 10, fila=2),
    ]

    totales = ventas.agregar_unidades(filas)

    assert totales == {}


def test_construir_statement_upsert_setea_unidades_a_excluded_nunca_suma():
    totales = {(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR"): Decimal("8")}

    stmt = ventas.construir_statement_upsert(totales, CARGA_ID)

    set_clause = stmt._post_values_clause.update_values_to_set
    valores_set = {
        (col if isinstance(col, str) else col.name): expr for col, expr in set_clause
    }
    assert "unidades" in valores_set
    columna_referenciada = valores_set["unidades"]
    # debe ser LITERALMENTE la columna `excluded.unidades`, nunca una expresión
    # aritmética (`VentaMensual.unidades + excluded.unidades`) -- eso es lo
    # que hace a T17 y al caso "meses solapados" ciertos por construcción.
    assert columna_referenciada.table.name == "excluded"
    assert columna_referenciada.name == "unidades"


def test_construir_statement_upsert_retorna_none_sin_totales():
    assert ventas.construir_statement_upsert({}, CARGA_ID) is None


async def test_aplicar_dos_veces_produce_resultado_identico_t17():
    filas = [_fila_staging(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR", 10)]
    totales_primera = ventas.agregar_unidades(filas)
    totales_segunda = ventas.agregar_unidades(filas)

    assert totales_primera == totales_segunda

    session = FakeAsyncSession(execute_queue=[[], []])
    await ventas.aplicar(session, totales_primera, CARGA_ID)
    await ventas.aplicar(session, totales_segunda, CARGA_ID)

    assert len(session.executed_statements) == 2


async def test_meses_solapados_la_segunda_carga_reemplaza_no_acumula():
    # Carga A: setiembre con 10 unidades. Carga B (nueva subida) también
    # cubre setiembre, con 3 unidades para la MISMA clave -- el resultado de
    # aplicar B debe reflejar SOLO los datos de B (spec "Overlapping-month
    # loads replace, not accumulate"), nunca 10+3.
    filas_carga_a = [_fila_staging(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR", 10)]
    filas_carga_b = [_fila_staging(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR", 3)]

    totales_a = ventas.agregar_unidades(filas_carga_a)
    totales_b = ventas.agregar_unidades(filas_carga_b)

    # `agregar_unidades`/`construir_statement_upsert` de la carga B no reciben
    # ni consultan nada de la carga A -- el upsert sólo toca las claves
    # presentes en SU propio staging (ADR-4/ADR-2b), nunca 10+3.
    assert totales_a == {(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR"): Decimal("10")}
    assert totales_b == {(SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR"): Decimal("3")}

    session = FakeAsyncSession(execute_queue=[[]])
    await ventas.aplicar(session, totales_b, CARGA_ID)

    insert_values = session.executed_statements[0].compile().construct_params()
    assert Decimal("3") in insert_values.values()
    assert Decimal("10") not in insert_values.values()
