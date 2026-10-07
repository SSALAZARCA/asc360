"""
Motored Pedidos — Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), task 9.4
(sdd/motored-pedidos-ingesta; design ADR-1/ADR-2/ADR-5/ADR-8/ADR-9, §Data
Flow, §API).

Orquesta lo que las Phases 3-8 dejaron listo pero deliberadamente sin
wiring: compone `lector`+`columnas`+`resolucion`+`errores`+`periodo`+cada
transform (`ventas`/`inventario`/`backorder`/`demanda_perdida`/`facturas`/
`ingresos`+`transito`) en los puntos de entrada que `api/cargas.py` invoca,
directa (`MAESTRO_*`, síncrono) o indirectamente (los 6 tipos de
movimiento, vía `JobRunner`).

Responsabilidades que NINGÚN módulo anterior tenía dueño (confirmado por
lectura directa de cada docstring "Fase 9" antes de este batch) y que por
lo tanto viven ACÁ:

- **Resolver `proveedor_id`**: NUNCA fue un `parametro_metodologia` (Phase
  9a confirmó, `apply-progress-phase9a`, que esa clave no existe ahí) --
  se resuelve contra el maestro real `proveedor.es_principal = true`
  (Fase 1, sin un solo caller hasta ahora), fallando con un error de
  dominio tipado (nunca un 500) si no hay ninguno o hay más de uno.
- **"Columna obligatoria faltante aborta todo el archivo"** (spec): ningún
  transform module lo implementaba -- cada `procesar_fila` asume que
  `mapa_columnas` YA tiene todo lo necesario. Se verifica ACÁ, antes de
  procesar la primera fila de datos.
- **Detección del encabezado real** (`columnas.encontrar_fila_encabezado`)
  aplicada al archivo REAL, lote a lote -- los transforms solo reciben un
  `mapa_columnas` ya resuelto.
- **El veredicto de período (ADR-9) decide `estado` en el dry-run**; el
  mismo veredicto se re-evalúa (determinístico, sobre las mismas filas
  staged) en `Aplicar` -- exactamente la separación que
  `ventas.evaluar_periodo_declarado`/`aplicar_con_periodo` documentan.
- **La advertencia "PARCIAL" de BACKORDER (task 9.6)** se calcula al cierre
  del dry-run y se persiste en `carga_archivo.log`, nunca cambia `estado`.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import (
    Any, Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple,
)

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.database import motored_session_maker
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.proveedor import Proveedor
from app.motored.schemas.carga import CargaResultado
from app.motored.services import kpi_resumen, parametros, parametros_claves
from app.motored.services import storage
from app.motored.services.carga_excel import CargaExcelError
from app.motored.services.ingesta import backorder as backorder_mod
from app.motored.services.ingesta import columnas as columnas_mod
from app.motored.services.ingesta import deteccion as deteccion_mod
from app.motored.services.ingesta import demanda_perdida as demanda_perdida_mod
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import facturas as facturas_mod
from app.motored.services.ingesta import ingresos as ingresos_mod
from app.motored.services.ingesta import inventario as inventario_mod
from app.motored.services.ingesta import lector as lector_mod
from app.motored.services.ingesta import maestros_adapter
from app.motored.services.ingesta import periodo as periodo_mod
from app.motored.services.ingesta import resolucion as resolucion_mod
from app.motored.services.ingesta import transito as transito_mod
from app.motored.services.ingesta import ventas as ventas_mod
from app.motored.services.ingesta import ventas_lineas as lineas_mod
from app.motored.services.trabajos import jobs
from app.motored.services.trabajos.supervisor import POOL_INGESTA

logger = logging.getLogger("motored.ingesta.orquestador")

CLAVE_TOLERANCIA_PERIODO = "periodo_tolerancia_pct"
# Ultimo valor leido bien: si una lectura falla, se sigue con este.
_memoria_tolerancia: dict = {}
_memoria_bodegas_excluidas: dict = {}
_memoria_tipos_excluidos: dict = {}

TIPOS_MOVIMIENTO: Tuple[str, ...] = (
    "VENTAS",
    "INVENTARIO",
    "BACKORDER",
    "FACTURAS_PEDIDOS",
    "INGRESOS_FACTURAS",
    "DEMANDA_PERDIDA",
)

TIPOS_MAESTRO: Tuple[str, ...] = ("MAESTRO_REFERENCIAS", "MAESTRO_BODEGAS")

# Ambos son errores de ARCHIVO COMPLETO (`fila=0`), igual categoría que los
# `E-CARGA-0XX` que `periodo.py` ya centraliza para ADR-9 -- numerados en la
# misma serie (review-readability) en vez de quedar como strings sueltas sin
# número, la única inconsistencia que tenían contra ese esquema ya establecido.
CODIGO_COLUMNA_OBLIGATORIA_FALTANTE = "E-CARGA-046"
CODIGO_ENCABEZADO_NO_ENCONTRADO = "E-CARGA-047"
CODIGO_ENCABEZADO_DUPLICADO = "E-CARGA-048"
CODIGO_SIN_FILAS_VALIDAS = "E-CARGA-049"
CODIGO_NINGUNA_LINEA_INCLUIDA = "E-CARGA-051"

_COLUMNAS_POR_TIPO: Dict[str, Tuple[str, ...]] = {
    "VENTAS": ventas_mod.COLUMNAS_ESPERADAS,
    "INVENTARIO": inventario_mod.COLUMNAS_ESPERADAS,
    "BACKORDER": backorder_mod.COLUMNAS_ESPERADAS,
    "FACTURAS_PEDIDOS": facturas_mod.COLUMNAS_ESPERADAS,
    "INGRESOS_FACTURAS": ingresos_mod.COLUMNAS_ESPERADAS,
    "DEMANDA_PERDIDA": demanda_perdida_mod.COLUMNAS_ESPERADAS,
}


# Alias de columnas opcionales que se MAPEAN pero no van a la plantilla
# (`deteccion.COLUMNAS_OPCIONALES_POR_TIPO` sí va): los 4 alias del C.O.
# de VENTAS no deben aparecer como 4 columnas en la plantilla.
_ALIAS_OPCIONALES_POR_TIPO: Dict[str, Tuple[str, ...]] = {
    "VENTAS": ventas_mod.ALIAS_COLUMNA_CO,
}


def _columnas_opcionales(tipo: str) -> Tuple[str, ...]:
    """Columnas que el encabezado puede traer sin ser obligatorias."""
    return (deteccion_mod.COLUMNAS_OPCIONALES_POR_TIPO.get(tipo, ())
            + _ALIAS_OPCIONALES_POR_TIPO.get(tipo, ()))


class ProveedorPrincipalError(Exception):
    """`proveedor.es_principal` no resuelve a EXACTAMENTE una fila -- nunca
    debe llegar como un 500/stack trace al usuario (project convention,
    spec §9.6 "the user never sees a stack trace")."""


class EstadoInvalidoParaAplicarError(Exception):
    """`estado` no es `VALIDADO` -- el caller (`api/cargas.py`) la traduce
    a un 409, nunca una excepción cruda."""


async def resolver_proveedor_principal(db: AsyncSession) -> uuid.UUID:
    """Único lookup real de `proveedor_id` para los 6 tipos de movimiento
    -- NINGUNO trae su propio código de proveedor en el archivo (todos son
    del proveedor HMCL). No es un `parametro_metodologia` (Phase 9a
    confirmó que esa clave no existe ahí) -- es un maestro real, Fase 1
    (`proveedor.es_principal`), sin un solo caller hasta este batch.

    Desde motored-referencia-identidad el proveedor ya NO participa en la
    resolución de referencias (se resuelven por código); los procesadores de
    fila lo siguen recibiendo por compatibilidad de firma y el orquestador
    sigue exigiendo que exista exactamente un principal."""
    result = await db.execute(select(Proveedor.id).where(Proveedor.es_principal.is_(True)))
    ids = result.scalars().all()
    if len(ids) != 1:
        raise ProveedorPrincipalError(
            f"Se esperaba exactamente un proveedor principal (es_principal=true); "
            f"se encontraron {len(ids)}."
        )
    return ids[0]


async def _leer_bodegas_excluidas(
    db: AsyncSession,
) -> FrozenSet[str]:
    """Una lectura por carga de `bodegas_excluidas`. Sin fila vigente vale
    el default del registro. Nunca lanza; sin rollback porque la carga
    tiene trabajo pendiente."""
    clave = parametros_claves.CLAVE_BODEGAS_EXCLUIDAS
    valores = await parametros.leer_con_memoria(
        db, datetime.now(timezone.utc).date(),
        {clave: list(parametros_claves.BODEGAS_EXCLUIDAS_DEFAULT)},
        _memoria_bodegas_excluidas, deshacer=False)
    return resolucion_mod.normalizar_bodegas_excluidas(valores[clave])


async def _leer_tipos_excluidos(db: AsyncSession) -> lineas_mod.ReglasExcluidas:
    """Una lectura por carga de `ventas_tipos_excluidos`. Mismo contrato
    que `_leer_bodegas_excluidas`: nunca lanza, sin rollback."""
    clave = parametros_claves.CLAVE_VENTAS_TIPOS_EXCLUIDOS
    valores = await parametros.leer_con_memoria(
        db, datetime.now(timezone.utc).date(),
        {clave: list(parametros_claves.REGISTRO[clave].default)},
        _memoria_tipos_excluidos, deshacer=False)
    return lineas_mod.compilar_excluidos(valores[clave])


ProcesadorFila = Callable[
    [Sequence[Any], int, int], Tuple[Optional[CargaFilaStaging], List[Any]]
]
_Construido = Tuple[ProcesadorFila, Dict[str, Any]]


def _con_parametros(modulo: Any, comunes: Dict[str, Any],
                    **extra: Any) -> ProcesadorFila:
    """Callable uniforme `(fila_raw, numero_fila, lote)` sobre el
    `procesar_fila` de `modulo` (se busca al llamar), con `comunes` y los
    parametros propios del tipo (`extra`)."""
    def procesar(fila_raw, numero_fila, lote):
        return modulo.procesar_fila(
            fila_raw, numero_fila=numero_fila, lote=lote,
            **comunes, **extra)
    return procesar


async def _procesador_ventas(db, en_fecha, comunes) -> _Construido:
    # Las lineas que cuentan son las `lineas_comerciales` vigentes (como las
    # lee el KPI); `tipos_inventario_incluidos` ya no interviene en VENTAS.
    lineas = await lineas_mod.leer_lineas_comerciales(db, en_fecha)
    bodegas_excluidas = await _leer_bodegas_excluidas(db)
    # El mapa C.O. se lee solo si el archivo trae la columna: sin ella la
    # resolución sigue siendo por bodega.
    sucursal_por_co = None
    if ventas_mod.tiene_columna_co(comunes["mapa_columnas"]):
        sucursal_por_co = await resolucion_mod.leer_sucursal_por_co(db)
    return _con_parametros(
        ventas_mod, comunes, lineas_incluidas=lineas,
        bodegas_excluidas=bodegas_excluidas,
        sucursal_por_co=sucursal_por_co,
        tipos_excluidos=await _leer_tipos_excluidos(db),
        linea_por_referencia=await lineas_mod.leer_lineas(db)), {}


async def _procesador_inventario(db, en_fecha, comunes) -> _Construido:
    bodegas_excluidas = await _leer_bodegas_excluidas(db)
    return _con_parametros(
        inventario_mod, comunes, bodegas_excluidas=bodegas_excluidas), {}


async def _procesador_backorder(db, en_fecha, comunes) -> _Construido:
    resolver = parametros.resolver_estados_backorder_vigentes
    estados, fue_default = await resolver(db, en_fecha)
    defaults = {}
    if fue_default:
        defaults[parametros.CLAVE_ESTADOS_BACKORDER_VIGENTES] = estados
    return _con_parametros(
        backorder_mod, comunes, estados_backorder_vigentes=estados), defaults


def _procesador_simple(modulo: Any):
    async def construir(db, en_fecha, comunes) -> _Construido:
        return _con_parametros(modulo, comunes), {}
    return construir


async def _procesador_ingresos(db, en_fecha, comunes) -> _Construido:
    # INGRESOS_FACTURAS no resuelve sucursal ni referencia.
    propios = {k: comunes[k] for k in ("mapa_columnas", "carga_id")}
    return _con_parametros(ingresos_mod, propios), {}


_CONSTRUCTORES_PROCESADOR = {
    "VENTAS": _procesador_ventas,
    "INVENTARIO": _procesador_inventario,
    "BACKORDER": _procesador_backorder,
    "DEMANDA_PERDIDA": _procesador_simple(demanda_perdida_mod),
    "FACTURAS_PEDIDOS": _procesador_simple(facturas_mod),
    "INGRESOS_FACTURAS": _procesador_ingresos,
}


async def _construir_procesador_fila(
    tipo: str,
    db: AsyncSession,
    mapa_columnas: Dict[str, int],
    cache: resolucion_mod.CacheResolucion,
    carga_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    en_fecha: date,
) -> _Construido:
    """Fábrica: resuelve los parámetros de negocio de `tipo` vía
    `parametros.py` (nunca hardcodeados, ver docstring del módulo) y arma un
    callable de firma uniforme `(fila_raw, numero_fila, lote) ->
    (fila_staging, errores)` sobre el `procesar_fila` real de cada
    transform -- cuyas firmas difieren entre sí (ver cada módulo). Cada
    tipo tiene su constructor en `_CONSTRUCTORES_PROCESADOR`.

    Retorna también `defaults_usados` (verify-report WARNING #2): un dict
    `{clave: valor}` con cada `parametro_metodologia` que resolvió a su
    default codificado (nunca uno que vino de una fila vigente) -- vacío si
    ninguno defaulteó. El caller (`_resolver_encabezado`) lo cuelga de
    `estado.parametros_default_usados` para que `_dry_run` lo persista en
    `carga.log`."""
    construir = _CONSTRUCTORES_PROCESADOR.get(tipo)
    if construir is None:
        raise ValueError(
            f"Tipo de movimiento no soportado por el orquestador: {tipo!r}")
    comunes = dict(
        mapa_columnas=mapa_columnas, cache=cache, carga_id=carga_id,
        proveedor_id=proveedor_id)
    return await construir(db, en_fecha, comunes)


async def ejecutar_dry_run(carga_id: uuid.UUID) -> None:
    """Handler registrado en `jobs.JOB_HANDLERS` para los 6 tipos de
    movimiento (ADR-1: `InlineRunner` lo llama directo en tests, el
    supervisor real lo despacha en producción). Abre su PROPIA sesión --
    mismo patrón que `supervisor.run_tick` -- ningún caller le pasa una."""
    session_maker = motored_session_maker()
    async with session_maker() as session:
        carga = await session.get(CargaArchivo, carga_id)
        if carga is None:
            return
        try:
            await _dry_run(session, carga)
        except Exception:  # noqa: BLE001 -- nunca debe tirar el loop del supervisor
            logger.exception("orquestador.ejecutar_dry_run: fallo procesando %s", carga_id)
            await session.rollback()
            carga = await session.get(CargaArchivo, carga_id)
            if carga is not None:
                carga.estado = "CON_ERRORES"
                carga.log = {
                    **(carga.log or {}),
                    "error_interno": "Ocurrió un error inesperado al procesar el archivo.",
                }
                await session.commit()


class _EstadoLoteDryRun:
    """Estado mutable acumulado a través de los lotes de UN dry-run --
    agrupa lo que antes eran variables locales sueltas de `_dry_run`
    (review-readability: la función original mezclaba lectura de lotes,
    detección de encabezado, guard de columna faltante, procesamiento por
    fila y los dos cross-checks de cierre en un solo cuerpo de ~150
    líneas, obligando al lector a rastrear 8 variables para saber cuáles
    seguían "vivas" en cada fase). Ahora las funciones de apoyo reciben/
    actualizan un solo objeto en vez de una lista larga de parámetros."""

    def __init__(self) -> None:
        self.fila_encabezado: Optional[Sequence[Any]] = None
        self.mapa_columnas: Dict[str, int] = {}
        self.procesar_fila: Optional[Callable] = None
        self.numero_fila_absoluto = 0
        self.filas_leidas = 0
        self.filas_validas = 0
        self.filas_rechazadas = 0
        # Filas con AL MENOS un `carga_error` (rechazadas + las staged con
        # sucursal/referencia sin resolver, que `Aplicar` excluye): lo que el
        # informe muestra como "filas con errores que no se cargaron".
        self.filas_con_error = 0
        self.filas_solo_detalle = 0
        # Filas de una bodega que no es tienda (`bodegas_excluidas`):
        # ignoradas sin staging ni error.
        self.filas_bodega_excluida = 0
        # Filas de VENTAS con la columna C.O. vacía, resueltas por bodega.
        self.filas_co_vacio = 0
        # Filas de VENTAS cuya celda `Costo promedio total` no se pudo
        # interpretar (quedó NULL, sin error de fila).
        self.filas_costo_invalido = 0
        # Filas de VENTAS por línea del maestro (ver `ventas_lineas`).
        self.filas_tipo_excluido = 0
        self.filas_fuera_de_linea = 0
        self.filas_sin_linea = 0
        # VENTAS rows that really enter venta_mensual: an included line with a
        # resolved referencia (an unknown code is not "kept").
        self.filas_conservadas = 0
        self.histograma: Dict[Tuple[int, int], int] = {}
        # Fecha de venta mas reciente del archivo (solo VENTAS), acumulada en
        # la misma pasada que `histograma`; `_verificar_periodo_ventas` la
        # deja en `log["fecha_max_detectada"]` (ADR-12).
        self.fecha_max: Optional[date] = None
        # Verify-report WARNING #2: `{clave: valor}` de cada
        # `parametro_metodologia` que resolvió a su default codificado
        # durante este dry-run (poblado por `_construir_procesador_fila`,
        # vía `_resolver_encabezado`) -- `_dry_run` lo vuelca a `carga.log`
        # al cierre, mismo tratamiento que `histograma`/`filas_por_periodo`.
        self.parametros_default_usados: Dict[str, Any] = {}


class _ArchivoAbortado(Exception):
    """Señal interna -- NUNCA sale de `_dry_run`. El abort de "columna
    obligatoria faltante" (`_abortar_columna_faltante`) ya persistió
    `estado`/`log`/`carga_error` y commiteó; esta excepción solo le avisa
    al `async for` de `_dry_run` que tiene que retornar sin más."""


async def _abortar_columna_faltante(
    session: AsyncSession, carga: CargaArchivo, faltantes: List[str]
) -> None:
    """spec "Missing mandatory columns abort the whole file"."""
    carga.estado = "CON_ERRORES"
    session.add(errores_mod.construir_error(
        carga.id, 0, None, ", ".join(faltantes),
        CODIGO_COLUMNA_OBLIGATORIA_FALTANTE,
        f"Faltan columnas obligatorias: {', '.join(faltantes)}.",
    ))
    carga.log = {**(carga.log or {}), "columnas_faltantes": faltantes}
    await session.commit()


async def _abortar_encabezado_duplicado(
    session: AsyncSession, carga: CargaArchivo, error: columnas_mod.EncabezadoDuplicadoError
) -> None:
    """Una columna esperada repetida en el encabezado aborta el archivo
    completo -- mismo contrato que `_abortar_columna_faltante`."""
    carga.estado = "CON_ERRORES"
    session.add(errores_mod.construir_error(
        carga.id, 0, None, ", ".join(error.columnas),
        CODIGO_ENCABEZADO_DUPLICADO, str(error),
    ))
    carga.log = {**(carga.log or {}), "columnas_duplicadas": error.columnas}
    await session.commit()


async def _resolver_encabezado(
    estado: _EstadoLoteDryRun,
    lote: Sequence[Sequence[Any]],
    tipo: str,
    columnas_esperadas: Tuple[str, ...],
    columnas_opcionales: Tuple[str, ...],
    session: AsyncSession,
    cache: resolucion_mod.CacheResolucion,
    carga: CargaArchivo,
    proveedor_id: uuid.UUID,
    en_fecha: date,
) -> Optional[Sequence[Sequence[Any]]]:
    """Busca el encabezado en `lote` -- la PRIMERA vez que `_dry_run` lo
    necesita, nunca de nuevo (el caller solo llama esto mientras `estado.
    fila_encabezado` sigue en `None`). Arma `estado.procesar_fila` para el
    resto del archivo si lo encuentra. Retorna la porción de `lote` que es
    dato real (después del encabezado), o `None` si este lote no lo tiene
    (el caller sigue escaneando el próximo lote). Lanza `_ArchivoAbortado`
    si el encabezado se encontró pero falta una columna obligatoria -- ya
    persistido por `_abortar_columna_faltante`, el caller solo retorna."""
    try:
        idx = columnas_mod.encontrar_fila_encabezado(lote, columnas_esperadas)
    except columnas_mod.EncabezadoNoEncontradoError:
        estado.numero_fila_absoluto += len(lote)
        return None

    estado.fila_encabezado = lote[idx]
    try:
        estado.mapa_columnas = columnas_mod.construir_mapa_columnas(
            estado.fila_encabezado, tuple(columnas_esperadas) + tuple(columnas_opcionales)
        )
    except columnas_mod.EncabezadoDuplicadoError as error:
        await _abortar_encabezado_duplicado(session, carga, error)
        raise _ArchivoAbortado()
    faltantes = [c for c in columnas_esperadas if c not in estado.mapa_columnas]
    if faltantes:
        await _abortar_columna_faltante(session, carga, faltantes)
        raise _ArchivoAbortado()

    estado.procesar_fila, estado.parametros_default_usados = await _construir_procesador_fila(
        tipo, session, estado.mapa_columnas, cache, carga.id, proveedor_id, en_fecha
    )
    estado.numero_fila_absoluto += idx + 1
    return lote[idx + 1:]


def _contar_clase_de_linea(
    estado: "_EstadoLoteDryRun", fila: Optional[CargaFilaStaging]
) -> None:
    clase = fila.payload.get(lineas_mod.CLAVE_CLASE_LINEA) if fila else None
    if clase == lineas_mod.CLASE_FUERA_DE_LINEA:
        estado.filas_fuera_de_linea += 1
    elif clase == lineas_mod.CLASE_SIN_LINEA:
        estado.filas_sin_linea += 1
    elif clase == lineas_mod.CLASE_TIPO_EXCLUIDO:
        estado.filas_tipo_excluido += 1


def _procesar_filas_del_lote(
    estado: _EstadoLoteDryRun,
    datos_del_lote: Sequence[Sequence[Any]],
    numero_lote: int,
    session: AsyncSession,
) -> List[CargaFilaStaging]:
    """Procesa cada fila de `datos_del_lote` con `estado.procesar_fila`,
    acumulando en `estado` (leídas/válidas/rechazadas) y en `session`
    (staging/errores). Retorna las filas efectivamente staged de ESTE
    lote -- lo único que el caller necesita para el histograma de VENTAS."""
    staged_del_lote: List[CargaFilaStaging] = []
    for fila_raw in datos_del_lote:
        estado.numero_fila_absoluto += 1
        estado.filas_leidas += 1
        resultado = estado.procesar_fila(
            fila_raw, estado.numero_fila_absoluto, numero_lote
        )
        if resultado is resolucion_mod.MarcaFila.BODEGA_EXCLUIDA:
            estado.filas_bodega_excluida += 1
            continue
        if resultado is lineas_mod.MarcaTipoExcluido.TIPO_EXCLUIDO:
            estado.filas_tipo_excluido += 1
            continue
        fila_staging, errores_fila = resultado
        for error in errores_fila:
            session.add(error)
        if errores_fila:
            estado.filas_con_error += 1
        if fila_staging is not None and ventas_mod.tiene_co_vacio(
                fila_staging):
            estado.filas_co_vacio += 1
        if fila_staging is not None and ventas_mod.tiene_costo_invalido(
                fila_staging):
            estado.filas_costo_invalido += 1
        _contar_clase_de_linea(estado, fila_staging)
        if fila_staging is not None and ventas_mod.es_solo_detalle(fila_staging):
            # Solo alimenta `venta_detalle`: ni valida, ni al histograma ni a
            # `fecha_max` -- `venta_mensual` y el periodo no la ven.
            session.add(fila_staging)
            estado.filas_solo_detalle += 1
        elif fila_staging is not None:
            session.add(fila_staging)
            staged_del_lote.append(fila_staging)
            estado.filas_validas += 1
            if fila_staging.referencia_id is not None:
                estado.filas_conservadas += 1
        elif errores_fila:
            estado.filas_rechazadas += 1
        # Una fila descartada EN SILENCIO (sin staging, sin error) no
        # cuenta ni como válida ni como rechazada -- filtro de negocio o
        # excepción documentada de cada transform (ver su docstring).
    return staged_del_lote


async def _verificar_corte_backorder(
    session: AsyncSession, carga: CargaArchivo, log: Dict[str, Any]
) -> None:
    """Task 9.6: cross-check ADR-9 "PARCIAL" de BACKORDER -- muta `log` in
    place, NUNCA cambia `estado` (ver `backorder.evaluar_corte_declarado`,
    es un aviso, no un rechazo)."""
    if not (carga.tipo == "BACKORDER" and carga.periodo_desde is not None):
        return
    result = await session.execute(
        select(CargaFilaStaging).where(CargaFilaStaging.carga_id == carga.id)
    )
    veredicto_corte = backorder_mod.evaluar_corte_declarado(
        result.scalars().all(), carga.periodo_desde
    )
    if veredicto_corte.advertencia:
        log["backorder_corte_advertencia"] = {
            "codigo": periodo_mod.CODIGO_BACKORDER_CORTE_POSTERIOR,
            "filas": list(veredicto_corte.filas_posteriores),
        }


async def _leer_tolerancia_periodo(session: AsyncSession) -> float:
    """Una lectura por carga de `periodo_tolerancia_pct`. Sin fila vigente
    vale `MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT` (leido ahora). Nunca
    lanza; sin rollback porque la carga tiene trabajo pendiente."""
    valores = await parametros.leer_con_memoria(
        session, datetime.now(timezone.utc).date(),
        {CLAVE_TOLERANCIA_PERIODO:
         settings.MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT},
        _memoria_tolerancia, deshacer=False)
    return float(valores[CLAVE_TOLERANCIA_PERIODO])


async def _verificar_periodo_ventas(
    session: AsyncSession,
    carga: CargaArchivo,
    log: Dict[str, Any],
    histograma: Dict[Tuple[int, int], int],
    fecha_max: Optional[date] = None,
) -> bool:
    """ADR-9 para VENTAS. Retorna `True` cuando `_dry_run` debe retornar
    de inmediato (RECHAZO: ya persistió `estado`/error/`log`, borró el
    staging y commiteó acá mismo -- design "a mislabeled period rejected
    ENTIRE, a previously-correct month stays intact"). Retorna `False`
    para ACEPTADO/ADVERTENCIA -- el archivo sigue su curso normal hacia
    `VALIDADO` en `_dry_run` (ADVERTENCIA ya dejó anotado un `carga_error`
    puntual por cada fila fuera de tolerancia antes de retornar). Deja en
    `log["fecha_max_detectada"]` la fecha de venta mas reciente (ISO) cuando
    el archivo la trae."""
    if carga.tipo != "VENTAS":
        return False

    if fecha_max is not None:
        log["fecha_max_detectada"] = fecha_max.isoformat()
    log["filas_por_periodo"] = {
        f"{anio}-{mes:02d}": cantidad for (anio, mes), cantidad in histograma.items()
    }
    veredicto = ventas_mod.evaluar_periodo_declarado(
        histograma, carga.periodo_desde, carga.periodo_hasta,
        await _leer_tolerancia_periodo(session),
    )
    log["periodo_veredicto"] = veredicto.tipo.value

    if veredicto.tipo == periodo_mod.TipoVeredictoPeriodo.RECHAZO:
        carga.estado = "CON_ERRORES"
        session.add(errores_mod.construir_error(
            carga.id, 0, None, None, periodo_mod.CODIGO_PERIODO_NO_COINCIDE,
            "El período declarado no coincide con las fechas reales del archivo.",
        ))
        await session.execute(delete(CargaFilaStaging).where(CargaFilaStaging.carga_id == carga.id))
        carga.log = log
        await session.commit()
        return True

    if veredicto.tipo == periodo_mod.TipoVeredictoPeriodo.ADVERTENCIA:
        meses_declarados = periodo_mod.meses_en_rango(carga.periodo_desde, carga.periodo_hasta)
        result = await session.execute(
            select(CargaFilaStaging).where(CargaFilaStaging.carga_id == carga.id)
        )
        for fila in result.scalars().all():
            if ventas_mod.es_solo_detalle(fila):
                continue
            clave = (fila.payload["anio"], fila.payload["mes"])
            if clave not in meses_declarados:
                session.add(errores_mod.construir_error(
                    carga.id, fila.fila, "Fecha", None,
                    periodo_mod.CODIGO_FILA_FUERA_DE_PERIODO,
                    "La fecha de esta fila cae fuera del período declarado "
                    "(dentro de tolerancia).",
                ))
    return False


async def _registrar_progreso_lote(
    session: AsyncSession, carga: CargaArchivo, estado: "_EstadoLoteDryRun", numero_lote: int
) -> None:
    """Progreso persistido al cierre de CADA lote (no solo al final del
    archivo) -- lo que le permite a `GET /cargas/{id}` reportar avance
    parcial mientras un archivo grande sigue leyéndose (design "visible
    progress")."""
    carga.filas_leidas = estado.filas_leidas
    carga.filas_validas = estado.filas_validas
    carga.filas_rechazadas = estado.filas_rechazadas
    carga.lotes_staged = numero_lote
    carga.latido_en = datetime.now(timezone.utc)
    await session.commit()


def _volcar_contadores(log: Dict[str, Any], estado: "_EstadoLoteDryRun") -> None:
    """Los contadores del dry-run que el informe muestra; los que valen 0
    no se escriben (salvo `filas_con_error`)."""
    log["filas_con_error"] = estado.filas_con_error
    for clave, cantidad in (
        ("filas_solo_detalle", estado.filas_solo_detalle),
        ("filas_bodega_excluida", estado.filas_bodega_excluida),
        ("filas_co_vacio", estado.filas_co_vacio),
        ("filas_costo_invalido", estado.filas_costo_invalido),
        ("filas_tipo_excluido", estado.filas_tipo_excluido),
        ("filas_fuera_de_linea", estado.filas_fuera_de_linea),
        ("filas_sin_linea", estado.filas_sin_linea),
    ):
        if cantidad:
            log[clave] = cantidad


def _fijar_estado_final(
    session: AsyncSession, carga: CargaArchivo, estado: "_EstadoLoteDryRun"
) -> None:
    """`VALIDADO` si hay filas validas o filas sin linea esperando que un
    usuario las asigne; `CON_ERRORES` con un error de archivo completo si
    todas las filas con datos quedaron fuera de las lineas incluidas, o si
    no hay ninguna fila valida."""
    es_ventas = carga.tipo == "VENTAS"
    conservadas = estado.filas_conservadas if es_ventas else estado.filas_validas
    if conservadas or estado.filas_sin_linea:
        carga.estado = "VALIDADO"
        return
    carga.estado = "CON_ERRORES"
    if es_ventas and (estado.filas_validas or estado.filas_solo_detalle
                      or estado.filas_tipo_excluido):
        codigo, mensaje = CODIGO_NINGUNA_LINEA_INCLUIDA, lineas_mod.MENSAJE_NINGUNA_LINEA
    else:
        codigo, mensaje = CODIGO_SIN_FILAS_VALIDAS, (
            "El archivo no tiene ninguna fila válida para cargar. Revisá los errores "
            "por fila (si los hay) o que el archivo tenga datos, y volvé a cargarlo.")
    session.add(errores_mod.construir_error(carga.id, 0, None, None, codigo, mensaje))


async def _cerrar_dry_run(
    session: AsyncSession, carga: CargaArchivo, estado: "_EstadoLoteDryRun"
) -> None:
    """Todo lo que pasa DESPUÉS de terminar de leer el archivo completo: el
    abort por encabezado nunca encontrado, el volcado de `parametros_
    default_usados` (verify-report WARNING #2) + los dos chequeos de cierre
    de ADR-9 (corte de BACKORDER, veredicto de período de VENTAS), y el
    estado final `CON_ERRORES`/`VALIDADO` (cero filas válidas es
    `CON_ERRORES` con un error de archivo completo que lo explica)."""
    if estado.fila_encabezado is None:
        carga.estado = "CON_ERRORES"
        session.add(errores_mod.construir_error(
            carga.id, 0, None, None, CODIGO_ENCABEZADO_NO_ENCONTRADO,
            "No se encontró una fila de encabezado reconocible para este tipo de archivo.",
        ))
        await session.commit()
        return

    log: Dict[str, Any] = dict(carga.log or {})
    _volcar_contadores(log, estado)
    if estado.parametros_default_usados:
        log["parametros_default_usados"] = dict(estado.parametros_default_usados)
    await _verificar_corte_backorder(session, carga, log)
    if await _verificar_periodo_ventas(
        session, carga, log, estado.histograma, estado.fecha_max
    ):
        return

    _fijar_estado_final(session, carga, estado)
    carga.log = log
    await session.commit()


def _acumular_ventas_del_lote(
    estado: _EstadoLoteDryRun, staged_del_lote: Sequence[CargaFilaStaging]
) -> None:
    """Suma al `estado` el histograma por periodo y la fecha maxima de venta
    de ESTE lote (misma pasada, sin releer el archivo)."""
    for clave, cantidad in ventas_mod.construir_filas_por_periodo(staged_del_lote).items():
        estado.histograma[clave] = estado.histograma.get(clave, 0) + cantidad
    fecha_lote = ventas_mod.fecha_maxima_de_filas(staged_del_lote)
    if fecha_lote is not None and (estado.fecha_max is None or fecha_lote > estado.fecha_max):
        estado.fecha_max = fecha_lote


async def _dry_run(session: AsyncSession, carga: CargaArchivo) -> None:
    tipo = carga.tipo
    columnas_esperadas = _COLUMNAS_POR_TIPO[tipo]
    columnas_opcionales = _columnas_opcionales(tipo)

    loop = asyncio.get_event_loop()
    file_bytes = await loop.run_in_executor(
        POOL_INGESTA, storage.descargar_archivo, carga.ruta_objeto
    )
    cache = await resolucion_mod.construir_cache(session)
    proveedor_id = await resolver_proveedor_principal(session)
    en_fecha = carga.periodo_desde or date.today()

    estado = _EstadoLoteDryRun()
    numero_lote = 0

    async for lote in lector_mod.leer_lotes(file_bytes, columnas_esperadas=columnas_esperadas):
        numero_lote += 1

        if estado.fila_encabezado is None:
            try:
                datos_del_lote = await _resolver_encabezado(
                    estado, lote, tipo, columnas_esperadas, columnas_opcionales,
                    session, cache, carga, proveedor_id, en_fecha,
                )
            except _ArchivoAbortado:
                return
            if datos_del_lote is None:
                continue
        else:
            datos_del_lote = lote

        staged_del_lote = _procesar_filas_del_lote(estado, datos_del_lote, numero_lote, session)

        if tipo == "VENTAS" and staged_del_lote:
            _acumular_ventas_del_lote(estado, staged_del_lote)

        await _registrar_progreso_lote(session, carga, estado, numero_lote)

    await _cerrar_dry_run(session, carga, estado)


async def ejecutar_maestro(
    session: AsyncSession, carga: CargaArchivo, file_bytes: bytes, usuario_id: Optional[uuid.UUID]
) -> Optional[CargaResultado]:
    """`MAESTRO_REFERENCIAS`/`MAESTRO_BODEGAS` (ADR-5): síncrono dentro del
    mismo request de `POST /cargas` -- nunca pasa por `JobRunner`/staging,
    exactamente como Fase 1's `procesar_carga` ya funciona. Retorna el
    `CargaResultado` para que el endpoint pueda componer la respuesta, o
    `None` si `procesar_maestro` lanzó (ver guard abajo).

    GAP encontrado por review-resilience y corregido acá: `procesar_maestro`
    puede lanzar `CargaExcelError` (columna obligatoria faltante, archivo
    corrupto, etc. -- un caso de USUARIO rutinario, no una excepción rara) y
    nada en la cadena la capturaba. `MAESTRO_*` nunca pasa por `JobRunner`,
    así que no hay heartbeat/sweep que lo recupere -- antes de este fix, una
    `CargaExcelError` real dejaba la carga en `PENDIENTE` PARA SIEMPRE, con
    un 500 crudo en el request de subida (spec §9.6: "the user never sees a
    stack trace"). Ahora termina en `CON_ERRORES` con el mensaje real (para
    `CargaExcelError`) o uno genérico (cualquier otra excepción) en `log`,
    mismo contrato de "nunca debe tirar el loop"/"siempre un estado
    terminal" que `ejecutar_dry_run` ya aplica para los 6 tipos de
    movimiento."""
    try:
        resultado = await maestros_adapter.procesar_maestro(
            session, carga.id, carga.tipo, carga.nombre_archivo, file_bytes, usuario_id
        )
    except Exception as exc:
        logger.exception("orquestador.ejecutar_maestro: fallo procesando %s", carga.id)
        await session.rollback()
        carga_fresca = await session.get(CargaArchivo, carga.id)
        if carga_fresca is not None:
            mensaje = (
                str(exc) if isinstance(exc, CargaExcelError)
                else "Ocurrió un error inesperado al procesar el archivo."
            )
            carga_fresca.estado = "CON_ERRORES"
            carga_fresca.log = {**(carga_fresca.log or {}), "error_interno": mensaje}
            await session.commit()
        return None

    carga.filas_leidas = resultado.total_filas
    if resultado.ok:
        carga.filas_validas = resultado.total_filas
        carga.filas_rechazadas = 0
        carga.estado = "APLICADO"
        carga.aplicado_en = datetime.now(timezone.utc)
    else:
        carga.filas_validas = 0
        carga.filas_rechazadas = resultado.total_filas
        carga.estado = "CON_ERRORES"
    await session.commit()
    return resultado


async def _recalcular_transito(session: AsyncSession) -> Dict[str, Any]:
    """Recalcula el cruce de tránsito completo (§5.6) -- disparado al
    aplicar CUALQUIERA de los dos tipos que lo alimentan
    (`FACTURAS_PEDIDOS`/`INGRESOS_FACTURAS`), sobre TODO lo persistido, no
    solo lo de esta carga: un ingreso cargado ayer puede recién cruzar hoy
    contra una factura cargada hoy, y viceversa.

    DECISIÓN DOCUMENTADA (deviation, ver apply-progress): ni FACTURAS_
    PEDIDOS ni INGRESOS_FACTURAS declaran período (ADR-9) -- no existe una
    fuente de `fecha_corte` para este cruce en el diseño. Se usa
    `date.today()` como corte del chequeo `transito_vencido`, señalado para
    confirmación del owner.

    Retorna `defaults_usados` (verify-report WARNING #2, mismo contrato que
    `_construir_procesador_fila`): `{clave: valor}` de cada
    `parametro_metodologia` que resolvió a su default codificado -- el
    caller (`ejecutar_aplicar`) lo persiste en `carga.log`."""
    hoy = date.today()
    dias_ventana, dias_ventana_fue_default = await parametros.resolver_dias_ventana_ingresos(
        session, hoy
    )
    tolerancia, tolerancia_fue_default = await parametros.resolver_tolerancia_ingreso_pct(
        session, hoy
    )
    defaults_usados: Dict[str, Any] = {}
    if dias_ventana_fue_default:
        defaults_usados[parametros.CLAVE_DIAS_VENTANA_INGRESOS] = dias_ventana
    if tolerancia_fue_default:
        defaults_usados[parametros.CLAVE_TOLERANCIA_INGRESO_PCT] = tolerancia

    facturas_result = await session.execute(
        select(
            FacturaProveedorLinea.prefijo_rh,
            FacturaProveedorLinea.numero_rh,
            func.sum(FacturaProveedorLinea.valor_total),
            func.min(FacturaProveedorLinea.fecha_factura),
        ).group_by(FacturaProveedorLinea.prefijo_rh, FacturaProveedorLinea.numero_rh)
    )
    facturas_por_documento = {
        (prefijo, numero): transito_mod.DocumentoFactura(
            valor_total=valor if valor is not None else Decimal("0"), fecha_factura=fecha
        )
        for prefijo, numero, valor, fecha in facturas_result.all()
    }

    ingresos_result = await session.execute(
        select(
            IngresoFactura.prefijo_rh,
            IngresoFactura.numero_rh,
            func.sum(IngresoFactura.valor_neto),
        ).group_by(IngresoFactura.prefijo_rh, IngresoFactura.numero_rh)
    )
    ingresos_por_documento = {
        (prefijo, numero): valor for prefijo, numero, valor in ingresos_result.all()
    }

    veredictos = transito_mod.calcular_veredictos(
        facturas_por_documento, ingresos_por_documento, hoy, dias_ventana, tolerancia,
    )
    await transito_mod.aplicar(session, veredictos)
    return defaults_usados


async def _recalcular_transito_y_registrar_defaults(
    session: AsyncSession, carga: CargaArchivo
) -> None:
    """Envoltorio de `_recalcular_transito` para `ejecutar_aplicar`: además
    de disparar el recálculo, persiste cualquier default usado dentro de
    `carga.log["parametros_default_usados"]` -- a diferencia del dry-run
    (que arma `log` recién al cierre), `ejecutar_aplicar` no tenía NINGÚN
    escritor de `log` hasta este batch, así que este es el primero."""
    defaults_usados = await _recalcular_transito(session)
    if not defaults_usados:
        return
    log = dict(carga.log or {})
    existentes = dict(log.get("parametros_default_usados", {}))
    existentes.update(defaults_usados)
    log["parametros_default_usados"] = existentes
    carga.log = log


async def ejecutar_aplicar(session: AsyncSession, carga: CargaArchivo) -> None:
    """Punto de integración de `POST /cargas/{id}/aplicar` para los 6 tipos
    de movimiento. `MAESTRO_*` nunca llega acá -- ya quedó `APLICADO`/
    `CON_ERRORES` en `ejecutar_maestro`, síncrono en el POST (ADR-5).

    GAP DOCUMENTADO (ver apply-progress): ADR-2 describe que `Aplicar` debe
    re-resolver los `sucursal_id`/`referencia_id` en `NULL` contra los
    maestros VIGENTES antes de agregar -- pero el `payload` que cada
    transform ya shippeado (Phases 4/6/7/8) persiste en `carga_fila_
    staging` NUNCA guarda el texto/código original de esos campos, solo el
    id ya resuelto (o `None`). No hay con qué re-intentar la resolución acá
    sin ese texto -- las filas con `sucursal_id`/`referencia_id = None`
    simplemente quedan excluidas de la agregación, exactamente como cada
    `agregar_*`/`consolidar_*` ya hace por sí solo. Corregir esto requiere
    tocar el payload de 5 transforms, fuera del alcance de este batch."""
    try:
        await _aplicar_carga(session, carga)
    except kpi_resumen.ResumenOcupadoError:
        # A KPI rebuild holds the summaries' lock: nothing of this apply may survive (the
        # summary refresh runs in the apply's own transaction). The carga stays VALIDADO, so
        # the user can apply it again once the rebuild ends; the API answers 409.
        await session.rollback()
        raise


CLAVE_REEMPLAZA_MES = lineas_mod.CLAVE_REEMPLAZA_MES


def reemplaza_mes_completo(carga: CargaArchivo) -> bool:
    """La carga VENTAS pidio reemplazar el mes completo para toda la red
    (se guarda en `carga.log` al subirla)."""
    return carga.tipo == "VENTAS" and (carga.log or {}).get(
        CLAVE_REEMPLAZA_MES) is True


async def _aplicar_ventas(
    session: AsyncSession, carga: CargaArchivo,
    filas_staging: Sequence[CargaFilaStaging],
) -> None:
    """VENTAS contra el maestro VIGENTE: con una referencia sin línea no se
    escribe nada (409); las filas de una línea fuera de las incluidas se
    descartan. Un veredicto de período RECHAZO (las líneas asignadas pueden
    mover el histograma) tampoco aplica: la carga sigue VALIDADO."""
    en_fecha = carga.periodo_desde or date.today()
    incluidas = await lineas_mod.leer_lineas_comerciales(session, en_fecha)
    lineas = await lineas_mod.leer_lineas(
        session,
        {f.referencia_id for f in filas_staging if f.referencia_id})
    sin_linea = {
        f.referencia_id for f in filas_staging
        if lineas_mod.clase_de_staging(
            f.payload, f.referencia_id, lineas, incluidas)
        == lineas_mod.CLASE_SIN_LINEA}
    if sin_linea:
        raise EstadoInvalidoParaAplicarError(
            lineas_mod.mensaje_sin_linea(len(sin_linea)))
    aplicables = lineas_mod.reclasificar(filas_staging, lineas, incluidas)
    # "Consideradas": las que entran a venta_mensual o traen el error de su
    # referencia desconocida; las solo-detalle no cuentan.
    if filas_staging and not any(
            not a.payload.get("solo_detalle") and a.referencia_id is not None
            for a in aplicables):
        raise EstadoInvalidoParaAplicarError(lineas_mod.MENSAJE_NINGUNA_LINEA)
    aplicar = (ventas_mod.aplicar_reemplazando_meses
               if reemplaza_mes_completo(carga)
               else ventas_mod.aplicar_con_periodo)
    veredicto = await aplicar(
        session, aplicables,
        carga.periodo_desde, carga.periodo_hasta, carga.id,
        await _leer_tolerancia_periodo(session))
    if veredicto.tipo == periodo_mod.TipoVeredictoPeriodo.RECHAZO:
        raise EstadoInvalidoParaAplicarError(
            "El período declarado ya no coincide con las filas que se "
            "aplicarían; revise las líneas asignadas.")


async def _aplicar_carga(session: AsyncSession, carga: CargaArchivo) -> None:
    if carga.estado != "VALIDADO":
        raise EstadoInvalidoParaAplicarError(
            f"No se puede aplicar una carga en estado '{carga.estado}' (se esperaba VALIDADO)."
        )
    tipo = carga.tipo
    result = await session.execute(
        select(CargaFilaStaging).where(CargaFilaStaging.carga_id == carga.id)
    )
    filas_staging = result.scalars().all()

    if tipo == "VENTAS":
        await _aplicar_ventas(session, carga, filas_staging)
    elif tipo == "INVENTARIO":
        consolidado = inventario_mod.consolidar_existencias(filas_staging)
        await inventario_mod.aplicar(session, consolidado, carga.periodo_desde, carga.id)
        await inventario_mod.aplicar_detalle(session, filas_staging, carga.periodo_desde, carga.id)
    elif tipo == "BACKORDER":
        consolidado = backorder_mod.consolidar_lineas(filas_staging)
        await backorder_mod.aplicar(session, consolidado, carga.periodo_desde, carga.id)
    elif tipo == "DEMANDA_PERDIDA":
        totales = demanda_perdida_mod.agregar_cantidad_solicitada(filas_staging)
        await demanda_perdida_mod.aplicar(session, totales, carga.periodo_desde, carga.id)
    elif tipo == "FACTURAS_PEDIDOS":
        consolidado = facturas_mod.agregar_lineas(filas_staging)
        await facturas_mod.aplicar(session, consolidado, carga.id)
        await _recalcular_transito_y_registrar_defaults(session, carga)
    elif tipo == "INGRESOS_FACTURAS":
        consolidado = ingresos_mod.agregar_documentos(filas_staging)
        await ingresos_mod.aplicar(session, consolidado, carga.id)
        await _recalcular_transito_y_registrar_defaults(session, carga)
    else:
        raise ValueError(f"Tipo no soportado por aplicar: {tipo!r}")

    carga.estado = "APLICADO"
    carga.aplicado_en = datetime.now(timezone.utc)
    carga.ultimo_lote_aplicado = carga.lotes_staged
    carga.latido_en = datetime.now(timezone.utc)
    await session.execute(delete(CargaFilaStaging).where(CargaFilaStaging.carga_id == carga.id))
    await session.commit()


def registrar_handlers() -> None:
    """Registra `ejecutar_dry_run` para los 6 tipos de movimiento en
    `jobs.JOB_HANDLERS` (ADR-1) -- llamado al importar este módulo,
    idéntico criterio de "un registro posterior pisa al anterior" que
    `jobs.register_job` ya documenta."""
    for tipo in TIPOS_MOVIMIENTO:
        jobs.register_job(tipo, ejecutar_dry_run)


registrar_handlers()
