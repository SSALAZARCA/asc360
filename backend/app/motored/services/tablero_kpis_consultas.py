"""
KPI's de Motored (feature motored-kpis, B5): consultas nuevas.

- Clientes Tecnired distintos (total y por mes) y los 5 mayores con su razon social.
- Inventario a costo por tienda y costo de venta de los ultimos 3 meses de
  calendario (para los dias de inventario).

Comparten las reglas de `tablero_asesores_consultas._desde_ventas`: cargas no
ANULADAS, rangos de fechas, tiendas y modo HMCL del `Filtro`, el cliente
normalizado como `normalizar_nit` y el costo unitario por referencia (mediana de
los costos positivos del ultimo corte de inventario). Son consultas de
PostgreSQL: solo las cubre `pg_real`.
"""
import datetime
from decimal import Decimal
from typing import Dict, List, NamedTuple, Optional, Tuple

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services.tablero_asesores import Filtro

TOP_TECNIRED = 5
MESES_COSTO_VENTA = 3


class FilaTopTecnired(NamedTuple):
    nit: str
    razon_social: Optional[str]
    venta: Decimal


class FilaInventario(NamedTuple):
    """Inventario a costo de una tienda: `sin_costo` cuenta las lineas con costo
    nulo o no positivo, que no entran en `valor`."""
    sucursal_id: str
    valor: Decimal
    sin_costo: int


def _ventas_tecnired(consulta, filtro: Filtro):
    """Ventas de clientes Tecnired (lineas de las 7 reconocidas), con el filtro."""
    lineas = q._lineas_por_referencia(filtro.reglas)
    cliente = q._expr_cliente_norm()
    consulta = q._desde_ventas(consulta, filtro, lineas, solo_lineas_reconocidas=True, con_vendedor=False)
    return consulta.where(cliente.in_(select(ClienteTecnired.nit)))


async def consultar_clientes_tecnired(db: AsyncSession, filtro: Filtro) -> Tuple[int, Dict[str, int]]:
    """`(clientes Tecnired distintos, {mes: distintos en el mes})`. Un cliente que
    compra en varios meses cuenta una vez en el total y una vez en cada mes."""
    cliente = q._expr_cliente_norm()
    total = await db.execute(_ventas_tecnired(select(func.count(func.distinct(cliente))), filtro))
    mes = q._expr_mes()
    por_mes = await db.execute(
        _ventas_tecnired(select(mes, func.count(func.distinct(cliente))).group_by(mes), filtro))
    return int(total.scalar() or 0), {m: int(n) for m, n in por_mes.all()}


async def consultar_top_tecnired(
    db: AsyncSession, filtro: Filtro, limite: int = TOP_TECNIRED,
) -> List[FilaTopTecnired]:
    """Los `limite` clientes Tecnired de mayor venta, con su razon social (None
    si la lista no la trae). Empates por NIT para que el orden sea estable."""
    cliente = q._expr_cliente_norm()
    venta = func.sum(q._expr_venta())
    consulta = _ventas_tecnired(select(ClienteTecnired.nit, ClienteTecnired.razon_social, venta), filtro)
    consulta = (
        consulta.join(ClienteTecnired, ClienteTecnired.nit == cliente)
        .group_by(ClienteTecnired.nit, ClienteTecnired.razon_social)
        .order_by(venta.desc(), ClienteTecnired.nit)
        .limit(limite)
    )
    return [FilaTopTecnired(nit, razon, Decimal(v)) for nit, razon, v in (await db.execute(consulta)).all()]


async def consultar_inventario(
    db: AsyncSession, filtro: Filtro, fecha_corte: Optional[datetime.date],
) -> List[FilaInventario]:
    """Inventario a costo por tienda en `fecha_corte` (existencia x costo unitario
    de cada linea con costo positivo), de las cargas no ANULADAS y de las tiendas
    del filtro. Sin corte no hay inventario.

    Por diseno usa el ULTIMO corte GLOBAL: la carga de inventario trae todas las
    tiendas en un solo archivo por dia, asi que una tienda ausente de ese archivo
    no aparece."""
    if fecha_corte is None:
        return []
    con_costo = InventarioDetalle.costo_unitario > 0
    consulta = (
        select(
            cast(InventarioDetalle.sucursal_id, String),
            func.coalesce(func.sum(case((con_costo, InventarioDetalle.existencia * InventarioDetalle.costo_unitario),
                                        else_=0)), 0),
            func.coalesce(func.sum(case((con_costo, 0), else_=1)), 0),
        )
        .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
        .where(InventarioDetalle.fecha_corte == fecha_corte, CargaArchivo.estado != "ANULADO")
        .group_by(InventarioDetalle.sucursal_id)
    )
    if filtro.sucursal_ids:
        consulta = consulta.where(InventarioDetalle.sucursal_id.in_(sorted(filtro.sucursal_ids, key=str)))
    return [FilaInventario(s, Decimal(v), int(n)) for s, v, n in (await db.execute(consulta)).all()]


def filtro_costo_venta(filtro: Filtro) -> Tuple[Filtro, int]:
    """El filtro sobre los 3 meses de calendario que terminan en el ultimo mes
    elegido (con HMCL incluido: es el costo de TODA la venta de la tienda) y los
    dias que suman. HMCL entra a proposito: los dias de inventario miden toda la
    salida de mercancia, no solo la venta que cuenta para el presupuesto."""
    ultimo = filtro.meses[-1]
    inicio, fin = t.limites_de_fecha(t.mes_desplazado(ultimo, -(MESES_COSTO_VENTA - 1)), ultimo)
    return filtro._replace(rangos=((inicio, fin),), modo_hmcl=t.HMCL_INCLUIR), (fin - inicio).days


async def consultar_costo_venta(
    db: AsyncSession, filtro: Filtro, fecha_corte: Optional[datetime.date],
) -> Tuple[Dict[str, Decimal], int]:
    """`({sucursal_id: costo de venta}, dias de la ventana)`: suma de cantidad x costo
    unitario (el mismo costo por referencia del margen del tablero) de las ventas
    de los ultimos 3 meses. Las referencias sin costo aportan 0."""
    ventana, dias = filtro_costo_venta(filtro)
    costos = q._subconsulta_costos(fecha_corte)
    lineas = q._lineas_por_referencia(ventana.reglas)
    tienda = cast(VentaDetalle.sucursal_id, String)
    consulta = q._desde_ventas(
        select(tienda, func.coalesce(func.sum(VentaDetalle.cantidad * costos.c.costo_unitario), 0)).group_by(tienda),
        ventana, lineas, solo_lineas_reconocidas=False, costos=costos, con_vendedor=False)
    return {s: Decimal(v) for s, v in (await db.execute(consulta)).all()}, dias


async def consultar_tiendas_activas(db: AsyncSession) -> List[Dict[str, str]]:
    """`[{id, nombre}]` de las sucursales activas, por nombre (para el filtro de tiendas)."""
    filas = await db.execute(
        select(Sucursal.id, Sucursal.nombre).where(Sucursal.activa.is_(True)).order_by(func.upper(Sucursal.nombre)))
    return [{"id": str(id_), "nombre": nombre} for id_, nombre in filas.all()]
