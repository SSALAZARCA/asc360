"""
Motored: declare "no data at this date" (odd/tasks/motored-cargas-sin-datos,
owner decision 2026-10-05, option A).

When HMCL truly has no backorder, no facturas de pedidos or no ingresos de
facturas for a period, an uploaded empty file ends CON_ERRORES and the
corrida preflight blocks. A declaration records that fact explicitly: an
APLICADO `carga_archivo` with zero rows, no file, the user and the date.

It satisfies the preflight with no special case, because it carries exactly
the fields `vigencia._elegir` reads: BACKORDER picks the latest
`periodo_desde` not past the cutoff (here `fecha`), FACTURAS/INGRESOS pick
the latest `aplicado_en` (here now). Anular is the regular EXCEL flow.

What the corrida reads from it:

- BACKORDER is read by `fecha_corte` (`cargador._consulta_backorder`), and
  an upload upserts by `(fecha_corte, sucursal, referencia, pedido)`
  without clearing that date first. A declaration at D therefore means zero
  backorder only while no live backorder row exists at D, so that case is
  rejected: the user must annul the uploaded carga first.
- Tránsito (W) is recomputed from every live factura and ingreso up to the
  cutoff (`transito_corte`), never per carga. A declaration adds nothing,
  so W keeps coming from earlier data, which is the existing semantics.

No schema change: `origen` stays `EXCEL` (the database only allows `EXCEL`
or `BOT`, and an EXCEL row must carry the four file columns), the marker is
`log.sin_datos`, and the file columns hold the `SIN_ARCHIVO` sentinel, which
never matches a real sha256 nor a MinIO object. The row is APLICADO from
birth, so nothing ever enqueues or downloads it.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.motored.models.backorder_linea import BackorderLinea
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.services.reloj import hoy_bogota

ESTADO_APLICADO = "APLICADO"
ESTADO_ANULADO = "ANULADO"
NOMBRE_ARCHIVO = "Sin datos (declarado)"
SIN_ARCHIVO = "sin-archivo"
# tipo -> name shown to the user
TIPOS_SIN_DATOS = {
    "BACKORDER": "backorder",
    "FACTURAS_PEDIDOS": "facturas de pedidos",
    "INGRESOS_FACTURAS": "ingresos de facturas",
}


class DeclaracionInvalida(Exception):
    """The request itself is invalid (HTTP 422)."""


class DeclaracionEnConflicto(Exception):
    """The declaration would contradict data already recorded (HTTP 409)."""


def validar(tipo: str, fecha: date, hoy: date) -> None:
    if tipo not in TIPOS_SIN_DATOS:
        raise DeclaracionInvalida(
            "Solo se puede declarar sin datos el backorder, las facturas "
            "de pedidos o los ingresos de facturas.")
    if fecha > hoy:
        raise DeclaracionInvalida("La fecha no puede estar en el futuro.")


async def _exigir_sin_declaracion_viva(db, tipo: str, fecha: date) -> None:
    existente = await db.execute(
        select(CargaArchivo.id).where(
            CargaArchivo.tipo == tipo,
            CargaArchivo.periodo_desde == fecha,
            CargaArchivo.estado == ESTADO_APLICADO,
            CargaArchivo.log["sin_datos"].astext == "true",
        ).limit(1))
    if existente.scalars().first() is not None:
        raise DeclaracionEnConflicto(
            f"Ya hay una declaración sin {TIPOS_SIN_DATOS[tipo]} para el "
            f"{fecha.isoformat()}.")


async def _exigir_backorder_vacio(db, fecha: date) -> None:
    """The corrida reads backorder by `fecha_corte` across live cargas: a
    declaration at a date that already has rows would not empty it."""
    filas = await db.execute(
        select(BackorderLinea.carga_id)
        .join(CargaArchivo, CargaArchivo.id == BackorderLinea.carga_id)
        .where(
            BackorderLinea.fecha_corte == fecha,
            CargaArchivo.estado != ESTADO_ANULADO,
        ).limit(1))
    if filas.scalars().first() is not None:
        raise DeclaracionEnConflicto(
            f"Ya hay backorder cargado con fecha de corte "
            f"{fecha.isoformat()}. Anulá esa carga antes de declarar que no "
            "hay backorder.")


def _nueva_carga(tipo, fecha, usuario_id, ahora) -> CargaArchivo:
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL",
        nombre_archivo=NOMBRE_ARCHIVO, hash_sha256=SIN_ARCHIVO,
        ruta_objeto=SIN_ARCHIVO, bytes=0, estado=ESTADO_APLICADO,
        filas_leidas=0, filas_validas=0, filas_rechazadas=0,
        lotes_staged=0, ultimo_lote_aplicado=0,
        periodo_desde=fecha, periodo_hasta=fecha,
        log={"sin_datos": True}, subido_por=usuario_id,
        aplicado_en=ahora,
        created_at=ahora.astimezone(timezone.utc).replace(tzinfo=None),
    )


async def declarar_sin_datos(
    db, tipo: str, fecha: date, usuario_id: uuid.UUID,
    ahora: Optional[datetime] = None,
) -> CargaArchivo:
    """Validate and add the declaration; the caller commits."""
    ahora = ahora or datetime.now(timezone.utc)
    validar(tipo, fecha, hoy_bogota(ahora))
    await _exigir_sin_declaracion_viva(db, tipo, fecha)
    if tipo == "BACKORDER":
        await _exigir_backorder_vacio(db, fecha)
    carga = _nueva_carga(tipo, fecha, usuario_id, ahora)
    db.add(carga)
    return carga
