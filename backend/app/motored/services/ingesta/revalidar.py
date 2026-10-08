"""
"Volver a validar" a carga (odd/tasks/motored-cargas-revalidar.md, R2).

While a carga is VALIDADO or CON_ERRORES the user fixes its errors (creates
referencias, maps sucursales, ignores rows) and then processes the SAME
stored file again, for the same carga id, with today's catalog. Nothing is
uploaded again.

`preparar_revalidacion` wipes what the dry-run produced (staging rows,
`carga_error` rows, counters, the dry-run keys of `carga.log`) and leaves
the carga `PENDIENTE`: the caller commits and enqueues it exactly like a
fresh upload, so the supervisor's atomic claim moves it to `PROCESANDO`
(a carga left `PROCESANDO` by hand would never be claimed).

Ignored rows survive the wipe: "Ignorar" stores its `(codigo_error, valor)`
in `carga.log["ignorados"]` (`registrar_ignorado`), and the dry-run skips
every row with an error matching one of them (`es_ignorada`), counted in
`log["filas_ignoradas"]`. The key is the same pair the Errores tab uses to
mark a row resolved, so "ignored" means the same thing on both sides.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, Iterable, Optional, Tuple

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta.ventas_lineas import CLAVE_REEMPLAZA_MES

ESTADOS_REVALIDABLES = frozenset({"VALIDADO", "CON_ERRORES"})
ESTADOS_EN_PROCESO = frozenset({"PENDIENTE", "PROCESANDO"})
CLAVE_IGNORADOS = "ignorados"
CLAVE_REVALIDACIONES = "revalidaciones"

# Keys of `carga.log` that are upload metadata or user decisions, never a
# dry-run result: everything else is rebuilt by the next dry-run.
CLAVES_QUE_SOBREVIVEN = (
    CLAVE_REEMPLAZA_MES,
    "asignaciones_linea",
    CLAVE_IGNORADOS,
    CLAVE_REVALIDACIONES,
)

ClaveIgnorada = Tuple[str, Optional[str]]


class RevalidacionNoPermitidaError(Exception):
    """The carga cannot be validated again; the message is for the user."""


class IgnorarNoPermitidoError(Exception):
    """A row cannot be ignored while the carga is being processed."""


def exigir_revalidable(carga: CargaArchivo) -> None:
    if carga.origen != "EXCEL" or not carga.ruta_objeto:
        raise RevalidacionNoPermitidaError(
            "Esta carga no tiene un archivo guardado para volver a validar.")
    if carga.estado not in ESTADOS_REVALIDABLES:
        raise RevalidacionNoPermitidaError(
            f"No se puede volver a validar una carga en estado "
            f"{carga.estado}: solo VALIDADO o CON_ERRORES.")


def _log_conservado(
    carga: CargaArchivo, usuario_id: uuid.UUID, ahora: datetime
) -> Dict[str, Any]:
    anterior = carga.log or {}
    log = {k: anterior[k] for k in CLAVES_QUE_SOBREVIVEN if k in anterior}
    log[CLAVE_REVALIDACIONES] = list(
        anterior.get(CLAVE_REVALIDACIONES, [])) + [
        {"usuario_id": str(usuario_id), "en": ahora.isoformat()}]
    return log


async def preparar_revalidacion(
    db: AsyncSession,
    carga: CargaArchivo,
    usuario_id: uuid.UUID,
    ahora: Optional[datetime] = None,
) -> None:
    """Checks the state, then wipes the dry-run output and leaves the
    carga `PENDIENTE`. The caller holds the carga's row lock, commits and
    enqueues; upload metadata (tipo, period, file, uploader) is kept."""
    exigir_revalidable(carga)
    ahora = ahora or datetime.now(timezone.utc)
    await db.execute(delete(CargaFilaStaging).where(
        CargaFilaStaging.carga_id == carga.id))
    await db.execute(delete(CargaError).where(
        CargaError.carga_id == carga.id))
    carga.log = _log_conservado(carga, usuario_id, ahora)
    carga.filas_leidas = 0
    carga.filas_validas = 0
    carga.filas_rechazadas = 0
    carga.lotes_staged = 0
    carga.ultimo_lote_aplicado = 0
    carga.latido_en = None
    carga.estado = "PENDIENTE"


def registrar_ignorado(
    carga: CargaArchivo, codigo_error: str, valor: Optional[str]
) -> None:
    """Remembers an "Ignorar" so a revalidation keeps the rows out. Only a
    carga that can still be revalidated stores it; while it is processing
    the dry-run would overwrite the log, so the action is refused."""
    if carga.estado in ESTADOS_EN_PROCESO:
        raise IgnorarNoPermitidoError(
            "La carga se está procesando: espere a que termine para "
            "ignorar filas.")
    if carga.estado not in ESTADOS_REVALIDABLES:
        return
    entrada = {"codigo_error": codigo_error, "valor": valor}
    ignorados = list((carga.log or {}).get(CLAVE_IGNORADOS, []))
    if entrada not in ignorados:
        ignorados.append(entrada)
    carga.log = {**(carga.log or {}), CLAVE_IGNORADOS: ignorados}


def claves_ignoradas(carga: CargaArchivo) -> FrozenSet[ClaveIgnorada]:
    return frozenset(
        (e["codigo_error"], e.get("valor"))
        for e in (carga.log or {}).get(CLAVE_IGNORADOS, []))


def es_ignorada(
    ignoradas: FrozenSet[ClaveIgnorada], errores: Iterable[CargaError]
) -> bool:
    """`True` when one of the row's errors is one the user ignored."""
    return bool(ignoradas) and any(
        (e.codigo_error, e.valor) in ignoradas for e in errores)
