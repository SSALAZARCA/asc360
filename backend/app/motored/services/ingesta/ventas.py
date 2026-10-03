"""
Motored Pedidos — Fase 2 "Ingesta", Phase 4 "VENTAS Transform" (PR4)
(sdd/motored-pedidos-ingesta, tasks 4.1/4.2; design ADR-2/ADR-2b/ADR-4/ADR-8,
spec "VENTAS net-signed aggregation preserving Módulo origin").

Compone `lector` + `columnas` + `resolucion` + `errores` (Phase 3) en el
PRIMER transform real de Fase 2: filtra por regla de negocio, resuelve
sucursal/referencia contra el cache de ADR-8, arma la fila de
`carga_fila_staging` (ADR-2) y, en `Aplicar`, agrega en memoria y hace el
upsert REPLACE-not-sum de ADR-4 (`ON CONFLICT DO UPDATE SET unidades =
EXCLUDED.unidades`, nunca `+=`) que hace ciertos T17 (idempotencia) y el
caso "meses solapados reemplazan, no acumulan" por construcción: cada
llamada sólo agrega/toca las claves presentes en SU PROPIO staging.

Fase 2 "Ingesta", Phase 5 "ADR-9 Period Module" (PR5) agrega el gate
declarado-vs-detectado (task 5.3): `construir_filas_por_periodo` arma el
histograma `{(anio, mes): cantidad}` leyendo el `payload` que `procesar_fila`
YA generó para cada fila staged de ESTE lote -- nunca una segunda pasada
sobre el archivo, el caller (Fase 9, el job real) simplemente llama esto una
vez por lote y acumula el resultado entre lotes (`Counter`/`dict` suma).
`evaluar_periodo_declarado`/`aplicar_con_periodo` envuelven
`services/ingesta/periodo.py` (ADR-9): sobre un veredicto `RECHAZO`,
`aplicar_con_periodo` no ejecuta NINGÚN `session.execute` -- ni agrega, ni
actualiza -- lo que hace que "cero filas de `venta_mensual`" y "un agosto
previo correcto queda intacto" sean ciertos por construcción, exactamente
como el upsert REPLACE-not-sum de ADR-4 ya hace con las claves que NO están
presentes en su propio staging.

Deliberadamente FUERA de alcance de esta fase (ver tasks.md Fase 9):
- Wiring a `JobRunner`/supervisor y a la API (`POST .../aplicar`) — Fase 9.
  `aplicar_con_periodo` es el punto de integración que ese job llamará; este
  módulo no conoce `carga_archivo` ni decide su `estado`/`log` -- eso sigue
  siendo responsabilidad exclusiva del caller (Fase 9), igual que borrar el
  staging tras un rechazo.
- Persistir en `carga_error` las filas individuales de un mes adyacente
  dentro de tolerancia (`A-CARGA-043`, veredicto `ADVERTENCIA`) — requiere
  identificar la fila staged concreta contra la BD (Fase 9); acá solo se
  calcula y expone el veredicto y los meses afectados.
- Creación automática de referencia bajo `OTROS`
  (`crear_referencias_desconocidas`) — depende de `parametros.resolver()`,
  Fase 9.
- Persistencia de `sucursal_alias` al resolver un error en la UI — Fase 9.

`tipos_inventario_incluidos` y `proveedor_id` los recibe el caller como
parámetros explícitos en vez de leerlos de `parametro_metodologia` o de una
columna del archivo -- ambas resoluciones son de Fase 9 y no se
re-implementan acá (ver apply-progress, sección "Deviations").
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.ingesta import columnas as columnas_mod
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import numeros as numeros_mod
from app.motored.services.ingesta import periodo as periodo_mod
from app.motored.services.ingesta.resolucion import (
    CacheResolucion,
    resolver_referencia,
    resolver_sucursal,
)

# Nombres CANÓNICOS (no normalizados) tal como los espera `columnas.
# construir_mapa_columnas` -- spec §5.1 (columna origen `Referencia`, NO
# `Dct.referencia`: esa es la columna RH de FACTURAS_PEDIDOS/INGRESOS_
# FACTURAS, §5.4/§5.5 -- confirmado además por la firma de detección de
# tipo de archivo del propio spec: "contiene Cantidad inv. + Desc.bodega +
# Referencia -> VENTAS").
COLUMNAS_ESPERADAS: Tuple[str, ...] = (
    "Estado",
    "Módulo",
    "Fecha",
    "Cantidad inv.",
    "Tipo inventario",
    "Desc.bodega",
    "Bodega",
    "Referencia",
    # Detalle por linea (`venta_detalle`): obligatorias desde 2026-09-30.
    "Nombre vendedor",
    "Valor bruto",
    "Valor descuentos",
    "Cliente factura",
    "Nro documento",
)

ESTADO_APROBADA = "Aprobada"
CODIGO_FECHA_INVALIDA = "FECHA_INVALIDA"
CODIGO_CANTIDAD_INVALIDA = "CANTIDAD_INVALIDA"
CODIGO_VALOR_BRUTO_INVALIDO = "VALOR_BRUTO_INVALIDO"
CODIGO_DESCUENTO_INVALIDO = "DESCUENTO_INVALIDO"
CODIGO_VENDEDOR_FALTANTE = "VENDEDOR_FALTANTE"
CODIGO_CLIENTE_FALTANTE = "CLIENTE_FACTURA_FALTANTE"
CODIGO_NRO_DOCUMENTO_FALTANTE = "NRO_DOCUMENTO_FALTANTE"
CODIGO_TEXTO_DEMASIADO_LARGO = "TEXTO_DEMASIADO_LARGO"

# Limites de las columnas de `venta_detalle`.
_LARGO_MAX_NOMBRE = 255
_LARGO_MAX_NRO_DOCUMENTO = 50
# Numeric(16, 2): 14 digitos enteros.
_VALOR_MAX_ABS = Decimal(10) ** 14
TAMANO_LOTE_DETALLE = 1000

# Marca del payload de las filas que solo alimentan `venta_detalle`.
CLAVE_SOLO_DETALLE = "solo_detalle"

_CLAVE_UPSERT = ("sucursal_id", "referencia_id", "anio", "mes", "origen")


def _extraer(fila_raw: Sequence[Any], mapa: Dict[str, int], nombre: str) -> Any:
    idx = mapa.get(nombre)
    if idx is None or idx >= len(fila_raw):
        return None
    return fila_raw[idx]


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _resolver_fecha(valor_fecha: Any) -> Optional[date]:
    """Devuelve la fecha completa de la venta (el caller deriva `anio`/`mes`
    y conserva el `dia`). `Fecha` puede llegar de dos formas, dependiendo de si la celda del
    ERP tiene formato de fecha aplicado o no: (a) `openpyxl` con
    `data_only=True` la entrega YA como `date`/`datetime` cuando la celda
    tiene formato de fecha -- confirmado contra el workbook real de
    producción (`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`, hoja "BD ventas
    ultimos 6 meses"), este es el caso real, no el hipotético; (b) un
    serial numérico crudo si la celda está en formato General/Número --
    mismo criterio que `columnas.convertir_fecha_excel`. Cualquier valor
    de un tipo distinto, no numérico, o fuera de 2015-2100 es `None` -- el
    caller lo traduce a `carga_error`, nunca deja escapar la excepción
    cruda (mismo contrato que `carga_excel.py`)."""
    fecha_celda = columnas_mod.a_fecha(valor_fecha)
    if fecha_celda is not None:
        if not columnas_mod.anio_es_plausible(fecha_celda.year):
            return None
        return fecha_celda
    try:
        return columnas_mod.convertir_fecha_excel(float(valor_fecha))
    except (TypeError, ValueError, columnas_mod.FechaExcelImplausibleError):
        return None


def _es_aprobada(fila_raw: Sequence[Any], mapa_columnas: Dict[str, int]) -> bool:
    return _texto(_extraer(fila_raw, mapa_columnas, "Estado")) == ESTADO_APROBADA


def _tipo_incluido(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    tipos_inventario_incluidos: Sequence[str],
) -> bool:
    tipo_inventario = _texto(_extraer(fila_raw, mapa_columnas, "Tipo inventario"))
    return tipo_inventario in tipos_inventario_incluidos


def _pasa_filtros_negocio(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    tipos_inventario_incluidos: Sequence[str],
) -> bool:
    """`Estado != 'Aprobada'` o tipo de inventario no incluido -- spec: esos
    estados "se cuentan y reportan en el log, nunca se suman"; no es una
    fila inválida, no genera `carga_error`."""
    return _es_aprobada(fila_raw, mapa_columnas) and _tipo_incluido(
        fila_raw, mapa_columnas, tipos_inventario_incluidos
    )


def _resolver_fecha_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[date], Optional[CargaError]]:
    """`Fecha` implausible/no interpretable -- sin fecha no hay payload
    posible para esa fila (`CODIGO_FECHA_INVALIDA`)."""
    valor_fecha = _extraer(fila_raw, mapa_columnas, "Fecha")
    fecha = _resolver_fecha(valor_fecha)
    if fecha is not None:
        return fecha, None
    error = errores_mod.construir_error(
        carga_id, numero_fila, "Fecha", _texto(valor_fecha), CODIGO_FECHA_INVALIDA,
        "La fecha de la fila no se pudo interpretar o cae fuera del rango plausible.",
    )
    return None, error


def _resolver_cantidad_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """`Cantidad inv.` vacía, con error de Excel o no numérica nunca debe
    propagar un `decimal.InvalidOperation` crudo ni convertirse en un cero
    silencioso (decisión del owner, 2026-09-29): la fila queda como
    `carga_error` (ver `numeros.resolver_decimal_o_error`). Un `0` real es
    un valor válido."""
    return numeros_mod.resolver_decimal_o_error(
        _extraer(fila_raw, mapa_columnas, "Cantidad inv."), "Cantidad inv.", carga_id,
        numero_fila, CODIGO_CANTIDAD_INVALIDA,
        "La cantidad de la fila no se pudo interpretar como un número.",
    )


def _normalizar_espacios(texto: str) -> str:
    return " ".join(texto.split())


def normalizar_vendedor(nombre: str) -> str:
    """Clave estable del vendedor: MAYUSCULAS, sin tildes y con espacios
    colapsados -- los nombres de Excel derivan ("Ana  Pérez" / "ANA PEREZ")."""
    descompuesto = unicodedata.normalize("NFD", nombre)
    sin_tildes = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return _normalizar_espacios(sin_tildes).upper()


def _texto_documento(valor: Any) -> Optional[str]:
    """Como `_texto`, pero un numero de Excel entero (`10234.0`) se guarda
    sin decimales: un nro de documento nunca debe quedar como "10234.0"."""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return _texto(valor)


def _limpiar_moneda(valor: Any) -> Any:
    """`$1.234.567` / `$ 2.500 .000` -> `1.234.567` / `2.500.000`: quita el
    simbolo y los espacios de un texto; cualquier otro valor pasa igual."""
    if isinstance(valor, str):
        return re.sub(r"[$\s]", "", valor)
    return valor


def _resolver_valor_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID,
    numero_fila: int, columna: str, codigo_invalido: str, vacio_es_cero: bool,
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """Valor monetario de `Valor bruto`/`Valor descuentos` (formato
    colombiano, ver `numeros.py`). Un negativo es valido (nota credito). Un
    bruto vacio rechaza la fila; un descuento vacio cuenta como 0 (una venta
    sin descuento no trae nada en la celda)."""
    valor = _limpiar_moneda(_extraer(fila_raw, mapa_columnas, columna))
    if vacio_es_cero and (valor is None or (isinstance(valor, str) and not valor)):
        return Decimal("0"), None
    mensaje = f"{columna} de la fila no se pudo interpretar como un valor numerico."
    try:
        decimal = numeros_mod.parsear_decimal(valor)
    except numeros_mod.CeldaFaltanteError:
        if vacio_es_cero:  # celda con error de Excel (#N/A): no es un descuento valido
            return None, errores_mod.construir_error(
                carga_id, numero_fila, columna, _texto(valor), codigo_invalido, mensaje
            )
        decimal, error = numeros_mod.resolver_decimal_o_error(
            valor, columna, carga_id, numero_fila, codigo_invalido, mensaje
        )
        return decimal, error
    except numeros_mod.CeldaInvalidaError:
        return None, errores_mod.construir_error(
            carga_id, numero_fila, columna, _texto(valor), codigo_invalido, mensaje
        )
    if abs(decimal) >= _VALOR_MAX_ABS:
        return None, errores_mod.construir_error(
            carga_id, numero_fila, columna, _texto(valor), codigo_invalido,
            f"{columna} de la fila es demasiado grande.",
        )
    return decimal, None


def _resolver_texto_o_error(
    valor: Any, columna: str, carga_id: uuid.UUID, numero_fila: int,
    codigo_faltante: str, largo_max: int,
) -> Tuple[Optional[str], Optional[CargaError]]:
    texto = _texto_documento(valor)
    if texto is None:
        return None, errores_mod.construir_error(
            carga_id, numero_fila, columna, None, codigo_faltante,
            f"{columna} vacio en la fila {numero_fila}: corregi el archivo y volve a cargarlo.",
        )
    texto = _normalizar_espacios(texto)
    if len(texto) > largo_max:
        return None, errores_mod.construir_error(
            carga_id, numero_fila, columna, texto[:60], CODIGO_TEXTO_DEMASIADO_LARGO,
            f"{columna} supera los {largo_max} caracteres en la fila {numero_fila}.",
        )
    return texto, None


def _resolver_campos_detalle(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID,
    numero_fila: int,
) -> Tuple[Optional[Dict[str, str]], Optional[CargaError]]:
    """Las 5 columnas del detalle por linea. El primer problema rechaza la
    fila (`carga_error`); si todo esta bien devuelve el aporte al payload."""
    campos: Dict[str, str] = {}
    for clave, columna, codigo, largo in (
        ("vendedor", "Nombre vendedor", CODIGO_VENDEDOR_FALTANTE, _LARGO_MAX_NOMBRE),
        ("cliente_factura", "Cliente factura", CODIGO_CLIENTE_FALTANTE, _LARGO_MAX_NOMBRE),
        ("nro_documento", "Nro documento", CODIGO_NRO_DOCUMENTO_FALTANTE,
         _LARGO_MAX_NRO_DOCUMENTO),
    ):
        texto, error = _resolver_texto_o_error(
            _extraer(fila_raw, mapa_columnas, columna), columna, carga_id, numero_fila,
            codigo, largo,
        )
        if error is not None:
            return None, error
        campos[clave] = texto
    for clave, columna, codigo, vacio_es_cero in (
        ("valor_bruto", "Valor bruto", CODIGO_VALOR_BRUTO_INVALIDO, False),
        ("valor_descuentos", "Valor descuentos", CODIGO_DESCUENTO_INVALIDO, True),
    ):
        valor, error = _resolver_valor_o_error(
            fila_raw, mapa_columnas, carga_id, numero_fila, columna, codigo, vacio_es_cero
        )
        if error is not None:
            return None, error
        campos[clave] = str(valor)
    return campos, None


def _resolver_claves(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    cache: CacheResolucion,
    carga_id: uuid.UUID,
    numero_fila: int,
    proveedor_id: uuid.UUID,
) -> Tuple[Optional[uuid.UUID], Optional[uuid.UUID], List[CargaError]]:
    """Resuelve sucursal/referencia contra el cache de ADR-8. Sucursal y/o
    referencia sin resolver NO abortan la fila -- spec "Per-row tolerance
    for movement loads": se retorna el/los id(s) en `None` (para que
    `Aplicar` sólo re-resuelva los `NULL`, ADR-2) junto con el
    `carga_error` correspondiente."""
    texto_sucursal = _texto(_extraer(fila_raw, mapa_columnas, "Desc.bodega")) or _texto(
        _extraer(fila_raw, mapa_columnas, "Bodega")
    )
    sucursal_id = resolver_sucursal(cache, texto_sucursal)

    codigo_referencia = _texto(_extraer(fila_raw, mapa_columnas, "Referencia"))
    referencia_id = resolver_referencia(cache, codigo_referencia)

    errores: List[CargaError] = []
    if sucursal_id is None:
        errores.append(
            errores_mod.error_sucursal_no_encontrada(
                carga_id, numero_fila, "Desc.bodega", texto_sucursal
            )
        )
    if referencia_id is None:
        errores.append(
            errores_mod.error_referencia_no_encontrada(
                carga_id, numero_fila, "Referencia", codigo_referencia
            )
        )
    return sucursal_id, referencia_id, errores


def _procesar_fila_solo_detalle(
    fila_raw: Sequence[Any],
    *,
    numero_fila: int,
    lote: int,
    mapa_columnas: Dict[str, int],
    cache: CacheResolucion,
    carga_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> Optional[CargaFilaStaging]:
    """Fila aprobada de un tipo de inventario excluido de `venta_mensual`
    (p.ej. "0001 - MOTOCICLETA"). Se stagea con `solo_detalle: True` para que
    `venta_detalle` la conserve; `agregar_unidades`, el histograma de periodo
    y la fecha maxima la ignoran, asi `venta_mensual` queda exactamente como
    si la fila no existiera.

    Es una ruta independiente: cualquier problema (fecha, cantidad, campos de
    detalle, sucursal o referencia sin resolver) la omite EN SILENCIO, sin
    `carga_error` -- hoy esas filas ya se descartan sin ruido y no deben
    aparecer como errores de la carga."""
    fecha, _ = _resolver_fecha_o_error(fila_raw, mapa_columnas, carga_id, numero_fila)
    if fecha is None:
        return None
    cantidad, _ = _resolver_cantidad_o_error(fila_raw, mapa_columnas, carga_id, numero_fila)
    if cantidad is None:
        return None
    campos_detalle, _ = _resolver_campos_detalle(fila_raw, mapa_columnas, carga_id, numero_fila)
    if campos_detalle is None:
        return None
    sucursal_id, referencia_id, _ = _resolver_claves(
        fila_raw, mapa_columnas, cache, carga_id, numero_fila, proveedor_id
    )
    if sucursal_id is None or referencia_id is None:
        return None
    modulo = _texto(_extraer(fila_raw, mapa_columnas, "Módulo")) or ""
    return CargaFilaStaging(
        carga_id=carga_id,
        fila=numero_fila,
        lote=lote,
        payload={
            "anio": fecha.year,
            "mes": fecha.month,
            "dia": fecha.day,
            "origen": modulo.upper(),
            "cantidad": str(cantidad),
            **campos_detalle,
            CLAVE_SOLO_DETALLE: True,
        },
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )


def procesar_fila(
    fila_raw: Sequence[Any],
    *,
    numero_fila: int,
    lote: int,
    mapa_columnas: Dict[str, int],
    cache: CacheResolucion,
    carga_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    tipos_inventario_incluidos: Sequence[str],
) -> Tuple[Optional[CargaFilaStaging], List[CargaError]]:
    """Procesa UNA fila cruda de VENTAS. Retorna `(fila_staging, errores)`
    orquestando los tres pasos de la transformación (ver los docstrings de
    `_pasa_filtros_negocio`/`_resolver_fecha_o_error`/`_resolver_claves`).

    Una linea aprobada de un tipo NO incluido no entra a `venta_mensual`,
    pero `venta_detalle` la guarda igual: ver `_procesar_fila_solo_detalle`."""
    if not _es_aprobada(fila_raw, mapa_columnas):
        return None, []
    if not _tipo_incluido(fila_raw, mapa_columnas, tipos_inventario_incluidos):
        return _procesar_fila_solo_detalle(
            fila_raw, numero_fila=numero_fila, lote=lote, mapa_columnas=mapa_columnas,
            cache=cache, carga_id=carga_id, proveedor_id=proveedor_id,
        ), []

    fecha, error_fecha = _resolver_fecha_o_error(fila_raw, mapa_columnas, carga_id, numero_fila)
    if fecha is None:
        return None, [error_fecha]

    cantidad, error_cantidad = _resolver_cantidad_o_error(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if cantidad is None:
        return None, [error_cantidad]

    campos_detalle, error_detalle = _resolver_campos_detalle(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if campos_detalle is None:
        return None, [error_detalle]

    modulo = _texto(_extraer(fila_raw, mapa_columnas, "Módulo")) or ""

    sucursal_id, referencia_id, errores = _resolver_claves(
        fila_raw, mapa_columnas, cache, carga_id, numero_fila, proveedor_id
    )

    payload = {
        "anio": fecha.year,
        "mes": fecha.month,
        "dia": fecha.day,
        "origen": modulo.upper(),
        "cantidad": str(cantidad),
        **campos_detalle,
    }
    fila_staging = CargaFilaStaging(
        carga_id=carga_id,
        fila=numero_fila,
        lote=lote,
        payload=payload,
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )
    return fila_staging, errores


ClaveVentaMensual = Tuple[uuid.UUID, uuid.UUID, int, int, str]


def es_solo_detalle(fila: CargaFilaStaging) -> bool:
    """True si la fila staged solo debe escribirse en `venta_detalle`."""
    return bool(fila.payload.get(CLAVE_SOLO_DETALLE))


def agregar_unidades(
    filas_staging: Sequence[CargaFilaStaging],
) -> Dict[ClaveVentaMensual, Decimal]:
    """Agregación NETA-firmada (ADR-4): suma `Cantidad inv.` tal cual llega
    (sin clasificación de devolución/nota de crédito) por clave
    `(sucursal_id, referencia_id, anio, mes, origen)`. Filas sin sucursal o
    sin referencia resuelta (`None`) se EXCLUYEN -- ya fueron reportadas
    como `carga_error` en `procesar_fila`; re-resolver esos `NULL` contra
    los maestros vigentes es responsabilidad del caller (Fase 9) ANTES de
    llamar a esta función.

    Pura y determinística: llamarla dos veces con el mismo input produce el
    mismo resultado (T17) -- no hay estado oculto ni acumulación contra un
    valor previamente aplicado."""
    totales: Dict[ClaveVentaMensual, Decimal] = {}
    for fila in filas_staging:
        if fila.sucursal_id is None or fila.referencia_id is None or es_solo_detalle(fila):
            continue
        payload = fila.payload
        clave: ClaveVentaMensual = (
            fila.sucursal_id,
            fila.referencia_id,
            payload["anio"],
            payload["mes"],
            payload["origen"],
        )
        cantidad = Decimal(payload["cantidad"])
        totales[clave] = totales.get(clave, Decimal("0")) + cantidad
    return totales


def construir_statement_upsert(totales: Dict[ClaveVentaMensual, Decimal], carga_id: uuid.UUID):
    """Construye el `INSERT ... ON CONFLICT DO UPDATE` de ADR-4:
    `SET unidades = EXCLUDED.unidades`, NUNCA `unidades = unidades +
    EXCLUDED.unidades`. Esta es la razón de fondo por la que T17
    (idempotencia) y "meses solapados reemplazan, no acumulan" (spec) se
    cumplen por construcción: la sentencia sólo conoce las claves presentes
    en `totales` -- nunca lee ni suma contra lo que ya existe en la tabla.
    Retorna `None` si no hay nada que aplicar (archivo sin filas
    resolubles)."""
    if not totales:
        return None

    valores = [
        {
            "id": uuid.uuid4(),
            "sucursal_id": sucursal_id,
            "referencia_id": referencia_id,
            "anio": anio,
            "mes": mes,
            "origen": origen,
            "unidades": unidades,
            "carga_id": carga_id,
        }
        for (sucursal_id, referencia_id, anio, mes, origen), unidades in totales.items()
    ]
    stmt = pg_insert(VentaMensual).values(valores)
    return stmt.on_conflict_do_update(
        index_elements=list(_CLAVE_UPSERT),
        set_={"unidades": stmt.excluded.unidades, "carga_id": stmt.excluded.carga_id},
    )


async def aplicar(session, totales: Dict[ClaveVentaMensual, Decimal], carga_id: uuid.UUID) -> None:
    """Ejecuta el upsert como UNA sola sentencia set-based (ADR-2b) -- nunca
    fila por fila. No hace `commit()`: eso es responsabilidad del caller
    (el job runner de Fase 9, que ya define su propio límite de
    transacción por lote)."""
    stmt = construir_statement_upsert(totales, carga_id)
    if stmt is not None:
        await session.execute(stmt)


def construir_detalle(
    filas_staging: Sequence[CargaFilaStaging], carga_id: uuid.UUID
) -> List[Dict[str, Any]]:
    """Filas de `venta_detalle` desde las filas de staging, incluidas las
    `solo_detalle` (sin sucursal o referencia resuelta no se escribe). Las filas staged por una version anterior al detalle (sin
    `nro_documento` en el payload) se omiten."""
    detalle: List[Dict[str, Any]] = []
    for fila in filas_staging:
        payload = fila.payload
        if fila.sucursal_id is None or fila.referencia_id is None:
            continue
        if "nro_documento" not in payload:
            continue
        detalle.append({
            "id": uuid.uuid4(),
            "carga_id": carga_id,
            "fecha": date(payload["anio"], payload["mes"], payload["dia"]),
            "anio": payload["anio"],
            "mes": payload["mes"],
            "sucursal_id": fila.sucursal_id,
            "referencia_id": fila.referencia_id,
            "origen": payload["origen"],
            "cantidad": Decimal(payload["cantidad"]),
            "vendedor": payload["vendedor"],
            "vendedor_norm": normalizar_vendedor(payload["vendedor"]),
            "valor_bruto": Decimal(payload["valor_bruto"]),
            "valor_descuentos": Decimal(payload["valor_descuentos"]),
            "cliente_factura": payload["cliente_factura"],
            "nro_documento": payload["nro_documento"],
        })
    return detalle


async def aplicar_detalle(
    session, filas_staging: Sequence[CargaFilaStaging], carga_id: uuid.UUID
) -> None:
    """Escribe `venta_detalle` en la MISMA transaccion que el upsert de
    `venta_mensual` (sin `commit()`). Delete-on-replace: borra el detalle de
    cada (sucursal, anio, mes) presente en ESTA carga y lo inserta de nuevo,
    por lotes. Nunca se llama para una carga rechazada ni se borra al anular."""
    detalle = construir_detalle(filas_staging, carga_id)
    if not detalle:
        return
    claves = {(d["sucursal_id"], d["anio"], d["mes"]) for d in detalle}
    await session.execute(
        delete(VentaDetalle).where(
            tuple_(VentaDetalle.sucursal_id, VentaDetalle.anio, VentaDetalle.mes).in_(list(claves))
        )
    )
    for inicio in range(0, len(detalle), TAMANO_LOTE_DETALLE):
        await session.execute(
            pg_insert(VentaDetalle).values(detalle[inicio:inicio + TAMANO_LOTE_DETALLE])
        )


def construir_filas_por_periodo(
    filas_staging: Sequence[CargaFilaStaging],
) -> Dict[Tuple[int, int], int]:
    """Histograma `{(anio, mes): cantidad}` (ADR-9) sobre filas YA staged de
    ESTE lote -- lee el mismo `payload["anio"/"mes"]` que `procesar_fila` ya
    calculó, nunca vuelve a interpretar `Fecha` ni reabre el archivo. El
    caller real (el job de Fase 9) llama esto una vez por lote, sobre las
    filas que ya tiene en memoria de ESE lote, y suma el resultado entre
    lotes -- por eso esto NUNCA es una segunda pasada sobre el archivo
    completo, solo una lectura más del mismo objeto en memoria."""
    histograma: Dict[Tuple[int, int], int] = {}
    for fila in filas_staging:
        if es_solo_detalle(fila):
            continue
        clave = (fila.payload["anio"], fila.payload["mes"])
        histograma[clave] = histograma.get(clave, 0) + 1
    return histograma


def fecha_maxima_de_filas(filas_staging: Sequence[CargaFilaStaging]) -> Optional[date]:
    """Fecha de venta mas reciente entre las filas staged de ESTE lote, leida
    del `payload` (`anio`/`mes`/`dia`) sin reinterpretar `Fecha`. Las filas
    staged por una version anterior no traen `dia` y se ignoran; `None` si
    ninguna lo trae. El caller acumula el maximo entre lotes, igual que el
    histograma."""
    fechas = [
        date(fila.payload["anio"], fila.payload["mes"], fila.payload["dia"])
        for fila in filas_staging
        if "dia" in fila.payload and not es_solo_detalle(fila)
    ]
    return max(fechas, default=None)


def evaluar_periodo_declarado(
    filas_por_periodo: Dict[Tuple[int, int], int],
    periodo_desde: date,
    periodo_hasta: date,
    tolerancia_pct: Optional[float] = None,
) -> periodo_mod.VeredictoPeriodo:
    """Envoltorio delgado sobre `periodo.evaluar_periodo` (ADR-9): calcula
    el conjunto `D` de meses declarados a partir de
    `carga_archivo.periodo_desde/hasta` (autoritativo, nunca reemplazado por
    lo detectado) y aplica el default de `settings` cuando el caller no fija
    una tolerancia explícita -- así un test puede fijar la tolerancia sin
    parchear `settings`, y el job real de Fase 9 puede omitir el argumento
    sin más."""
    tolerancia = (
        tolerancia_pct
        if tolerancia_pct is not None
        else settings.MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT
    )
    meses_declarados = periodo_mod.meses_en_rango(periodo_desde, periodo_hasta)
    return periodo_mod.evaluar_periodo(filas_por_periodo, meses_declarados, tolerancia)


async def aplicar_con_periodo(
    session,
    filas_staging: Sequence[CargaFilaStaging],
    periodo_desde: date,
    periodo_hasta: date,
    carga_id: uuid.UUID,
    tolerancia_pct: Optional[float] = None,
) -> periodo_mod.VeredictoPeriodo:
    """Punto de integración de ADR-9: evalúa el período declarado contra el
    histograma de `filas_staging` y SOLO agrega/aplica (`agregar_unidades`
    + `aplicar`) cuando el veredicto NO es `RECHAZO`. Sobre `RECHAZO` no se
    ejecuta ningún `session.execute` -- ni una fila de `venta_mensual` se
    toca, lo que reproduce exactamente el comportamiento que el bug
    histórico real necesitaba (design ADR-9, edge case E1: archivo
    mal-etiquetado rechazado ENTERO, un agosto previo correcto queda
    intacto porque nada lo sobrescribe).

    Sobre `ADVERTENCIA` (regla 2, meses adyacentes dentro de tolerancia),
    las filas cuyo `(anio, mes)` NO está en el período declarado se
    EXCLUYEN de la agregación -- design regla 2, verbatim: "those rows are
    rejected individually to carga_error ... so they never reach
    venta_mensual; the rest applies". Sin este filtro, el upsert
    REPLACE-not-sum de ADR-4 sobrescribiría el mes adyacente (p.ej. un
    agosto ya correcto) con solo el puñado de filas sueltas de ESTE
    archivo -- exactamente el tipo de corrupción silenciosa que ADR-9
    existe para prevenir, a menor escala que el rechazo total de E1.

    Deliberadamente NO decide `carga_archivo.estado`/`log`, ni borra
    staging, ni PERSISTE el `carga_error` de cada fila excluida
    (`A-CARGA-043`) -- eso sigue siendo responsabilidad exclusiva del
    caller (Fase 9), que además es quien conoce `carga_id` como fila real de
    `carga_archivo`, no solo como FK de agregación. Lo que SÍ hace esta
    función, dentro de su propio alcance puro, es garantizar que esas filas
    nunca lleguen a `venta_mensual`."""
    meses_declarados = periodo_mod.meses_en_rango(periodo_desde, periodo_hasta)
    veredicto = evaluar_periodo_declarado(
        construir_filas_por_periodo(filas_staging), periodo_desde, periodo_hasta, tolerancia_pct
    )
    if veredicto.tipo == periodo_mod.TipoVeredictoPeriodo.RECHAZO:
        return veredicto

    filas_dentro_de_periodo = [
        fila for fila in filas_staging
        if (fila.payload["anio"], fila.payload["mes"]) in meses_declarados
    ]
    totales = agregar_unidades(filas_dentro_de_periodo)
    await aplicar(session, totales, carga_id)
    await aplicar_detalle(session, filas_dentro_de_periodo, carga_id)
    return veredicto
