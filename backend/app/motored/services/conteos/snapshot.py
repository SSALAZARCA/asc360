"""
Inventory counts -- schedule, reschedule, annul and start a TOTAL count
(odd/motored-conteos-inventario, WU5; design §1.1, §4.10, §5.1, ADR-1,
ADR-2, ADR-9).

Iniciar COPIES the store's latest inventory into `conteo_snapshot_linea`
in ONE SQL statement (`_SQL_SNAPSHOT`): it resolves the newest
`(fecha_corte, aplicado_en)` carga with rows for THAT store (never the
network-wide date, and never an ANULADO carga) and copies its rows in the
same statement, so an INVENTARIO apply committing in between can never
leave an empty or mixed snapshot. Later Maestros uploads never touch it.

Owner override: the count is per STORE. One line per referencia sums the
store's own bodegas (principal and secondary; ingest already resolved
each raw bodega to its store), and `existencia_por_bodega` keeps the
per-bodega quantities for the adjustment Excel only.

Unit cost (`costo_fuente`), first hit wins:
1. BODEGA: the store's own rows with cost > 0, weighted by the positive
   quantities (plain average of the costs when none is positive);
2. REFERENCIA: other stores' rows of the same carga with cost > 0 and a
   positive quantity, weighted by quantity;
3. MEDIANA: median of every cost > 0 of the referencia in the same carga
   (any store, any quantity; same rule as the KPI board);
4. PRECIO: `referencia.precio_normal` > 0;
5. SIN_COSTO: no cost (NULL), flagged.

Nothing here commits: the caller (the API) owns the transaction. Role
rules (ADMIN schedules, the assigned leader starts) live in the API.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping, NamedTuple, Optional

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo import (
    ESTADOS_ABIERTOS, INDICE_TOTAL_ABIERTO, Conteo,
)
from app.motored.models.conteo_sesion import ConteoSesion
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import parametros
from app.motored.services import parametros_claves as pc
from app.motored.services.conteos import acceso, errores
from app.motored.services.reloj import BOGOTA_OFFSET, hoy_bogota

# Which estados each action may start from (design §5.1).
TRANSICIONES = {
    "reprogramar": ("PROGRAMADO",),
    "iniciar": ("PROGRAMADO",),
    "anular": ("PROGRAMADO",) + ESTADOS_ABIERTOS,
}
_VERBOS = {
    "reprogramar": "reprogramar", "iniciar": "iniciar", "anular": "anular",
}
_NOMBRE_ESTADO = {
    "PROGRAMADO": "programado", "EN_CONTEO": "en conteo",
    "EN_RECONTEO": "en reconteo", "CERRADO": "cerrado",
    "ANULADO": "anulado",
}
_CLAVES_UMBRALES = (
    pc.CLAVE_CONTEO_UMBRAL_RECONTEO, pc.CLAVE_CONTEO_UMBRAL_CRITICO,
    pc.CLAVE_CONTEO_VIGENCIA_HORAS,
)
_UNA_DECIMA = Decimal("0.1")

_SQL_SNAPSHOT = text("""
WITH ultima AS (
    SELECT d.carga_id, d.fecha_corte, c.aplicado_en
    FROM inventario_detalle d
    JOIN carga_archivo c ON c.id = d.carga_id
    WHERE d.sucursal_id = CAST(:sucursal AS uuid)
      AND c.estado <> 'ANULADO'
    ORDER BY d.fecha_corte DESC, c.aplicado_en DESC NULLS LAST
    LIMIT 1
), filas AS (
    SELECT d.sucursal_id, d.referencia_id, d.bodega, d.existencia,
           d.costo_unitario
    FROM inventario_detalle d
    JOIN ultima u
      ON u.carga_id = d.carga_id AND u.fecha_corte = d.fecha_corte
), propias AS (
    SELECT referencia_id, sum(existencia) AS existencia,
           coalesce(
               sum(existencia * costo_unitario)
                   FILTER (WHERE costo_unitario > 0 AND existencia > 0)
               / nullif(sum(existencia)
                   FILTER (WHERE costo_unitario > 0 AND existencia > 0), 0),
               avg(costo_unitario) FILTER (WHERE costo_unitario > 0)
           ) AS costo
    FROM filas
    WHERE sucursal_id = CAST(:sucursal AS uuid)
    GROUP BY referencia_id
), por_bodega AS (
    SELECT referencia_id,
           jsonb_object_agg(bodega, existencia) AS existencias
    FROM (
        SELECT referencia_id, bodega, sum(existencia) AS existencia
        FROM filas
        WHERE sucursal_id = CAST(:sucursal AS uuid)
        GROUP BY referencia_id, bodega
    ) b
    GROUP BY referencia_id
), ajenas AS (
    SELECT referencia_id,
           sum(existencia * costo_unitario) / sum(existencia) AS costo
    FROM filas
    WHERE sucursal_id <> CAST(:sucursal AS uuid)
      AND costo_unitario > 0 AND existencia > 0
    GROUP BY referencia_id
), mediana AS (
    SELECT referencia_id,
           CAST(percentile_cont(0.5) WITHIN GROUP (
               ORDER BY costo_unitario) AS numeric) AS costo
    FROM filas
    WHERE costo_unitario > 0
    GROUP BY referencia_id
), copiadas AS (
    INSERT INTO conteo_snapshot_linea (
        id, conteo_id, referencia_id, existencia, existencia_por_bodega,
        costo_unitario, costo_fuente)
    SELECT gen_random_uuid(), CAST(:conteo AS uuid), p.referencia_id,
           p.existencia, b.existencias,
           round(coalesce(
               p.costo, a.costo, m.costo,
               CASE WHEN r.precio_normal > 0 THEN r.precio_normal END), 2),
           CASE WHEN p.costo IS NOT NULL THEN 'BODEGA'
                WHEN a.costo IS NOT NULL THEN 'REFERENCIA'
                WHEN m.costo IS NOT NULL THEN 'MEDIANA'
                WHEN r.precio_normal > 0 THEN 'PRECIO'
                ELSE 'SIN_COSTO' END
    FROM propias p
    JOIN referencia r ON r.id = p.referencia_id
    JOIN por_bodega b ON b.referencia_id = p.referencia_id
    LEFT JOIN ajenas a ON a.referencia_id = p.referencia_id
    LEFT JOIN mediana m ON m.referencia_id = p.referencia_id
    RETURNING 1
)
SELECT u.carga_id, u.fecha_corte, u.aplicado_en,
       (SELECT count(*) FROM copiadas) AS lineas
FROM ultima u
""")


class FuenteSnapshot(NamedTuple):
    """The carga a snapshot was copied from, and how many lines."""

    carga_id: uuid.UUID
    fecha_corte: date
    aplicado_en: Optional[datetime]
    lineas: int


class Umbrales(NamedTuple):
    """Configuración values frozen on the conteo at Iniciar (ADR-9)."""

    reconteo: Decimal
    critico: Decimal
    vigencia_horas: int


@dataclass(frozen=True)
class InicioConteo:
    """What Iniciar returns. `codigo` is the plain 6-digit code: it is
    never stored, so this is the only time it can be shown."""

    conteo: Conteo
    codigo: str
    fuente: FuenteSnapshot
    advertencia: Optional[dict]


# --- pure rules -------------------------------------------------------------


def exigir_estado(conteo: Any, accion: str) -> None:
    """EstadoInvalido unless `accion` may start from `conteo.estado`."""
    if conteo.estado in TRANSICIONES[accion]:
        return
    nombre = _NOMBRE_ESTADO.get(conteo.estado, conteo.estado)
    raise errores.EstadoInvalido(
        f"No se puede {_VERBOS[accion]} un conteo {nombre}.",
        estado=conteo.estado, accion=accion)


def limpiar_motivo(motivo: Optional[str]) -> str:
    """The trimmed reason, or MotivoRequerido when it is blank."""
    limpio = (motivo or "").strip()
    if not limpio:
        raise errores.MotivoRequerido()
    return limpio


def umbrales_desde(valores: Mapping[str, Any]) -> Umbrales:
    """Thresholds from the Configuración values; UmbralesInvalidos when
    the saved reconteo amount is not below the critical one."""
    reconteo = valores[pc.CLAVE_CONTEO_UMBRAL_RECONTEO]
    critico = valores[pc.CLAVE_CONTEO_UMBRAL_CRITICO]
    try:
        pc.validar_umbrales_conteo(reconteo, critico)
    except pc.ErrorParametro as error:
        raise errores.UmbralesInvalidos(
            reconteo=str(reconteo), critico=str(critico)) from error
    return Umbrales(
        Decimal(str(reconteo)), Decimal(str(critico)),
        int(valores[pc.CLAVE_CONTEO_VIGENCIA_HORAS]))


def _momento_de_carga(fuente: FuenteSnapshot) -> datetime:
    """When the inventory was loaded; without `aplicado_en`, the start of
    its cut date in Bogotá."""
    if fuente.aplicado_en is not None:
        return fuente.aplicado_en
    return datetime.combine(fuente.fecha_corte, time(0), BOGOTA_OFFSET)


def antiguedad_horas(fuente: FuenteSnapshot, ahora: datetime) -> Decimal:
    """Age of the inventory in hours, one decimal."""
    segundos = (ahora - _momento_de_carga(fuente)).total_seconds()
    horas = Decimal(str(segundos)) / Decimal(3600)
    return horas.quantize(_UNA_DECIMA, rounding=ROUND_HALF_UP)


def revisar_antiguedad(
        fuente: FuenteSnapshot, vigencia_horas: int, ahora: datetime,
        confirmado: bool, usuario_id: uuid.UUID) -> Optional[dict]:
    """None for a fresh inventory. A stale one raises InventarioAntiguo
    with the carga facts unless `confirmado`; then it returns the warning
    stored in `conteo.snapshot_advertencias`."""
    segundos = (ahora - _momento_de_carga(fuente)).total_seconds()
    if segundos <= vigencia_horas * 3600:
        return None
    horas = str(antiguedad_horas(fuente, ahora))
    if confirmado:
        return {
            "antiguedad_horas": horas, "vigencia_horas": vigencia_horas,
            "confirmada_por": str(usuario_id)}
    raise errores.InventarioAntiguo(
        f"El inventario de la tienda es del "
        f"{fuente.fecha_corte:%d/%m/%Y} y se cargó hace {horas} horas; el "
        f"límite es {vigencia_horas} horas. Cargue uno nuevo en Maestros "
        "o confirme que quiere contar contra ese.",
        carga_id=str(fuente.carga_id),
        fecha_corte=fuente.fecha_corte.isoformat(),
        aplicado_en=(
            fuente.aplicado_en.isoformat() if fuente.aplicado_en else None),
        antiguedad_horas=horas, vigencia_horas=vigencia_horas)


# --- schedule, reschedule, annul --------------------------------------------


async def _validar_sucursal(db: AsyncSession, sucursal_id) -> None:
    sucursal = await db.get(Sucursal, sucursal_id)
    if sucursal is None or not sucursal.activa:
        raise errores.SucursalInvalida()


async def _validar_lider(db: AsyncSession, lider_id) -> None:
    lider = await db.get(Usuario, lider_id)
    if (lider is None or not lider.activo
            or lider.role != MotoredRole.LIDER_INVENTARIOS):
        raise errores.LiderInvalido()


async def programar_conteo(
        db: AsyncSession, sucursal_id: uuid.UUID, lider_id: uuid.UUID,
        fecha_programada: date, creado_por: uuid.UUID) -> Conteo:
    """A new TOTAL conteo in PROGRAMADO for an active store, assigned to
    an active LIDER_INVENTARIOS. Several may be scheduled for one store;
    only one can be running (checked at Iniciar)."""
    await _validar_sucursal(db, sucursal_id)
    await _validar_lider(db, lider_id)
    conteo = Conteo(
        id=uuid.uuid4(), tipo="TOTAL", estado="PROGRAMADO",
        origen="MANUAL", sucursal_id=sucursal_id, lider_id=lider_id,
        fecha_programada=fecha_programada, creado_por=creado_por)
    db.add(conteo)
    await db.flush()
    return conteo


async def reprogramar_conteo(
        db: AsyncSession, conteo_id: uuid.UUID, fecha_programada: date,
        lider_id: Optional[uuid.UUID] = None) -> Conteo:
    """A PROGRAMADO conteo gets a new date and, optionally, a new
    leader."""
    conteo = await acceso.bloquear_conteo(db, conteo_id)
    exigir_estado(conteo, "reprogramar")
    if lider_id is not None:
        await _validar_lider(db, lider_id)
        conteo.lider_id = lider_id
    conteo.fecha_programada = fecha_programada
    await db.flush()
    return conteo


async def anular_conteo(
        db: AsyncSession, conteo_id: uuid.UUID, anulado_por: uuid.UUID,
        motivo: Optional[str], ahora: Optional[datetime] = None) -> Conteo:
    """PROGRAMADO, EN_CONTEO or EN_RECONTEO -> ANULADO with a reason.
    Readings are kept; the code stops working and every device session
    is closed."""
    limpio = limpiar_motivo(motivo)
    conteo = await acceso.bloquear_conteo(db, conteo_id)
    exigir_estado(conteo, "anular")
    conteo.estado = "ANULADO"
    conteo.anulado_por = anulado_por
    conteo.anulado_en = ahora or datetime.now(timezone.utc)
    conteo.motivo_anulacion = limpio
    conteo.codigo_hash = None
    await db.execute(
        update(ConteoSesion)
        .where(ConteoSesion.conteo_id == conteo.id,
               ConteoSesion.estado != "CERRADA")
        .values(estado="CERRADA"))
    await db.flush()
    return conteo


# --- Iniciar ----------------------------------------------------------------


async def leer_umbrales(db: AsyncSession, hoy: date) -> Umbrales:
    """The Configuración values in force today (defaults when unset)."""
    respaldos = {c: pc.REGISTRO[c].default for c in _CLAVES_UMBRALES}
    return umbrales_desde(await parametros.leer_valores(db, hoy, respaldos))


async def _exigir_sin_total_abierto(db: AsyncSession, conteo) -> None:
    otro = await db.scalar(
        select(Conteo.id).where(
            Conteo.sucursal_id == conteo.sucursal_id,
            Conteo.tipo == "TOTAL", Conteo.estado.in_(ESTADOS_ABIERTOS),
            Conteo.id != conteo.id).limit(1))
    if otro is not None:
        raise errores.ConteoTotalAbierto(conteo_abierto_id=str(otro))


async def copiar_snapshot(
        db: AsyncSession, conteo_id: uuid.UUID,
        sucursal_id: uuid.UUID) -> FuenteSnapshot:
    """Resolves the store's latest carga and copies it (ONE statement).
    SinInventario when the store has no inventory at all."""
    fila = (await db.execute(_SQL_SNAPSHOT, {
        "conteo": str(conteo_id), "sucursal": str(sucursal_id),
    })).first()
    if fila is None or not fila.lineas:
        raise errores.SinInventario()
    return FuenteSnapshot(
        fila.carga_id, fila.fecha_corte, fila.aplicado_en, fila.lineas)


def _marcar_iniciado(
        conteo: Conteo, fuente: FuenteSnapshot, umbrales: Umbrales,
        advertencia: Optional[dict], iniciado_por: uuid.UUID,
        ahora: datetime) -> str:
    conteo.estado = "EN_CONTEO"
    conteo.iniciado_por = iniciado_por
    conteo.iniciado_en = ahora
    conteo.snapshot_carga_id = fuente.carga_id
    conteo.snapshot_fecha_corte = fuente.fecha_corte
    conteo.snapshot_aplicado_en = fuente.aplicado_en
    conteo.snapshot_tomado_en = ahora
    conteo.snapshot_advertencias = advertencia
    conteo.umbral_reconteo_pesos = umbrales.reconteo
    conteo.umbral_critico_pesos = umbrales.critico
    conteo.enlace_slug = acceso.nuevo_slug()
    return acceso.asignar_codigo(conteo, ahora)


async def iniciar_conteo(
        db: AsyncSession, conteo_id: uuid.UUID, iniciado_por: uuid.UUID,
        confirmar_inventario_viejo: bool = False,
        ahora: Optional[datetime] = None) -> InicioConteo:
    """PROGRAMADO -> EN_CONTEO: copies the snapshot, freezes the
    thresholds, creates the link slug and the code. Holds the conteo row
    lock and re-checks the estado, so a double Iniciar is refused. A
    refused start (stale inventory, another running count) leaves no
    snapshot line behind (SAVEPOINT)."""
    ahora = ahora or datetime.now(timezone.utc)
    conteo = await acceso.bloquear_conteo(db, conteo_id)
    exigir_estado(conteo, "iniciar")
    await _exigir_sin_total_abierto(db, conteo)
    umbrales = await leer_umbrales(db, hoy_bogota(ahora))
    try:
        async with db.begin_nested():
            fuente = await copiar_snapshot(db, conteo.id, conteo.sucursal_id)
            advertencia = revisar_antiguedad(
                fuente, umbrales.vigencia_horas, ahora,
                confirmar_inventario_viejo, iniciado_por)
            codigo = _marcar_iniciado(
                conteo, fuente, umbrales, advertencia, iniciado_por, ahora)
            await db.flush()
    except IntegrityError as error:
        if INDICE_TOTAL_ABIERTO in str(error.orig):
            raise errores.ConteoTotalAbierto() from error
        raise
    return InicioConteo(conteo, codigo, fuente, advertencia)
