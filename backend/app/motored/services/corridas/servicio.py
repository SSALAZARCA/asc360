"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6a, ADR-3/ADR-4/
ADR-5/ADR-9, decisiones #14 y #16): servicio de la corrida.

- `crear_corrida` valida (corte no futuro, overrides, sucursales), corre el
  preflight de forma SÍNCRONA (un rechazo es un `ErrorCorrida` con el bloque
  de antigüedades por tipo) y congela los insumos en la cabecera: parámetros
  con su fuente, maestro de sustitución, cortes, antigüedades y mes en curso
  efectivo. Los parámetros se resuelven AL CORTE (spec "version effective at
  the corte"), no a la fecha de creación.
- `calcular_corrida` es el recorrido directo en la transacción del llamador.
  El job de S6b (`ejecucion.py`) usa las mismas piezas (`preparar`,
  `procesar_sucursal`, `finalizar_corrida`) pero confirma cada sucursal,
  reintenta las fallas transitorias de base y calcula en el ejecutor. Ambos
  reclaman la corrida (PENDIENTE -> CALCULANDO), arman el contexto SÓLO con
  lo congelado, calculan el tránsito al corte una vez y procesan cada
  sucursal en su propio savepoint. Una sucursal que falla queda FALLIDA con
  su código y las demás siguen; una corrida anulada a mitad de camino
  detiene el recorrido (ver `persistencia._guardia`).
- `finalizar_corrida` decide BORRADOR o FALLIDA (sólo si TODAS fallan) y
  verifica, con las cargas bloqueadas `FOR SHARE`, que ninguna se anuló
  mientras corría (si no, la corrida queda `invalidada`). Al quedar BORRADOR
  inicia el pedido de las tiendas OK (`pedido_tienda`, F4).
- `anular_corrida` aplica la regla de anulación. Cerrar es POR TIENDA y vive
  en `pedido_tienda` (F4, B3a); `cerrar_corrida` ya no existe.

Ningún commit acá: la transacción es del llamador. La API (S7, `api/
corridas.py`) crea y anula; el job de S6b las calcula.
"""
import asyncio
import logging
import uuid
from concurrent.futures import Executor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence
from uuid import UUID

from sqlalchemy import func, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import (
    DataError,
    DBAPIError,
    IntegrityError,
    NotSupportedError,
    ProgrammingError,
)

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.services import parametros, parametros_claves as pc
from app.motored.services.corridas import (
    bloqueos,
    cargador,
    cargas_perdida,
    codigos,
    estados,
    parametros_corrida,
    pedido_tienda,
    persistencia,
    transito_corte,
    vigencia,
)
from app.motored.services.corridas.cargador import (
    ContextoCarga, ErrorCargador, indexar_transito)
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import ParametrosMotor
from app.motored.services.reloj import hoy_bogota

logger = logging.getLogger(__name__)

PREFIJO_PRODUCCION = "PED"
PREFIJO_ESCENARIO = "ESC"
MAX_INTENTOS_CODIGO = 5


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# --- Código de la corrida ---------------------------------------------------


def formatear_codigo(prefijo: str, fecha_corte: date, numero: int) -> str:
    """`PED-{añoISO}-S{semanaISO}-{nnn}`; los escenarios usan `ESC-`."""
    anio, semana, _ = fecha_corte.isocalendar()
    return f"{prefijo}-{anio}-S{semana:02d}-{numero:03d}"


async def _ultimo_numero(db, prefijo: str, fecha_corte: date) -> int:
    base = formatear_codigo(prefijo, fecha_corte, 0).rsplit("-", 1)[0]
    resultado = await db.execute(
        select(Corrida.codigo)
        .where(Corrida.codigo.like(f"{base}-%"))
        .order_by(func.length(Corrida.codigo).desc(), Corrida.codigo.desc())
        .limit(1))
    ultimo = resultado.scalars().first()
    return 0 if ultimo is None else int(ultimo.rsplit("-", 1)[1])


async def _insertar_corrida(
    db, valores: Dict[str, Any], escenario: bool,
) -> Corrida:
    """Inserta la cabecera con el siguiente código libre; ante un choque de
    UNIQUE (otra corrida de la misma semana en paralelo) reintenta con el
    siguiente número, en un savepoint para no perder la transacción."""
    prefijo = PREFIJO_ESCENARIO if escenario else PREFIJO_PRODUCCION
    fecha_corte = valores["fecha_corte"]
    numero = await _ultimo_numero(db, prefijo, fecha_corte)
    for intento in range(1, MAX_INTENTOS_CODIGO + 1):
        corrida = Corrida(
            id=uuid.uuid4(),
            codigo=formatear_codigo(prefijo, fecha_corte, numero + intento),
            **valores)
        try:
            async with db.begin_nested():
                db.add(corrida)
                await db.flush()
            return corrida
        except IntegrityError:
            if intento == MAX_INTENTOS_CODIGO:
                raise
    raise AssertionError("inalcanzable")  # pragma: no cover


# --- crear_corrida ----------------------------------------------------------


async def _cargas_vinculadas(db, fecha_corte: date, resultado):
    """Las cargas del preflight más las EXCEL de demanda perdida que el
    cargador va a leer (la ventana depende del modo efectivo del mes en
    curso congelado en `seleccion_datos`)."""
    bloque = resultado.seleccion_datos["mes_en_curso"]
    perdida = await cargas_perdida.cargas_demanda_perdida_excel(
        db, fecha_corte, bloque["modo_efectivo"] == "PONDERADO")
    return {**resultado.cargas_usadas, "demanda_perdida": perdida}


def _validar_overrides(overrides: Optional[Mapping[str, Any]]) -> None:
    try:
        parametros_corrida.validar_overrides(overrides)
    except pc.ErrorParametro as error:
        raise ErrorCorrida(error.codigo, error.mensaje) from error


def _sucursales_invalidas(filas, sucursal_ids) -> List[str]:
    if sucursal_ids is None:
        return [] if filas else ["no hay sucursales activas"]
    existentes = {fila.id for fila in filas}
    faltan = [str(i) for i in sucursal_ids if i not in existentes]
    inactivas = [fila.nombre.strip() for fila in filas if not fila.activa]
    return (
        [f"no existe {i}" for i in faltan]
        + [f"{nombre} está inactiva" for nombre in inactivas])


async def _resolver_sucursales(db, sucursal_ids: Optional[Sequence[UUID]]):
    """Filas `(id, nombre, activa)` en orden de nombre."""
    consulta = select(Sucursal.id, Sucursal.nombre, Sucursal.activa)
    if sucursal_ids is None:
        consulta = consulta.where(Sucursal.activa.is_(True))
    else:
        consulta = consulta.where(Sucursal.id.in_(list(sucursal_ids)))
    filas = (await db.execute(consulta)).all()
    invalidas = _sucursales_invalidas(filas, sucursal_ids)
    if invalidas:
        raise ErrorCorrida(
            codigos.E_CORRIDA_SUCURSAL_INVALIDA,
            codigos.mensaje(
                codigos.E_CORRIDA_SUCURSAL_INVALIDA,
                detalle="; ".join(invalidas)))
    return sorted(filas, key=lambda f: (f.nombre.strip(), str(f.id)))


async def _correr_preflight(db, fecha_corte: date, params):
    try:
        return await vigencia.ejecutar_preflight(db, fecha_corte, params)
    except vigencia.ErrorVigencia as error:
        raise ErrorCorrida(
            error.codigo, error.mensaje, error.detalle) from error


def _seleccion_congelada(resultado) -> Dict[str, Any]:
    """`seleccion_datos` con las antigüedades por tipo (decisión #16), los
    cortes, el mes en curso efectivo y los avisos del preflight."""
    return {
        **resultado.seleccion_datos,
        "advertencias": [
            {"codigo": aviso.codigo, "mensaje": aviso.mensaje}
            for aviso in resultado.advertencias],
    }


def _valores_corrida(
    fecha_corte: date, proveedor, params, resultado, maestro,
    overrides: Optional[Mapping[str, Any]], alcance: str, total: int,
    usuario_id: Optional[UUID], nota: Optional[str] = None,
) -> Dict[str, Any]:
    creada: Dict[str, Any] = {
        "evento": "CREADA", "en": _ahora().isoformat(),
        "usuario_id": None if usuario_id is None else str(usuario_id)}
    if nota:
        creada["nota"] = nota
    return {
        "proveedor_id": proveedor.id,
        "fecha_corte": fecha_corte,
        "estado": estados.PENDIENTE,
        "es_escenario": bool(overrides),
        "overrides": dict(overrides) if overrides else None,
        "alcance": alcance,
        "parametros_en_fecha": fecha_corte,
        "parametros_snapshot": params.snapshot,
        "maestro_sustitucion": persistencia.maestro_a_json(maestro),
        "seleccion_datos": _seleccion_congelada(resultado),
        "sucursales_total": total,
        "usuario_id": usuario_id,
        "log": [creada],
    }


async def crear_corrida(
    db, *, fecha_corte: date, sucursal_ids: Optional[Sequence[UUID]] = None,
    overrides: Optional[Mapping[str, Any]] = None,
    usuario_id: Optional[UUID] = None, hoy: Optional[date] = None,
    nota: Optional[str] = None,
) -> Corrida:
    """Crea la corrida PENDIENTE con sus insumos congelados (ver módulo).

    `nota` (texto libre del POST, ADR-9) no tiene columna: queda en el evento
    CREADA del `log`, que es append-only."""
    if fecha_corte > (hoy or hoy_bogota()):
        raise ErrorCorrida(
            codigos.E_CORRIDA_CORTE_FUTURO,
            codigos.mensaje(codigos.E_CORRIDA_CORTE_FUTURO))
    _validar_overrides(overrides)
    filas = await _resolver_sucursales(db, sucursal_ids)
    ids = [fila.id for fila in filas]
    proveedor = await cargador.cargar_proveedor_principal(db)
    params = await parametros_corrida.cargar_parametros_corrida(
        db, fecha_corte, ids, overrides)
    resultado = await _correr_preflight(db, fecha_corte, params)
    maestro = await cargador.cargar_maestro(db, proveedor.id)
    valores = _valores_corrida(
        fecha_corte, proveedor, params, resultado, maestro, overrides,
        "TODAS" if sucursal_ids is None else "SELECCION", len(ids),
        usuario_id, nota)
    corrida = await _insertar_corrida(db, valores, bool(overrides))
    for orden, sucursal_id in enumerate(ids, start=1):
        db.add(CorridaSucursal(
            corrida_id=corrida.id, sucursal_id=sucursal_id, orden=orden,
            estado=estados.SUC_PENDIENTE))
    persistencia.registrar_cargas(
        db, corrida.id, await _cargas_vinculadas(db, fecha_corte, resultado))
    await db.flush()
    return corrida


# --- calcular_corrida -------------------------------------------------------


async def reclamar_corrida(db, corrida_id: UUID) -> None:
    """PENDIENTE -> CALCULANDO de forma atómica; otro estado es E-040."""
    resultado = await db.execute(
        update(Corrida)
        .where(Corrida.id == corrida_id,
               Corrida.estado == estados.PENDIENTE)
        .values(
            estado=estados.CALCULANDO,
            intentos=Corrida.intentos + 1,
            iniciado_en=func.now(),
            latido_en=func.now())
        .returning(Corrida.id)
        .execution_options(synchronize_session=False))
    if resultado.first() is None:
        raise ErrorCorrida(
            codigos.E_CORRIDA_ESTADO_NO_ADMITE,
            codigos.mensaje(
                codigos.E_CORRIDA_ESTADO_NO_ADMITE,
                estado=f"no es {estados.PENDIENTE}"))


async def _transito(db, corrida: Corrida):
    """W al corte, una vez por corrida. Los parámetros de F2 que el veredicto
    necesita se resuelven antes de llamar al cargador de tránsito."""
    en_fecha = corrida.parametros_en_fecha
    dias, _ = await parametros.resolver_dias_ventana_ingresos(db, en_fecha)
    tolerancia, _ = await parametros.resolver_tolerancia_ingreso_pct(
        db, en_fecha)
    excluir = pc.parsear(
        "excluir_transito_vencido",
        corrida.parametros_snapshot["parametros"][
            "excluir_transito_vencido"]["valor"])
    return await transito_corte.cargar_transito_corte(
        db, corrida.fecha_corte,
        excluir_vencido=excluir,
        dias_ventana_ingresos=int(dias),
        tolerancia_ingreso_pct=float(tolerancia))


async def preparar(db, corrida: Corrida):
    """`(parámetros del motor, contexto del cargador)` desde lo congelado."""
    snapshot, seleccion = corrida.parametros_snapshot, corrida.seleccion_datos
    motor = parametros_corrida.parametros_motor_desde_snapshot(
        snapshot, seleccion)
    proveedor = await cargador.cargar_proveedor_principal(db)
    transito = await _transito(db, corrida)
    maestro = persistencia.maestro_desde_json(corrida.maestro_sustitucion)
    cortes = seleccion["cortes"]
    ctx = ContextoCarga(
        proveedor=proveedor,
        fecha_corte=corrida.fecha_corte,
        corte_inventario=date.fromisoformat(cortes["inventario"]),
        corte_backorder=date.fromisoformat(cortes["backorder"]),
        mes_en_curso=motor.mes_en_curso,
        transito=indexar_transito(transito.w),
        dias_entre_pedidos=dict(
            parametros_corrida.dias_entre_pedidos_desde_snapshot(snapshot)),
        consolidar=motor.consolidar_sustituidas,
        resoluciones=(
            resolver_cadenas(maestro) if motor.consolidar_sustituidas
            else {}),
    )
    return motor, ctx


async def pendientes(db, corrida_id: UUID) -> List[UUID]:
    resultado = await db.execute(
        select(CorridaSucursal.sucursal_id)
        .where(CorridaSucursal.corrida_id == corrida_id,
               CorridaSucursal.estado == estados.SUC_PENDIENTE)
        .order_by(CorridaSucursal.orden))
    return list(resultado.scalars().all())


async def marcar_fallida(
    db, corrida_id: UUID, sucursal_id: UUID, codigo: str, mensaje: str,
) -> bool:
    """`False` si la corrida se anuló mientras tanto (detener el recorrido)."""
    try:
        await persistencia.marcar_sucursal_fallida(
            db, corrida_id, sucursal_id, codigo, mensaje)
    except ErrorCorrida as error:
        if error.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE:
            return False
        raise
    return True


@dataclass(frozen=True)
class CorridaRef:
    """Lo mínimo de la corrida que necesita el recorrido. El job pasa esto y
    no el `Corrida` del ORM: tras un rollback (reintento de una falla
    transitoria) el objeto queda expirado y leerlo en async falla."""

    id: UUID
    codigo: str


_NO_TRANSITORIOS = (
    IntegrityError, DataError, ProgrammingError, NotSupportedError)


def es_transitorio(error: BaseException) -> bool:
    """Falla de base que vale la pena reintentar (conexión, deadlock,
    serialización). Los errores deterministas de SQL (integridad, datos,
    programación) fallarían igual la próxima vez: no se reintentan."""
    return isinstance(error, DBAPIError) and not isinstance(
        error, _NO_TRANSITORIOS)


async def _calcular(ejecutor: Optional[Executor], *args):
    """`calcular_sucursal` en el `ejecutor` (fuera del event loop) o, sin
    ejecutor, en línea (recorrido directo y tests)."""
    if ejecutor is None:
        return calcular_sucursal(*args)
    return await asyncio.get_running_loop().run_in_executor(
        ejecutor, calcular_sucursal, *args)


async def procesar_sucursal(
    db, corrida, sucursal_id: UUID, ctx: ContextoCarga,
    motor: ParametrosMotor, ejecutor: Optional[Executor] = None,
) -> bool:
    """Carga, calcula y guarda UNA sucursal en su savepoint; `False` detiene
    el recorrido (corrida anulada). Aísla las fallas de la sucursal, salvo
    las transitorias de base: esas se relanzan para que el llamador
    reintente. `corrida` es cualquier objeto con `id` y `codigo`."""
    try:
        async with db.begin_nested():
            datos = await cargador.cargar_sucursal(db, sucursal_id, ctx)
            resultado = await _calcular(
                ejecutor, datos.entradas, datos.atributos, motor,
                ctx.resoluciones)
            await persistencia.guardar_sucursal(
                db, corrida.id, datos, resultado,
                consolidar=ctx.consolidar)
        return True
    except ErrorCorrida as error:
        if error.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE:
            return False
        raise
    except ErrorCargador as error:
        return await marcar_fallida(
            db, corrida.id, sucursal_id, error.codigo, error.mensaje)
    except Exception as error:  # aislamiento: nada tumba a las demás
        if es_transitorio(error):
            raise
        logger.exception(
            "corrida %s: falló la sucursal %s", corrida.codigo, sucursal_id)
        return await marcar_fallida(
            db, corrida.id, sucursal_id, codigos.E_CORRIDA_INTERNO,
            codigos.mensaje(codigos.E_CORRIDA_INTERNO))


async def calcular_corrida(
    db, corrida_id: UUID, ejecutor: Optional[Executor] = None,
) -> str:
    """Recorre la corrida completa y devuelve su estado final.

    `ANULADA` si la anularon mientras corría (el recorrido se detiene sin
    finalizar). Ver el docstring del módulo.
    """
    await reclamar_corrida(db, corrida_id)
    corrida = await db.get(Corrida, corrida_id)
    motor, ctx = await preparar(db, corrida)
    for sucursal_id in await pendientes(db, corrida_id):
        if not await procesar_sucursal(
                db, corrida, sucursal_id, ctx, motor, ejecutor):
            return estados.ANULADA
    return await finalizar_corrida(db, corrida_id)


# --- finalizar_corrida ------------------------------------------------------


def con_evento(evento: Dict[str, Any]):
    """Expresión SQL que agrega un evento al `log` append-only."""
    return func.coalesce(Corrida.log, literal([], JSONB)).op("||")(
        literal([evento], JSONB))


async def finalizar_corrida(db, corrida_id: UUID) -> str:
    """BORRADOR si alguna sucursal quedó OK u OMITIDA, si no FALLIDA
    (E-CORRIDA-030); marca `invalidada` si una carga se anuló mientras
    corría. Devuelve el estado, o `ANULADA` si ya no estaba CALCULANDO."""
    anuladas = await bloqueos.cargas_anuladas(db, corrida_id)
    filas = await db.execute(
        select(CorridaSucursal.estado, func.count())
        .where(CorridaSucursal.corrida_id == corrida_id)
        .group_by(CorridaSucursal.estado))
    conteos = dict(filas.all())
    sin_falla = (
        conteos.get(estados.SUC_OK, 0) + conteos.get(estados.SUC_OMITIDA, 0))
    estado = estados.BORRADOR if sin_falla else estados.FALLIDA
    evento: Dict[str, Any] = {
        "evento": "FINALIZADA", "en": _ahora().isoformat(),
        "estado": estado, "sucursales": dict(conteos)}
    if estado == estados.FALLIDA:
        evento["codigo"] = codigos.E_CORRIDA_TODAS_FALLIDAS
    valores: Dict[str, Any] = {
        "estado": estado, "terminado_en": func.now(),
        "log": con_evento(evento)}
    if anuladas:
        valores["invalidada"] = True
        valores["motivo_invalidacion"] = {
            "tipo": "CARGA_ANULADA", "carga_ids": [str(i) for i in anuladas]}
    resultado = await db.execute(
        update(Corrida)
        .where(Corrida.id == corrida_id,
               Corrida.estado == estados.CALCULANDO)
        .values(**valores)
        .returning(Corrida.estado)
        .execution_options(synchronize_session=False))
    if resultado.first() is None:
        return estados.ANULADA
    if estado == estados.BORRADOR:
        await pedido_tienda.iniciar_pedidos(db, corrida_id)
    return estado


# --- Ciclo de vida: anular -----------------------------------------


def _no_admite(estado: str) -> ErrorCorrida:
    return ErrorCorrida(
        codigos.E_CORRIDA_ESTADO_NO_ADMITE,
        codigos.mensaje(codigos.E_CORRIDA_ESTADO_NO_ADMITE, estado=estado))


async def _bloquear_corrida(db, corrida_id: UUID) -> Corrida:
    resultado = await db.execute(
        select(Corrida).where(Corrida.id == corrida_id).with_for_update()
        .execution_options(populate_existing=True))
    corrida = resultado.scalars().first()
    if corrida is None:
        raise LookupError(f"la corrida {corrida_id} no existe")
    return corrida


async def anular_corrida(
    db, corrida_id: UUID, usuario_id: UUID, motivo: str,
) -> Corrida:
    """PENDIENTE/CALCULANDO/FALLIDA/BORRADOR -> ANULADA. Una corrida que
    calcula se detiene de forma cooperativa en su siguiente escritura."""
    corrida = await _bloquear_corrida(db, corrida_id)
    if corrida.estado not in estados.ANULABLES:
        raise _no_admite(corrida.estado)
    corrida.estado = estados.ANULADA
    corrida.anulada_en = _ahora()
    corrida.anulada_por = usuario_id
    corrida.motivo_anulacion = motivo
    await db.flush()
    return corrida
