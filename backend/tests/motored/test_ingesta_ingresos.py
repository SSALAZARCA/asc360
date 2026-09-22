"""
Fase 2 "Ingesta", Phase 8 "FACTURAS/INGRESOS + Tránsito" (PR8)
(sdd/motored-pedidos-ingesta, task 8.1) — `services/ingesta/ingresos.py`
(design ADR-9, spec "Tránsito cruce by RH document identity").

No live Postgres: same `FakeAsyncSession` convention as
`test_ingesta_facturas.py`.

Columns confirmed against the real production workbook
(`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`, hoja "ingreso facturas ultimo 45
dias", header at row 1): `Nrodocumento`, `Fecha`, `Estado`,
`Dct.referencia`, `Valornetolocal` -- matches spec §5.5 literally.

**Real gap found against both the source spec's original data model
(§4.3) and the design's condensed schema, fixed via migration
`3956c0ebd69c` (see its docstring for the full rationale)**: this sheet is
DOCUMENT-level (one row per `Nrodocumento`) with NO `Sucursal`/`Parte`
columns at all, unlike `facturas pedidos`. `sucursal_id`/`referencia_id`
are therefore always `None` for every row of this type -- there is no
resolution failure to report (`SUCURSAL_NO_ENCONTRADA`/`REFERENCIA_NO_
ENCONTRADA` never apply here, there is no column to resolve in the first
place), and the model's `cantidad` field was renamed `valor_neto` (this
file has no unit-quantity column, only a monetary net value).

`Dct.referencia` real values include documents that do NOT match the H3
regex at all (`CH-70752`, 474 of 1 395 non-blank rows) and prefixes other
than `RH` (`FE15892`) -- both are per-row-tolerant concerns for THIS
module (a row that cannot be decomposed into `(prefijo, numero)` cannot be
staged at all), while the cruce itself (`transito.py`) naturally ignores
non-`RH`-keyed rows without any extra filter (a `('RH', N)` factura key
never collides with `('FE', N)`/unparseable rows).
"""
import uuid
from datetime import date
from decimal import Decimal

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import columnas, ingresos

CARGA_ID = uuid.uuid4()

_MAPA_COLUMNAS = {nombre: idx for idx, nombre in enumerate(ingresos.COLUMNAS_ESPERADAS)}


def _fila(
    nrodocumento="16-00000036",
    fecha=date(2026, 7, 15),
    estado="Facturado",
    dct_referencia="RH193043",
    valor_neto=Decimal("2290580"),
):
    valores = {
        "Nrodocumento": nrodocumento,
        "Fecha": fecha,
        "Estado": estado,
        "Dct.referencia": dct_referencia,
        "Valornetolocal": valor_neto,
    }
    return tuple(valores[nombre] for nombre in ingresos.COLUMNAS_ESPERADAS)


def _procesar(fila_raw, **overrides):
    kwargs = dict(numero_fila=2, lote=1, mapa_columnas=_MAPA_COLUMNAS, carga_id=CARGA_ID)
    kwargs.update(overrides)
    return ingresos.procesar_fila(fila_raw, **kwargs)


# ---------------------------------------------------------------------------
# 8.1 — mapeo + fila de relleno (RED)
# ---------------------------------------------------------------------------


def test_columnas_esperadas_mapean_por_nombre_via_columnas_modulo():
    encabezado = ("Nrodocumento", "Fecha", "Estado", "Dct.referencia", "Valornetolocal")
    mapa = columnas.construir_mapa_columnas(encabezado, ingresos.COLUMNAS_ESPERADAS)

    esperado = dict(zip(ingresos.COLUMNAS_ESPERADAS, range(len(ingresos.COLUMNAS_ESPERADAS))))
    assert mapa == esperado


def test_documento_ausente_se_descarta_en_silencio_como_fila_de_relleno():
    fila_staging, errores = _procesar(_fila(dct_referencia=None, nrodocumento=None))

    assert fila_staging is None
    assert errores == []


def test_documento_con_formato_invalido_emite_error_tipado():
    fila_staging, errores = _procesar(_fila(dct_referencia="CH-70752"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == ingresos.CODIGO_DOCUMENTO_RH_INVALIDO


def test_documento_con_prefijo_distinto_de_rh_igual_se_stagea():
    # El archivo real trae `FE15892` -- H3 no exige que el prefijo sea
    # literalmente "RH" para poder EXTRAERLO, solo para que el CRUCE
    # (transito.py) lo use más adelante.
    fila_staging, errores = _procesar(_fila(dct_referencia="FE15892"))

    assert errores == []
    assert fila_staging.payload["prefijo_rh"] == "FE"
    assert fila_staging.payload["numero_rh"] == 15892


# ---------------------------------------------------------------------------
# 8.1 — fecha / valor_neto inválidos (RED)
# ---------------------------------------------------------------------------


def test_fecha_invalida_emite_error_y_no_genera_staging():
    fila_staging, errores = _procesar(_fila(fecha="no es una fecha"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == ingresos.CODIGO_FECHA_INVALIDA


def test_valor_neto_no_numerico_emite_error_y_no_genera_staging():
    fila_staging, errores = _procesar(_fila(valor_neto="N/D"))

    assert fila_staging is None
    assert len(errores) == 1
    assert errores[0].codigo_error == ingresos.CODIGO_VALOR_NETO_INVALIDO


def test_valor_neto_ausente_se_trata_como_cero():
    fila_staging, errores = _procesar(_fila(valor_neto=None))

    assert errores == []
    assert Decimal(fila_staging.payload["valor_neto"]) == Decimal("0")


# ---------------------------------------------------------------------------
# 8.1 — sucursal/referencia siempre None: no hay columna que resolver (RED)
# ---------------------------------------------------------------------------


def test_fila_aplicable_nunca_tiene_sucursal_ni_referencia_y_no_genera_esos_errores():
    fila_staging, errores = _procesar(_fila())

    assert fila_staging is not None
    assert fila_staging.sucursal_id is None
    assert fila_staging.referencia_id is None
    assert errores == []


def test_documento_valido_conserva_prefijo_numero_y_valor_neto_en_el_payload():
    fila_staging, errores = _procesar(
        _fila(dct_referencia="RH193043", valor_neto=Decimal("2290580"))
    )

    assert errores == []
    assert fila_staging.payload["prefijo_rh"] == "RH"
    assert fila_staging.payload["numero_rh"] == 193043
    assert Decimal(fila_staging.payload["valor_neto"]) == Decimal("2290580")


# ---------------------------------------------------------------------------
# 8.1 — consolidación por documento + upsert REPLACE-not-sum (RED)
# ---------------------------------------------------------------------------


def _fila_staging(
    prefijo_rh, numero_rh, valor_neto, fecha_ingreso=date(2026, 7, 15), fila=1, lote=1
):
    return CargaFilaStaging(
        carga_id=CARGA_ID,
        fila=fila,
        lote=lote,
        payload={
            "prefijo_rh": prefijo_rh,
            "numero_rh": numero_rh,
            "fecha_ingreso": fecha_ingreso.isoformat(),
            "valor_neto": str(valor_neto),
        },
        sucursal_id=None,
        referencia_id=None,
    )


def test_agregar_documentos_mantiene_documentos_distintos_separados():
    filas = [
        _fila_staging("RH", 193043, Decimal("2290580"), fila=1),
        _fila_staging("RH", 192406, Decimal("369931"), fila=2),
    ]

    consolidado = ingresos.agregar_documentos(filas)

    assert consolidado[("RH", 193043)]["valor_neto"] == Decimal("2290580")
    assert consolidado[("RH", 192406)]["valor_neto"] == Decimal("369931")


def test_agregar_documentos_reune_multiples_filas_del_mismo_documento():
    # No observado en el workbook real (cada Nrodocumento aparece una vez),
    # pero la agregación es aditiva por robustez, mismo criterio que
    # `ventas.agregar_unidades`.
    filas = [
        _fila_staging("RH", 193043, Decimal("1000"), fila=1),
        _fila_staging("RH", 193043, Decimal("500"), fila=2),
    ]

    consolidado = ingresos.agregar_documentos(filas)

    assert consolidado[("RH", 193043)]["valor_neto"] == Decimal("1500")


def test_construir_statement_upsert_setea_valor_neto_a_excluded_nunca_suma():
    consolidado = {
        ("RH", 193043): {"valor_neto": Decimal("2290580"), "fecha_ingreso": date(2026, 7, 15)},
    }

    stmt = ingresos.construir_statement_upsert(consolidado, CARGA_ID)

    set_clause = stmt._post_values_clause.update_values_to_set
    valores_set = {
        (col if isinstance(col, str) else col.name): expr for col, expr in set_clause
    }
    assert "valor_neto" in valores_set
    assert valores_set["valor_neto"].table.name == "excluded"
    assert valores_set["valor_neto"].name == "valor_neto"


def test_construir_statement_upsert_retorna_none_sin_consolidado():
    assert ingresos.construir_statement_upsert({}, CARGA_ID) is None


async def test_aplicar_ejecuta_una_sola_sentencia_set_based():
    consolidado = {
        ("RH", 193043): {"valor_neto": Decimal("2290580"), "fecha_ingreso": date(2026, 7, 15)},
    }
    session = FakeAsyncSession(execute_queue=[[]])

    await ingresos.aplicar(session, consolidado, CARGA_ID)

    assert len(session.executed_statements) == 1


async def test_aplicar_no_ejecuta_nada_sin_consolidado():
    session = FakeAsyncSession(execute_queue=[])

    await ingresos.aplicar(session, {}, CARGA_ID)

    assert session.executed_statements == []
