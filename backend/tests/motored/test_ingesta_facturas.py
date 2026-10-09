"""
Fase 2 "Ingesta", Phase 8 "FACTURAS/INGRESOS + Tránsito" (PR8)
(sdd/motored-pedidos-ingesta, task 8.1) — `services/ingesta/facturas.py`
(design ADR-8/ADR-9, spec "FACTURAS_PEDIDOS Parte column and NC
subtraction").

No live Postgres: same `FakeAsyncSession` convention as
`test_ingesta_backorder.py`. Upsert semantics are asserted at the
SQL-construction level.

Columns confirmed against the real production workbook
(`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`, hoja "facturas pedidos", header at
row 6): `SIIC`, `Sucursal`, `Nota crédito`, `Factura`, `Fecha`,
`Parte Pedida`, `Parte`, `Cantidad`, `Vlr. Total Neto` (22 434 data rows;
10 054 usable, 12 380 fully-blank trailing rows -- the same
Excel-formula-remnant shape Phase 6/7 already found in INVENTARIO/
BACKORDER). `Parte` and `Parte Pedida` differ on 153 of the 10 054 usable
rows -- confirming the spec's "use `Parte`, never `Parte Pedida`" rule is
not a hypothetical edge case here. `Tipo documento` is `'RH'` on every
single usable row this cycle (never literally `'NC'`) -- the real
credit-note signal is the separate `Nota crédito` column having a value,
matching the source spec's own parenthetical ("Nota crédito con valor"),
NOT `Tipo documento`. Zero rows this cycle have a populated `Nota crédito`,
so the NC-subtraction shape could not be verified end-to-end against real
data -- same limitation Phase 7 hit for DEMANDA_PERDIDA's `sucursal`
column, flagged for re-check once a real credit-note load exists.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.motored.conftest import FakeAsyncSession
from tests.motored.sql_upsert import upsert_set_clause

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import columnas, facturas, numeros
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()

_MAPA_COLUMNAS = {
    nombre: idx for idx, nombre in enumerate(facturas.COLUMNAS_ESPERADAS)
}


def _cache(sucursales_por_sic=(), sucursales_por_texto=(), referencias=()):
    return CacheResolucion(
        sucursal_por_texto={texto: sid for texto, sid in sucursales_por_texto},
        referencia_por_codigo={codigo: (rid, prov) for (codigo, prov), rid in referencias},
        sucursal_por_sic={sic: sid for sic, sid in sucursales_por_sic},
    )


def _cache_resuelta():
    return _cache(
        sucursales_por_sic=[("1801", SUCURSAL_ID)],
        referencias=[(("12310-ABW-800TS", PROVEEDOR_ID), REFERENCIA_ID)],
    )


def _fila(
    siic="1801",
    sucursal="MR BUCARAMANGA LA 27",
    nota_credito=None,
    factura="RH194067",
    fecha=date(2026, 7, 15),
    parte="12310-ABW-800TS",
    cantidad=5,
    valor_total_neto=Decimal("275130"),
):
    valores = {
        "SIIC": siic,
        "Sucursal": sucursal,
        "Nota crédito": nota_credito,
        "Factura": factura,
        "Fecha": fecha,
        "Parte": parte,
        "Cantidad": cantidad,
        "Vlr. Total Neto": valor_total_neto,
    }
    return tuple(valores[nombre] for nombre in facturas.COLUMNAS_ESPERADAS)


def _procesar(fila_raw, **overrides):
    kwargs = dict(
        numero_fila=7,
        lote=1,
        mapa_columnas=_MAPA_COLUMNAS,
        cache=_cache_resuelta(),
        carga_id=CARGA_ID,
        proveedor_id=PROVEEDOR_ID,
    )
    kwargs.update(overrides)
    return facturas.procesar_fila(fila_raw, **kwargs)


# ---------------------------------------------------------------------------
# 8.1 — fila de relleno / mapeo por Parte (nunca Parte Pedida) (RED)
# ---------------------------------------------------------------------------


def test_factura_ausente_se_descarta_en_silencio_como_fila_de_relleno():
    # Reproduce el bloque de 12 380 filas en blanco del sheet real.
    fila_staging, errores = _procesar(_fila(factura=None, siic=None, sucursal=None))

    assert fila_staging is None
    assert errores == []


def test_documento_rh_con_formato_invalido_emite_error_tipado():
    fila_staging, errores = _procesar(_fila(factura="CH-70752"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == facturas.CODIGO_DOCUMENTO_RH_INVALIDO


def test_columnas_esperadas_mapean_por_nombre_via_columnas_modulo():
    encabezado = (
        "SIIC", "Sucursal", "Nota crédito", "Factura", "Fecha",
        "Parte", "Cantidad", "Vlr. Total Neto",
    )
    mapa = columnas.construir_mapa_columnas(encabezado, facturas.COLUMNAS_ESPERADAS)

    esperado = dict(zip(facturas.COLUMNAS_ESPERADAS, range(len(facturas.COLUMNAS_ESPERADAS))))
    assert mapa == esperado


def test_usa_parte_nunca_parte_pedida():
    # `Parte Pedida` NI SIQUIERA está en `COLUMNAS_ESPERADAS` -- si alguna
    # vez se agregara por error, este test lo detectaría.
    assert "Parte Pedida" not in facturas.COLUMNAS_ESPERADAS
    assert "Parte" in facturas.COLUMNAS_ESPERADAS


# ---------------------------------------------------------------------------
# 8.1 — fecha / cantidad / valor_total inválidos (RED)
# ---------------------------------------------------------------------------


def test_fecha_invalida_emite_error_y_no_genera_staging():
    fila_staging, errores = _procesar(_fila(fecha="no es una fecha"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == facturas.CODIGO_FECHA_INVALIDA


def test_cantidad_no_numerica_emite_error_y_no_genera_staging():
    fila_staging, errores = _procesar(_fila(cantidad="N/D"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == facturas.CODIGO_CANTIDAD_INVALIDA


@pytest.mark.parametrize("valor", [None, "#N/A", "#VALUE!"])
def test_cantidad_vacia_o_con_error_de_excel_es_error_de_fila(valor):
    fila_staging, errores = _procesar(_fila(cantidad=valor))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == numeros.CODIGO_VALOR_FALTANTE
    assert errores[0].columna == "Cantidad"


def test_cantidad_cero_real_sigue_siendo_valida():
    fila_staging, errores = _procesar(_fila(cantidad=0))

    assert errores == []
    assert Decimal(fila_staging.payload["cantidad"]) == Decimal("0")


def test_valor_total_no_numerico_emite_error_y_no_genera_staging():
    fila_staging, errores = _procesar(_fila(valor_total_neto="N/D"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == facturas.CODIGO_VALOR_TOTAL_INVALIDO


@pytest.mark.parametrize("valor", [None, "#N/A", "#REF!"])
def test_valor_total_vacio_o_con_error_de_excel_es_error_de_fila(valor):
    fila_staging, errores = _procesar(_fila(valor_total_neto=valor))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == numeros.CODIGO_VALOR_FALTANTE
    assert errores[0].columna == "Vlr. Total Neto"


def test_valor_total_cero_real_sigue_siendo_valido():
    fila_staging, errores = _procesar(_fila(valor_total_neto=0))

    assert errores == []
    assert Decimal(fila_staging.payload["valor_total"]) == Decimal("0")


# ---------------------------------------------------------------------------
# 8.1 — resolución de sucursal (SIIC/SIC primero, Sucursal como respaldo) (RED)
# ---------------------------------------------------------------------------


def test_sucursal_resuelve_por_siic_primero():
    fila_staging, errores = _procesar(_fila(siic="1801", sucursal="TEXTO QUE NO MATCHEA"))

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_sucursal_cae_a_texto_cuando_siic_no_resuelve():
    cache = _cache(
        sucursales_por_texto=[("BUCARAMANGA LA 27", SUCURSAL_ID)],
        referencias=[(("12310-ABW-800TS", PROVEEDOR_ID), REFERENCIA_ID)],
    )
    fila_staging, errores = _procesar(
        _fila(siic="9999", sucursal="MR Bucaramanga La 27"), cache=cache
    )

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_ID


def test_sucursal_no_resuelta_genera_staging_con_null_y_carga_error():
    fila_staging, errores = _procesar(_fila(siic="9999", sucursal="NO EXISTE"))

    assert fila_staging is not None
    assert fila_staging.sucursal_id is None
    assert len(errores) == 1
    assert errores[0].codigo_error == "SUCURSAL_NO_ENCONTRADA"


def test_referencia_no_resuelta_genera_staging_con_null_y_carga_error():
    fila_staging, errores = _procesar(_fila(parte="NO-EXISTE"))

    assert fila_staging is not None
    assert fila_staging.referencia_id is None
    assert len(errores) == 1
    assert errores[0].codigo_error == "REFERENCIA_NO_ENCONTRADA"


# ---------------------------------------------------------------------------
# 8.1 — nota de crédito resta cantidad (RED)
# ---------------------------------------------------------------------------


def test_fila_normal_conserva_cantidad_positiva():
    fila_staging, errores = _procesar(_fila(cantidad=5, nota_credito=None))

    assert errores == []
    assert Decimal(fila_staging.payload["cantidad"]) == Decimal("5")


def test_nota_credito_con_valor_resta_cantidad():
    fila_staging, errores = _procesar(_fila(cantidad=5, nota_credito="X"))

    assert errores == []
    assert Decimal(fila_staging.payload["cantidad"]) == Decimal("-5")


def test_nota_credito_con_valor_resta_tambien_el_valor_total():
    fila_staging, errores = _procesar(
        _fila(cantidad=5, valor_total_neto=Decimal("275130"), nota_credito="X")
    )

    assert errores == []
    assert Decimal(fila_staging.payload["valor_total"]) == Decimal("-275130")


def test_documento_valido_conserva_prefijo_y_numero_rh_en_el_payload():
    fila_staging, errores = _procesar(_fila(factura="RH194067"))

    assert errores == []
    assert fila_staging.payload["prefijo_rh"] == "RH"
    assert fila_staging.payload["numero_rh"] == 194067


# ---------------------------------------------------------------------------
# 8.1 — consolidación por clave natural + upsert REPLACE-not-sum (RED)
# ---------------------------------------------------------------------------


def _fila_staging(
    sucursal_id, referencia_id, prefijo_rh, numero_rh, cantidad, valor_total,
    fecha_factura=date(2026, 7, 15), fila=1, lote=1,
):
    return CargaFilaStaging(
        carga_id=CARGA_ID,
        fila=fila,
        lote=lote,
        payload={
            "prefijo_rh": prefijo_rh,
            "numero_rh": numero_rh,
            "fecha_factura": fecha_factura.isoformat(),
            "cantidad": str(cantidad),
            "valor_total": str(valor_total),
        },
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )


def test_agregar_lineas_suma_cantidad_y_valor_total_por_clave_natural():
    filas = [
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067, 5, 275130, fila=1),
        _fila_staging(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067, -2, -110052, fila=2),
    ]

    consolidado = facturas.agregar_lineas(filas)

    clave = (SUCURSAL_ID, REFERENCIA_ID, "RH", 194067)
    assert consolidado[clave]["cantidad"] == Decimal("3")
    assert consolidado[clave]["valor_total"] == Decimal("165078")
    assert consolidado[clave]["fecha_factura"] == date(2026, 7, 15)


def test_agregar_lineas_excluye_filas_sin_clave_resuelta():
    filas = [
        _fila_staging(None, REFERENCIA_ID, "RH", 194067, 5, 275130),
        _fila_staging(SUCURSAL_ID, None, "RH", 194078, 5, 275130, fila=2),
    ]

    assert facturas.agregar_lineas(filas) == {}


def test_construir_statement_upsert_setea_cantidad_y_valor_total_a_excluded():
    consolidado = {
        (SUCURSAL_ID, REFERENCIA_ID, "RH", 194067): {
            "cantidad": Decimal("3"), "valor_total": Decimal("165078"),
            "fecha_factura": date(2026, 7, 15),
        },
    }

    stmt = facturas.construir_statement_upsert(consolidado, CARGA_ID)

    valores_set = upsert_set_clause(stmt)
    for campo in ("cantidad", "valor_total"):
        assert campo in valores_set
        assert valores_set[campo] == f"excluded.{campo}"


def test_construir_statement_upsert_retorna_none_sin_consolidado():
    assert facturas.construir_statement_upsert({}, CARGA_ID) is None


async def test_aplicar_ejecuta_una_sola_sentencia_set_based():
    consolidado = {
        (SUCURSAL_ID, REFERENCIA_ID, "RH", 194067): {
            "cantidad": Decimal("3"), "valor_total": Decimal("165078"),
            "fecha_factura": date(2026, 7, 15),
        },
    }
    session = FakeAsyncSession(execute_queue=[[]])

    await facturas.aplicar(session, consolidado, CARGA_ID)

    assert len(session.executed_statements) == 1


async def test_aplicar_no_ejecuta_nada_sin_consolidado():
    session = FakeAsyncSession(execute_queue=[])

    await facturas.aplicar(session, {}, CARGA_ID)

    assert session.executed_statements == []


# ---------------------------------------------------------------------------
# Optional "Vlr. Unitario" column -> factura_proveedor_linea.valor_unitario
# ---------------------------------------------------------------------------


def _mapa_con_unitario():
    mapa = dict(_MAPA_COLUMNAS)
    mapa["Vlr. Unitario"] = len(mapa)
    return mapa


def _fila_con_unitario(unitario, **kwargs):
    return _fila(**kwargs) + (unitario,)


def test_vlr_unitario_es_una_columna_opcional_y_no_obligatoria():
    assert facturas.COLUMNAS_OPCIONALES[0] == "Vlr. Unitario"
    assert "Vlr. Unitario" not in facturas.COLUMNAS_ESPERADAS


def test_vlr_unitario_se_guarda_en_el_payload():
    fila_staging, errores = _procesar(
        _fila_con_unitario(Decimal("55026"), cantidad=5),
        mapa_columnas=_mapa_con_unitario(),
    )

    assert errores == []
    assert Decimal(fila_staging.payload["valor_unitario"]) == Decimal("55026")


def test_sin_la_columna_vlr_unitario_la_fila_carga_igual_sin_precio():
    fila_staging, errores = _procesar(_fila())

    assert errores == []
    assert "valor_unitario" not in fila_staging.payload


@pytest.mark.parametrize("valor", [None, "", "abc", "#N/A"])
def test_vlr_unitario_vacio_o_invalido_no_rechaza_la_fila(valor):
    fila_staging, errores = _procesar(
        _fila_con_unitario(valor), mapa_columnas=_mapa_con_unitario()
    )

    assert errores == []
    assert fila_staging is not None
    assert "valor_unitario" not in fila_staging.payload


def test_nota_credito_mantiene_el_precio_unitario_positivo():
    fila_staging, errores = _procesar(
        _fila_con_unitario(Decimal("55026"), nota_credito="NC1", cantidad=2),
        mapa_columnas=_mapa_con_unitario(),
    )

    assert errores == []
    assert Decimal(fila_staging.payload["valor_unitario"]) == Decimal("55026")


def test_agregar_lineas_conserva_el_ultimo_precio_unitario_informado():
    primera = _fila_staging(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067, 5, 275130, fila=1)
    primera.payload["valor_unitario"] = "55026"
    segunda = _fila_staging(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067, 1, 1, fila=2)

    consolidado = facturas.agregar_lineas([primera, segunda])

    clave = (SUCURSAL_ID, REFERENCIA_ID, "RH", 194067)
    assert consolidado[clave]["valor_unitario"] == Decimal("55026")


def test_agregar_lineas_deja_el_precio_en_none_si_ninguna_fila_lo_trae():
    consolidado = facturas.agregar_lineas(
        [_fila_staging(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067, 5, 275130)]
    )

    assert consolidado[(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067)]["valor_unitario"] is None


def test_el_upsert_escribe_valor_unitario_sin_borrar_el_guardado_si_llega_nulo():
    consolidado = {
        (SUCURSAL_ID, REFERENCIA_ID, "RH", 194067): {
            "cantidad": Decimal("3"), "valor_total": Decimal("165078"),
            "valor_unitario": None, "fecha_factura": date(2026, 7, 15),
        },
    }

    valores_set = upsert_set_clause(facturas.construir_statement_upsert(consolidado, CARGA_ID))

    assert "coalesce(excluded.valor_unitario" in valores_set["valor_unitario"].lower()


# ---------------------------------------------------------------------------
# Optional "Número Identificación" / "Tipo de Pedido" columns ->
# factura_proveedor_linea.cliente_nit / tipo_pedido
# ---------------------------------------------------------------------------

COL_NIT = "Número Identificación"
COL_TIPO = "Tipo de Pedido"


def _mapa_con_cliente():
    mapa = dict(_MAPA_COLUMNAS)
    mapa[COL_NIT] = len(mapa)
    mapa[COL_TIPO] = len(mapa)
    return mapa


def _fila_con_cliente(nit, tipo, **kwargs):
    return _fila(**kwargs) + (nit, tipo)


def test_nit_y_tipo_de_pedido_son_columnas_opcionales():
    assert COL_NIT in facturas.COLUMNAS_OPCIONALES
    assert COL_TIPO in facturas.COLUMNAS_OPCIONALES
    assert COL_NIT not in facturas.COLUMNAS_ESPERADAS
    assert COL_TIPO not in facturas.COLUMNAS_ESPERADAS


def test_nit_y_tipo_se_guardan_en_el_payload():
    fila_staging, errores = _procesar(
        _fila_con_cliente("900723988", "GARANTIA25"),
        mapa_columnas=_mapa_con_cliente(),
    )

    assert errores == []
    assert fila_staging.payload["cliente_nit"] == "900723988"
    assert fila_staging.payload["tipo_pedido"] == "GARANTIA25"


@pytest.mark.parametrize("crudo, esperado", [
    (900723988, "900723988"),
    (900723988.0, "900723988"),
    (" 900 883 086 ", "900883086"),
    ("900.723.988", "900723988"),
    ("900723988-1", "900723988"),
    ("900723988.0", "900723988"),
    ("900.723.000", "900723000"),
    ("900.000.000", "900000000"),
])
def test_el_nit_se_normaliza_a_digitos(crudo, esperado):
    fila_staging, _ = _procesar(
        _fila_con_cliente(crudo, "X"), mapa_columnas=_mapa_con_cliente())

    assert fila_staging.payload["cliente_nit"] == esperado


@pytest.mark.parametrize("crudo, esperado", [
    ("garantia25", "GARANTIA25"), ("  Normal ", "NORMAL")])
def test_el_tipo_de_pedido_va_recortado_y_en_mayusculas(crudo, esperado):
    fila_staging, _ = _procesar(
        _fila_con_cliente("1", crudo), mapa_columnas=_mapa_con_cliente())

    assert fila_staging.payload["tipo_pedido"] == esperado


def test_sin_las_columnas_la_fila_carga_igual():
    fila_staging, errores = _procesar(_fila())

    assert errores == []
    assert "cliente_nit" not in fila_staging.payload
    assert "tipo_pedido" not in fila_staging.payload


@pytest.mark.parametrize("nit, tipo", [(None, None), ("", "  "), ("abc", None)])
def test_nit_o_tipo_vacio_o_sin_digitos_no_rechaza_la_fila(nit, tipo):
    fila_staging, errores = _procesar(
        _fila_con_cliente(nit, tipo), mapa_columnas=_mapa_con_cliente())

    assert errores == []
    assert fila_staging is not None
    assert "cliente_nit" not in fila_staging.payload
    assert "tipo_pedido" not in fila_staging.payload


def test_agregar_lineas_conserva_el_ultimo_nit_y_tipo_informados():
    primera = _fila_staging(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067, 5, 275130, fila=1)
    primera.payload.update(cliente_nit="900723988", tipo_pedido="GARANTIA25")
    segunda = _fila_staging(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067, 1, 1, fila=2)

    consolidado = facturas.agregar_lineas([primera, segunda])

    datos = consolidado[(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067)]
    assert datos["cliente_nit"] == "900723988"
    assert datos["tipo_pedido"] == "GARANTIA25"


def test_agregar_lineas_deja_nit_y_tipo_en_none_si_ninguna_fila_los_trae():
    consolidado = facturas.agregar_lineas(
        [_fila_staging(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067, 5, 275130)])

    datos = consolidado[(SUCURSAL_ID, REFERENCIA_ID, "RH", 194067)]
    assert datos["cliente_nit"] is None
    assert datos["tipo_pedido"] is None


def test_el_upsert_sobrescribe_con_un_valor_nuevo_y_conserva_el_guardado_si_llega_nulo():
    consolidado = {
        (SUCURSAL_ID, REFERENCIA_ID, "RH", 194067): {
            "cantidad": Decimal("3"), "valor_total": Decimal("165078"),
            "valor_unitario": None, "cliente_nit": None, "tipo_pedido": None,
            "fecha_factura": date(2026, 7, 15),
        },
    }

    valores_set = upsert_set_clause(facturas.construir_statement_upsert(consolidado, CARGA_ID))

    assert "coalesce(excluded.cliente_nit" in valores_set["cliente_nit"].lower()
    assert "coalesce(excluded.tipo_pedido" in valores_set["tipo_pedido"].lower()
