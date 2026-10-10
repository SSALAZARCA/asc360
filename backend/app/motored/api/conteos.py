"""
Motored -- inventory counts, leader API (odd/motored-conteos-inventario,
WU6/WU7/WU8/WU9/WU10; design §6.1, §5.1, §5.2, §5.3, §4.3).

Prefix `/api/motored/conteos`. The path rules already let LIDER_INVENTARIOS,
COORDINADOR_REPUESTOS and GERENCIA reach it; each endpoint then picks its
roles. A leader is LIDER_INVENTARIOS or COORDINADOR_REPUESTOS (owner
decision 2026-10-09; `snapshot.ROLES_LIDER_CONTEO`):

- reads: ADMIN, the leaders, GERENCIA;
- schedule, reschedule or change the leader, annul, the leaders list:
  ADMIN only (owner decision);
- iniciar, mark / unmark a pending item "Verificado en el ERP" (WU15),
  rotate the code, the QR, disconnect a pair, create / rename /
  deactivate the store's locations, end round 1, add / assign /
  auto-assign / cancel reconteos, close: ADMIN or the assigned leader.
  GERENCIA gets 403 on every write (it reads the differences, the
  result and the Excel downloads).

Scoping: a leader only sees its own conteos (`lider_id`); another's
answers 404, never 403, so ids do not leak (`consultas.conteo_visible`).

Test counts (`es_prueba`, odd/tasks/motored-conteo-prueba.md): only ADMIN
schedules, sees and deletes them; every other role gets 404, and the list
shows them to ADMIN only with `incluir_pruebas=true`.

Domain errors (`ErrorConteo`) become `{"detail": {"code", "mensaje",
...datos}}` with the status from `_ESTADO_HTTP`. No response carries
`codigo_hash` or a cédula; the plain code is returned only by iniciar and
rotar, the two moments it exists.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import (
    get_motored_db_or_503, require_motored_ready, require_roles,
)
from app.motored.models.conteo import ESTADOS_ABIERTOS, Conteo
from app.motored.schemas import conteos as esquemas
from app.motored.services.auth import MotoredUser
from app.motored.services.conteos import (
    acceso, cierre, consultas, diferencias, errores, excel_ajustes, panel,
    pendientes, reconteos, sesiones, snapshot, ubicaciones,
)
from app.motored.services.corridas.exportacion_hmcl import (
    content_disposition,
)
from app.motored.services.reloj import hoy_bogota

ADMIN = "ADMIN"
LECTORES = (ADMIN, "GERENCIA") + consultas.ROLES_LIDER
OPERADORES = (ADMIN,) + consultas.ROLES_LIDER
PREFIJO_API = "/api/motored/conteos"
ESTADOS_EDITABLES = ("PROGRAMADO",) + ESTADOS_ABIERTOS
SIN_CACHE = {"Cache-Control": "no-store"}

_ESTADO_HTTP = {
    errores.ConteoNoEncontrado: 404,
    errores.SesionNoEncontrada: 404,
    errores.UbicacionNoEncontrada: 404,
    errores.LecturaNoEncontrada: 404,
    errores.ReconteoNoEncontrado: 404,
    errores.PendienteNoEncontrado: 404,
    errores.CodigoDesconocido: 422,
    errores.ReconteoDuplicado: 409,
    errores.SesionNoDisponible: 409,
    errores.MismaPareja: 409,
    errores.HayParejaElegible: 409,
    errores.SucursalInvalida: 422,
    errores.LiderInvalido: 422,
    errores.PendienteInvalido: 422,
    errores.MotivoRequerido: 422,
    errores.DatosIngresoInvalidos: 422,
    errores.UbicacionInvalida: 422,
    errores.UbicacionChocaReferencia: 422,
    errores.EstadoInvalido: 409,
    errores.NoEsPrueba: 409,
    errores.ConteoTotalAbierto: 409,
    errores.SinInventario: 409,
    errores.InventarioAntiguo: 409,
    errores.PendientesPorSanear: 409,
    errores.UmbralesInvalidos: 409,
    errores.EnlaceSinConfigurar: 409,
    errores.UbicacionInactiva: 409,
    errores.UbicacionDuplicada: 409,
    errores.SinUbicacion: 409,
    errores.RondaCerrada: 409,
    errores.ReconteosAbiertos: 409,
    errores.SinBodegaPrincipal: 409,
    errores.AccesoInvalido: 401,
    errores.SesionInactiva: 401,
    errores.DemasiadosIntentos: 429,
}

router = APIRouter(
    prefix="/conteos",
    tags=["motored-conteos"],
    dependencies=[Depends(require_motored_ready)],
)

lector = require_roles(*LECTORES)
operador = require_roles(*OPERADORES)
solo_admin = require_roles(ADMIN)


def error_http(error: errores.ErrorConteo) -> HTTPException:
    """The HTTP form of a domain error (shared with the public API)."""
    estado = next(
        (_ESTADO_HTTP[c] for c in type(error).__mro__ if c in _ESTADO_HTTP),
        400)
    detalle = {"code": error.codigo, "mensaje": error.mensaje}
    detalle.update(error.datos)
    return HTTPException(status_code=estado, detail=detalle)


def _uuid(usuario: MotoredUser) -> uuid.UUID:
    return uuid.UUID(str(usuario.user_id))


def _acceso(conteo: Conteo) -> Optional[esquemas.AccesoSalida]:
    if conteo.estado not in ESTADOS_ABIERTOS or not conteo.enlace_slug:
        return None
    try:
        url = acceso.url_publica(conteo.enlace_slug)
    except errores.EnlaceSinConfigurar:
        url = None
    return esquemas.AccesoSalida(
        slug=conteo.enlace_slug, url=url,
        qr_url=f"{PREFIJO_API}/{conteo.id}/qr.png",
        codigo_rotado_en=conteo.codigo_rotado_en)


def _resumen(conteo: Conteo, sucursal: str, lider: Optional[str]) -> dict:
    return dict(
        id=conteo.id, tipo=conteo.tipo, estado=conteo.estado,
        origen=conteo.origen, fecha_programada=conteo.fecha_programada,
        sucursal=esquemas.Nombrado(id=conteo.sucursal_id, nombre=sucursal),
        lider=(None if conteo.lider_id is None else esquemas.Nombrado(
            id=conteo.lider_id, nombre=lider or "")),
        iniciado_en=conteo.iniciado_en, cerrado_en=conteo.cerrado_en,
        anulado_en=conteo.anulado_en,
        motivo_anulacion=conteo.motivo_anulacion,
        created_at=conteo.created_at, es_prueba=bool(conteo.es_prueba))


def _snapshot(conteo: Conteo, resumen) -> Optional[esquemas.SnapshotSalida]:
    if resumen is None:
        return None
    return esquemas.SnapshotSalida(
        carga_id=conteo.snapshot_carga_id,
        nombre_archivo=resumen.nombre_archivo,
        fecha_corte=conteo.snapshot_fecha_corte,
        aplicado_en=conteo.snapshot_aplicado_en,
        tomado_en=conteo.snapshot_tomado_en, lineas=resumen.lineas,
        valor_sistema=resumen.valor_sistema, sin_costo=resumen.sin_costo,
        advertencias=conteo.snapshot_advertencias)


async def _detalle(
        db: AsyncSession, conteo: Conteo,
        usuario: MotoredUser) -> esquemas.ConteoDetalle:
    """The full view. GERENCIA (read-only) never gets the access link."""
    datos = await consultas.datos_conteo(db, conteo)
    return esquemas.ConteoDetalle(
        **_resumen(conteo, datos.sucursal, datos.lider),
        snapshot=_snapshot(conteo, datos.snapshot),
        umbrales=esquemas.UmbralesSalida(
            reconteo=conteo.umbral_reconteo_pesos,
            critico=conteo.umbral_critico_pesos),
        acceso=_acceso(conteo) if usuario.role in OPERADORES else None)


def _sesion_lider(fila: sesiones.FilaSesion) -> esquemas.SesionLider:
    nombres = [p.nombre for p in fila.integrantes]
    ubicacion = fila.ubicacion
    sesion = fila.sesion
    return esquemas.SesionLider(
        id=sesion.id, numero=fila.numero,
        etiqueta=sesiones.etiqueta(fila.numero, nombres),
        estado=sesion.estado, dispositivo=sesion.dispositivo,
        integrantes=nombres,
        ubicacion_actual=(None if ubicacion is None else
                          esquemas.UbicacionSalida(
                              id=ubicacion.id, nombre=ubicacion.nombre)),
        conectada_en=sesion.conectada_en,
        ultima_actividad_en=sesion.ultima_actividad_en,
        desconectada_en=sesion.desconectada_en)


# --- lists (static paths first: they would match `/{conteo_id}`) ------------


@router.get("", response_model=List[esquemas.ConteoResumen])
async def listar_conteos(
    estado: Optional[esquemas.EstadoConteo] = Query(default=None),
    sucursal_id: Optional[uuid.UUID] = Query(default=None),
    tipo: Optional[esquemas.TipoConteo] = Query(default=None),
    incluir_pruebas: bool = Query(default=False),
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Test counts only for ADMIN, and only when asked."""
    lider_id = _uuid(usuario) if consultas.es_lider(usuario) else None
    filas = await consultas.listar(
        db, estado=estado, sucursal_id=sucursal_id, tipo=tipo,
        lider_id=lider_id,
        incluir_pruebas=incluir_pruebas and consultas.es_admin(usuario))
    avances = await panel.progreso(
        db, [c.id for c, _, _ in filas if c.estado in ESTADOS_ABIERTOS])
    return [esquemas.ConteoResumen(
        **_resumen(c, s, lid), progreso=_progreso(avances, c))
        for c, s, lid in filas]


def _progreso(avances, conteo: Conteo) -> Optional[esquemas.ProgresoConteo]:
    """Open conteos only; one with no snapshot line shows 0 of 0."""
    if conteo.estado not in ESTADOS_ABIERTOS:
        return None
    avance = avances.get(conteo.id, panel.Progreso(0, 0))
    return esquemas.ProgresoConteo(**avance._asdict())


@router.get("/lideres", response_model=List[esquemas.LiderOpcion])
async def listar_lideres(
    usuario: MotoredUser = Depends(solo_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    filas = await consultas.lideres_activos(db)
    return [esquemas.LiderOpcion(
        id=f.id, nombre=f.nombre, email=f.email, rol=f.rol) for f in filas]


@router.get("/sucursales", response_model=List[esquemas.SucursalOpcion])
async def listar_sucursales(
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    return await consultas.sucursales(db)


# --- schedule (ADMIN) --------------------------------------------------------


@router.post("", response_model=esquemas.ConteoDetalle, status_code=201)
async def programar(
    cuerpo: esquemas.ProgramarEntrada,
    usuario: MotoredUser = Depends(solo_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    try:
        conteo = await snapshot.programar_conteo(
            db, cuerpo.sucursal_id, cuerpo.lider_id,
            cuerpo.fecha_programada, _uuid(usuario),
            es_prueba=cuerpo.es_prueba)
        salida = await _detalle(db, conteo, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return salida


@router.patch("/{conteo_id}", response_model=esquemas.ConteoDetalle)
async def reprogramar(
    conteo_id: uuid.UUID,
    cuerpo: esquemas.ReprogramarEntrada,
    usuario: MotoredUser = Depends(solo_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    try:
        conteo = await snapshot.reprogramar_conteo(
            db, conteo_id, cuerpo.fecha_programada, cuerpo.lider_id)
        salida = await _detalle(db, conteo, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return salida


@router.post("/{conteo_id}/anular", response_model=esquemas.ConteoDetalle)
async def anular(
    conteo_id: uuid.UUID,
    cuerpo: esquemas.AnularEntrada,
    usuario: MotoredUser = Depends(solo_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    try:
        conteo = await snapshot.anular_conteo(
            db, conteo_id, _uuid(usuario), cuerpo.motivo)
        salida = await _detalle(db, conteo, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return salida


@router.delete(
    "/{conteo_id}", status_code=204, response_class=Response)
async def borrar_prueba(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(solo_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Hard-deletes a TEST conteo with every row keyed to it, in any
    estado. A real conteo is a 409 NO_ES_PRUEBA: it is never deleted."""
    try:
        await snapshot.borrar_conteo_prueba(db, conteo_id)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return Response(status_code=204)


# --- one conteo --------------------------------------------------------------


@router.get("/{conteo_id}", response_model=esquemas.ConteoDetalle)
async def detalle(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
        return await _detalle(db, conteo, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error


@router.post("/{conteo_id}/iniciar", response_model=esquemas.IniciarSalida)
async def iniciar(
    conteo_id: uuid.UUID,
    cuerpo: Optional[esquemas.IniciarEntrada] = None,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """PROGRAMADO -> EN_CONTEO. The only answer with the plain code; a
    stale inventory and the store's pending invoices / transfers are
    409s with their facts until each is confirmed (any order)."""
    cuerpo = cuerpo or esquemas.IniciarEntrada()
    try:
        await consultas.conteo_visible(db, conteo_id, usuario)
        inicio = await snapshot.iniciar_conteo(
            db, conteo_id, _uuid(usuario),
            confirmar_inventario_viejo=cuerpo.confirmar_antiguedad,
            confirmar_pendientes=cuerpo.confirmar_pendientes)
        conteo = await _detalle(db, inicio.conteo, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.IniciarSalida(
        conteo=conteo, codigo=inicio.codigo,
        advertencia=inicio.advertencia)


# --- pendientes por sanear (WU15) --------------------------------------------


async def _pendientes(db: AsyncSession, conteo: Conteo) -> dict:
    return await pendientes.leer(
        db, conteo.sucursal_id, hoy_bogota(),
        pendientes.verificados_de(conteo.snapshot_advertencias))


@router.get("/{conteo_id}/pendientes")
async def leer_pendientes(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """The store's invoices pending ingreso and transfers pending
    reception, each with its ERP mark, plus the load dates."""
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    return await _pendientes(db, conteo)


@router.post("/{conteo_id}/pendientes/verificar")
async def verificar_pendiente(
    conteo_id: uuid.UUID,
    cuerpo: esquemas.PendienteEntrada,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Marks an item "Verificado en el ERP" on THIS conteo only
    (PROGRAMADO). Answers the refreshed list."""
    try:
        await consultas.conteo_visible(db, conteo_id, usuario)
        conteo = await pendientes.marcar(
            db, conteo_id, cuerpo.tipo, cuerpo.clave, _uuid(usuario),
            datetime.now(timezone.utc))
        salida = await _pendientes(db, conteo)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return salida


@router.post("/{conteo_id}/pendientes/desverificar")
async def desverificar_pendiente(
    conteo_id: uuid.UUID,
    cuerpo: esquemas.PendienteEntrada,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Undoes the ERP mark (PROGRAMADO). Answers the refreshed list."""
    try:
        await consultas.conteo_visible(db, conteo_id, usuario)
        conteo = await pendientes.desmarcar(
            db, conteo_id, cuerpo.tipo, cuerpo.clave)
        salida = await _pendientes(db, conteo)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return salida


@router.post(
    "/{conteo_id}/codigo/rotar", response_model=esquemas.CodigoSalida)
async def rotar_codigo(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """A new code; the old one stops working, connected pairs keep
    counting. The only answer with the new plain code."""
    ahora = datetime.now(timezone.utc)
    try:
        await consultas.conteo_visible(db, conteo_id, usuario)
        codigo = await acceso.rotar_codigo(db, conteo_id, ahora)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.CodigoSalida(codigo=codigo, rotado_en=ahora)


@router.get("/{conteo_id}/qr.png", response_class=Response)
async def qr(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """The QR of the pairs' join URL (the code is never inside)."""
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
        if conteo.estado not in ESTADOS_ABIERTOS or not conteo.enlace_slug:
            raise errores.EstadoInvalido(
                "El QR solo existe mientras el conteo está en curso.",
                estado=conteo.estado)
        url = acceso.url_publica(conteo.enlace_slug)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    return Response(
        acceso.qr_png(url), media_type="image/png", headers=SIN_CACHE)


# --- pair sessions -----------------------------------------------------------


@router.get(
    "/{conteo_id}/sesiones", response_model=List[esquemas.SesionLider])
async def listar_sesiones(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    return [_sesion_lider(f) for f in await sesiones.listar(db, conteo.id)]


@router.post(
    "/{conteo_id}/sesiones/{sesion_id}/desconectar",
    response_model=esquemas.SesionLider)
async def desconectar_sesion(
    conteo_id: uuid.UUID,
    sesion_id: uuid.UUID,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """The leader cuts a pair; its readings are kept."""
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
        fila = await sesiones.desconectar(
            db, conteo.id, sesion_id, _uuid(usuario))
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return _sesion_lider(fila)


# --- the store's locations (WU8) ---------------------------------------------


def _ubicacion_lider(ubicacion) -> esquemas.UbicacionLider:
    return esquemas.UbicacionLider(
        id=ubicacion.id, codigo=ubicacion.codigo, nombre=ubicacion.nombre,
        activa=ubicacion.activa, origen=ubicacion.origen,
        created_at=ubicacion.created_at)


async def _conteo_editable(
        db: AsyncSession, conteo_id: uuid.UUID,
        usuario: MotoredUser) -> Conteo:
    """A visible conteo that is not finished (locations are prepared
    before and fixed during a count)."""
    conteo = await consultas.conteo_visible(db, conteo_id, usuario)
    if conteo.estado not in ESTADOS_EDITABLES:
        raise errores.EstadoInvalido(
            "Las ubicaciones solo se editan desde un conteo programado o "
            "en curso.", estado=conteo.estado)
    return conteo


@router.get(
    "/{conteo_id}/ubicaciones",
    response_model=List[esquemas.UbicacionLider])
async def listar_ubicaciones(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Every location of the conteo's store, inactive ones included;
    `origen` 'PAREJA' marks one a pair created during a count."""
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    filas = await ubicaciones.listar(
        db, conteo.sucursal_id, solo_activas=False)
    return [_ubicacion_lider(u) for u in filas]


@router.post(
    "/{conteo_id}/ubicaciones", response_model=esquemas.UbicacionLider,
    status_code=201)
async def crear_ubicacion(
    conteo_id: uuid.UUID,
    cuerpo: esquemas.UbicacionCrear,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Body `{codigo, nombre?}`; `codigo` may carry the `UBI-` prefix."""
    try:
        conteo = await _conteo_editable(db, conteo_id, usuario)
        ubicacion = await ubicaciones.crear(
            db, conteo.sucursal_id, cuerpo.codigo, cuerpo.nombre,
            _uuid(usuario))
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return _ubicacion_lider(ubicacion)


@router.patch(
    "/{conteo_id}/ubicaciones/{ubicacion_id}",
    response_model=esquemas.UbicacionLider)
async def editar_ubicacion(
    conteo_id: uuid.UUID,
    ubicacion_id: uuid.UUID,
    cuerpo: esquemas.UbicacionEditar,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Body `{nombre?, activa?}`: rename and/or (de)activate. The code
    never changes (its label may be printed)."""
    try:
        conteo = await _conteo_editable(db, conteo_id, usuario)
        ubicacion = await ubicaciones.editar(
            db, conteo.sucursal_id, ubicacion_id, cuerpo.nombre,
            cuerpo.activa)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return _ubicacion_lider(ubicacion)


# --- reconteo (WU9) ----------------------------------------------------------


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def _etiquetas(
        db: AsyncSession, conteo_id: uuid.UUID) -> Dict[uuid.UUID, str]:
    """session id -> 'Pareja N · Ana R. y Luis G.'."""
    return {
        f.sesion.id: sesiones.etiqueta(
            f.numero, [p.nombre for p in f.integrantes])
        for f in await sesiones.listar(db, conteo_id)}


def _en_diferencia(
        vista, etiquetas) -> Optional[esquemas.ReconteoEnDiferencia]:
    if vista is None:
        return None
    sesion = None
    if vista.sesion_id is not None:
        sesion = esquemas.SesionCorta(
            id=vista.sesion_id, etiqueta=etiquetas.get(vista.sesion_id, ""))
    return esquemas.ReconteoEnDiferencia(
        id=vista.id, estado=vista.estado, origen=vista.origen,
        sesion=sesion,
        misma_pareja_autorizada=vista.misma_pareja_autorizada)


def _diferencia(fila, etiquetas) -> esquemas.DiferenciaSalida:
    datos = fila._asdict()
    datos["reconteo"] = _en_diferencia(fila.reconteo, etiquetas)
    return esquemas.DiferenciaSalida(**datos)


@router.get(
    "/{conteo_id}/diferencias", response_model=esquemas.DiferenciasSalida)
async def ver_diferencias(
    conteo_id: uuid.UUID,
    filtro: esquemas.FiltroDiferencias = Query(default="todas"),
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Leader-only: system vs counted per code, valued at the frozen
    cost, largest |value| first. `parcial` while round 1 is open."""
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    lista = await diferencias.listar(db, conteo)
    etiquetas = await _etiquetas(db, conteo.id)
    return esquemas.DiferenciasSalida(
        estado=conteo.estado, parcial=conteo.estado == "EN_CONTEO",
        umbrales=esquemas.UmbralesSalida(
            reconteo=conteo.umbral_reconteo_pesos,
            critico=conteo.umbral_critico_pesos),
        total=len(lista), criticas=sum(1 for f in lista if f.critico),
        en_reconteo=sum(1 for f in lista if f.reconteo is not None),
        items=[_diferencia(f, etiquetas)
               for f in diferencias.filtrar(lista, filtro)])


@router.get(
    "/{conteo_id}/panel",
    response_model=Union[esquemas.PanelSinCambios, esquemas.PanelSalida])
async def ver_panel(
    conteo_id: uuid.UUID,
    version: Optional[int] = Query(default=None),
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """The live panel (ADR-8). With the client's last `version` still
    current, the answer is `{version, sin_cambios: true}` from ONE
    query; otherwise the progress, partial accuracy, pairs and the
    differences summary."""
    try:
        huella = await panel.huella(db, conteo_id)
        if huella is None or not (
                consultas.ve_prueba(usuario, huella.es_prueba)
                and consultas.ve_lider(usuario, huella.lider_id)):
            raise errores.ConteoNoEncontrado()
        if version == huella.version:
            return esquemas.PanelSinCambios(version=version)
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    return await panel.armar(db, conteo, huella.version)


@router.post(
    "/{conteo_id}/terminar-ronda", response_model=esquemas.FinRondaSalida)
async def terminar_ronda(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """EN_CONTEO -> EN_RECONTEO; creates the threshold reconteos."""
    try:
        await consultas.conteo_visible(db, conteo_id, usuario)
        fin = await reconteos.terminar_ronda(db, conteo_id, _ahora())
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.FinRondaSalida(
        estado=fin.conteo.estado,
        ronda_terminada_en=fin.conteo.ronda_terminada_en,
        diferencias=fin.diferencias, reconteos_creados=fin.reconteos)


@router.post(
    "/{conteo_id}/reconteos", response_model=esquemas.ReconteoLider,
    status_code=201)
async def crear_reconteo(
    conteo_id: uuid.UUID,
    cuerpo: esquemas.ReconteoManualEntrada,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Body `{codigo}`: a manual reconteo, under the amount or not."""
    try:
        await consultas.conteo_visible(db, conteo_id, usuario)
        reconteo = await reconteos.crear_manual(db, conteo_id, cuerpo.codigo)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.ReconteoLider.model_validate(reconteo)


@router.post(
    "/{conteo_id}/reconteos/auto-asignar",
    response_model=esquemas.RepartoSalida)
async def auto_asignar(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Spreads the PENDIENTE reconteos over the eligible connected
    pairs; `sin_pareja` are the ones no eligible pair could take."""
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
        resultado = await reconteos.auto_asignar(
            db, conteo, _uuid(usuario), _ahora())
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    validar = esquemas.ReconteoLider.model_validate
    return esquemas.RepartoSalida(
        asignados=[validar(r) for r in resultado.asignados],
        sin_pareja=[validar(r) for r in resultado.sin_pareja])


@router.post(
    "/{conteo_id}/reconteos/{reconteo_id}/asignar",
    response_model=esquemas.ReconteoLider)
async def asignar_reconteo(
    conteo_id: uuid.UUID,
    reconteo_id: uuid.UUID,
    cuerpo: esquemas.AsignarEntrada,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Body `{sesion_id, autorizar_misma_pareja?, motivo?}`: a different
    pair (disjoint cédulas), or the same one with a reason when no other
    eligible pair is connected."""
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
        reconteo = await reconteos.asignar(
            db, conteo, reconteo_id, cuerpo.sesion_id, _uuid(usuario),
            autorizar=cuerpo.autorizar_misma_pareja, motivo=cuerpo.motivo,
            ahora=_ahora())
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.ReconteoLider.model_validate(reconteo)


@router.post(
    "/{conteo_id}/reconteos/{reconteo_id}/cancelar",
    response_model=esquemas.ReconteoLider)
async def cancelar_reconteo(
    conteo_id: uuid.UUID,
    reconteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    try:
        conteo = await consultas.conteo_visible(db, conteo_id, usuario)
        reconteo = await reconteos.cancelar(
            db, conteo, reconteo_id, _ahora())
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.ReconteoLider.model_validate(reconteo)


# --- close and the adjustment list (WU10) ------------------------------------


@router.post("/{conteo_id}/cerrar", response_model=esquemas.CerrarSalida)
async def cerrar(
    conteo_id: uuid.UUID,
    cuerpo: Optional[esquemas.CerrarEntrada] = None,
    usuario: MotoredUser = Depends(operador),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """EN_RECONTEO -> CERRADO. Open reconteos are a 409 with their
    counts unless `forzar` with a `motivo` (they are cancelled)."""
    cuerpo = cuerpo or esquemas.CerrarEntrada()
    try:
        await consultas.conteo_visible(db, conteo_id, usuario)
        hecho = await cierre.cerrar(
            db, conteo_id, _uuid(usuario), forzar=cuerpo.forzar,
            motivo=cuerpo.motivo, ahora=_ahora())
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.CerrarSalida(
        estado=hecho.conteo.estado, cerrado_en=hecho.conteo.cerrado_en,
        reconteos_cancelados=hecho.reconteos_cancelados,
        motivo_cierre_forzado=hecho.conteo.motivo_cierre_forzado,
        kpi=esquemas.KpiSalida(**hecho.kpi._asdict()))


async def _conteo_en(
        db: AsyncSession, conteo_id: uuid.UUID, usuario: MotoredUser,
        estados, mensaje: str) -> Conteo:
    conteo = await consultas.conteo_visible(db, conteo_id, usuario)
    if conteo.estado not in estados:
        raise errores.EstadoInvalido(mensaje, estado=conteo.estado)
    return conteo


async def _cerrado(
        db: AsyncSession, conteo_id: uuid.UUID,
        usuario: MotoredUser) -> Conteo:
    return await _conteo_en(
        db, conteo_id, usuario, ("CERRADO",),
        "El resultado y los ajustes existen cuando el conteo está "
        "cerrado.")


@router.get(
    "/{conteo_id}/resultado", response_model=esquemas.ResultadoSalida)
async def ver_resultado(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """The KPI and every result line (no pagination: one line per
    referencia of a store), largest |valor| first."""
    try:
        conteo = await _cerrado(db, conteo_id, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    lineas = await cierre.resultado(db, conteo)
    datos = await cierre.encabezado(db, conteo, lineas)
    return esquemas.ResultadoSalida(
        conteo_id=conteo.id, estado=conteo.estado,
        cerrado_en=conteo.cerrado_en,
        motivo_cierre_forzado=datos.motivo_cierre_forzado,
        bodega=datos.bodega, kpi=esquemas.KpiSalida(**datos.kpi._asdict()),
        total=len(lineas),
        items=[esquemas.LineaResultado(**f._asdict()) for f in lineas])


def _excel(contenido: bytes, nombre: str) -> Response:
    return Response(
        contenido, media_type=excel_ajustes.XLSX, headers={
            "Content-Disposition": content_disposition(nombre),
            **SIN_CACHE})


def _libro(conteo: Conteo, datos, lineas, prefijo: str,
           momento: datetime) -> Response:
    """The workbook download; a test count's is marked as such."""
    prueba = bool(conteo.es_prueba)
    nombre = excel_ajustes.nombre_archivo(
        prefijo, datos.codigo_co, hoy_bogota(momento), prueba=prueba)
    return _excel(excel_ajustes.libro(datos, lineas, prueba=prueba), nombre)


@router.get("/{conteo_id}/ajustes.xlsx", response_class=Response)
async def descargar_ajustes(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """The ERP adjustment list of a closed conteo."""
    try:
        conteo = await _cerrado(db, conteo_id, usuario)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    lineas = await cierre.resultado(db, conteo)
    datos = await cierre.encabezado(db, conteo, lineas)
    return _libro(conteo, datos, lineas, "ajustes", datos.cerrado_en)


@router.get("/{conteo_id}/avance.xlsx", response_class=Response)
async def descargar_avance(
    conteo_id: uuid.UUID,
    usuario: MotoredUser = Depends(lector),
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """The same layout from the live differences of an open conteo."""
    try:
        conteo = await _conteo_en(
            db, conteo_id, usuario, ESTADOS_ABIERTOS,
            "El avance solo se descarga con el conteo en curso.")
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    lineas = await cierre.avance(db, conteo)
    datos = await cierre.encabezado(db, conteo, lineas)
    return _libro(conteo, datos, lineas, "avance", _ahora())
