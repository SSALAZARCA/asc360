"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S7, ADR-9, spec "API
under /api/motored/corridas" y "RBAC (T19)"): `/api/motored/corridas`.

Router delgado: las reglas viven en `services/corridas/` (servicio para
escribir, `consultas` para leer). No hay UI en F3.

RBAC: crear, cerrar y anular son de ADMIN y COMPRAS; leer, de esos dos más
CONSULTA y SUCURSAL. SUCURSAL ve sólo sus sucursales (el alcance se pasa a
las consultas, que lo aplican en SQL; una sucursal ajena en las líneas es
403; una corrida sin ninguna sucursal suya es 404). SERVICIO_CLIENTE queda
afuera por el confinamiento de prefijos de `deps.get_current_motored_user`.

`POST /corridas` valida y corre el preflight de forma síncrona (un rechazo es
un 422 con su código y, en los de vigencia, el detalle de antigüedades por
tipo), guarda la corrida PENDIENTE, confirma y la encola en el runner: nunca
calcula en línea. Cerrar y anular responden 409 con el código de la regla
que los rechazó. Ninguna ruta edita `pedido_final` ni el ajuste Z.
"""
import logging
import uuid
from datetime import date
from typing import Any, Dict, FrozenSet, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import (
    MotoredUser,
    get_motored_db_or_503,
    require_motored_ready,
    require_roles,
)
from app.motored.schemas.corrida import (
    CorridaAnular,
    CorridaCreada,
    CorridaCreate,
    CorridaDetalle,
    CorridaEstado,
    LineaRead,
    PaginaCorridas,
    PaginaLineas,
    Progreso,
)
from app.motored.services.corridas import codigos, consultas, servicio
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.trabajos.runner_corridas import (
    CorridaRunner,
    SupervisorCorridaRunner,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/corridas",
    tags=["motored-corridas"],
    dependencies=[Depends(require_motored_ready)],
)

_require_write = require_roles("ADMIN", "COMPRAS")
_require_read = require_roles("ADMIN", "COMPRAS", "CONSULTA", "SUCURSAL")

ROL_SUCURSAL = "SUCURSAL"
PAGINA_CORRIDAS, PAGINA_CORRIDAS_MAX = 50, 200
PAGINA_LINEAS, PAGINA_LINEAS_MAX = 500, 2000
ESTADOS = Literal[
    "PENDIENTE", "CALCULANDO", "FALLIDA", "BORRADOR", "EN_REVISION",
    "CERRADA", "ENVIADA", "ANULADA"]
# Rechazos por el estado o el contenido de la corrida (el resto es 422).
_CONFLICTOS = frozenset({
    codigos.E_CORRIDA_ESTADO_NO_ADMITE,
    codigos.E_CORRIDA_INVALIDADA,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
    codigos.E_CORRIDA_SUCURSAL_FALLIDA,
})


def get_corrida_runner() -> CorridaRunner:
    """Seam inyectable: en producción sólo garantiza el loop en marcha."""
    return SupervisorCorridaRunner()


def _alcance(user: MotoredUser) -> Optional[FrozenSet[uuid.UUID]]:
    """Sucursales visibles: `None` (todas) salvo para el rol SUCURSAL."""
    if user.role != ROL_SUCURSAL:
        return None
    propias = set()
    for texto in user.sucursal_ids:
        try:
            propias.add(uuid.UUID(str(texto)))
        except ValueError:
            continue
    return frozenset(propias)


def _rechazo(error: ErrorCorrida) -> HTTPException:
    """422 (la petición no es válida ahora) o 409 (la corrida no admite la
    operación), con `{code, message[, detalle]}`."""
    cuerpo: Dict[str, Any] = {
        "code": error.codigo, "message": error.mensaje}
    if error.detalle:
        cuerpo["detalle"] = error.detalle
    estado = (
        status.HTTP_409_CONFLICT if error.codigo in _CONFLICTOS
        else status.HTTP_422_UNPROCESSABLE_ENTITY)
    return HTTPException(status_code=estado, detail=cuerpo)


def _no_existe() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Corrida no encontrada.")


async def _enqueue(runner: CorridaRunner, corrida_id: uuid.UUID) -> None:
    """La corrida ya está confirmada como PENDIENTE: si el runner falla, el
    loop de corridas la reclama igual en su siguiente vuelta."""
    try:
        await runner.enqueue(corrida_id)
    except Exception:  # noqa: BLE001 -- la respuesta ya no puede fallar
        logger.exception("no se pudo encolar la corrida %s", corrida_id)


# --- Escritura --------------------------------------------------------------


@router.post(
    "", status_code=status.HTTP_202_ACCEPTED, response_model=CorridaCreada)
async def crear_corrida(
    cuerpo: CorridaCreate,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
    runner: CorridaRunner = Depends(get_corrida_runner),
):
    """Crea la corrida PENDIENTE (preflight síncrono) y la encola."""
    try:
        corrida = await servicio.crear_corrida(
            db, fecha_corte=cuerpo.fecha_corte,
            sucursal_ids=cuerpo.sucursal_ids, overrides=cuerpo.overrides,
            usuario_id=uuid.UUID(user.user_id), nota=cuerpo.nota or None)
    except ErrorCorrida as error:
        await db.rollback()
        raise _rechazo(error) from error
    await db.commit()
    await _enqueue(runner, corrida.id)
    return CorridaCreada(
        id=corrida.id, codigo=corrida.codigo, estado=corrida.estado,
        es_escenario=corrida.es_escenario)


async def _transicion(db, operacion, *args) -> CorridaEstado:
    """Cierra o anula: 404 si no existe, 409 coded si no lo admite."""
    try:
        corrida = await operacion(db, *args)
    except LookupError as error:
        await db.rollback()
        raise _no_existe() from error
    except ErrorCorrida as error:
        await db.rollback()
        raise _rechazo(error) from error
    await db.commit()
    return CorridaEstado(
        id=corrida.id, codigo=corrida.codigo, estado=corrida.estado)


@router.post("/{corrida_id}/cerrar", response_model=CorridaEstado)
async def cerrar_corrida(
    corrida_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """BORRADOR -> CERRADA (inmutable)."""
    return await _transicion(
        db, servicio.cerrar_corrida, corrida_id, uuid.UUID(user.user_id))


@router.post("/{corrida_id}/anular", response_model=CorridaEstado)
async def anular_corrida(
    corrida_id: uuid.UUID,
    cuerpo: CorridaAnular,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """PENDIENTE, CALCULANDO, FALLIDA o BORRADOR -> ANULADA."""
    return await _transicion(
        db, servicio.anular_corrida, corrida_id, uuid.UUID(user.user_id),
        cuerpo.motivo)


# --- Lectura ----------------------------------------------------------------


@router.get("", response_model=PaginaCorridas)
async def listar_corridas(
    proveedor_id: Optional[uuid.UUID] = None,
    estado: Optional[ESTADOS] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    escenario: Optional[bool] = None,
    limite: int = Query(PAGINA_CORRIDAS, ge=1, le=PAGINA_CORRIDAS_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_read),
):
    """Corridas filtradas por proveedor, estado, rango de `fecha_corte` y
    escenario (la más reciente primero)."""
    items, total = await consultas.listar(
        db, alcance=_alcance(user), proveedor_id=proveedor_id,
        estado=estado, desde=desde, hasta=hasta, escenario=escenario,
        limite=limite, offset=offset)
    return PaginaCorridas(
        items=items, total=total, limite=limite, offset=offset)


@router.get("/{corrida_id}", response_model=CorridaDetalle)
async def detalle_corrida(
    corrida_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_read),
):
    """Cabecera, cargas usadas, snapshot, estado por sucursal, resumen,
    avisos y la antigüedad de cada dato de entrada."""
    cuerpo = await consultas.detalle(db, corrida_id, _alcance(user))
    if cuerpo is None:
        raise _no_existe()
    return cuerpo


@router.get("/{corrida_id}/progreso", response_model=Progreso)
async def progreso_corrida(
    corrida_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_read),
):
    cuerpo = await consultas.progreso(db, corrida_id, _alcance(user))
    if cuerpo is None:
        raise _no_existe()
    return cuerpo


@router.get("/{corrida_id}/lineas", response_model=PaginaLineas)
async def lineas_corrida(
    corrida_id: uuid.UUID,
    sucursal_id: Optional[uuid.UUID] = None,
    incluir_excluidas: bool = False,
    clase: Optional[str] = None,
    estado_quiebre: Optional[str] = None,
    limite: int = Query(PAGINA_LINEAS, ge=1, le=PAGINA_LINEAS_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_read),
):
    """Líneas paginadas. Las excluidas (sustituidas o sin reemplazo) sólo
    con `incluir_excluidas`."""
    alcance = _alcance(user)
    if alcance is not None and sucursal_id is not None \
            and sucursal_id not in alcance:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esa sucursal.")
    pagina = await consultas.lineas(
        db, corrida_id, alcance, sucursal_id=sucursal_id,
        incluir_excluidas=incluir_excluidas, clase=clase,
        estado_quiebre=estado_quiebre, limite=limite, offset=offset)
    if pagina is None:
        raise _no_existe()
    filas, total = pagina
    return PaginaLineas(
        items=[LineaRead.model_validate(f) for f in filas], total=total,
        limite=limite, offset=offset)
