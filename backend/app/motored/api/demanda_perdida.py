"""
Motored Pedidos — indicador de cobertura del bot Lore (sdd/motored-ventas-
perdidas-bot, Phase 6 "Demanda perdida — bot write path", design D1) y
listado ADMIN del panel de Ventas Perdidas (sdd/motored-ventas-perdidas-
panel, Phase 4, design D2).

`GET /api/motored/demanda-perdida/cobertura-bot`: la fecha `ACTIVA` más
reciente del ledger `demanda_perdida_bot_linea` por sucursal -- el
indicador "última carga por bot" que Fase 7 (frontend) consumirá. Design
D1 es explícito: esto es SOLO advisory -- una subida Excel que se superpone
con fechas ya cubiertas por el bot NUNCA debe bloquearse por esto (ese
guard, si existiera, viviría en la ingesta EXCEL, nunca acá; este endpoint
es de solo lectura).

Auth/scoping: el MISMO criterio fail-closed que `api/cargas.py::
_filtrar_errores_por_sucursal`/`_filtrar_staging_por_sucursal` -- un
usuario `SUCURSAL` solo ve sus propias sucursales; los otros 3 roles ven
todas. `ASESOR_MOSTRADOR` nunca llega acá (no tiene acceso a ningún
endpoint web pre-existente, spec "RBAC role enforcement" delta) -- este
router usa `get_current_motored_user`/JWT, no el secreto del bot.

`GET /api/motored/demanda-perdida/bot-lineas` (Phase 4, S4 commit slice):
listado plano ADMIN-only, una fila por `demanda_perdida_bot_linea`, sin
paginación (tope `_LIMITE_BOT_LINEAS`, design D2's own volume mitigation --
mismo criterio de `_BOT_RANGO_MAX_DIAS` en `api/cargas.py::listar_cargas`
para `origen=BOT`, pero con `desde`/`hasta` SIEMPRE requeridos acá -- este
endpoint no tiene un camino "sin filtro de origen" que necesite mantener
`Optional`). No hay NINGÚN filtro `activa`/`activo` (Q1 resuelto del
design: una línea de una sucursal o asesor ya desactivado sigue apareciendo,
editable/anulable, con su flag de actividad expuesto para que el frontend
la etiquete en vez de ocultarla). No hay filtro explícito de `origen` porque
`demanda_perdida_bot_linea` es estructuralmente BOT-only -- Excel nunca
escribe en esa tabla (ver su propio docstring de modelo).

`PATCH /api/motored/demanda-perdida/bot-lineas/{linea_id}` y `POST
/api/motored/demanda-perdida/bot-lineas/{linea_id}/anular` (Phase 5, S5
commit slice, design D3/D4): edición/anulación ADMIN-only de UNA línea
puntual, sin ownership ni ventana de fecha (a diferencia de sus equivalentes
del bot en `api/bot_demanda_perdida.py`) -- un ADMIN actúa sobre cualquier
línea, de cualquier asesor, cualquier fecha. El PATCH reutiliza el `EditarLineaRequest`
del bot (design D3: "This keeps one bounds rule", nunca una segunda regla de
rango paralela) y el mismo despachador `aplicar_delta_demanda_perdida` que
la edición del bot ya usa. El anular delega en `anular_linea_bot` (Phase 3)
-- NUNCA en `anular_registro_bot`, que cancelaría el header completo y sus
líneas hermanas."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.motored.api.bot_demanda_perdida import EditarLineaRequest
from app.motored.deps import (
    MotoredUser,
    get_current_motored_user,
    get_motored_db_or_503,
    require_motored_ready,
    require_roles,
)
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import Usuario
from app.motored.schemas.demanda_perdida_panel import (
    AnularLineaAdminResponse,
    BotLineaAdminRead,
    PersonaRef,
    ReferenciaRef,
    SucursalRef,
)
from app.motored.services import demanda_perdida_bot as demanda_perdida_bot_mod

router = APIRouter(
    prefix="/demanda-perdida",
    tags=["motored-demanda-perdida"],
    dependencies=[Depends(require_motored_ready)],
)

_require_admin = require_roles("ADMIN")

_LINEAS_RANGO_MAX_DIAS = 31
_LIMITE_BOT_LINEAS = 2000


@router.get("/cobertura-bot")
async def cobertura_bot(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
) -> List[dict]:
    stmt = (
        select(DemandaPerdidaBotLinea.sucursal_id, func.max(DemandaPerdidaBotLinea.fecha))
        .where(DemandaPerdidaBotLinea.estado == "ACTIVA")
        .group_by(DemandaPerdidaBotLinea.sucursal_id)
    )

    if user.role == "SUCURSAL":
        propias = [uuid.UUID(sid) for sid in user.sucursal_ids]
        if not propias:
            return []
        stmt = stmt.where(DemandaPerdidaBotLinea.sucursal_id.in_(propias))

    result = await db.execute(stmt)
    return [
        {"sucursal_id": str(sucursal_id), "ultima_fecha_bot": fecha.isoformat()}
        for sucursal_id, fecha in result.all()
    ]


def _validar_rango_lineas(desde: date, hasta: date) -> None:
    """Mismo criterio de `api/cargas.py::_validar_rango_bot` (rango
    inválido -> 422), con un código estructurado para el tope de 31 días
    (design D2: `{"code": "RANGO_MAXIMO_31_DIAS"}`) -- `desde`/`hasta`
    faltantes ya son rechazados por FastAPI antes de llegar acá, al ser
    query params requeridos (a diferencia de `listar_cargas`, que los
    mantiene `Optional` por su propio camino `origen=EXCEL`)."""
    if hasta < desde:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'hasta' no puede ser anterior a 'desde'.",
        )
    if (hasta - desde).days > _LINEAS_RANGO_MAX_DIAS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "RANGO_MAXIMO_31_DIAS"},
        )


def _persona_ref(
    id_: Optional[uuid.UUID], nombre: Optional[str], activo: Optional[bool]
) -> Optional[PersonaRef]:
    """`None` si el `LEFT JOIN` (editor/anulador) no matcheó -- las 3
    columnas vienen NULL juntas siempre (misma fila del alias), así que
    chequear solo `id_` alcanza."""
    if id_ is None:
        return None
    return PersonaRef(id=id_, nombre=nombre, activo=activo)


def _stmt_base_bot_lineas():
    """Joins compartidos entre el listado (`_construir_stmt_bot_lineas`,
    Phase 4) y el re-fetch-y-mapeo de UNA línea tras un PATCH/anular
    (`_obtener_bot_linea_admin_read`, Phase 5) -- el mismo `SELECT` con
    joins de design D2, sin el `WHERE`/`ORDER BY`/`LIMIT` propios de cada
    caller: `INNER JOIN` a `usuario` (asesor), `sucursal`, `referencia` y
    `carga_archivo` (para `log->>'metodo'`), más 2 `LEFT JOIN` a `usuario`
    aliased (editor/anulador, ambos opcionales)."""
    asesor = aliased(Usuario)
    editor = aliased(Usuario)
    anulador = aliased(Usuario)

    return (
        select(
            DemandaPerdidaBotLinea,
            Sucursal.nombre,
            Sucursal.activa,
            asesor.nombre,
            asesor.activo,
            Referencia.codigo,
            Referencia.nombre,
            CargaArchivo.log,
            editor.id,
            editor.nombre,
            editor.activo,
            anulador.id,
            anulador.nombre,
            anulador.activo,
        )
        .join(asesor, asesor.id == DemandaPerdidaBotLinea.usuario_id)
        .join(Sucursal, Sucursal.id == DemandaPerdidaBotLinea.sucursal_id)
        .join(Referencia, Referencia.id == DemandaPerdidaBotLinea.referencia_id)
        .join(CargaArchivo, CargaArchivo.id == DemandaPerdidaBotLinea.carga_id)
        .outerjoin(editor, editor.id == DemandaPerdidaBotLinea.editado_por)
        .outerjoin(anulador, anulador.id == DemandaPerdidaBotLinea.anulado_por)
    )


def _construir_stmt_bot_lineas(
    desde: date,
    hasta: date,
    sucursal_id: Optional[uuid.UUID],
    usuario_id: Optional[uuid.UUID],
    estado: Optional[str],
):
    """Design D2: orden `fecha DESC, created_at DESC`, tope
    `_LIMITE_BOT_LINEAS` filas -- sin envelope de paginación (design D2's
    "bounded flat list, no pagination envelope")."""
    stmt = (
        _stmt_base_bot_lineas()
        .where(
            DemandaPerdidaBotLinea.fecha >= desde,
            DemandaPerdidaBotLinea.fecha <= hasta,
        )
        .order_by(DemandaPerdidaBotLinea.fecha.desc(), DemandaPerdidaBotLinea.created_at.desc())
        .limit(_LIMITE_BOT_LINEAS)
    )
    if sucursal_id is not None:
        stmt = stmt.where(DemandaPerdidaBotLinea.sucursal_id == sucursal_id)
    if usuario_id is not None:
        stmt = stmt.where(DemandaPerdidaBotLinea.usuario_id == usuario_id)
    if estado is not None:
        stmt = stmt.where(DemandaPerdidaBotLinea.estado == estado)
    return stmt


async def _obtener_bot_linea_admin_read(db: AsyncSession, linea_id: uuid.UUID) -> BotLineaAdminRead:
    """Re-fetch-y-mapeo tras un PATCH/anular (Phase 5): mismos joins que el
    listado (`_stmt_base_bot_lineas`), filtrados por `id`, para construir la
    respuesta pública sin duplicar el armado de la query. Se asume que
    `linea_id` existe -- ambos callers ya lo confirmaron antes de mutar."""
    stmt = _stmt_base_bot_lineas().where(DemandaPerdidaBotLinea.id == linea_id)
    result = await db.execute(stmt)
    return _fila_a_bot_linea_admin_read(result.first())


def _fila_a_bot_linea_admin_read(fila) -> BotLineaAdminRead:
    """Convierte una fila del `SELECT` de `_construir_stmt_bot_lineas` en
    la respuesta pública -- aislado del armado de la query para que cada
    uno se pueda leer (y, si hace falta, testear) por separado."""
    (
        linea,
        sucursal_nombre,
        sucursal_activa,
        asesor_nombre,
        asesor_activo,
        referencia_codigo,
        referencia_nombre,
        carga_log,
        editor_id,
        editor_nombre,
        editor_activo,
        anulador_id,
        anulador_nombre,
        anulador_activo,
    ) = fila
    return BotLineaAdminRead(
        linea_id=linea.id,
        carga_id=linea.carga_id,
        fecha=linea.fecha,
        cantidad=float(linea.cantidad),
        estado=linea.estado,
        metodo=(carga_log or {}).get("metodo"),
        created_at=linea.created_at,
        asesor=PersonaRef(id=linea.usuario_id, nombre=asesor_nombre, activo=asesor_activo),
        sucursal=SucursalRef(id=linea.sucursal_id, nombre=sucursal_nombre, activa=sucursal_activa),
        referencia=ReferenciaRef(
            id=linea.referencia_id, codigo=referencia_codigo, nombre=referencia_nombre
        ),
        editado_por=_persona_ref(editor_id, editor_nombre, editor_activo),
        editado_en=linea.editado_en,
        anulado_por=_persona_ref(anulador_id, anulador_nombre, anulador_activo),
        anulado_en=linea.anulado_en,
    )


@router.get("/bot-lineas", response_model=List[BotLineaAdminRead])
async def listar_bot_lineas(
    desde: date,
    hasta: date,
    sucursal_id: Optional[uuid.UUID] = None,
    usuario_id: Optional[uuid.UUID] = None,
    estado: Optional[Literal["ACTIVA", "ANULADA"]] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_admin),
) -> List[BotLineaAdminRead]:
    """Orquesta: valida el rango, arma la query (`_construir_stmt_bot_
    lineas`) y mapea cada fila a la respuesta pública (`_fila_a_bot_linea_
    admin_read`) -- ningún concern propio más allá de eso."""
    _validar_rango_lineas(desde, hasta)
    stmt = _construir_stmt_bot_lineas(desde, hasta, sucursal_id, usuario_id, estado)
    result = await db.execute(stmt)
    return [_fila_a_bot_linea_admin_read(fila) for fila in result.all()]


@router.patch("/bot-lineas/{linea_id}", response_model=BotLineaAdminRead)
async def editar_bot_linea_admin(
    linea_id: uuid.UUID,
    payload: EditarLineaRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> BotLineaAdminRead:
    """Design D3: ADMIN-only, SIN ownership ni ventana de fecha (a
    diferencia de `PATCH /bot/demanda-perdida/lineas/{id}`, cuyo `Editar
    LineaRequest` reutiliza este endpoint para mantener una única regla de
    rango 1..9999, nunca una segunda regla paralela). Mismos códigos
    404/409 que ese endpoint del bot (`LINEA_NO_ENCONTRADA`/`LINEA_
    ANULADA`), sin su chequeo de dueño/`fecha == hoy_bogota()`, que no
    corresponde a un ADMIN.

    `delta == 0` (nueva cantidad igual a la actual) NO estampa `editado_por`/
    `editado_en` -- spec: los 4 campos de auditoría atribuyen únicamente
    acciones REALES del panel, no un guardado sin cambios."""
    result = await db.execute(
        select(DemandaPerdidaBotLinea)
        .where(DemandaPerdidaBotLinea.id == linea_id)
        .with_for_update()
    )
    linea = result.scalars().first()
    if linea is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "LINEA_NO_ENCONTRADA"}
        )
    if linea.estado != "ACTIVA":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "LINEA_ANULADA"}
        )

    nueva_cantidad = Decimal(payload.cantidad)
    delta = nueva_cantidad - linea.cantidad
    if delta != 0:
        await demanda_perdida_bot_mod.aplicar_delta_demanda_perdida(
            db,
            fecha=linea.fecha,
            sucursal_id=linea.sucursal_id,
            referencia_id=linea.referencia_id,
            delta=delta,
            carga_id=linea.carga_id,
        )
        linea.cantidad = nueva_cantidad
        linea.editado_por = uuid.UUID(user.user_id)
        linea.editado_en = datetime.now(timezone.utc)

    await db.commit()
    return await _obtener_bot_linea_admin_read(db, linea_id)


@router.post("/bot-lineas/{linea_id}/anular", response_model=AnularLineaAdminResponse)
async def anular_bot_linea_admin(
    linea_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> AnularLineaAdminResponse:
    """Design D4: mirrors `anular_registro_propio` -- bloquea la línea FOR
    UPDATE, delega TODA la lógica en `anular_linea_bot` (Phase 3), NUNCA en
    `anular_registro_bot` (que cancelaría el header completo y sus líneas
    hermanas). Traduce `LineaYaAnuladaError` a 409 con el MISMO código
    `LINEA_ANULADA` que el PATCH de acá usa para el mismo estado de dominio
    a nivel de línea (a diferencia del código `YA_ANULADA` que `anular_
    registro_propio` usa para el header -- son entidades distintas; este
    panel opera exclusivamente a nivel de línea)."""
    result = await db.execute(
        select(DemandaPerdidaBotLinea)
        .where(DemandaPerdidaBotLinea.id == linea_id)
        .with_for_update()
    )
    linea = result.scalars().first()
    if linea is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "LINEA_NO_ENCONTRADA"}
        )

    try:
        agregado_consistente = await demanda_perdida_bot_mod.anular_linea_bot(db, linea, user)
    except demanda_perdida_bot_mod.LineaYaAnuladaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "LINEA_ANULADA"}
        )

    await db.commit()
    linea_read = await _obtener_bot_linea_admin_read(db, linea_id)
    return AnularLineaAdminResponse(
        **linea_read.model_dump(), agregado_consistente=agregado_consistente
    )
