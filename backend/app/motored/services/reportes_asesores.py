"""
Daily per-asesor report data (odd/motored-reporte-diario-asesor, T2).

`reportes_asesores(db, fecha)` computes, ONCE for the whole network, the month of `fecha` up to `fecha`
(month-to-date, HMCL included) and slices it per cedula: the commission fields the PDF header needs
(flat) plus `detalle`, the KPI single-asesor view shaped for a server-side PDF. Nothing is queried per
asesor: the cube, budgets, rules, tablero pieces and the Tecnired clients (one grouped query) are read once.

Everything comes from the same builders as the web card (`tablero_asesor_detalle`, `tablero_comisiones`,
`tablero_kpis`), so the report always matches `calcular_kpis_asesor_detalle`.

Source: the KPI summaries answer when they are usable AND hold nothing after `fecha` (they keep months, not
days); a past `fecha` in a month that already has later sales is answered live. Tecnired clients are always read
live (one month, one query).

Money is whole pesos (what is still missing rounds up), percentages are fractions.
"""
import datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any, Callable, Dict, List, NamedTuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import presupuestos as pres
from app.motored.services import tablero_asesor_detalle as d
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_comisiones as c
from app.motored.services import tablero_kpis as k
from app.motored.services.tablero_asesores import DIM_ASESOR, DIM_TOTAL, HMCL_INCLUIR, Filtro


def _arriba(valor: float) -> int:
    return int(Decimal(str(valor)).to_integral_value(rounding=ROUND_CEILING))


def _reporte(
    fila: Dict[str, Any], reglas: c.ReglasComision, mes: str, fecha_datos: datetime.date,
    detalle: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    explicacion = d.explicar_fila(fila, mes, fecha_datos)
    sig = explicacion["siguiente_tramo"]
    return {
        "cedula": fila["cedula"], "nombre": fila["nombre"], "tienda": fila["tienda"], "mes": mes,
        "fecha_datos": fecha_datos.isoformat(),
        "venta_cumplimiento": d.pesos(fila["venta_cumplimiento"]), "venta_comision": d.pesos(fila["venta_comision"]),
        "presupuesto": fila["presupuesto"], "cumplimiento_pct": fila["cumplimiento_pct"],
        "tramo": {"nombre": fila["tramo"], "tasa_pct": fila["tasa_pct"]},
        "comision": d.pesos(fila["comision"]), "bono_total": fila["bono_total"],
        "total_a_pagar": d.pesos(fila["total_a_pagar"]),
        "siguiente_tramo": None if sig is None else {
            "nombre": sig["nombre"], "falta": _arriba(sig["falta"]), "comision_si_llega": d.pesos(sig["comision_si_llega"])},
        "compuerta": {
            "umbral_pct": fila["gate"]["umbral"], "cumple": fila["gate"]["cumple"],
            "falta": explicacion["falta_compuerta"]},
        "falta_100": _arriba(explicacion["falta_100"]),
        "dias_habiles_restantes": explicacion["dias_habiles_restantes"],
        "venta_diaria_necesaria": explicacion["venta_diaria_necesaria"],
        "bonos": [
            {"linea": b["linea"], "etiqueta": b["etiqueta"], "meta_pct": b["pct_meta"], "bono": b["bono"],
             "activo": b["activo"], "ganado": b["paga"], "pagado": b["bono_pagado"],
             "falta_venta": b["falta_venta"] if b["activo"] else None}
            for b in fila["bonos"]],
        "tramos": [
            {"nombre": x.nombre, "desde_pct": float(x.desde_pct), "tasa_pct": float(x.tasa_pct)}
            for x in reglas.tramos],
        "detalle": detalle,
    }


def armar_reportes(
    reglas: c.ReglasComision, mes: str, asesores: List[Dict[str, Any]], advertencias: Dict[str, Any],
    sin_cedula: Dict[str, Decimal], nombres_por_clave: Dict[str, str], fecha_datos: Optional[datetime.date],
    detalle_de: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """PURE slicing of one liquidated month (`tablero_comisiones.liquidar_mes`) into
    `{reportes: {cedula: ...}, sin_presupuesto: [...], sin_cedula: [...]}`. Without `fecha_datos` (no sale
    loaded) there is nothing to report. `detalle_de(cedula)` supplies each report's `detalle`."""
    reportes = {} if fecha_datos is None else {
        a["cedula"]: _reporte(a, reglas, mes, fecha_datos, detalle_de(a["cedula"]) if detalle_de else None)
        for a in asesores}
    return {
        "reportes": reportes,
        "sin_presupuesto": [
            {"cedula": x["cedula"], "nombre": x["nombre"], "venta": d.pesos(x["venta"])}
            for x in advertencias["sin_presupuesto"]],
        "sin_cedula": [
            {"vendedor": nombres_por_clave.get(clave) or clave, "venta": d.pesos(float(venta))}
            for clave, venta in sorted(sin_cedula.items(), key=lambda kv: (-kv[1], kv[0]))],
    }


class _Vivo:
    """The live queries behind the same names `kpi_resumen_lectura` dispatches."""

    @staticmethod
    async def cubo(db, filtro, corte, dimension=DIM_ASESOR):
        return await q.consultar_cubo(db, filtro, corte, dimension)

    @staticmethod
    async def facturas(db, filtro, *, dimension):
        return await q.consultar_facturas(db, filtro, dimension=dimension)

    @staticmethod
    async def clientes(db, filtro, *, dimension):
        return await q.consultar_clientes(db, filtro, dimension=dimension)

    @staticmethod
    async def personas(db, filtro):
        return await q.consultar_personas(db, filtro)


def _primero(mes: str) -> datetime.date:
    return datetime.date(int(mes[:4]), int(mes[5:]), 1)


async def _fuente_corte(db: AsyncSession, fuente) -> Optional[datetime.date]:
    """The cost cut of the source that answers (the summary holds its own)."""
    return await (lectura.fecha_corte_costos(db) if fuente is lectura else q.fecha_corte_costos(db))


class _Periodo(NamedTuple):
    mes: str
    meses_anio: List[str]
    fecha_datos: Optional[datetime.date]
    fuente: Any
    reglas: Any
    f_mes: Filtro
    f_anio: Filtro


async def _periodo(db: AsyncSession, fecha: datetime.date) -> _Periodo:
    """The month and the year to date of `fecha`, the date of the last loaded sale, the filters and the source."""
    mes = f"{fecha:%Y-%m}"
    ultima = await q.ultima_fecha_venta(db, mes)
    fecha_datos = ultima if ultima is None or ultima <= fecha else await q.ultima_fecha_venta(db, mes, hasta=fecha)
    meses_anio = [f"{fecha.year}-{m:02d}" for m in range(1, fecha.month + 1)]
    base = await q.cargar_filtro(db, [mes], HMCL_INCLUIR)
    hasta = fecha + datetime.timedelta(days=1)
    f_anio = Filtro(((datetime.date(fecha.year, 1, 1), hasta),), HMCL_INCLUIR, None, base.reglas, tuple(meses_anio))
    fuente = lectura if (fecha_datos == ultima and await lectura.usar_resumen(db)) else _Vivo
    return _Periodo(mes, meses_anio, fecha_datos, fuente, base.reglas, base._replace(rangos=((_primero(mes), hasta),)), f_anio)


async def _tablero_del_mes(db: AsyncSession, p: _Periodo):
    """`(cubo del anio, tablero del mes)`. The year-to-date cube (with costs, for the margin tile) feeds the
    month, the trend and the liquidation."""
    cubo_anio = await p.fuente.cubo(db, p.f_anio, await _fuente_corte(db, p.fuente), DIM_ASESOR)
    facturas = [
        *await p.fuente.facturas(db, p.f_mes, dimension=DIM_ASESOR),
        *await p.fuente.facturas(db, p.f_mes, dimension=DIM_TOTAL)]
    clientes = [
        *await p.fuente.clientes(db, p.f_mes, dimension=DIM_ASESOR),
        *await p.fuente.clientes(db, p.f_mes, dimension=DIM_TOTAL)]
    personas = await p.fuente.personas(db, p.f_mes)
    tablero = t.construir_tablero(
        [f for f in cubo_anio if f.mes == p.mes], facturas, clientes, personas, [p.mes], p.reglas)
    tablero["meses"] = [p.mes]
    tablero["reglas"] = q.eco_reglas(p.reglas, p.mes)
    return cubo_anio, tablero


async def _cumplimiento_y_liquidacion(db: AsyncSession, p: _Periodo, cubo_anio, tablero):
    """`(por_mes, sucursales, reglas, asesores, advertencias, sin_cedula)`: cumplimiento of every month of
    the year and the liquidation of the month."""
    presupuestos = k.presupuestos_del_rango(
        await pres.presupuesto_por_asesor(db, _primero(p.meses_anio[0]), _primero(p.mes)), p.meses_anio, None,
        await lectura.principales(db))
    sucursales = await q.consultar_sucursales(db, {str(x.sucursal_id) for x in presupuestos.values()})
    extra = {
        "sucursales": sucursales,
        "nombres": await q.consultar_nombres_por_cedula(db, {ced for _, ced in presupuestos}),
        "nombres_por_clave": {f["clave"]: f["nombre"] for f in tablero["filas"] if f["tipo"] == t.TIPO_PERSONA},
    }
    por_mes = k.cumplimiento_por_mes(cubo_anio, presupuestos, p.reglas, p.meses_anio, **extra)
    del_mes = {clave: linea for clave, linea in presupuestos.items() if clave[0] == p.mes}
    liquidacion = await k.liquidar_cubo_del_mes(db, p.f_anio, p.mes, cubo_anio, del_mes)
    return (por_mes, sucursales, *liquidacion)


def _constructor_de_detalle(
    p: _Periodo, tablero, por_mes, comision, tecnired, maestro, tiendas,
) -> Callable[[str], Optional[Dict[str, Any]]]:
    """`cedula -> detalle`: the full asesor detail of the month shaped for the report, from the shared data."""

    def detalle_de(cedula: str) -> Optional[Dict[str, Any]]:
        clave = d.clave_de_asesor(tablero, cedula)
        lista = tecnired.get(clave, []) if clave else []
        m = maestro.get(cedula)
        completo = d.construir_detalle(
            cedula, tablero, por_mes[p.mes], {p.mes: por_mes[p.mes]}, comision, len(lista), lista[:q.TOP_CLIENTES],
            None if m is None else {"nombre": m.nombre, "cargo": m.cargo, "tienda": m.tienda, "sucursal_id": m.sucursal_id},
            tiendas, p.fecha_datos)
        if completo is None:
            return None
        return d.para_reporte(completo, d.tendencia_de(por_mes, p.meses_anio, cedula))

    return detalle_de


async def reportes_asesores(db: AsyncSession, fecha: datetime.date) -> Dict[str, Any]:
    """`{reportes, sin_presupuesto, sin_cedula}` of the month of `fecha` up to `fecha`, whole network,
    HMCL included, rules in force that month. See the module docstring and `armar_reportes`."""
    with lectura.memo_de_peticion(db):  # the state of the summaries is read once, not once per read
        return await _reportes_asesores(db, fecha)


async def _reportes_asesores(db: AsyncSession, fecha: datetime.date) -> Dict[str, Any]:
    p = await _periodo(db, fecha)
    cubo_anio, tablero = await _tablero_del_mes(db, p)
    por_mes, sucursales, reglas, asesores, advertencias, sin_cedula = await _cumplimiento_y_liquidacion(
        db, p, cubo_anio, tablero)
    comision = {
        "mes_liquidado": p.mes, "reglas": {"comision_base_pago": reglas.base_pago},
        "resumen": c.resumen_de(asesores, reglas), "tramos": c.tramos_con_conteo(asesores, reglas),
        "asesores": asesores}
    maestro = {m.cedula: m for m in await q.consultar_asesores_maestro(db)}
    detalle_de = _constructor_de_detalle(
        p, tablero, por_mes, comision, await q.consultar_tecnired_por_asesor(db, p.f_mes), maestro,
        {i: nombre for i, (nombre, _) in sucursales.items()})
    nombres = {f["clave"]: f["nombre"] for f in tablero["filas"] if f["tipo"] == t.TIPO_PERSONA}
    return armar_reportes(reglas, p.mes, asesores, advertencias, sin_cedula, nombres, p.fecha_datos, detalle_de)
