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
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, List, Mapping, NamedTuple, Optional

from sqlalchemy import select

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services.parametros_claves import REGISTRO

logger = logging.getLogger(__name__)


async def registrar_cambio(
    db,
    clave: str,
    valor: Any,
    vigente_desde: date,
    usuario_id: Optional[uuid.UUID] = None,
    sucursal_id: Optional[uuid.UUID] = None,
) -> ParametroMetodologia:
    """Un "cambio" es SIEMPRE una fila nueva. La fila anterior (si existe)
    ni se toca ni se consulta aquí -- este método no necesita saber si hay
    una versión previa para insertar la siguiente. `sucursal_id=None` es el
    alcance global."""
    nueva_version = ParametroMetodologia(
        id=uuid.uuid4(),
        clave=clave,
        valor=valor,
        vigente_desde=vigente_desde,
        sucursal_id=sucursal_id,
        created_by=usuario_id,
    )
    db.add(nueva_version)
    return nueva_version


async def obtener_vigente(db, clave: str, en_fecha: date) -> Optional[ParametroMetodologia]:
    """La versión GLOBAL vigente para `clave` en `en_fecha`: la de mayor
    `vigente_desde` que sea `<= en_fecha`. Las filas por sucursal se ignoran
    (los lectores de F2 siguen viendo lo mismo que antes de S4b). Si dos
    versiones comparten `vigente_desde`, gana la creada después."""
    result = await db.execute(
        select(ParametroMetodologia)
        .where(
            ParametroMetodologia.clave == clave,
            ParametroMetodologia.sucursal_id.is_(None),
            ParametroMetodologia.vigente_desde <= en_fecha,
        )
        .order_by(
            ParametroMetodologia.vigente_desde.desc(),
            ParametroMetodologia.created_at.desc().nulls_last(),
        )
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
# una función pura y clave-agnóstica como esta puede escribir.
#
# Verify-report WARNING #2 (sdd/motored-pedidos-ingesta): ese `logging`
# ephemeral nunca llegaba al `carga_archivo.log` que un ADMIN ve en el
# informe -- `resolver()` ahora retorna también `fue_default` (además del
# `logging.warning` de siempre, que se deja intacto) para que el caller
# (orquestador.py, el único que sabe qué carga puntual está resolviendo)
# pueda decidir persistir ese hecho, igual que `ventas.py`/`transito.py`
# dejan la decisión de `estado`/`log` a su propio caller.
# ---------------------------------------------------------------------------


class ResolverResultado(NamedTuple):
    """`(valor, fue_default)` -- `fue_default=True` cuando no había fila
    `parametro_metodologia` vigente para la `clave` y se usó el default
    codificado. Un `NamedTuple` para que `valor, fue_default = await
    resolver(...)` siga leyéndose como una tupla plana en cada call site."""

    valor: Any
    fue_default: bool


async def resolver(db, clave: str, en_fecha: date, default: Any) -> ResolverResultado:
    """Resuelve el valor vigente de `clave` en `en_fecha`, o `default` si no
    existe ninguna fila vigente. Nunca lanza por una `clave` ausente -- un
    `parametro_metodologia` sin configurar es un caso esperado y cubierto,
    no un error (spec "A missing clave falls back and is logged")."""
    fila = await obtener_vigente(db, clave, en_fecha)
    if fila is not None:
        return ResolverResultado(fila.valor, False)

    logger.warning(
        "parametro_metodologia sin fila vigente para clave=%s en fecha=%s -- "
        "usando default codificado=%r",
        clave, en_fecha, default,
    )
    return ResolverResultado(default, True)


# Los 5 claves que Fase 2 realmente consume (spec §6.10 + proposal
# "parametro_metodologia READ path -- first consumer ever"). Cada default
# está codificado UNA sola vez acá -- una sola fuente de verdad, igual que
# `coerce_unidad_empaque`/`normalize_sucursal_nombre` en `validators.py`.
#
# `prefijos_documento_devolucion` NO está acá a propósito: dropped del
# alcance de Fase 2 (proposal Decision #2) -- el signed `Cantidad inv.` se
# suma tal cual, sin ninguna clasificación de devolución/nota de crédito.
CLAVE_TIPOS_INVENTARIO_INCLUIDOS = "tipos_inventario_incluidos"
DEFAULT_TIPOS_INVENTARIO_INCLUIDOS: List[str] = ["0002 - REPUESTOS", "IRPTOSYACC", "IVNLUBGR", "0003 - OTROS"]

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


async def resolver_tipos_inventario_incluidos(db, en_fecha: date) -> ResolverResultado:
    return await resolver(
        db, CLAVE_TIPOS_INVENTARIO_INCLUIDOS, en_fecha, DEFAULT_TIPOS_INVENTARIO_INCLUIDOS
    )


async def resolver_crear_referencias_desconocidas(db, en_fecha: date) -> ResolverResultado:
    return await resolver(
        db, CLAVE_CREAR_REFERENCIAS_DESCONOCIDAS, en_fecha, DEFAULT_CREAR_REFERENCIAS_DESCONOCIDAS
    )


async def resolver_estados_backorder_vigentes(db, en_fecha: date) -> ResolverResultado:
    return await resolver(
        db, CLAVE_ESTADOS_BACKORDER_VIGENTES, en_fecha, DEFAULT_ESTADOS_BACKORDER_VIGENTES
    )


async def resolver_dias_ventana_ingresos(db, en_fecha: date) -> ResolverResultado:
    return await resolver(db, CLAVE_DIAS_VENTANA_INGRESOS, en_fecha, DEFAULT_DIAS_VENTANA_INGRESOS)


async def resolver_tolerancia_ingreso_pct(db, en_fecha: date) -> ResolverResultado:
    return await resolver(
        db, CLAVE_TOLERANCIA_INGRESO_PCT, en_fecha, DEFAULT_TOLERANCIA_INGRESO_PCT
    )


# ---------------------------------------------------------------------------
# S4b (sdd/motored-pedidos-motor, ADR-7): lectura de los parámetros del motor
# con alcance por sucursal. UNA consulta trae la versión vigente de cada
# (clave, sucursal); la precedencia se resuelve en memoria:
# override de escenario > sucursal > global > default codificado.
# ---------------------------------------------------------------------------

FUENTE_OVERRIDE = "OVERRIDE"
FUENTE_SUCURSAL = "SUCURSAL"
FUENTE_GLOBAL = "GLOBAL"
FUENTE_DEFAULT = "DEFAULT"


class ResolucionParametro(NamedTuple):
    """Valor efectivo de un parámetro y de dónde salió."""

    valor: Any
    fuente: str
    parametro_id: Optional[uuid.UUID]
    vigente_desde: Optional[date]


def _clave_fila(clave: str, sucursal_id: Any) -> tuple:
    return (clave, None if sucursal_id is None else str(sucursal_id))


@dataclass(frozen=True)
class VigentesMotor:
    """Versiones vigentes al corte, listas para resolver por sucursal."""

    en_fecha: date
    filas: Mapping[tuple, ParametroMetodologia]
    overrides: Mapping[str, Any]

    @classmethod
    def desde_filas(
        cls,
        filas: Iterable[ParametroMetodologia],
        en_fecha: date,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> "VigentesMotor":
        """Las filas llegan ordenadas de la más nueva a la más vieja: se
        conserva la primera de cada (clave, sucursal)."""
        indice: dict = {}
        for fila in filas:
            indice.setdefault(_clave_fila(fila.clave, fila.sucursal_id), fila)
        return cls(en_fecha, indice, dict(overrides or {}))

    def resolver(
        self, clave: str, sucursal_id: Any = None,
    ) -> ResolucionParametro:
        """Precedencia: override > sucursal > global > default. Una clave
        que el registro no conoce se lee igual (default `None`)."""
        if clave in self.overrides:
            return ResolucionParametro(
                self.overrides[clave], FUENTE_OVERRIDE, None, None)
        propia = self.filas.get(_clave_fila(clave, sucursal_id))
        if sucursal_id is not None and propia is not None:
            return _desde_fila(propia, FUENTE_SUCURSAL)
        global_ = self.filas.get(_clave_fila(clave, None))
        if global_ is not None:
            return _desde_fila(global_, FUENTE_GLOBAL)
        espec = REGISTRO.get(clave)
        default = None if espec is None else espec.default
        return ResolucionParametro(default, FUENTE_DEFAULT, None, None)


def _desde_fila(fila: ParametroMetodologia, fuente: str):
    return ResolucionParametro(
        fila.valor, fuente, fila.id, fila.vigente_desde)


async def obtener_vigentes_motor(
    db,
    claves: Iterable[str],
    en_fecha: date,
    overrides: Optional[Mapping[str, Any]] = None,
) -> VigentesMotor:
    """Una sola consulta `DISTINCT ON (clave, sucursal_id)`: la versión de
    mayor `vigente_desde <= en_fecha` de cada clave y sucursal (empate por
    `created_at` más reciente)."""
    columna = ParametroMetodologia
    resultado = await db.execute(
        select(columna)
        .where(
            columna.clave.in_(list(claves)),
            columna.vigente_desde <= en_fecha,
        )
        .distinct(columna.clave, columna.sucursal_id)
        .order_by(
            columna.clave,
            columna.sucursal_id,
            columna.vigente_desde.desc(),
            columna.created_at.desc().nulls_last(),
        )
    )
    return VigentesMotor.desde_filas(
        resultado.scalars().all(), en_fecha, overrides)
