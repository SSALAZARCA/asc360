"""
Motored -- the asesor's public report (odd/motored-reporte-diario-asesor, T3b).

`abrir_informe` backs `POST /publico/informe/{token}`: the secret link
(`ReporteAsesorLink`) plus the cédula the asesor types. Every failure to
identify (unknown/revoked token, usuario no longer qualifying, wrong cédula)
is the SAME 401, so nothing tells a guesser which part was wrong. Wrong
cédulas are counted on the link row: the 5th locks it for 15 minutes.
The counter write is COMMITTED before the 401 is raised (the request
session rolls back on an exception, which would erase it).

The cédula is never echoed and the token is never logged.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import Usuario
from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores_consultas as consultas
from app.motored.services import tablero_kpis as kpis
from app.motored.services.tablero_asesores import HMCL_INCLUIR

MAX_INTENTOS = 5
BLOQUEO = timedelta(minutes=15)
MSG_GENERICO = "Enlace o cédula no válidos."
MSG_BLOQUEADO = "Demasiados intentos. Intenta de nuevo en unos minutos."
MSG_SIN_DATOS = "Aún no hay información para mostrar."


class InformeError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _no_valido() -> InformeError:
    return InformeError(401, MSG_GENERICO)


def usuario_califica(usuario: Usuario, link: ReporteAsesorLink) -> bool:
    return bool(
        usuario.activo and usuario.status == "approved"
        and usuario.cedula_aprobada and usuario.cedula == link.cedula)


def cedula_coincide(digitada: Any, esperada: str) -> bool:
    try:
        return limpiar_cedula(digitada) == esperada
    except ValueError:
        return False


def registrar_fallo(link: ReporteAsesorLink, ahora: datetime) -> None:
    link.intentos_fallidos = (link.intentos_fallidos or 0) + 1
    if link.intentos_fallidos >= MAX_INTENTOS:
        link.bloqueado_hasta = ahora + BLOQUEO
        link.intentos_fallidos = 0


async def detalle_del_anio(db: AsyncSession, cedula: str) -> Optional[Dict[str, Any]]:
    """The `/kpis/asesores/detalle` payload for the year to date: January to
    the latest month with loaded sales, every store, HMCL included. None when
    there are no sales at all or the asesor has nothing in the filter."""
    meses = await lectura.meses(db)
    if not meses:
        return None
    ultimo = meses[-1]
    anio, mes = ultimo[:4], int(ultimo[5:])
    del_anio = [f"{anio}-{m:02d}" for m in range(1, mes + 1)]
    filtro = await consultas.cargar_filtro(db, del_anio, HMCL_INCLUIR, None)
    return await kpis.calcular_kpis_asesor_detalle(db, filtro, cedula)


async def abrir_informe(
    db: AsyncSession, token: str, cedula: Any, ahora: Optional[datetime] = None,
) -> Dict[str, Any]:
    ahora = ahora or datetime.now(timezone.utc)
    stmt = (
        select(ReporteAsesorLink, Usuario)
        .join(Usuario, Usuario.id == ReporteAsesorLink.usuario_id)
        .where(ReporteAsesorLink.token == token,
               ReporteAsesorLink.revocado_en.is_(None))
        .with_for_update(of=ReporteAsesorLink)
    )
    fila = (await db.execute(stmt)).first()
    if fila is None:
        raise _no_valido()
    link, usuario = fila[0], fila[1]

    if link.bloqueado_hasta and link.bloqueado_hasta > ahora:
        raise InformeError(429, MSG_BLOQUEADO)
    if not usuario_califica(usuario, link):
        raise _no_valido()

    if not cedula_coincide(cedula, link.cedula):
        registrar_fallo(link, ahora)
        await db.commit()
        raise _no_valido()

    link.intentos_fallidos = 0
    link.bloqueado_hasta = None
    link.ultimo_acceso_en = ahora
    await db.commit()  # also releases the row lock before the heavy read

    resultado = await detalle_del_anio(db, link.cedula)
    if resultado is None:
        raise InformeError(404, MSG_SIN_DATOS)
    return resultado
