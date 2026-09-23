"""
Motored Pedidos — `parametro_metodologia` (sdd/motored-pedidos-cimientos,
Fase 3, task 3.6, §6.10). Versionado por INSERCIÓN: `registrar_cambio`
SIEMPRE agrega una fila nueva (`db.add`), jamás modifica ni hace `merge`/
UPDATE de una fila existente (spec "Updating a parameter creates a new
version").

Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), task 9.2 (sdd/motored-
pedidos-ingesta; spec "parametro_metodologia vigente-by-clave read path")
agrega `resolver()` -- el PRIMER lector real de esta tabla: Fase 1 sólo
construyó la estructura y el escritor (`registrar_cambio`/`obtener_
vigente`), sin un solo caller en todo el motor hasta ahora.
"""
import logging
import uuid
from datetime import date
from typing import Any, List, Optional

from sqlalchemy import select

from app.motored.models.parametro_metodologia import ParametroMetodologia

logger = logging.getLogger(__name__)


async def registrar_cambio(
    db,
    clave: str,
    valor: Any,
    vigente_desde: date,
    usuario_id: Optional[uuid.UUID] = None,
) -> ParametroMetodologia:
    """Un "cambio" es SIEMPRE una fila nueva. La fila anterior (si existe)
    ni se toca ni se consulta aquí -- este método no necesita saber si hay
    una versión previa para insertar la siguiente."""
    nueva_version = ParametroMetodologia(
        id=uuid.uuid4(),
        clave=clave,
        valor=valor,
        vigente_desde=vigente_desde,
        created_by=usuario_id,
    )
    db.add(nueva_version)
    return nueva_version


async def obtener_vigente(db, clave: str, en_fecha: date) -> Optional[ParametroMetodologia]:
    """La versión vigente para `clave` en `en_fecha`: la de mayor
    `vigente_desde` que sea `<= en_fecha`."""
    result = await db.execute(
        select(ParametroMetodologia)
        .where(ParametroMetodologia.clave == clave, ParametroMetodologia.vigente_desde <= en_fecha)
        .order_by(ParametroMetodologia.vigente_desde.desc())
        .limit(1)
    )
    return result.scalars().first()


# ---------------------------------------------------------------------------
# `resolver()` (task 9.2, ADR referenced in design "services/parametros.py
# -- resolver(clave, en_fecha, default) on top of obtener_vigente, logging
# every default fallback"). Envoltorio delgado sobre `obtener_vigente`: si
# no hay fila vigente para `clave` en `en_fecha`, retorna el `default`
# CODIFICADO que trae el caller y deja un registro (spec: "the fact is
# recorded in the load log, so a silent default never looks like a
# configured choice") -- vía el `logging` estándar, que es el único log que
# una función pura y clave-agnóstica como esta puede escribir; persistir
# ESE hecho dentro del `carga_archivo.log` de una carga puntual es
# responsabilidad del caller (Fase 9.4, fuera de alcance de este batch),
# que sí sabe qué carga está resolviendo, igual que `ventas.py`/`transito.py`
# dejan la decisión de `estado`/`log` a su propio caller.
# ---------------------------------------------------------------------------


async def resolver(db, clave: str, en_fecha: date, default: Any) -> Any:
    """Resuelve el valor vigente de `clave` en `en_fecha`, o `default` si no
    existe ninguna fila vigente. Nunca lanza por una `clave` ausente -- un
    `parametro_metodologia` sin configurar es un caso esperado y cubierto,
    no un error (spec "A missing clave falls back and is logged")."""
    fila = await obtener_vigente(db, clave, en_fecha)
    if fila is not None:
        return fila.valor

    logger.warning(
        "parametro_metodologia sin fila vigente para clave=%s en fecha=%s -- "
        "usando default codificado=%r",
        clave, en_fecha, default,
    )
    return default


# Los 5 claves que Fase 2 realmente consume (spec §6.10 + proposal
# "parametro_metodologia READ path -- first consumer ever"). Cada default
# está codificado UNA sola vez acá -- una sola fuente de verdad, igual que
# `coerce_unidad_empaque`/`normalize_sucursal_nombre` en `validators.py`.
#
# `prefijos_documento_devolucion` NO está acá a propósito: dropped del
# alcance de Fase 2 (proposal Decision #2) -- el signed `Cantidad inv.` se
# suma tal cual, sin ninguna clasificación de devolución/nota de crédito.
CLAVE_TIPOS_INVENTARIO_INCLUIDOS = "tipos_inventario_incluidos"
DEFAULT_TIPOS_INVENTARIO_INCLUIDOS: List[str] = ["0002 - REPUESTOS"]

CLAVE_CREAR_REFERENCIAS_DESCONOCIDAS = "crear_referencias_desconocidas"
# Sin default explícito en la especificación fuente (verificado por
# búsqueda directa: ninguna fila para esta clave en la tabla §6.10 ni en
# ningún otro lugar de `ESPECIFICACION_MOTORED_PEDIDOS.md`). `False` (no
# autocrear) CONFIRMADO por el owner (2026-09-22): una referencia
# desconocida cae a `carga_error` con una acción explícita "crear como
# OTROS" en vez de un side-effect de escritura silencioso -- mismo
# criterio "off por default" que `MOTORED_RETENCION_ENABLED=False`
# (design ADR-3).
DEFAULT_CREAR_REFERENCIAS_DESCONOCIDAS: bool = False

CLAVE_ESTADOS_BACKORDER_VIGENTES = "estados_backorder_vigentes"
DEFAULT_ESTADOS_BACKORDER_VIGENTES: List[str] = ["BACKORDER"]

CLAVE_DIAS_VENTANA_INGRESOS = "dias_ventana_ingresos"
DEFAULT_DIAS_VENTANA_INGRESOS: int = 45

CLAVE_TOLERANCIA_INGRESO_PCT = "tolerancia_ingreso_pct"
# NOTA: la especificación fuente (§6.10) lista esta clave como `0.02`, en
# escala FRACCIÓN (0-1). El código real de `transito.py::calcular_veredicto`
# -- ya implementado y probado en Phase 8 -- computa `diferencia_pct` en
# escala PORCENTAJE (multiplica por 100 antes de comparar), así que el
# default correcto para esa comparación es `2.0`, no `0.02`. Se prioriza la
# escala que el código ya shippeado espera (Phase 8, 1760 tests verdes)
# sobre la escala literal de la tabla de la especificación -- una
# discrepancia de unidades entre doc y código, no un desacuerdo de negocio
# sobre el porcentaje real (2%).
DEFAULT_TOLERANCIA_INGRESO_PCT: float = 2.0


async def resolver_tipos_inventario_incluidos(db, en_fecha: date) -> List[str]:
    return await resolver(
        db, CLAVE_TIPOS_INVENTARIO_INCLUIDOS, en_fecha, DEFAULT_TIPOS_INVENTARIO_INCLUIDOS
    )


async def resolver_crear_referencias_desconocidas(db, en_fecha: date) -> bool:
    return await resolver(
        db, CLAVE_CREAR_REFERENCIAS_DESCONOCIDAS, en_fecha, DEFAULT_CREAR_REFERENCIAS_DESCONOCIDAS
    )


async def resolver_estados_backorder_vigentes(db, en_fecha: date) -> List[str]:
    return await resolver(
        db, CLAVE_ESTADOS_BACKORDER_VIGENTES, en_fecha, DEFAULT_ESTADOS_BACKORDER_VIGENTES
    )


async def resolver_dias_ventana_ingresos(db, en_fecha: date) -> int:
    return await resolver(db, CLAVE_DIAS_VENTANA_INGRESOS, en_fecha, DEFAULT_DIAS_VENTANA_INGRESOS)


async def resolver_tolerancia_ingreso_pct(db, en_fecha: date) -> float:
    return await resolver(
        db, CLAVE_TOLERANCIA_INGRESO_PCT, en_fecha, DEFAULT_TOLERANCIA_INGRESO_PCT
    )
