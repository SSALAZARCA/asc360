"""
Motored Pedidos — router del bot Lore, superficie de demanda perdida
(sdd/motored-ventas-perdidas-bot, Phase 6 "Demanda perdida — bot write
path", design D3/D4).

Fix-up finding #6 (CRITICAL): extraído de `api/bot.py` -- ese archivo había
crecido a ~850 líneas mezclando 2 concerns sin relación (Fase 5's flujo de
auto-registro/aprobación admin, y esta Fase 6's superficie de escritura de
demanda perdida), el mismo patrón de "archivo gigante multi-concern" que
`gga` ya había señalado en otras fases. Mismo precedente que esta MISMA
fase ya estableció para el endpoint web (`api/demanda_perdida.py`,
extraído como su propio archivo de 65 líneas, montado por separado en
`router.py`).

Monta `/api/motored/bot/*` -- MISMO prefix que `bot.router` (Fase 5), con
las MISMAS dependencias de disponibilidad (`require_motored_ready`,
`require_lore_ready`); FastAPI permite montar 2 `APIRouter`s con el mismo
prefix sin conflicto mientras sus paths no se superpongan (no lo hacen:
`/referencias/resolver`, `/demanda-perdida*` acá vs. `/yo`, `/sucursales`,
`/registro`, `/admin/*` en `bot.py`). Puro reordenamiento de archivos --
sin cambio de comportamiento.

Todos los endpoints acá autenticados por `require_bot_asesor_o_admin`
-- eran la superficie exclusiva del ASESOR_MOSTRADOR (`require_bot_asesor`)
hasta un pedido ad-hoc del dueño del producto, POSTERIOR a la Fase 10
(deliberadamente NO logueado contra la lista numerada de tasks): un ADMIN
también puede registrar ventas perdidas por acá, para CUALQUIER sucursal
activa -- a diferencia de un ASESOR_MOSTRADOR, un ADMIN no tiene filas
`usuario_sucursal` propias, así que `registrar_demanda_perdida` SALTEA el
chequeo `sucursal_id not in actor.sucursal_ids` para ese rol (ver su propio
docstring), sin tocar ese chequeo para ASESOR_MOSTRADOR. El resto de la
superficie (`hoy`/`lineas/{id}`/`{carga_id}/anular`) no necesitó ningún
cambio adicional: ya estaba scopeada por `usuario_id`/dueño del actor, nunca
por sucursal -- un registro propio de un ADMIN es "propio" igual que el de
cualquier asesor. Toda escritura ADITIVA de `demanda_perdida` pasa por
`services/demanda_perdida_bot.py::aplicar_delta_demanda_perdida`, nunca una
segunda implementación del upsert/delta acá.

**Idempotencia de `/demanda-perdida` (load-bearing, flagged explícitamente)**:
design D7 dice "`registro_id = uuid4()` se fija cuando se abre la pantalla
de confirmación y se usa como Idempotency-Key". Se interpreta LITERALMENTE:
el valor del header `Idempotency-Key` ES `carga_archivo.id` (la PK del
header de esta registración), no una clave separada resuelta contra una
tabla de dedup aparte. Un pre-chequeo secuencial (`SELECT ... WHERE id=
:idempotency_key`) es la ruta feliz -- si ya existe Y pertenece al MISMO
actor, se devuelve 200 con el registro existente en vez de reinsertar (un
replay real: doble-tap del cliente, retry de red). Si pertenece a OTRO
actor, 409 (una colisión de UUID entre dos actores distintos es
virtualmente imposible, pero de todos modos no se asume "es un replay"
solo porque el id ya existe). Ese pre-chequeo NO cubre la carrera real
(dos llamadas casi simultáneas con la MISMA key, ninguna ve la fila
todavía): el PK real de `carga_archivo.id` es el backstop -- un
`IntegrityError` de violación de PK en el `commit()` se traduce, tras un
`rollback()` + re-`SELECT`, al mismo 200 idempotente si es del mismo actor
(mismo criterio `except IntegrityError` que Fase 5 ya estableció para
`/registro`/`/admin/vincular`), nunca un 500 sin manejar."""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import get_motored_db_or_503, require_motored_ready
from app.motored.deps_bot import BotActor, require_bot_asesor_o_admin, require_lore_ready
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.services import demanda_perdida_bot as demanda_perdida_bot_mod
from app.motored.services.ingesta.orquestador import resolver_proveedor_principal
from app.motored.services.reloj import hoy_bogota

logger = logging.getLogger("motored.bot_demanda_perdida")

router = APIRouter(
    prefix="/bot",
    tags=["motored-bot"],
    dependencies=[Depends(require_motored_ready), Depends(require_lore_ready)],
)

_MAX_REFERENCIAS_POR_LOTE = 30
_CANTIDAD_MINIMA = 1
_CANTIDAD_MAXIMA = 9999


class ResolverReferenciasRequest(BaseModel):
    """Task 6.5 -- `codigos[≤30]` (design D5's table)."""

    codigos: List[str]

    @field_validator("codigos")
    @classmethod
    def _codigos_no_vacio_y_acotado(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("codigos no puede estar vacío")
        if len(value) > _MAX_REFERENCIAS_POR_LOTE:
            raise ValueError(f"codigos admite un máximo de {_MAX_REFERENCIAS_POR_LOTE} elementos")
        return value


class LineaRegistroRequest(BaseModel):
    referencia_id: uuid.UUID
    cantidad: int

    @field_validator("cantidad")
    @classmethod
    def _cantidad_en_rango(cls, value: int) -> int:
        if not (_CANTIDAD_MINIMA <= value <= _CANTIDAD_MAXIMA):
            raise ValueError(
                f"cantidad debe estar entre {_CANTIDAD_MINIMA} y {_CANTIDAD_MAXIMA}"
            )
        return value


class RegistrarDemandaPerdidaRequest(BaseModel):
    """Task 6.6 -- design D5's table: `{sucursal_id, metodo:MANUAL|FOTO,
    lineas[{referencia_id, cantidad}] unique refs}`."""

    sucursal_id: uuid.UUID
    metodo: str
    lineas: List[LineaRegistroRequest]

    @field_validator("metodo")
    @classmethod
    def _metodo_valido(cls, value: str) -> str:
        if value not in ("MANUAL", "FOTO"):
            raise ValueError("metodo debe ser MANUAL o FOTO")
        return value

    @field_validator("lineas")
    @classmethod
    def _lineas_no_vacias(cls, value: List[LineaRegistroRequest]) -> List[LineaRegistroRequest]:
        if not value:
            raise ValueError("lineas no puede estar vacío")
        return value

    @model_validator(mode="after")
    def _referencias_unicas(self) -> "RegistrarDemandaPerdidaRequest":
        referencia_ids = [linea.referencia_id for linea in self.lineas]
        if len(referencia_ids) != len(set(referencia_ids)):
            raise ValueError("lineas no puede repetir la misma referencia_id")
        return self


class EditarLineaRequest(BaseModel):
    cantidad: int

    @field_validator("cantidad")
    @classmethod
    def _cantidad_en_rango(cls, value: int) -> int:
        if not (_CANTIDAD_MINIMA <= value <= _CANTIDAD_MAXIMA):
            raise ValueError(
                f"cantidad debe estar entre {_CANTIDAD_MINIMA} y {_CANTIDAD_MAXIMA}"
            )
        return value


@router.post("/referencias/resolver")
async def resolver_referencias(
    payload: ResolverReferenciasRequest,
    actor: BotActor = Depends(require_bot_asesor_o_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Task 6.5, design D3 "Reference resolution": exact match `upper(trim(
    codigo))` dentro de `resolver_proveedor_principal()` y `activa`. Más de
    un hit para el mismo texto normalizado cuenta como NO resuelto -- nunca
    hay matching difuso (`sustituida_por` se ignora en v1, design D5)."""
    proveedor_id = await resolver_proveedor_principal(db)
    normalizados: Dict[str, str] = {
        entrada: entrada.strip().upper() for entrada in payload.codigos
    }
    valores_normalizados = set(normalizados.values())

    result = await db.execute(
        select(Referencia.id, Referencia.codigo, Referencia.nombre).where(
            Referencia.proveedor_id == proveedor_id,
            Referencia.activa.is_(True),
            func.upper(func.trim(Referencia.codigo)).in_(valores_normalizados),
        )
    )
    filas_por_normalizado: Dict[str, list] = {}
    for referencia_id, codigo, nombre in result.all():
        filas_por_normalizado.setdefault(codigo.strip().upper(), []).append(
            (referencia_id, codigo, nombre)
        )

    resueltas: List[dict] = []
    no_resueltas: List[str] = []
    for entrada, normalizado in normalizados.items():
        filas = filas_por_normalizado.get(normalizado, [])
        if len(filas) == 1:
            referencia_id, codigo, nombre = filas[0]
            resueltas.append(
                {
                    "entrada": entrada,
                    "referencia_id": str(referencia_id),
                    "codigo": codigo,
                    "nombre": nombre,
                }
            )
        else:
            no_resueltas.append(entrada)
    return {"resueltas": resueltas, "no_resueltas": no_resueltas}


async def _serializar_registro(db: AsyncSession, carga: CargaArchivo) -> dict:
    """Compartido por `registrar_demanda_perdida` (201/200) -- reconstruye
    la respuesta a partir del ledger, nunca de datos en memoria del request
    (imprescindible para el camino de replay idempotente, donde `carga` es
    una fila RE-leída de una registración anterior, no la que el request
    actual construyó)."""
    lineas_result = await db.execute(
        select(DemandaPerdidaBotLinea).where(DemandaPerdidaBotLinea.carga_id == carga.id)
    )
    lineas = lineas_result.scalars().all()
    primera = lineas[0] if lineas else None
    return {
        "carga_id": str(carga.id),
        "sucursal_id": str(primera.sucursal_id) if primera else None,
        "fecha": primera.fecha.isoformat() if primera else None,
        "estado": carga.estado,
        "lineas": [
            {
                "linea_id": str(linea.id),
                "referencia_id": str(linea.referencia_id),
                "cantidad": float(linea.cantidad),
                "estado": linea.estado,
            }
            for linea in lineas
        ],
    }


async def _replay_idempotente_si_existe(
    db: AsyncSession, idempotency_key: uuid.UUID, actor: BotActor, response: Response
) -> Optional[dict]:
    """Fix-up finding #4 -- pre-chequeo de idempotencia extraído de
    `registrar_demanda_perdida`. `None` significa "no existe todavía, seguí
    con el registro nuevo"; un dict significa "ya existía, esto ES la
    respuesta final" (200, ya con `response.status_code` mutado). Levanta
    409 directamente si la clave ya existe pero pertenece a OTRO actor --
    ver el docstring del módulo, sección "Idempotencia", para el contrato
    completo."""
    existente_result = await db.execute(
        select(CargaArchivo).where(CargaArchivo.id == idempotency_key)
    )
    carga_existente = existente_result.scalars().first()
    if carga_existente is None:
        return None
    if str(carga_existente.subido_por) != actor.usuario_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "IDEMPOTENCY_KEY_EN_USO"}
        )
    response.status_code = status.HTTP_200_OK
    return await _serializar_registro(db, carga_existente)


@router.post("/demanda-perdida", status_code=status.HTTP_201_CREATED)
async def registrar_demanda_perdida(
    payload: RegistrarDemandaPerdidaRequest,
    response: Response,
    idempotency_key: uuid.UUID = Header(..., alias="Idempotency-Key"),
    actor: BotActor = Depends(require_bot_asesor_o_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Task 6.6/6.7, design D3/D5: UNA transacción escribe el header
    `carga_archivo(BOT,APLICADO)` + `demanda_perdida_bot_linea[]` + el delta
    ADITIVO de `demanda_perdida` (vía `aplicar_delta_demanda_perdida`, nunca
    una segunda implementación del upsert). `fecha` se computa UNA sola vez
    acá (`hoy_bogota()`) y la comparten TODAS las líneas de esta
    registración -- invariante del que depende `anular_registro_bot(
    validar_ventana=True)` (ver su docstring).

    Fix-up finding #4 (CRITICAL): esta función mezclaba 4 concerns
    (autorización, pre-chequeo + replay temprano de idempotencia,
    construcción de header/líneas, commit-con-recuperación-de-carrera) en
    91 líneas -- el propio `gga` ya había bloqueado este cambio 3 veces por
    eso. Extraída en pasos lineales, cada uno delegado a su propio helper
    (`_replay_idempotente_si_existe`, `_recuperar_de_integrity_error_
    registro`) donde el concern lo amerita.

    Ver el docstring del módulo, sección "Idempotencia", para el contrato
    completo de `Idempotency-Key` = `carga_archivo.id`.

    Fix-up finding #1 del gga post-Fase-10 (function-length, converge con
    los fix-up findings #1/#2 de la revisión de 4 lentes): el chequeo de
    sucursal condicional por rol y su log de auditoría viven en
    `_validar_sucursal_para_actor`; la construcción del header/líneas + el
    delta aditivo vive en `_agregar_registro`. Ver esos dos docstrings para
    el contrato completo de cada paso -- esta función solo orquesta: validar
    sucursal -> replay de idempotencia -> construir registro -> commit-con-
    recuperación-de-carrera."""
    await _validar_sucursal_para_actor(db, payload, actor)

    replay = await _replay_idempotente_si_existe(db, idempotency_key, actor, response)
    if replay is not None:
        return replay

    carga = await _agregar_registro(db, payload, actor, idempotency_key)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        return await _recuperar_de_integrity_error_registro(db, exc, idempotency_key, actor, response)

    return await _serializar_registro(db, carga)


async def _validar_sucursal_para_actor(
    db: AsyncSession, payload: "RegistrarDemandaPerdidaRequest", actor: BotActor
) -> None:
    """Paso 1 de `registrar_demanda_perdida` (gga post-Fase-10, function-
    length): existencia+actividad de la sucursal, pertenencia condicional
    por rol, y el log de auditoría del bypass de ADMIN -- extraído para que
    el endpoint no mezcle esto con la construcción del registro ni el
    commit. Levanta `HTTPException` directamente; no devuelve nada en el
    camino feliz.

    Chequeo de sucursal condicional por rol (ad-hoc, post-Fase-10): un
    ASESOR_MOSTRADOR sigue restringido a `actor.sucursal_ids` (sus propias
    filas `usuario_sucursal`), SIN CAMBIOS. Un ADMIN no tiene ninguna fila
    `usuario_sucursal` propia -- exigirle pertenencia a una lista siempre
    vacía lo bloquearía para TODA sucursal, el resultado opuesto al pedido
    ("puede registrar para cualquier sucursal activa") -- así que este
    chequeo se SALTEA por completo para ese rol. Una `sucursal_id` que no
    existe EN ABSOLUTO sigue fallando más abajo también, vía la violación de
    FK real -> 404 (`_recuperar_de_integrity_error_registro`), para la
    carrera real (sucursal borrada/desactivada ENTRE el chequeo de acá y
    el `commit()`) -- sin tocar esa ruta.

    Fix-up finding #1 (WARNING, resilience): el bypass de ADMIN salteaba MÁS
    de lo previsto -- una `sucursal_id` que EXISTE pero está DESACTIVADA
    (`Sucursal.activa is False`) no tenía NINGÚN chequeo en este camino, para
    NINGÚN rol (un ASESOR_MOSTRADOR cuya sucursal asignada se desactiva sin
    borrar su fila `usuario_sucursal` tampoco quedaba cubierto). Se agrega un
    chequeo explícito de "existe y está activa", aplicado a TODO caller sin
    importar el rol, ANTES del chequeo condicional de pertenencia de abajo
    -- así el bypass de ADMIN solo salta la pregunta "¿es ESTA MI sucursal?",
    nunca la pregunta "¿esta sucursal existe y es usable?". Reutiliza el
    MISMO código 404 `SUCURSAL_NO_ENCONTRADA` que ya devuelve la violación de
    FK más abajo -- indistinguible para un cliente entre "nunca existió" y
    "existe pero está desactivada"."""
    sucursal_result = await db.execute(select(Sucursal).where(Sucursal.id == payload.sucursal_id))
    sucursal = sucursal_result.scalars().first()
    if sucursal is None or not sucursal.activa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "SUCURSAL_NO_ENCONTRADA"}
        )

    if actor.role != "ADMIN" and str(payload.sucursal_id) not in actor.sucursal_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": "SUCURSAL_NO_AUTORIZADA"}
        )

    # Fix-up finding #2 (SUGGESTION, resilience): visibilidad de auditoría --
    # cada vez que el bypass de arriba se ejerce de verdad (sucursal ya
    # validada como existente+activa, y el actor SÍ es ADMIN), se deja
    # rastro explícito con el usuario_id/sucursal_id involucrados.
    if actor.role == "ADMIN":
        logger.info(
            "registrar_demanda_perdida: bypass de sucursal-ownership por ADMIN -- "
            "usuario_id=%s sucursal_id=%s",
            actor.usuario_id, payload.sucursal_id,
        )


async def _agregar_registro(
    db: AsyncSession,
    payload: "RegistrarDemandaPerdidaRequest",
    actor: BotActor,
    idempotency_key: uuid.UUID,
) -> CargaArchivo:
    """Paso 3 de `registrar_demanda_perdida` (gga post-Fase-10, function-
    length): construye el header `carga_archivo(BOT,APLICADO)` +
    `demanda_perdida_bot_linea[]` y aplica el delta ADITIVO de cada línea
    (vía `aplicar_delta_demanda_perdida`, nunca una segunda implementación
    del upsert) -- todo dentro de la MISMA sesión, sin comitear (el commit y
    su recuperación de carrera siguen viviendo en el endpoint, junto al
    `try/except IntegrityError` que ya los envuelve). `fecha` se computa acá
    UNA sola vez (`hoy_bogota()`) y la comparten TODAS las líneas de esta
    registración -- invariante del que depende `anular_registro_bot(
    validar_ventana=True)` (ver su docstring)."""
    fecha = hoy_bogota()
    carga = CargaArchivo(
        id=idempotency_key,
        tipo="DEMANDA_PERDIDA",
        origen="BOT",
        estado="APLICADO",
        subido_por=uuid.UUID(actor.usuario_id),
        log={"metodo": payload.metodo},
    )
    db.add(carga)
    for linea in payload.lineas:
        db.add(
            DemandaPerdidaBotLinea(
                id=uuid.uuid4(),
                carga_id=carga.id,
                usuario_id=uuid.UUID(actor.usuario_id),
                fecha=fecha,
                sucursal_id=payload.sucursal_id,
                referencia_id=linea.referencia_id,
                cantidad=Decimal(linea.cantidad),
                estado="ACTIVA",
            )
        )
        await demanda_perdida_bot_mod.aplicar_delta_demanda_perdida(
            db,
            fecha=fecha,
            sucursal_id=payload.sucursal_id,
            referencia_id=linea.referencia_id,
            delta=Decimal(linea.cantidad),
            carga_id=carga.id,
        )
    return carga


async def _recuperar_de_integrity_error_registro(
    db: AsyncSession,
    exc: IntegrityError,
    idempotency_key: uuid.UUID,
    actor: BotActor,
    response: Response,
) -> dict:
    """Fix-up finding #4/#7 -- rama de "commit con recuperación de carrera"
    extraída de `registrar_demanda_perdida`, que ya había sido bloqueada 3
    veces por `gga` por mezclar demasiados concerns en una sola función.

    Fix-up finding #7 (WARNING, converge risk/resilience/reliability): el
    `except IntegrityError` traducía CUALQUIER violación no relacionada a
    `carga_archivo_pkey` como `REFERENCIA_NO_ENCONTRADA`, sin loguear la
    causa real (`exc.orig`) -- un FK real sobre `sucursal_id` (p.ej. una
    sucursal desactivada entre `GET /sucursales` y esta llamada) quedaba
    mal etiquetado, y CUALQUIER otra violación desconocida se escondía
    detrás del mismo código sin dejar rastro en los logs.

    Se loguea `exc.orig` a nivel ERROR para todo caso que NO sea el replay
    idempotente exitoso (ese no es un error real -- es el camino feliz de
    la carrera de idempotencia, ya cubierto por el pre-chequeo secuencial
    de arriba). El resto de la traducción sigue el criterio ya tested:
    `carga_archivo_pkey` -> replay idempotente (o 409 si es de otro
    actor); un FK real sobre `referencia_id`/`sucursal_id` -> el código
    específico correspondiente; cualquier otra causa desconocida -> su
    PROPIO código (`REGISTRO_INCONSISTENTE`, 409), nunca relabeleada en
    silencio como "referencia no encontrada"."""
    detalle = str(exc.orig)
    if "carga_archivo_pkey" in detalle:
        # Carrera real (post-review-pattern, Fase 5): dos requests con la
        # MISMA Idempotency-Key pasaron ambas el pre-chequeo de arriba
        # antes de que cualquiera comiteara. Re-leer y tratar como el
        # MISMO replay idempotente que el pre-chequeo ya maneja.
        repetida_result = await db.execute(
            select(CargaArchivo).where(CargaArchivo.id == idempotency_key)
        )
        carga_repetida = repetida_result.scalars().first()
        if carga_repetida is not None and str(carga_repetida.subido_por) == actor.usuario_id:
            response.status_code = status.HTTP_200_OK
            return await _serializar_registro(db, carga_repetida)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "IDEMPOTENCY_KEY_EN_USO"}
        )

    logger.error(
        "registrar_demanda_perdida: IntegrityError no relacionado a idempotencia -- "
        "carga_id=%s actor=%s detalle=%s",
        idempotency_key, actor.usuario_id, detalle,
    )
    if "referencia_id" in detalle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "REFERENCIA_NO_ENCONTRADA"}
        )
    if "sucursal_id" in detalle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "SUCURSAL_NO_ENCONTRADA"}
        )
    # Restricción desconocida (p.ej. una FK sobre usuario_id, o cualquier
    # otra que no exista todavía): nunca se relabelea como REFERENCIA_NO_
    # ENCONTRADA -- se devuelve su PROPIO código, limpio, nunca un 500 sin
    # manejar, pero tampoco un caso conocido disfrazado.
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail={"code": "REGISTRO_INCONSISTENTE"}
    )


@router.get("/demanda-perdida/hoy")
async def listar_registros_de_hoy(
    actor: BotActor = Depends(require_bot_asesor_o_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> List[dict]:
    """Task 6.8/6.9, design D4: SOLO los headers propios, no-ANULADO, de
    hoy (Bogotá) -- para el menú de autocorrección. Fuente de "hoy": el
    ledger (`demanda_perdida_bot_linea.fecha`), NUNCA `carga_archivo.
    periodo_desde` -- ver el docstring de `services/demanda_perdida_bot.py`
    (esa columna nunca se puebla para una fila BOT, invariante ya
    shippeado en Fase 3).

    Fix-up finding #5 (CRITICAL): esta función tenía 77 líneas -- 4
    consultas batch seguidas de 2 pasadas de armado de dict con lookup de
    referencia repetido dos veces inline. Extraída en `_cargar_
    relacionados` (las 3 consultas de lookup) y `_construir_respuesta_hoy`
    (el armado de la respuesta), de forma que esta función quede como una
    orquestación corta y legible: traer las líneas propias de hoy, traer
    sus relacionados, armar la respuesta."""
    hoy = hoy_bogota()
    lineas_result = await db.execute(
        select(DemandaPerdidaBotLinea).where(
            DemandaPerdidaBotLinea.usuario_id == uuid.UUID(actor.usuario_id),
            DemandaPerdidaBotLinea.fecha == hoy,
            DemandaPerdidaBotLinea.estado == "ACTIVA",
        )
    )
    lineas = lineas_result.scalars().all()
    if not lineas:
        return []

    cargas_por_id, referencias_por_id, sucursales_por_id = await _cargar_relacionados(db, lineas)
    return _construir_respuesta_hoy(lineas, cargas_por_id, referencias_por_id, sucursales_por_id)


async def _cargar_relacionados(db: AsyncSession, lineas) -> tuple:
    """Fix-up finding #5 -- las 3 consultas batch de `GET .../hoy` (nunca
    N+1: una sola consulta por tabla relacionada, con los ids ya
    deduplicados de `lineas`). Devuelve `(cargas_por_id, referencias_por_id,
    sucursales_por_id)`; `cargas_por_id` solo incluye headers NO-ANULADOS
    (design D4: un header anulado concurrentemente no debe aparecer en el
    menú de autocorrección)."""
    carga_ids = sorted({linea.carga_id for linea in lineas}, key=str)
    cargas_result = await db.execute(
        select(CargaArchivo).where(
            CargaArchivo.id.in_(carga_ids), CargaArchivo.estado != "ANULADO"
        )
    )
    cargas_por_id = {carga.id: carga for carga in cargas_result.scalars().all()}

    referencia_ids = {linea.referencia_id for linea in lineas}
    referencias_result = await db.execute(select(Referencia).where(Referencia.id.in_(referencia_ids)))
    referencias_por_id = {r.id: r for r in referencias_result.scalars().all()}

    sucursal_ids = {linea.sucursal_id for linea in lineas}
    sucursales_result = await db.execute(select(Sucursal).where(Sucursal.id.in_(sucursal_ids)))
    sucursales_por_id = {s.id: s for s in sucursales_result.scalars().all()}

    return cargas_por_id, referencias_por_id, sucursales_por_id


def _construir_respuesta_hoy(
    lineas, cargas_por_id: Dict[uuid.UUID, CargaArchivo], referencias_por_id, sucursales_por_id
) -> List[dict]:
    """Fix-up finding #5 -- el armado de `GET .../hoy`'s respuesta,
    agrupando líneas por `carga_id`. Una línea cuyo `carga_id` no está en
    `cargas_por_id` (el header fue anulado concurrentemente, o no es
    NO-ANULADO por cualquier otro motivo) se excluye del todo -- nunca
    aparece como una carga "fantasma" sin header."""
    lineas_por_carga: Dict[uuid.UUID, list] = {}
    for linea in lineas:
        if linea.carga_id in cargas_por_id:
            lineas_por_carga.setdefault(linea.carga_id, []).append(linea)

    resultado: List[dict] = []
    for carga_id, lineas_de_la_carga in lineas_por_carga.items():
        carga = cargas_por_id[carga_id]
        sucursal = sucursales_por_id.get(lineas_de_la_carga[0].sucursal_id)
        resultado.append(
            {
                "carga_id": str(carga.id),
                "creado_en": carga.created_at.isoformat() if carga.created_at else None,
                "sucursal": (
                    {"id": str(sucursal.id), "nombre": sucursal.nombre} if sucursal else None
                ),
                "lineas": [
                    {
                        "linea_id": str(linea.id),
                        "referencia": {
                            "codigo": (
                                referencias_por_id[linea.referencia_id].codigo
                                if linea.referencia_id in referencias_por_id
                                else None
                            ),
                            "nombre": (
                                referencias_por_id[linea.referencia_id].nombre
                                if linea.referencia_id in referencias_por_id
                                else None
                            ),
                        },
                        "cantidad": float(linea.cantidad),
                    }
                    for linea in lineas_de_la_carga
                ],
            }
        )
    return resultado


@router.patch("/demanda-perdida/lineas/{linea_id}")
async def editar_linea_demanda_perdida(
    linea_id: uuid.UUID,
    payload: EditarLineaRequest,
    actor: BotActor = Depends(require_bot_asesor_o_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Task 6.10/6.11, design D4: no-actor's line -> 404; `fecha !=
    hoy_bogota()` -> 409 `FUERA_DE_VENTANA`; línea `ANULADA` -> 409;
    en caso contrario, `delta = nueva - actual` se aplica vía `aplicar_
    delta_demanda_perdida` (nunca un reemplazo ciego de `demanda_perdida`).

    Fix-up finding #8: `.with_for_update()` acá es un idioma DISTINTO al
    `UPDATE ... WHERE ... RETURNING` atómico que el resto de este módulo
    usa (p.ej. `_reclamar_anulacion`) -- y ambos son necesarios, no
    intercambiables. El lock de fila protege la VENTANA lectura-valida-
    decide (chequear dueño/fecha/estado ANTES de decidir si esta edición
    procede), algo que el idioma de claim atómico no cubre por sí solo
    porque `nueva_cantidad` es un valor provisto por el cliente -- no hay
    un `WHERE` fijo que pueda "ganar" atómicamente contra un valor
    arbitrario. El claim atómico se sigue usando DEBAJO, para la
    transición de estado real una vez tomada la decisión (`aplicar_delta_
    demanda_perdida` -> `construir_upsert_aditivo`/`_ejecutar_delta_
    negativo`, ambos statements column-relative atómicos)."""
    result = await db.execute(
        select(DemandaPerdidaBotLinea)
        .where(DemandaPerdidaBotLinea.id == linea_id)
        .with_for_update()
    )
    linea = result.scalars().first()
    if linea is None or str(linea.usuario_id) != actor.usuario_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "LINEA_NO_ENCONTRADA"}
        )
    if linea.fecha != hoy_bogota():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "FUERA_DE_VENTANA"}
        )
    if linea.estado == "ANULADA":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "LINEA_ANULADA"}
        )

    nueva_cantidad = Decimal(payload.cantidad)
    delta = nueva_cantidad - linea.cantidad
    await demanda_perdida_bot_mod.aplicar_delta_demanda_perdida(
        db,
        fecha=linea.fecha,
        sucursal_id=linea.sucursal_id,
        referencia_id=linea.referencia_id,
        delta=delta,
        carga_id=linea.carga_id,
    )
    linea.cantidad = nueva_cantidad
    await db.commit()
    return {"linea_id": str(linea.id), "cantidad": float(linea.cantidad)}


@router.post("/demanda-perdida/{carga_id}/anular")
async def anular_registro_propio(
    carga_id: uuid.UUID,
    actor: BotActor = Depends(require_bot_asesor_o_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Task 6.12/6.13, design D4: delega TODA la lógica en `anular_
    registro_bot(..., validar_ventana=True)` -- el MISMO servicio que el
    web ADMIN ya usa (`validar_ventana=False`), nunca una segunda
    implementación de la reversa.

    Fix-up finding #8: mismo motivo que `editar_linea_demanda_perdida`
    (ver su docstring) para el `.with_for_update()` de acá -- protege la
    ventana lectura-valida-decide de `_validar_ventana_propia` (dueño +
    fecha de hoy) ANTES de que `anular_registro_bot` decida si esta
    anulación procede. El idioma de claim atómico (`UPDATE ... WHERE ...
    RETURNING`) sigue siendo el que efectivamente transiciona el estado
    una vez tomada esa decisión -- lo ejecuta `_reclamar_anulacion`, DENTRO
    de `anular_registro_bot`, no acá."""
    result = await db.execute(
        select(CargaArchivo).where(CargaArchivo.id == carga_id).with_for_update()
    )
    carga = result.scalars().first()
    if carga is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "CARGA_NO_ENCONTRADA"}
        )

    try:
        await demanda_perdida_bot_mod.anular_registro_bot(db, carga, actor, validar_ventana=True)
    except demanda_perdida_bot_mod.CargaNoPerteneceAlActorError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "CARGA_NO_ENCONTRADA"}
        )
    except demanda_perdida_bot_mod.FueraDeVentanaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "FUERA_DE_VENTANA"}
        )
    except demanda_perdida_bot_mod.CargaYaAnuladaError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "YA_ANULADA"})

    await db.commit()
    return {"carga_id": str(carga.id), "estado": carga.estado}
