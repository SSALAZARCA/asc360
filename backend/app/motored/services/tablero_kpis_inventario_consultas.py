"""
KPI's de Motored, pestana Inventario: las consultas (PostgreSQL; solo las cubre `pg_real`).

Una peticion corre un numero fijo de consultas agrupadas (nada por tienda ni por referencia):
cortes, valor por corte y tienda, pares (tienda principal x referencia) con existencia, venta mensual
por par, ventas perdidas por par, costo de venta por mes x tienda x linea, transito al corte y nombres.
Comparten las reglas de `tablero_asesores_consultas`: cargas no ANULADAS, tiendas del filtro (una
principal incluye a sus asociadas y todo se agrupa en la principal), la valoracion del inventario
(`_valoracion_inventario`), la linea por referencia y el costo de venta por linea (`_expr_costo_fila`).
"""
import datetime
import uuid
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.referencia import Referencia
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services.corridas import transito_corte
from app.motored.services.corridas.cargador import ORIGEN_BOT, ORIGENES_VENTA
from app.motored.services.tablero_asesores import Filtro

ESTADO_ANULADO = "ANULADO"
LOTE_REFERENCIAS = 5000


def _ym(anio, mes):
    return anio * 12 + mes - 1


def _por_tienda(consulta, columna, filtro: Filtro):
    """Cruza la tienda principal de `columna` y aplica las tiendas del filtro."""
    consulta = q.con_principal(consulta, columna)
    if filtro.sucursal_ids:
        consulta = consulta.where(q.donde_sucursales(columna, filtro.sucursal_ids))
    return consulta


async def consultar_cortes(db: AsyncSession) -> List[datetime.date]:
    """Los `fecha_corte` de inventario con carga no ANULADA, del mas viejo al mas nuevo."""
    filas = await db.execute(
        select(InventarioDetalle.fecha_corte).distinct()
        .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
        .where(CargaArchivo.estado != ESTADO_ANULADO).order_by(InventarioDetalle.fecha_corte))
    return [fecha for (fecha,) in filas.all()]


async def consultar_valor_por_corte(
    db: AsyncSession, filtro: Filtro, cortes: Iterable[datetime.date],
) -> Dict[datetime.date, Dict[str, Decimal]]:
    """`{corte: {tienda principal: valor a costo}}` con la misma valoracion de `consultar_inventario`."""
    cortes = sorted(set(cortes))
    if not cortes:
        return {}
    valor, _, _ = q._valoracion_inventario()
    tienda = cast(q.principal_expr(InventarioDetalle.sucursal_id), String)
    consulta = (
        select(InventarioDetalle.fecha_corte, tienda, valor).select_from(InventarioDetalle)
        .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
        .outerjoin(Referencia, Referencia.id == InventarioDetalle.referencia_id)
        .where(InventarioDetalle.fecha_corte.in_(cortes), CargaArchivo.estado != ESTADO_ANULADO)
        .group_by(InventarioDetalle.fecha_corte, tienda))
    consulta = _por_tienda(consulta, InventarioDetalle.sucursal_id, filtro)
    salida: Dict[datetime.date, Dict[str, Decimal]] = {c: {} for c in cortes}
    for corte, id_tienda, v in (await db.execute(consulta)).all():
        salida[corte][id_tienda] = Decimal(v)
    return salida


async def consultar_pares_con_existencia(
    db: AsyncSession, filtro: Filtro, corte: datetime.date,
) -> List[Tuple[str, Any, Optional[str], Decimal, Decimal]]:
    """`(tienda, referencia_id, linea, existencia, valor)` de cada par con existencia total > 0 en `corte`."""
    lineas = q._lineas_por_referencia(filtro.reglas)
    valor, _, _ = q._valoracion_inventario()
    existencia = func.sum(InventarioDetalle.existencia)
    tienda = cast(q.principal_expr(InventarioDetalle.sucursal_id), String)
    consulta = (
        select(tienda, InventarioDetalle.referencia_id, lineas.c.linea, existencia, valor)
        .select_from(InventarioDetalle)
        .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
        .outerjoin(Referencia, Referencia.id == InventarioDetalle.referencia_id)
        .outerjoin(lineas, lineas.c.id == InventarioDetalle.referencia_id)
        .where(InventarioDetalle.fecha_corte == corte, CargaArchivo.estado != ESTADO_ANULADO)
        .group_by(tienda, InventarioDetalle.referencia_id, lineas.c.linea)
        .having(existencia > 0))
    consulta = _por_tienda(consulta, InventarioDetalle.sucursal_id, filtro)
    return [(s, r, ln, Decimal(e), Decimal(v)) for s, r, ln, e, v in (await db.execute(consulta)).all()]


async def consultar_ventas_por_par(
    db: AsyncSession, filtro: Filtro, corte_ym: int, ventana_ym: Tuple[int, int],
) -> List[Tuple[str, Any, Optional[str], Decimal, Optional[int]]]:
    """`(tienda, referencia_id, linea, vendidas en la ventana, ultimo mes con venta)` por par, de la venta
    mensual (ambos origenes). El ultimo mes con venta mira hasta el mes del corte (`unidades > 0`)."""
    lineas = q._lineas_por_referencia(filtro.reglas)
    ym = _ym(VentaMensual.anio, VentaMensual.mes)
    vendidas = func.coalesce(func.sum(case(
        (and_(ym >= ventana_ym[0], ym <= ventana_ym[1]), VentaMensual.unidades), else_=0)), 0)
    ultimo = func.max(case((and_(VentaMensual.unidades > 0, ym <= corte_ym), ym)))
    tienda = cast(q.principal_expr(VentaMensual.sucursal_id), String)
    consulta = (
        select(tienda, VentaMensual.referencia_id, lineas.c.linea, vendidas, ultimo)
        .select_from(VentaMensual)
        .join(CargaArchivo, CargaArchivo.id == VentaMensual.carga_id)
        .outerjoin(lineas, lineas.c.id == VentaMensual.referencia_id)
        .where(CargaArchivo.estado != ESTADO_ANULADO, VentaMensual.origen.in_(ORIGENES_VENTA))
        .group_by(tienda, VentaMensual.referencia_id, lineas.c.linea))
    consulta = _por_tienda(consulta, VentaMensual.sucursal_id, filtro)
    return [
        (s, r, ln, Decimal(v), int(u) if u is not None else None)
        for s, r, ln, v, u in (await db.execute(consulta)).all()]


async def consultar_primer_mes_con_venta(db: AsyncSession) -> Optional[int]:
    """El primer mes (indice anio*12+mes-1) con venta de toda la historia cargada, de todas las tiendas."""
    consulta = (
        select(func.min(_ym(VentaMensual.anio, VentaMensual.mes)))
        .join(CargaArchivo, CargaArchivo.id == VentaMensual.carga_id)
        .where(CargaArchivo.estado != ESTADO_ANULADO, VentaMensual.unidades > 0))
    resultado = (await db.execute(consulta)).scalar()
    return int(resultado) if resultado is not None else None


async def consultar_perdidas_por_par(
    db: AsyncSession, filtro: Filtro, desde: datetime.date, hasta: datetime.date,
) -> List[Tuple[str, Any, Optional[str], Decimal]]:
    """`(tienda, referencia_id, linea, unidades perdidas)` por par en `[desde, hasta)`: las del bot siempre
    cuentan y las del Excel solo con la carga no ANULADA (la regla del cargador del motor)."""
    lineas = q._lineas_por_referencia(filtro.reglas)
    tienda = cast(q.principal_expr(DemandaPerdida.sucursal_id), String)
    perdidas = func.sum(DemandaPerdida.cantidad_solicitada)
    consulta = (
        select(tienda, DemandaPerdida.referencia_id, lineas.c.linea, perdidas)
        .select_from(DemandaPerdida)
        .join(CargaArchivo, CargaArchivo.id == DemandaPerdida.carga_id)
        .outerjoin(lineas, lineas.c.id == DemandaPerdida.referencia_id)
        .where(
            DemandaPerdida.fecha >= desde, DemandaPerdida.fecha < hasta,
            or_(DemandaPerdida.origen == ORIGEN_BOT, CargaArchivo.estado != ESTADO_ANULADO))
        .group_by(tienda, DemandaPerdida.referencia_id, lineas.c.linea))
    consulta = _por_tienda(consulta, DemandaPerdida.sucursal_id, filtro)
    return [(s, r, ln, Decimal(p)) for s, r, ln, p in (await db.execute(consulta)).all()]


async def consultar_costos_por_mes(
    db: AsyncSession, filtro: Filtro, corte: Optional[datetime.date], desde_mes: str, hasta_mes: str,
) -> List[Tuple[str, str, Optional[str], Decimal]]:
    """`(mes, tienda, linea, costo de venta)` de los meses `desde_mes..hasta_mes`, con la regla de costo
    de `consultar_costo_venta` (HMCL incluido: es el costo de TODA la salida de mercancia)."""
    inicio, fin = t.limites_de_fecha(desde_mes, hasta_mes)
    ventana = filtro._replace(rangos=((inicio, fin),), modo_hmcl=t.HMCL_INCLUIR)
    costos = q._subconsulta_costos(corte)
    lineas = q._lineas_por_referencia(ventana.reglas)
    tienda = cast(q.principal_expr(VentaDetalle.sucursal_id), String)
    mes = q._expr_mes()
    consulta = q._desde_ventas(
        select(mes, tienda, lineas.c.linea, func.coalesce(func.sum(q._costo_de_venta(costos)), 0))
        .group_by(mes, tienda, lineas.c.linea),
        ventana, lineas, solo_lineas_reconocidas=False, costos=costos, con_vendedor=False, por_sucursal=True)
    return [(m, s, ln, Decimal(c)) for m, s, ln, c in (await db.execute(consulta)).all()]


async def consultar_transito_por_par(
    db: AsyncSession, filtro: Filtro, corte: datetime.date, principales: Dict[Any, Any], *,
    excluir_vencido: bool, dias_ventana_ingresos: int, tolerancia_ingreso_pct: float,
) -> Dict[Tuple[str, Any], Decimal]:
    """`{(tienda principal, referencia): unidades en transito al corte}` con el calculo W del motor de
    pedidos (`cargar_transito_corte`), sumado a la principal y limitado a las tiendas del filtro."""
    resultado = await transito_corte.cargar_transito_corte(
        db, corte, excluir_vencido=excluir_vencido, dias_ventana_ingresos=dias_ventana_ingresos,
        tolerancia_ingreso_pct=tolerancia_ingreso_pct)
    elegidas = {principales.get(s, s) for s in filtro.sucursal_ids} if filtro.sucursal_ids else None
    salida: Dict[Tuple[str, Any], Decimal] = {}
    for (sucursal, referencia), cantidad in resultado.w.items():
        principal = principales.get(sucursal, sucursal)
        if elegidas is not None and principal not in elegidas:
            continue
        clave = (str(principal), referencia)
        salida[clave] = salida.get(clave, Decimal(0)) + Decimal(cantidad)
    return salida


async def consultar_referencias(db: AsyncSession, ids: Iterable[Any]) -> Dict[Any, Tuple[str, Optional[str]]]:
    """`{referencia_id: (codigo, nombre)}`, en lotes para no pasar el tope de parametros."""
    pendientes = sorted({uuid.UUID(str(i)) for i in ids}, key=str)
    salida: Dict[Any, Tuple[str, Optional[str]]] = {}
    for inicio in range(0, len(pendientes), LOTE_REFERENCIAS):
        lote = pendientes[inicio:inicio + LOTE_REFERENCIAS]
        filas = await db.execute(
            select(Referencia.id, Referencia.codigo, Referencia.nombre).where(Referencia.id.in_(lote)))
        salida.update({i: (codigo, nombre) for i, codigo, nombre in filas.all()})
    return salida

