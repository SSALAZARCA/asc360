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
from app.motored.models.usuario import Usuario
from app.motored.services import kpi_resumen
from app.motored.services.parametros_claves import (
    REGISTRO, SECCIONES, ficha,
)

logger = logging.getLogger(__name__)

# Configuracion keys the KPI summaries are built against (their union of historical values
# decides which lines / NITs are kept apart): writing one needs a full rebuild.
CLAVES_DE_RESUMEN_KPI = frozenset({"hmcl_nits", "lineas_comerciales"})


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
    if clave in CLAVES_DE_RESUMEN_KPI:
        await kpi_resumen.marcar_sucio_si_construido(db)
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
# Linea comercial de la columna "Tipo inventario" de VENTAS (todas cuentan).
DEFAULT_TIPOS_INVENTARIO_INCLUIDOS: List[str] = [
    "REPUESTOS", "ACCESORIOS", "LUBRICANTES", "LLANTAS", "BATERIAS", "CASCOS", "GPS",
]

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


def primer_dia_del_mes(fecha: date) -> date:
    return fecha.replace(day=1)


async def vigente_en(
    db, clave: str, fecha: date, sucursal_id: Any = None,
) -> ResolucionParametro:
    """Lectura puntual en el tiempo: la versión de mayor `vigente_desde`
    <= el día 1 del mes de `fecha`, con la misma precedencia que el motor
    (sucursal > global > default del registro). Así una comisión de un mes
    pasado usa las reglas que regían ese mes."""
    vigentes = await obtener_vigentes_motor(
        db, [clave], primer_dia_del_mes(fecha))
    return vigentes.resolver(clave, sucursal_id)


class HistorialFila(NamedTuple):
    """Una versión guardada y el nombre de quien la creó (None si el
    usuario ya no existe o la fila no tiene autor)."""

    fila: ParametroMetodologia
    autor: Optional[str]

    @property
    def valor(self) -> Any:
        return self.fila.valor


LIMITE_HISTORIAL = 200


async def listar_historial(
    db, clave: str, limite: int = LIMITE_HISTORIAL,
) -> List[HistorialFila]:
    """Las versiones de `clave` (todas las sucursales y la global), de la
    más nueva a la más vieja."""
    columna = ParametroMetodologia
    resultado = await db.execute(
        select(columna, Usuario.nombre)
        .outerjoin(Usuario, Usuario.id == columna.created_by)
        .where(columna.clave == clave)
        .order_by(
            columna.vigente_desde.desc(),
            columna.created_at.desc().nulls_last(),
        )
        .limit(limite)
    )
    return [HistorialFila(fila, autor) for fila, autor in resultado.all()]


async def _programadas(db, desde: date) -> List[ParametroMetodologia]:
    """Versiones que aún no rigen: `vigente_desde` posterior a `desde`."""
    columna = ParametroMetodologia
    resultado = await db.execute(
        select(columna)
        .where(
            columna.clave.in_(list(REGISTRO)),
            columna.vigente_desde > desde,
        )
        .order_by(columna.vigente_desde, columna.created_at)
    )
    return list(resultado.scalars().all())


def _ficha_con_valores(
    espec, vigentes: VigentesMotor, programadas: List[ParametroMetodologia],
) -> dict:
    efectivo = vigentes.resolver(espec.clave)
    por_sucursal = [
        {"sucursal_id": fila.sucursal_id, "valor": fila.valor,
         "vigente_desde": fila.vigente_desde, "parametro_id": fila.id}
        for (clave, sucursal), fila in vigentes.filas.items()
        if clave == espec.clave and sucursal is not None
    ]
    futuras = [
        {"valor": f.valor, "vigente_desde": f.vigente_desde,
         "sucursal_id": f.sucursal_id}
        for f in programadas if f.clave == espec.clave
    ]
    return {
        **ficha(espec),
        "efectivo_global": efectivo._asdict(),
        "por_sucursal": por_sucursal,
        "programados": futuras,
    }


async def leer_configuracion(db, hoy: date) -> List[dict]:
    """El modelo de lectura de la pantalla: cada clave registrada con su
    ficha, su valor efectivo global, sus excepciones por sucursal y las
    versiones programadas, agrupada por pestaña y por grupo. Las
    pestañas sin claves salen igual (vacías) y en orden fijo."""
    inicio = primer_dia_del_mes(hoy)
    vigentes = await obtener_vigentes_motor(db, list(REGISTRO), inicio)
    programadas = await _programadas(db, inicio)
    secciones = {nombre: {} for nombre in SECCIONES}
    for espec in REGISTRO.values():
        entrada = _ficha_con_valores(espec, vigentes, programadas)
        grupos = secciones.setdefault(entrada["seccion"], {})
        grupos.setdefault(espec.grupo, []).append(entrada)
    return [
        {"seccion": nombre,
         "grupos": [{"grupo": g, "claves": c} for g, c in grupos.items()]}
        for nombre, grupos in secciones.items()
    ]


# ---------------------------------------------------------------------------
# Lectura de ciclo (Configuración T3-T5): los trabajos de fondo (avisos,
# purgas, ingesta) leen sus ajustes UNA vez por ciclo con esta función. Una
# fila vigente (y válida) gana; si no hay, vale el respaldo del llamador
# (la constante o la variable de entorno de siempre). Un fallo de lectura
# nunca tumba el ciclo: se usa el último valor conocido y, sin él, el respaldo.
# ---------------------------------------------------------------------------


async def leer_valores(
    db, fecha: date, respaldos: Mapping[str, Any],
) -> dict:
    """`{clave: valor}` de cada clave de `respaldos`: la versión vigente al
    día 1 del mes de `fecha` o, sin fila (o con una que ya no cumple la
    regla del registro), el respaldo."""
    vigentes = await obtener_vigentes_motor(
        db, list(respaldos), primer_dia_del_mes(fecha))
    valores = {}
    for clave, respaldo in respaldos.items():
        resolucion = vigentes.resolver(clave)
        valores[clave] = respaldo
        if resolucion.fuente == FUENTE_DEFAULT:
            continue
        espec = REGISTRO.get(clave)
        if espec is not None and not espec.validar(resolucion.valor):
            logger.warning(
                "parametro_metodologia %s: el valor guardado %r ya no "
                "cumple la regla; se usa el respaldo", clave,
                resolucion.valor)
            continue
        valores[clave] = resolucion.valor
    return valores


async def _deshacer(db) -> None:
    """Limpia la transacción abortada por un fallo de lectura; si la sesión
    tampoco puede, sigue: el llamador ya tiene su respaldo."""
    try:
        await db.rollback()
    except Exception:  # noqa: BLE001 -- nunca hacia el ciclo
        logger.warning("no se pudo deshacer la lectura fallida")


async def leer_con_memoria(
    db, fecha: date, respaldos: Mapping[str, Any], memoria: dict,
    deshacer: bool = True,
) -> dict:
    """`leer_valores` que jamás lanza. Guarda cada lectura buena en
    `memoria` (un dict del módulo que lee); si la siguiente falla, devuelve
    esa memoria y, sin ella, `respaldos`. Con `deshacer=False` no hace
    rollback (para sesiones con trabajo pendiente)."""
    try:
        valores = await leer_valores(db, fecha, respaldos)
    except Exception:  # noqa: BLE001 -- un ajuste no tumba el ciclo
        logger.exception(
            "no se pudieron leer los ajustes %s; se usa el último valor "
            "conocido", sorted(respaldos))
        if deshacer:
            await _deshacer(db)
        return dict(memoria) if memoria else dict(respaldos)
    memoria.clear()
    memoria.update(valores)
    return valores
