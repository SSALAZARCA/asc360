"""
KPI summary tables: build and refresh (odd/motored-kpis-resumenes, R2).

Fills the tables of `models/kpi_resumen.py` from the raw tables with set-based
SQL (one INSERT ... SELECT per table, never a Python loop over rows). Nothing
here commits: every function works inside the CALLER's transaction. Triggers and
read paths are wired later (R3+).

Rules shared with the live KPI queries (`tablero_asesores_consultas`), reused
rather than copied so the summaries cannot drift from them:
- only lines of cargas that are not ANULADO;
- sale = `valor_bruto - valor_descuentos`;
- client normalized like `normalizar_nit` (`_expr_cliente_norm`);
- line = `referencia.linea_comercial` trimmed, upper-cased, without accents.

What is stored does not depend on Configuracion, so it is wider than any one
configuration needs:
- `linea_norm` keeps a line only if it belongs to the union of ALL historical
  `lineas_comerciales` values (every `parametro_metodologia` row, any scope) plus
  the registry default; any other value collapses to NULL ("not a recognized
  line"). That keeps the rows few while every past or present configuration can
  still be answered at read time.
- `nit_especial` is the normalized client when it belongs to the union of ALL
  historical `hmcl_nits` values (plus the default) or to `cliente_tecnired`; else
  NULL. Plain clients are not stored in `kpi_venta_mes` / `kpi_factura_firma`.
- An invoice is `(nro_documento, sucursal_id)`. The live queries count it once per
  group of the request (per asesor row, store or in total), however many months,
  vendedores or special NITs its lines span, so `kpi_factura_firma` keeps it in one of
  two shapes: a plain invoice (all its lines in ONE month, vendedor and special NIT) is a
  row of that key whose `firma` is the sorted distinct lines; any other invoice is ONE
  row of the sentinel NIT `NIT_FACTURA_IRREGULAR` (month = its first, vendedor ''),
  whose `firma` holds one `YYYY-MM-DD|linea|nit|vendedor` token per combination (a pipe inside
  the line or the NIT is stored as `ESCAPE_DELIMITADOR`; the vendedor is last, so it is read whole),
  which the read splits and filters like the live query does line by line.

Costs: the unit cost of a referencia is the median of its positive costs in the
latest non-annulled inventory cut (`fuente = 'inventario'`); a referencia with no
positive inventory cost falls back to `precio_normal` when it is > 0 (`fuente =
'maestro'`); otherwise it has no cost. `costo_estimado` is the part of `costo`
priced from the master. Only the latest cut is kept (the KPI's only ever read it),
in `kpi_costo_referencia` and, per store, in `kpi_inventario_corte`. Without any
inventory cut the cost table is keyed by today's date.

Concurrency: ONE transaction-level advisory lock (`LOCK_KEY`) serializes the full
rebuild, the costs rebuild and the incremental refresh. They all take it before
touching any summary table and nothing else is locked afterwards, so they cannot
deadlock with a carga apply (which only takes it at the end, holding row locks
on the raw tables the rebuild merely reads under MVCC). A full rebuild uses
DELETE, not TRUNCATE: readers keep seeing the old rows until it commits. A carga
that commits while a rebuild runs is picked up by that carga's own refresh, which
waits for the lock and runs afterwards.
"""
import datetime
from typing import Any, Iterable, NamedTuple, Optional, Sequence, Set, Tuple

from sqlalchemy import (
    Date, Text, and_, case, cast, delete, func, insert, literal, null, or_, select, tuple_,
)
from sqlalchemy.dialects.postgresql import ARRAY, aggregate_order_by
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.kpi_resumen import (
    KpiClienteMes, KpiCostoReferencia, KpiFacturaFirma, KpiInventarioCorte, KpiResumenEstado, KpiVentaMes,
)
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.referencia import Referencia
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q

LOCK_KEY = 7_203_581_101
ESCAPE_DELIMITADOR = "\x1f"  # stands for a `|` inside the line / NIT fields of an irregular-invoice token
NIT_FACTURA_IRREGULAR = "~"  # `kpi_factura_firma.nit_especial` of the invoices that span several combinations
FUENTE_MAESTRO = q.FUENTE_MAESTRO
Clave = Tuple[Any, int, int]  # (sucursal_id, anio, mes)


class Estado(NamedTuple):
    sucio: bool
    reconstruyendo: bool
    actualizado_en: Optional[datetime.datetime]
    ultima_reconstruccion_total: Optional[datetime.datetime]
    version: int


# --- Pure helpers -----------------------------------------------------------------------------


def union_lineas(valores: Iterable[Any]) -> Tuple[str, ...]:
    """The registry default plus every historical `lineas_comerciales` value,
    normalized like a referencia's line. Values of the wrong shape are ignored."""
    lineas = set(t.LINEAS)
    for valor in valores:
        if isinstance(valor, (list, tuple)):
            lineas.update(n for n in (t.texto_de_linea(x) for x in valor if isinstance(x, str)) if n)
    return tuple(sorted(lineas))


def union_nits(valores: Iterable[Any]) -> Tuple[str, ...]:
    """The registry default plus every historical `hmcl_nits` value (trimmed)."""
    nits = set(t.HMCL_NITS)
    for valor in valores:
        if isinstance(valor, (list, tuple)):
            nits.update(n for n in (x.strip() for x in valor if isinstance(x, str)) if n)
    return tuple(sorted(nits))


def _mes_siguiente(anio: int, mes: int) -> datetime.date:
    return datetime.date(anio + (mes == 12), mes % 12 + 1, 1)


async def _uniones(db: AsyncSession) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    filas = (await db.execute(
        select(ParametroMetodologia.clave, ParametroMetodologia.valor)
        .where(ParametroMetodologia.clave.in_(["lineas_comerciales", "hmcl_nits"])))).all()
    return (union_lineas(v for c, v in filas if c == "lineas_comerciales"),
            union_nits(v for c, v in filas if c == "hmcl_nits"))


class ResumenOcupadoError(RuntimeError):
    """The summaries are being rebuilt and the wait for the lock ran out."""


_BLOQUEO_NO_DISPONIBLE = "55P03"  # lock_not_available (the SQLSTATE of `lock_timeout`)


async def _bloquear(db: AsyncSession) -> None:
    """Takes the advisory lock, waiting at most `MOTORED_KPI_RESUMEN_LOCK_TIMEOUT_SEGUNDOS`
    (a `lock_timeout` scoped to this wait, restored afterwards so it does not leak to the
    caller's other statements). A full rebuild holds the lock while it runs, so a carga apply
    or a Configuracion change that arrives meanwhile fails with a clear message instead of
    hanging until the rebuild ends."""
    anterior = (await db.execute(select(func.current_setting("lock_timeout")))).scalar_one()
    espera = max(int(settings.MOTORED_KPI_RESUMEN_LOCK_TIMEOUT_SEGUNDOS), 1)
    await db.execute(select(func.set_config("lock_timeout", f"{espera}s", True)))
    try:
        await db.execute(select(func.pg_advisory_xact_lock(LOCK_KEY)))
    except DBAPIError as exc:
        if getattr(getattr(exc, "orig", None), "sqlstate", None) != _BLOQUEO_NO_DISPONIBLE:
            raise
        raise ResumenOcupadoError(
            "Los resúmenes de KPI se están reconstruyendo y la operación no pudo esperar a que "
            "terminen. Intente de nuevo en unos minutos.") from exc
    await db.execute(select(func.set_config("lock_timeout", anterior, True)))


# --- State row --------------------------------------------------------------------------------


async def estado(db: AsyncSession) -> Optional[Estado]:
    fila = (await db.execute(select(KpiResumenEstado).where(KpiResumenEstado.id == 1))).scalar_one_or_none()
    if fila is None:
        return None
    return Estado(fila.sucio, fila.reconstruyendo, fila.actualizado_en, fila.ultima_reconstruccion_total,
                  fila.version)


async def _guardar_estado(db: AsyncSession, inicial: dict, cambios: dict) -> None:
    """Upsert of the single row: `inicial` when it does not exist yet, `cambios` when it does."""
    consulta = pg_insert(KpiResumenEstado).values(id=1, **inicial)
    await db.execute(consulta.on_conflict_do_update(index_elements=[KpiResumenEstado.id], set_=cambios))


async def marcar_sucio(db: AsyncSession) -> None:
    """Flags the summaries as out of date (a full rebuild is pending)."""
    await _guardar_estado(db, {"sucio": True}, {"sucio": True})


async def marcar_sucio_si_construido(db: AsyncSession) -> bool:
    """`marcar_sucio`, but only once the summaries were fully built at least once (the first
    full build reads every input anyway). Meant for the code paths that change an input of the
    summaries, in THEIR transaction. The lock is taken first, as in `refrescar_si_construido`:
    a rebuild in flight read the inputs before this change committed, so the flag must land
    after that rebuild's own commit (which clears it) for the next rebuild to see the change.
    True when it marked."""
    marca = _transaccion_actual(db)
    if marca is not None and db.info.get(_CLAVE_MARCA) is marca:
        return True  # already flagged in this transaction (a mass edit calls this once per row)
    await _bloquear(db)
    actual = await estado(db)
    if actual is None or actual.ultima_reconstruccion_total is None:
        return False
    await marcar_sucio(db)
    if marca is not None:
        db.info[_CLAVE_MARCA] = marca
    return True


_CLAVE_MARCA = "kpi_resumen_sucio_en"


def _transaccion_actual(db: AsyncSession) -> Any:
    """The session's current transaction object (None when it cannot be told). Compared by
    identity, and kept referenced in `db.info`, so a recycled `id()` can never match."""
    try:
        return db.sync_session.get_transaction()
    except AttributeError:
        return None


async def _marcar_reconstruido(db: AsyncSession) -> None:
    ahora = func.now()
    await _guardar_estado(
        db, {"sucio": False, "reconstruyendo": False, "actualizado_en": ahora,
             "ultima_reconstruccion_total": ahora, "version": 1},
        {"sucio": False, "reconstruyendo": False, "actualizado_en": ahora,
         "ultima_reconstruccion_total": ahora, "version": KpiResumenEstado.version + 1})


async def _marcar_actualizado(db: AsyncSession) -> None:
    """A partial update: the data is fresher, but a never-built summary stays dirty."""
    await _guardar_estado(db, {"sucio": True, "actualizado_en": func.now()}, {"actualizado_en": func.now()})


# --- Base of the ventas tables ----------------------------------------------------------------


def _filtro_claves(claves: Sequence[Clave]):
    return or_(*[
        and_(VentaDetalle.sucursal_id == s, VentaDetalle.fecha >= datetime.date(a, m, 1),
             VentaDetalle.fecha < _mes_siguiente(a, m))
        for s, a, m in claves])


def _base(lineas: Tuple[str, ...], nits: Tuple[str, ...], claves: Optional[Sequence[Clave]], sucursales=None):
    """One row per venta_detalle line with every derived column the three tables
    group by. The key filter uses plain date ranges (never `date_trunc` in WHERE)."""
    cte = q._lineas_por_referencia(t.Reglas(lineas=lineas))
    cliente = q._expr_cliente_norm()
    corte = select(func.max(KpiCostoReferencia.fecha_corte)).scalar_subquery()
    unitario = KpiCostoReferencia.costo_unitario
    costo = VentaDetalle.cantidad * unitario
    consulta = (
        select(
            cast(func.date_trunc("month", VentaDetalle.fecha), Date).label("anio_mes"),
            VentaDetalle.sucursal_id.label("sucursal_id"),
            VentaDetalle.vendedor_norm.label("vendedor_norm"),
            cte.c.linea.label("linea"),
            cliente.label("cliente"),
            case((or_(cliente.in_(list(nits)), cliente.in_(select(ClienteTecnired.nit))), cliente),
                 else_=None).label("nit_especial"),
            q._expr_es_mostrador().label("es_mostrador"),
            q._expr_venta().label("venta"),
            VentaDetalle.valor_bruto.label("bruto"),
            VentaDetalle.valor_descuentos.label("descuentos"),
            VentaDetalle.cantidad.label("cantidad"),
            VentaDetalle.nro_documento.label("nro_documento"),
            unitario.is_not(None).label("con_costo"),
            func.coalesce(costo, 0).label("costo"),
            case((KpiCostoReferencia.fuente == FUENTE_MAESTRO, costo), else_=0).label("costo_estimado"),
        )
        .select_from(VentaDetalle)
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .join(cte, cte.c.id == VentaDetalle.referencia_id)
        .outerjoin(KpiCostoReferencia, and_(
            KpiCostoReferencia.referencia_id == VentaDetalle.referencia_id,
            KpiCostoReferencia.fecha_corte == corte))
        .where(CargaArchivo.estado != "ANULADO")
    )
    if claves is not None:
        consulta = consulta.where(_filtro_claves(claves))
    if sucursales is not None:
        consulta = consulta.where(VentaDetalle.sucursal_id.in_(sorted(sucursales, key=str)))
    return consulta.subquery("base")


async def _insertar_venta_mes(db, base) -> None:
    llave = [base.c.anio_mes, base.c.sucursal_id, base.c.vendedor_norm, base.c.linea, base.c.nit_especial,
             base.c.es_mostrador, base.c.con_costo]
    consulta = select(
        *llave, func.sum(base.c.venta), func.sum(base.c.bruto), func.sum(base.c.descuentos),
        func.sum(base.c.cantidad), func.count(), func.sum(base.c.costo), func.sum(base.c.costo_estimado),
    ).group_by(*llave)
    columnas = ["anio_mes", "sucursal_id", "vendedor_norm", "linea_norm", "nit_especial", "es_mostrador",
                "con_costo", "venta", "bruto", "descuentos", "cantidad", "lineas", "costo", "costo_estimado"]
    await db.execute(insert(KpiVentaMes).from_select(columnas, consulta))


def _escapar(columna):
    """A token field with its pipes replaced by `ESCAPE_DELIMITADOR` (the read undoes it)."""
    return func.replace(columna, "|", ESCAPE_DELIMITADOR)


def _es_simple(anio_mes, vendedor_norm, nit):
    """True when all the lines of an invoice share the month, the vendedor and the special NIT.
    Null-safe: with `=` a NULL key makes the flag NULL, which is neither simple nor irregular,
    and the invoice would be dropped from both shapes."""
    return (func.min(anio_mes).is_not_distinct_from(func.max(anio_mes))
            & func.min(vendedor_norm).is_not_distinct_from(func.max(vendedor_norm))
            & func.min(nit).is_not_distinct_from(func.max(nit)))


async def _insertar_factura_firma(db, base) -> None:
    """Plain invoices as `(mes, sucursal, vendedor, nit, firma)` rows; the ones that span
    several months, vendedores or special NITs as one sentinel row of tokens (see the module
    docstring). An invoice with no recognized line is a plain row with an empty `firma`."""
    por_linea = select(
        base.c.anio_mes, base.c.sucursal_id, base.c.vendedor_norm, base.c.nit_especial, base.c.nro_documento,
        base.c.linea,
    ).group_by(
        base.c.anio_mes, base.c.sucursal_id, base.c.vendedor_norm, base.c.nit_especial, base.c.nro_documento,
        base.c.linea,
    ).subquery("por_linea")
    c = por_linea.c
    sin_nit = func.coalesce(c.nit_especial, "")
    # The vendedor is the LAST field (the read takes everything after the third delimiter), so it
    # needs no escaping; the line and the NIT do: `ESCAPE_DELIMITADOR` stands for a literal pipe.
    marca = (func.to_char(c.anio_mes, "YYYY-MM-DD") + "|" + _escapar(c.linea) + "|" + _escapar(sin_nit) + "|"
             + c.vendedor_norm)
    por_factura = select(
        c.sucursal_id, c.nro_documento,
        func.min(c.anio_mes).label("anio_mes"), func.min(c.vendedor_norm).label("vendedor_norm"),
        func.min(c.nit_especial).label("nit_especial"),
        _es_simple(c.anio_mes, c.vendedor_norm, sin_nit).label("simple"),
        func.array_remove(func.array_agg(aggregate_order_by(c.linea, c.linea)), null(), type_=ARRAY(Text)).label("firma"),
        func.array_remove(func.array_agg(aggregate_order_by(marca, marca)), null(), type_=ARRAY(Text)).label("marcas"),
    ).group_by(c.sucursal_id, c.nro_documento).subquery("por_factura")
    f = por_factura.c
    columnas = ["anio_mes", "sucursal_id", "vendedor_norm", "nit_especial", "firma", "n_facturas"]
    simples = select(f.anio_mes, f.sucursal_id, f.vendedor_norm, f.nit_especial, f.firma, func.count()).where(
        f.simple).group_by(f.anio_mes, f.sucursal_id, f.vendedor_norm, f.nit_especial, f.firma)
    irregulares = select(
        f.anio_mes, f.sucursal_id, literal(""), literal(NIT_FACTURA_IRREGULAR), f.marcas, func.count(),
    ).where(~f.simple, func.cardinality(f.marcas) > 0).group_by(f.anio_mes, f.sucursal_id, f.marcas)
    await db.execute(insert(KpiFacturaFirma).from_select(columnas, simples))
    await db.execute(insert(KpiFacturaFirma).from_select(columnas, irregulares))


async def _insertar_cliente_mes(db, base) -> None:
    llave = [base.c.anio_mes, base.c.sucursal_id, base.c.vendedor_norm, base.c.cliente, base.c.linea]
    consulta = select(*llave, func.sum(base.c.venta)).where(base.c.linea.is_not(None)).group_by(*llave)
    await db.execute(insert(KpiClienteMes).from_select(
        ["anio_mes", "sucursal_id", "vendedor_norm", "cliente_norm", "linea_norm", "venta"], consulta))


async def _insertar_ventas(db: AsyncSession, claves: Optional[Sequence[Clave]]) -> None:
    lineas, nits = await _uniones(db)
    await _insertar_venta_mes(db, _base(lineas, nits, claves))
    # An invoice can span months: its rows are derived from ALL the months of its stores.
    await _insertar_factura_firma(
        db, _base(lineas, nits, None, None if claves is None else {c[0] for c in claves}))
    await _insertar_cliente_mes(db, _base(lineas, nits, claves))


# --- Costs and inventory ----------------------------------------------------------------------


async def _reconstruir_costos_e_inventario(db: AsyncSession) -> None:
    corte = await q.fecha_corte_costos(db)
    await db.execute(delete(KpiCostoReferencia))
    await db.execute(delete(KpiInventarioCorte))
    fecha = corte or datetime.date.today()
    costos = q._subconsulta_costos(corte)  # the live rule itself: median, else precio_normal
    await db.execute(insert(KpiCostoReferencia).from_select(
        ["fecha_corte", "referencia_id", "costo_unitario", "fuente"],
        select(literal(fecha, Date), costos.c.referencia_id, costos.c.costo_unitario, costos.c.fuente)))
    if corte is not None:
        await _insertar_inventario(db, corte)


async def _insertar_inventario(db: AsyncSession, corte: datetime.date) -> None:
    """Inventory at cost per store, valued by the live rule (`q._valoracion_inventario`)."""
    valor, sin_costo, costo_maestro = q._valoracion_inventario()
    consulta = (
        select(literal(corte, Date), InventarioDetalle.sucursal_id, valor, sin_costo, costo_maestro)
        .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
        .outerjoin(Referencia, Referencia.id == InventarioDetalle.referencia_id)
        .where(InventarioDetalle.fecha_corte == corte, CargaArchivo.estado != "ANULADO")
        .group_by(InventarioDetalle.sucursal_id)
    )
    await db.execute(insert(KpiInventarioCorte).from_select(
        ["fecha_corte", "sucursal_id", "valor", "lineas_sin_costo", "lineas_costo_maestro"], consulta))


# --- Public API -------------------------------------------------------------------------------


async def refrescar_periodos(db: AsyncSession, claves: Set[Clave]) -> None:
    """Re-derives the ventas summaries of the given `(sucursal_id, anio, mes)` keys: DELETE
    those rows and INSERT ... SELECT them again from the non-annulled lines of those
    months. Runs in the caller's transaction (a carga apply or annul)."""
    if not claves:
        return
    ordenadas = sorted(claves, key=lambda c: (str(c[0]), c[1], c[2]))
    await _bloquear(db)
    meses = [(s, datetime.date(a, m, 1)) for s, a, m in ordenadas]
    for modelo in (KpiVentaMes, KpiClienteMes):
        await db.execute(delete(modelo).where(tuple_(modelo.sucursal_id, modelo.anio_mes).in_(meses)))
    await db.execute(delete(KpiFacturaFirma).where(KpiFacturaFirma.sucursal_id.in_({c[0] for c in claves})))
    await _insertar_ventas(db, ordenadas)
    await _marcar_actualizado(db)


async def refrescar_si_construido(db: AsyncSession, claves: Set[Clave]) -> bool:
    """`refrescar_periodos`, but only once the summaries were fully built at least once (the
    first full build reads every line anyway). The lock is taken BEFORE looking at the state:
    a first build that is running holds it until it commits, so either its commit is visible
    here (and we refresh) or it starts after ours (and reads our lines). Anything that fails
    propagates: the caller's transaction (a carga apply or annul) rolls back with the summary,
    which therefore never silently diverges from `venta_detalle`. True when it refreshed."""
    if not claves:
        return False
    await _bloquear(db)
    actual = await estado(db)
    if actual is None or actual.ultima_reconstruccion_total is None:
        return False
    await refrescar_periodos(db, claves)
    return True


async def claves_de_carga(db: AsyncSession, carga_id: Any) -> Set[Clave]:
    """The `(sucursal_id, anio, mes)` keys that a carga's lines of `venta_detalle` belong to."""
    filas = await db.execute(
        select(VentaDetalle.sucursal_id, VentaDetalle.anio, VentaDetalle.mes)
        .where(VentaDetalle.carga_id == carga_id).distinct())
    return {(sucursal, anio, mes) for sucursal, anio, mes in filas.all()}


async def reconstruir_todo(db: AsyncSession) -> None:
    """Full rebuild of every summary (costs first: the ventas rows are priced from them)."""
    await _bloquear(db)
    for modelo in (KpiVentaMes, KpiFacturaFirma, KpiClienteMes):
        await db.execute(delete(modelo))
    await _reconstruir_costos_e_inventario(db)
    await _insertar_ventas(db, None)
    await _marcar_reconstruido(db)


async def reconstruir_costos(db: AsyncSession) -> None:
    """Rebuilds the costs and the inventory summaries and re-prices the sales rows. Only
    `kpi_venta_mes` carries costs, so only it is rebuilt (the invoice and client tables
    do not depend on them); the 'never fully built' flag is left as it was."""
    await _bloquear(db)
    await db.execute(delete(KpiVentaMes))
    await _reconstruir_costos_e_inventario(db)
    lineas, nits = await _uniones(db)
    await _insertar_venta_mes(db, _base(lineas, nits, None))
    await _marcar_actualizado(db)
