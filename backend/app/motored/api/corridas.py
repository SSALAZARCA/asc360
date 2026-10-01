"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S7, ADR-9, spec "API
under /api/motored/corridas" y "RBAC (T19)"): `/api/motored/corridas`.

Router delgado: las reglas viven en `services/corridas/` (servicio para
escribir, `consultas` para leer). No hay UI en F3.

RBAC (F4-16): todo `/corridas`, leer o escribir, es sólo de ADMIN y COMPRAS;
SUCURSAL y CONSULTA reciben 403. `_alcance` se conserva y devuelve `None`
para los dos roles permitidos: las consultas siguen aceptando el alcance por
sucursal como defensa en profundidad. SERVICIO_CLIENTE queda afuera por el
confinamiento de prefijos de `deps.get_current_motored_user`.

`POST /corridas` valida y corre el preflight de forma síncrona (un rechazo es
un 422 con su código y, en los de vigencia, el detalle de antigüedades por
tipo), guarda la corrida PENDIENTE, confirma y la encola en el runner: nunca
calcula en línea. Anular responde 409 con el código de la regla
que los rechazó. Ninguna ruta edita `pedido_final` ni el ajuste Z.
"""
import logging
import uuid
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.api import corridas_comun as comun
from app.motored.deps import (
    MotoredUser,
    get_motored_db_or_503,
    require_motored_ready,
)
from app.motored.schemas.corrida import (
    CorridaAnular,
    CorridaCreada,
    CorridaCreate,
    CorridaDetalle,
    CorridaEstado,
    PaginaCorridas,
    PaginaLineas,
    Progreso,
)
from app.motored.services.corridas import consultas, servicio
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

_require_write = comun.require_write
_require_read = comun.require_read

PAGINA_CORRIDAS, PAGINA_CORRIDAS_MAX = 50, 200
PAGINA_LINEAS, PAGINA_LINEAS_MAX = 500, 2000
PEDIDOS = Literal["abiertos", "por_enviar", "enviados"]
ESTADOS = Literal[
    "PENDIENTE", "CALCULANDO", "FALLIDA", "BORRADOR", "EN_REVISION",
    "CERRADA", "ENVIADA", "ANULADA"]


def get_corrida_runner() -> CorridaRunner:
    """Seam inyectable: en producción sólo garantiza el loop en marcha."""
    return SupervisorCorridaRunner()


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
    """Crea la corrida PENDIENTE (preflight síncrono) y la encola. Sólo
    ADMIN lanza un escenario (con `overrides`): E-CORRIDA-062."""
    comun.exigir_admin_para_overrides(user, cuerpo.overrides)
    try:
        corrida = await servicio.crear_corrida(
            db, fecha_corte=cuerpo.fecha_corte,
            sucursal_ids=cuerpo.sucursal_ids, overrides=cuerpo.overrides,
            usuario_id=uuid.UUID(user.user_id), nota=cuerpo.nota or None)
    except ErrorCorrida as error:
        await db.rollback()
        raise comun.rechazo(error) from error
    await db.commit()
    await _enqueue(runner, corrida.id)
    return CorridaCreada(
        id=corrida.id, codigo=corrida.codigo, estado=corrida.estado,
        es_escenario=corrida.es_escenario)


async def _transicion(db, operacion, *args) -> CorridaEstado:
    """Anula: 404 si no existe, 409 coded si no lo admite."""
    try:
        corrida = await operacion(db, *args)
    except LookupError as error:
        await db.rollback()
        raise comun.no_existe() from error
    except ErrorCorrida as error:
        await db.rollback()
        raise comun.rechazo(error) from error
    await db.commit()
    return CorridaEstado(
        id=corrida.id, codigo=corrida.codigo, estado=corrida.estado)


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
    pedidos: Optional[PEDIDOS] = None,
    limite: int = Query(PAGINA_CORRIDAS, ge=1, le=PAGINA_CORRIDAS_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_read),
):
    """Corridas filtradas por proveedor, estado, rango de `fecha_corte`,
    escenario y por el punto del ciclo de sus pedidos (la más reciente
    primero); cada una trae el resumen de sus pedidos."""
    items, total = await consultas.listar(
        db, alcance=comun.alcance_de(user), proveedor_id=proveedor_id,
        estado=estado, desde=desde, hasta=hasta, escenario=escenario,
        limite=limite, offset=offset, pedidos=pedidos)
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
    cuerpo = await consultas.detalle(db, corrida_id, comun.alcance_de(user))
    if cuerpo is None:
        raise comun.no_existe()
    return cuerpo


@router.get("/{corrida_id}/progreso", response_model=Progreso)
async def progreso_corrida(
    corrida_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_read),
):
    cuerpo = await consultas.progreso(db, corrida_id, comun.alcance_de(user))
    if cuerpo is None:
        raise comun.no_existe()
    return cuerpo


@router.get("/{corrida_id}/lineas", response_model=PaginaLineas)
async def lineas_corrida(
    corrida_id: uuid.UUID,
    sucursal_id: Optional[uuid.UUID] = None,
    incluir_excluidas: bool = False,
    clase: Optional[str] = None,
    estado_quiebre: Optional[str] = None,
    q: Optional[str] = None,
    solo_editadas: bool = False,
    solo_fuera_empaque: bool = False,
    limite: int = Query(PAGINA_LINEAS, ge=1, le=PAGINA_LINEAS_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_read),
):
    """Líneas paginadas. Las excluidas (sustituidas o sin reemplazo) sólo
    con `incluir_excluidas`; `q` busca por código o nombre."""
    alcance = comun.alcance_de(user)
    if alcance is not None and sucursal_id is not None \
            and sucursal_id not in alcance:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para ver esa sucursal.")
    pagina = await consultas.lineas(
        db, corrida_id, alcance, sucursal_id=sucursal_id,
        incluir_excluidas=incluir_excluidas, clase=clase,
        estado_quiebre=estado_quiebre, limite=limite, offset=offset,
        q=(q or "").strip() or None, solo_editadas=solo_editadas,
        solo_fuera_empaque=solo_fuera_empaque)
    if pagina is None:
        raise comun.no_existe()
    filas, total = pagina
    ediciones = await consultas.ediciones_de(db, [f.id for f in filas])
    return PaginaLineas(
        items=[comun.linea_read(f, ediciones.get(f.id)) for f in filas],
        total=total, limite=limite, offset=offset)
