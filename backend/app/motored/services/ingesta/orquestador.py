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
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.database import motored_session_maker
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.proveedor import Proveedor
from app.motored.schemas.carga import CargaResultado
from app.motored.services import parametros
from app.motored.services import storage
from app.motored.services.carga_excel import CargaExcelError
from app.motored.services.ingesta import backorder as backorder_mod
from app.motored.services.ingesta import columnas as columnas_mod
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
from app.motored.services.trabajos import jobs
from app.motored.services.trabajos.supervisor import POOL_INGESTA

logger = logging.getLogger("motored.ingesta.orquestador")

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

_COLUMNAS_POR_TIPO: Dict[str, Tuple[str, ...]] = {
    "VENTAS": ventas_mod.COLUMNAS_ESPERADAS,
    "INVENTARIO": inventario_mod.COLUMNAS_ESPERADAS,
    "BACKORDER": backorder_mod.COLUMNAS_ESPERADAS,
    "FACTURAS_PEDIDOS": facturas_mod.COLUMNAS_ESPERADAS,
    "INGRESOS_FACTURAS": ingresos_mod.COLUMNAS_ESPERADAS,
    "DEMANDA_PERDIDA": demanda_perdida_mod.COLUMNAS_ESPERADAS,
}

_COLUMNAS_OPCIONALES_POR_TIPO: Dict[str, Tuple[str, ...]] = {
    "BACKORDER": backorder_mod.COLUMNAS_OPCIONALES,
}


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
    (`proveedor.es_principal`), sin un solo caller hasta este batch."""
    result = await db.execute(select(Proveedor.id).where(Proveedor.es_principal.is_(True)))
    ids = result.scalars().all()
    if len(ids) != 1:
        raise ProveedorPrincipalError(
            f"Se esperaba exactamente un proveedor principal (es_principal=true); "
            f"se encontraron {len(ids)}."
        )
    return ids[0]


async def _construir_procesador_fila(
    tipo: str,
    db: AsyncSession,
    mapa_columnas: Dict[str, int],
    cache: resolucion_mod.CacheResolucion,
    carga_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    en_fecha: date,
) -> Callable[[Sequence[Any], int, int], Tuple[Optional[CargaFilaStaging], List[Any]]]:
    """Fábrica: resuelve los parámetros de negocio de `tipo` vía
    `parametros.py` (nunca hardcodeados, ver docstring del módulo) y arma un
    callable de firma uniforme `(fila_raw, numero_fila, lote) ->
    (fila_staging, errores)` sobre el `procesar_fila` real de cada
    transform -- cuyas firmas difieren entre sí (ver cada módulo)."""
    if tipo == "VENTAS":
        tipos_inventario_incluidos = await parametros.resolver_tipos_inventario_incluidos(
            db, en_fecha
        )
        return lambda fila_raw, numero_fila, lote: ventas_mod.procesar_fila(
            fila_raw, numero_fila=numero_fila, lote=lote, mapa_columnas=mapa_columnas,
            cache=cache, carga_id=carga_id, proveedor_id=proveedor_id,
            tipos_inventario_incluidos=tipos_inventario_incluidos,
        )
    if tipo == "INVENTARIO":
        return lambda fila_raw, numero_fila, lote: inventario_mod.procesar_fila(
            fila_raw, numero_fila=numero_fila, lote=lote, mapa_columnas=mapa_columnas,
            cache=cache, carga_id=carga_id, proveedor_id=proveedor_id,
        )
    if tipo == "BACKORDER":
        estados_backorder_vigentes = await parametros.resolver_estados_backorder_vigentes(
            db, en_fecha
        )
        return lambda fila_raw, numero_fila, lote: backorder_mod.procesar_fila(
            fila_raw, numero_fila=numero_fila, lote=lote, mapa_columnas=mapa_columnas,
            cache=cache, carga_id=carga_id, proveedor_id=proveedor_id,
            estados_backorder_vigentes=estados_backorder_vigentes,
        )
    if tipo == "DEMANDA_PERDIDA":
        return lambda fila_raw, numero_fila, lote: demanda_perdida_mod.procesar_fila(
            fila_raw, numero_fila=numero_fila, lote=lote, mapa_columnas=mapa_columnas,
            cache=cache, carga_id=carga_id, proveedor_id=proveedor_id,
        )
    if tipo == "FACTURAS_PEDIDOS":
        return lambda fila_raw, numero_fila, lote: facturas_mod.procesar_fila(
            fila_raw, numero_fila=numero_fila, lote=lote, mapa_columnas=mapa_columnas,
            cache=cache, carga_id=carga_id, proveedor_id=proveedor_id,
        )
    if tipo == "INGRESOS_FACTURAS":
        return lambda fila_raw, numero_fila, lote: ingresos_mod.procesar_fila(
            fila_raw, numero_fila=numero_fila, lote=lote,
            mapa_columnas=mapa_columnas, carga_id=carga_id,
        )
    raise ValueError(f"Tipo de movimiento no soportado por el orquestador: {tipo!r}")


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
        self.histograma: Dict[Tuple[int, int], int] = {}


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
    estado.mapa_columnas = columnas_mod.construir_mapa_columnas(
        estado.fila_encabezado, tuple(columnas_esperadas) + tuple(columnas_opcionales)
    )
    faltantes = [c for c in columnas_esperadas if c not in estado.mapa_columnas]
    if faltantes:
        await _abortar_columna_faltante(session, carga, faltantes)
        raise _ArchivoAbortado()

    estado.procesar_fila = await _construir_procesador_fila(
        tipo, session, estado.mapa_columnas, cache, carga.id, proveedor_id, en_fecha
    )
    estado.numero_fila_absoluto += idx + 1
    return lote[idx + 1:]


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
        fila_staging, errores_fila = estado.procesar_fila(
            fila_raw, estado.numero_fila_absoluto, numero_lote
        )
        for error in errores_fila:
            session.add(error)
        if fila_staging is not None:
            session.add(fila_staging)
            staged_del_lote.append(fila_staging)
            estado.filas_validas += 1
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


async def _verificar_periodo_ventas(
    session: AsyncSession,
    carga: CargaArchivo,
    log: Dict[str, Any],
    histograma: Dict[Tuple[int, int], int],
) -> bool:
    """ADR-9 para VENTAS. Retorna `True` cuando `_dry_run` debe retornar
    de inmediato (RECHAZO: ya persistió `estado`/error/`log`, borró el
    staging y commiteó acá mismo -- design "a mislabeled period rejected
    ENTIRE, a previously-correct month stays intact"). Retorna `False`
    para ACEPTADO/ADVERTENCIA -- el archivo sigue su curso normal hacia
    `VALIDADO` en `_dry_run` (ADVERTENCIA ya dejó anotado un `carga_error`
    puntual por cada fila fuera de tolerancia antes de retornar)."""
    if carga.tipo != "VENTAS":
        return False

    log["filas_por_periodo"] = {
        f"{anio}-{mes:02d}": cantidad for (anio, mes), cantidad in histograma.items()
    }
    veredicto = ventas_mod.evaluar_periodo_declarado(
        histograma, carga.periodo_desde, carga.periodo_hasta
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
            clave = (fila.payload["anio"], fila.payload["mes"])
            if clave not in meses_declarados:
                session.add(errores_mod.construir_error(
                    carga.id, fila.fila, "Fecha", None,
                    periodo_mod.CODIGO_FILA_FUERA_DE_PERIODO,
                    "La fecha de esta fila cae fuera del período declarado "
                    "(dentro de tolerancia).",
                ))
    return False


async def _dry_run(session: AsyncSession, carga: CargaArchivo) -> None:
    tipo = carga.tipo
    columnas_esperadas = _COLUMNAS_POR_TIPO[tipo]
    columnas_opcionales = _COLUMNAS_OPCIONALES_POR_TIPO.get(tipo, ())

    loop = asyncio.get_event_loop()
    file_bytes = await loop.run_in_executor(
        POOL_INGESTA, storage.descargar_archivo, carga.ruta_objeto
    )
    cache = await resolucion_mod.construir_cache(session)
    proveedor_id = await resolver_proveedor_principal(session)
    en_fecha = carga.periodo_desde or date.today()

    estado = _EstadoLoteDryRun()
    numero_lote = 0

    async for lote in lector_mod.leer_lotes(file_bytes):
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
            for clave, cantidad in ventas_mod.construir_filas_por_periodo(staged_del_lote).items():
                estado.histograma[clave] = estado.histograma.get(clave, 0) + cantidad

        carga.filas_leidas = estado.filas_leidas
        carga.filas_validas = estado.filas_validas
        carga.filas_rechazadas = estado.filas_rechazadas
        carga.lotes_staged = numero_lote
        carga.latido_en = datetime.now(timezone.utc)
        await session.commit()

    if estado.fila_encabezado is None:
        carga.estado = "CON_ERRORES"
        session.add(errores_mod.construir_error(
            carga.id, 0, None, None, CODIGO_ENCABEZADO_NO_ENCONTRADO,
            "No se encontró una fila de encabezado reconocible para este tipo de archivo.",
        ))
        await session.commit()
        return

    log: Dict[str, Any] = dict(carga.log or {})
    await _verificar_corte_backorder(session, carga, log)
    if await _verificar_periodo_ventas(session, carga, log, estado.histograma):
        return

    carga.estado = "CON_ERRORES" if estado.filas_validas == 0 else "VALIDADO"
    carga.log = log
    await session.commit()


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


async def _recalcular_transito(session: AsyncSession) -> None:
    """Recalcula el cruce de tránsito completo (§5.6) -- disparado al
    aplicar CUALQUIERA de los dos tipos que lo alimentan
    (`FACTURAS_PEDIDOS`/`INGRESOS_FACTURAS`), sobre TODO lo persistido, no
    solo lo de esta carga: un ingreso cargado ayer puede recién cruzar hoy
    contra una factura cargada hoy, y viceversa.

    DECISIÓN DOCUMENTADA (deviation, ver apply-progress): ni FACTURAS_
    PEDIDOS ni INGRESOS_FACTURAS declaran período (ADR-9) -- no existe una
    fuente de `fecha_corte` para este cruce en el diseño. Se usa
    `date.today()` como corte del chequeo `transito_vencido`, señalado para
    confirmación del owner."""
    hoy = date.today()
    dias_ventana = await parametros.resolver_dias_ventana_ingresos(session, hoy)
    tolerancia = await parametros.resolver_tolerancia_ingreso_pct(session, hoy)

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
        await ventas_mod.aplicar_con_periodo(
            session, filas_staging, carga.periodo_desde, carga.periodo_hasta, carga.id
        )
    elif tipo == "INVENTARIO":
        consolidado = inventario_mod.consolidar_existencias(filas_staging)
        await inventario_mod.aplicar(session, consolidado, carga.periodo_desde, carga.id)
    elif tipo == "BACKORDER":
        consolidado = backorder_mod.consolidar_lineas(filas_staging)
        await backorder_mod.aplicar(session, consolidado, carga.periodo_desde, carga.id)
    elif tipo == "DEMANDA_PERDIDA":
        totales = demanda_perdida_mod.agregar_cantidad_solicitada(filas_staging)
        await demanda_perdida_mod.aplicar(session, totales, carga.periodo_desde, carga.id)
    elif tipo == "FACTURAS_PEDIDOS":
        consolidado = facturas_mod.agregar_lineas(filas_staging)
        await facturas_mod.aplicar(session, consolidado, carga.id)
        await _recalcular_transito(session)
    elif tipo == "INGRESOS_FACTURAS":
        consolidado = ingresos_mod.agregar_documentos(filas_staging)
        await ingresos_mod.aplicar(session, consolidado, carga.id)
        await _recalcular_transito(session)
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
