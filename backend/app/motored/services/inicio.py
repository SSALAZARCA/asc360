"""
Motored "Inicio": what each role should look at today.

`construir_inicio` returns the sections of the caller's role. It owns no
business rule: every number comes from an existing read service.

- `pedidos_borrador` / `ultimo_pedido_enviado`: per-tienda counts from
  `corridas.pedido_tienda.resumen_pedidos`.
- `datos_por_vencer`: the preflight facts and limits
  (`corridas.vigencia`, `corridas.parametros_corrida`) classified with the
  avisos rules (`avisos_antiguedad`): "por vencer" is the day before and
  the day of the last valid day, exactly when the Telegram aviso goes out.
- `detractores_sin_gestionar`: the open cases of `caso_detractor.listar`.
- `encuestas_mes`: the survey loads of the month (Bogota).
- `venta_mes`, `tiendas_verde`, `tiendas_rojo`: the KPI sales tab
  (`tablero_kpis.calcular_kpis_ventas`) for the current month, all
  tiendas, HMCL included; colors and cut-offs come from Configuracion.

Every section runs on its own savepoint and fails soft: an exception is
logged and the section answers `{"disponible": false}`, never a 500 for
the whole page. Read only: nothing here commits.
"""
import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from sqlalchemy import exists, func, select

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.encuesta_carga import EncuestaCarga
from app.motored.services import (
    avisos_antiguedad,
    caso_detractor,
    tablero_asesores_consultas,
    tablero_kpis,
)
from app.motored.services.corridas import (
    estados,
    parametros_corrida,
    pedido_tienda,
    vigencia,
)
from app.motored.services.fechas_utc import a_utc_iso
from app.motored.services.reloj import BOGOTA_OFFSET, hoy_bogota
from app.motored.services.tablero_asesores import HMCL_INCLUIR

logger = logging.getLogger("motored.inicio")

AL_DIA, POR_VENCER = "al_dia", "por_vencer"
VENCIDO, SIN_DATOS = "vencido", "sin_datos"
# `caso_detractor.ESTADOS`: a case nobody has taken yet.
CASO_SIN_GESTIONAR = "ABIERTO"

SECCIONES_POR_ROL: Mapping[str, tuple] = {
    "ADMIN": (
        "pedidos_borrador", "datos_por_vencer",
        "detractores_sin_gestionar"),
    "COMPRAS": (
        "pedidos_borrador", "datos_por_vencer", "ultimo_pedido_enviado"),
    "GERENCIA": ("venta_mes", "tiendas_verde", "tiendas_rojo"),
    "SERVICIO_CLIENTE": ("detractores_sin_gestionar", "encuestas_mes"),
}


@dataclass
class Contexto:
    """One request: the session, Bogota's today and a per-request memo
    (the three management cards share one KPI read)."""

    db: Any
    hoy: date
    memo: Dict[str, Any] = field(default_factory=dict)


# --- Pedidos -----------------------------------------------------------------


async def _resumen(db, corrida) -> Dict[str, int]:
    resumen = await pedido_tienda.resumen_pedidos(db, [corrida.id])
    return resumen.get(corrida.id) or {}


async def _pedidos_borrador(ctx: Contexto) -> Dict[str, Any]:
    """Tiendas in BORRADOR in the latest non-annulled real corrida."""
    fila = (await ctx.db.execute(
        select(Corrida.id, Corrida.codigo)
        .where(Corrida.es_escenario.is_(False),
               Corrida.estado != estados.ANULADA)
        .order_by(Corrida.created_at.desc(), Corrida.codigo.desc())
        .limit(1))).first()
    if fila is None:
        return {"corrida_id": None, "codigo": None, "tiendas": 0,
                "total": 0}
    resumen = await _resumen(ctx.db, fila)
    return {"corrida_id": str(fila.id), "codigo": fila.codigo,
            "tiendas": resumen.get("borrador", 0),
            "total": resumen.get("total", 0)}


async def _ultimo_pedido_enviado(ctx: Contexto) -> Dict[str, Any]:
    """The latest real corrida with a tienda sent, and how many were."""
    enviada = exists().where(
        CorridaSucursal.corrida_id == Corrida.id,
        CorridaSucursal.estado_pedido == estados.PEDIDO_ENVIADO)
    fila = (await ctx.db.execute(
        select(Corrida.id, Corrida.codigo)
        .where(Corrida.es_escenario.is_(False), enviada)
        .order_by(Corrida.created_at.desc(), Corrida.codigo.desc())
        .limit(1))).first()
    if fila is None:
        return {"corrida_id": None, "codigo": None, "enviadas": 0,
                "total": 0}
    resumen = await _resumen(ctx.db, fila)
    return {"corrida_id": str(fila.id), "codigo": fila.codigo,
            "enviadas": resumen.get("enviados", 0),
            "total": resumen.get("total", 0)}


# --- Data staleness ----------------------------------------------------------


def _ultimo_dia(fecha: date) -> date:
    return fecha.replace(
        day=calendar.monthrange(fecha.year, fecha.month)[1])


def _cuando(vence: Optional[date], hoy: date) -> Optional[str]:
    """`hoy` / `manana` when the last valid day is today or tomorrow."""
    return {hoy: "hoy", hoy + timedelta(days=1): "manana"}.get(vence)


def _entrada(tipo: str, fecha: Optional[date], limite: Optional[int],
             vence: Optional[date], hoy: date, estado: str,
             cuando: Optional[str] = None) -> Dict[str, Any]:
    return {
        "tipo": tipo,
        "fecha": None if fecha is None else fecha.isoformat(),
        "antiguedad_dias": (
            None if fecha is None else max(0, (hoy - fecha).days)),
        "limite_dias": limite,
        "vence": None if vence is None else vence.isoformat(),
        "vence_cuando": cuando,
        "estado": estado,
    }


def _entrada_preflight(tipo_carga: str, fecha: Optional[date], limite: int,
                       hoy: date, aviso: Optional[str]) -> Dict[str, Any]:
    """INVENTARIO, BACKORDER, FACTURAS, INGRESOS: valid through
    `fecha + limite` (the preflight blocks from the next day)."""
    if fecha is None:
        return _entrada(tipo_carga, None, limite, None, hoy, SIN_DATOS)
    vence = fecha + timedelta(days=limite)
    if vence < hoy:
        estado = VENCIDO
    else:
        estado = POR_VENCER if aviso else AL_DIA
    return _entrada(tipo_carga, fecha, limite, vence, hoy, estado, aviso)


def _entrada_ventas(vivas, hoy: date) -> Dict[str, Any]:
    """VENTAS has no age limit: the preflight needs the closed months
    covered. Stale when the last closed month is not; por vencer on the
    last two days of a month whose sales are not loaded yet (from the
    first of the next month it becomes a closed month)."""
    hastas = [c.periodo_hasta for c in vivas
              if c.tipo == "VENTAS" and c.periodo_hasta]
    if not hastas:
        return _entrada("VENTAS", None, None, None, hoy, SIN_DATOS)
    ultima = max(hastas)
    if ultima < _ultimo_dia(vigencia.meses_cerrados(hoy)[-1]):
        return _entrada("VENTAS", ultima, None, None, hoy, VENCIDO)
    fin_mes = _ultimo_dia(hoy)
    vence = fin_mes if ultima < fin_mes else None
    cuando = _cuando(vence, hoy)
    estado = POR_VENCER if cuando else AL_DIA
    return _entrada("VENTAS", ultima, None, vence, hoy, estado, cuando)


def estado_de_los_datos(
    hechos: vigencia.HechosVigencia, limites: Mapping[str, int], hoy: date,
) -> List[Dict[str, Any]]:
    """One entry per data type the pedido needs, with the preflight's
    choice of load and the avisos' "por vencer" window."""
    vivas = [
        c for c in hechos.cargas if c.estado == vigencia.ESTADO_APLICADO]
    vigentes = avisos_antiguedad.calcular_vencimientos(hechos, limites, hoy)
    avisos = {
        venc.tipo: etiqueta for venc, etiqueta
        in avisos_antiguedad.avisos_del_dia(vigentes, hoy)}
    entradas = []
    for tipo, espec in vigencia.TIPOS_ANTIGUEDAD.items():
        _, fecha = vigencia.elegir_carga_vigente(vivas, tipo, hoy)
        entradas.append(_entrada_preflight(
            espec[0], fecha, limites[tipo], hoy, avisos.get(tipo)))
    entradas.append(_entrada_ventas(vivas, hoy))
    return entradas


async def _datos_por_vencer(ctx: Contexto) -> Dict[str, Any]:
    params = await parametros_corrida.cargar_parametros_corrida(
        ctx.db, ctx.hoy, ())
    hechos = await vigencia.cargar_hechos(ctx.db, ctx.hoy)
    datos = estado_de_los_datos(hechos, params.limites_antiguedad, ctx.hoy)

    def contar(estado):
        return sum(1 for d in datos if d["estado"] == estado)

    cuenta = {"por_vencer": contar(POR_VENCER), "vencidos": contar(VENCIDO),
              "sin_datos": contar(SIN_DATOS)}
    return {"cantidad": sum(cuenta.values()), **cuenta, "datos": datos}


# --- Survey ------------------------------------------------------------------


async def _detractores_sin_gestionar(ctx: Contexto) -> Dict[str, Any]:
    resultado = await caso_detractor.listar(ctx.db, page=1, page_size=1)
    conteo = resultado["conteo_por_estado"]
    return {"cantidad": conteo.get(CASO_SIN_GESTIONAR, 0)}


def _inicio_de_mes_utc(hoy: date) -> datetime:
    """First instant of the Bogota month as naive UTC, the way
    `encuesta_carga.created_at` is stored."""
    inicio = datetime.combine(hoy.replace(day=1), time.min, BOGOTA_OFFSET)
    return inicio.astimezone(timezone.utc).replace(tzinfo=None)


async def _encuestas_mes(ctx: Contexto) -> Dict[str, Any]:
    del_mes = EncuestaCarga.created_at >= _inicio_de_mes_utc(ctx.hoy)
    fila = (await ctx.db.execute(select(
        func.count(EncuestaCarga.id).filter(del_mes),
        func.sum(EncuestaCarga.total_registros).filter(del_mes),
        func.max(EncuestaCarga.created_at),
    ))).first()
    cargas, registros, ultima = fila
    return {"cargas": int(cargas or 0), "registros": int(registros or 0),
            "ultima_carga": a_utc_iso(ultima)}


# --- Management --------------------------------------------------------------


async def _kpis(ctx: Contexto):
    """`(filtro, ventas)` of the KPI sales tab for the current month,
    read once per request (a failure is remembered and raised again)."""
    previo = ctx.memo.get("kpis")
    if isinstance(previo, Exception):
        raise previo
    if previo is not None:
        return previo
    try:
        filtro = await tablero_asesores_consultas.cargar_filtro(
            ctx.db, [ctx.hoy.strftime("%Y-%m")], HMCL_INCLUIR, None)
        previo = (
            filtro, await tablero_kpis.calcular_kpis_ventas(ctx.db, filtro))
    except Exception as exc:
        ctx.memo["kpis"] = exc
        raise
    ctx.memo["kpis"] = previo
    return previo


async def _venta_mes(ctx: Contexto) -> Dict[str, Any]:
    _, ventas = await _kpis(ctx)
    compania = ventas["cumplimiento"].get("compania")
    base = {
        "mes": ctx.hoy.strftime("%Y-%m"),
        "usando_resumen": ventas.get("usando_resumen"),
        "datos_actualizados_en": ventas.get("datos_actualizados_en"),
    }
    if not compania or not compania.get("presupuesto"):
        venta = compania.get("venta") if compania else None
        return {**base, "estado": "sin_presupuesto", "venta": venta}
    return {**base, "estado": "ok", **{
        k: compania[k] for k in ("venta", "presupuesto", "pct", "semaforo")}}


def _tiendas(ventas) -> Dict[str, int]:
    return ventas["cumplimiento"]["conteos"]["tiendas"]


async def _tiendas_verde(ctx: Contexto) -> Dict[str, Any]:
    filtro, ventas = await _kpis(ctx)
    conteo = _tiendas(ventas)
    return {"cantidad": conteo.get(tablero_kpis.VERDE, 0),
            "total": sum(conteo.values()),
            "desde_pct": filtro.reglas.semaforo["verde_desde"]}


async def _tiendas_rojo(ctx: Contexto) -> Dict[str, Any]:
    """Below the amber cut-off: the KPI's `violeta` (atrasado)."""
    filtro, ventas = await _kpis(ctx)
    conteo = _tiendas(ventas)
    return {"cantidad": conteo.get(tablero_kpis.VIOLETA, 0),
            "total": sum(conteo.values()),
            "menor_a_pct": filtro.reglas.semaforo["ambar_desde"]}


# --- Composition -------------------------------------------------------------

Constructor = Callable[[Contexto], Awaitable[Dict[str, Any]]]

CONSTRUCTORES: Dict[str, Constructor] = {
    "pedidos_borrador": _pedidos_borrador,
    "ultimo_pedido_enviado": _ultimo_pedido_enviado,
    "datos_por_vencer": _datos_por_vencer,
    "detractores_sin_gestionar": _detractores_sin_gestionar,
    "encuestas_mes": _encuestas_mes,
    "venta_mes": _venta_mes,
    "tiendas_verde": _tiendas_verde,
    "tiendas_rojo": _tiendas_rojo,
}


async def _seccion(ctx: Contexto, nombre: str) -> Dict[str, Any]:
    """One section on its own savepoint: a failed query cannot poison the
    transaction for the next section."""
    try:
        async with ctx.db.begin_nested():
            datos = await CONSTRUCTORES[nombre](ctx)
    except Exception:
        logger.exception("inicio: section %s is unavailable", nombre)
        return {"disponible": False}
    return {"disponible": True, **datos}


async def construir_inicio(
    db, rol: Any, hoy: Optional[date] = None,
) -> Dict[str, Any]:
    """`{rol, hoy, secciones}` with the sections of `rol` (none for a
    role without screens)."""
    rol = getattr(rol, "value", rol)
    ctx = Contexto(db=db, hoy=hoy or hoy_bogota())
    secciones = {}
    for nombre in SECCIONES_POR_ROL.get(rol, ()):
        secciones[nombre] = await _seccion(ctx, nombre)
    return {"rol": rol, "hoy": ctx.hoy.isoformat(), "secciones": secciones}
