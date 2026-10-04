"""
KPI's de Motored (feature motored-kpis, B3): constructores por pestana.

Capa por encima del tablero de asesores: las consultas viven en
`tablero_asesores_consultas.py` y los indicadores por fila en
`tablero_asesores.py` (puros). Aqui se arman las filas de TIENDA (dimension
sucursal: TODA la venta de la tienda, tambien RESTO y COMERCIALES) con su
crecimiento de 3 meses de calendario, y los puntos de entrada que llamaran los
endpoints de cada pestana (`calcular_kpis_ventas`, `calcular_kpis_tiendas`).

Crecimiento (`tablero_asesores.crecimiento_3m`): necesita la venta de los 6 meses
de calendario que terminan en el ultimo mes elegido, ELIJA LO QUE ELIJA el
usuario. Se trae con una consulta liviana aparte (venta mensual por tienda en
esa ventana, mismos filtros de sucursal y HMCL) y no ampliando el cubo, que
arrastraria hasta 6 meses de mas por linea y bandera.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services.tablero_asesores import DIM_SUCURSAL, DIM_TOTAL, Filtro


def filtro_de_ventana(filtro: Filtro) -> Filtro:
    """El mismo filtro pero sobre los 6 meses de calendario que terminan en el
    ultimo mes elegido (la ventana del crecimiento 3M vs 3M)."""
    ultimo = filtro.meses[-1]
    inicio = t.mes_desplazado(ultimo, -(t.MESES_VENTANA_CRECIMIENTO - 1))
    return filtro._replace(rangos=(t.limites_de_fecha(inicio, ultimo),))


def ventana_por_clave(filas: Iterable[q.FilaVentana], modo_hmcl: str) -> Dict[str, Dict[str, Decimal]]:
    """`{clave: {mes: venta}}` de la consulta de ventana, con el modo HMCL aplicado."""
    resultado: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for f in t.filtrar_cubo_por_hmcl(filas, modo_hmcl):
        resultado[f.clave][f.mes] += f.venta
    return resultado


def construir_filas_sucursal(
    cubo: Iterable[t.FilaCubo],
    facturas: Iterable[t.FilaFacturas],
    clientes: Iterable[t.FilaClientes],
    ventana: Dict[str, Dict[str, Decimal]],
    sucursales: Dict[str, Tuple[str, Optional[Any]]],
    meses: List[str],
    reglas: t.Reglas = t.REGLAS_POR_DEFECTO,
) -> Tuple[List[Dict[str, Any]], Decimal]:
    """Una fila por tienda con venta (mix, por mes, por mes y linea), margen,
    ticket, facturas, clientes, Tecnired y `crecimiento`; de mayor a menor venta.
    Devuelve tambien la venta excluida por no tener linea reconocida."""
    acumulados, sin_linea = t.acumular_cubo(cubo, reglas)
    facturas_por, clientes_por = {f.clave: f for f in facturas}, {c.clave: c for c in clientes}
    filas: List[Dict[str, Any]] = []
    for clave, acum in acumulados.items():
        if clave == t.CLAVE_TOTAL:
            continue
        nombre, apertura = sucursales.get(clave, (clave, None))
        fila: Dict[str, Any] = {"sucursal_id": clave, "nombre": nombre}
        fila.update(t.indicadores(acum, facturas_por.get(clave), clientes_por.get(clave), meses, reglas.lineas))
        del fila["ranking"], fila["tendencia"]
        fila["crecimiento"] = t.crecimiento_3m(ventana.get(clave, {}), meses[-1], apertura)
        filas.append(fila)
    filas.sort(key=lambda f: (-f["venta"]["total"], f["nombre"].upper()))
    return filas, sin_linea


def resumen_crecimiento(filas: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    conteo = {t.CRECE: 0, t.CAE: 0, t.NUEVA: 0}
    for f in filas:
        conteo[f["crecimiento"]["clasificacion"]] += 1
    return conteo


def _encabezado(filtro: Filtro) -> Dict[str, Any]:
    return {
        "meses": list(filtro.meses),
        "hmcl": filtro.modo_hmcl,
        "sucursales": sorted(str(s) for s in (filtro.sucursal_ids or ())),
        "reglas": q.eco_reglas(filtro.reglas, filtro.meses[-1]),
    }


async def _filas_de_tiendas(db: AsyncSession, filtro: Filtro, cubo, *, completas: bool):
    """Filas de tienda del cubo ya consultado. `completas=False` omite facturas,
    clientes y la ventana de crecimiento (la pestana Ventas solo muestra venta y margen)."""
    facturas = clientes = []
    ventana: Dict[str, Dict[str, Decimal]] = {}
    if completas:
        facturas = await q.consultar_facturas(db, filtro, dimension=DIM_SUCURSAL)
        clientes = await q.consultar_clientes(db, filtro, dimension=DIM_SUCURSAL)
        ventana = ventana_por_clave(
            await q.consultar_ventana_mensual(db, filtro_de_ventana(filtro), DIM_SUCURSAL), filtro.modo_hmcl)
    sucursales = await q.consultar_sucursales(db, {f.clave for f in cubo})
    return construir_filas_sucursal(
        t.filtrar_cubo_por_hmcl(cubo, filtro.modo_hmcl), facturas, clientes, ventana, sucursales,
        list(filtro.meses), filtro.reglas)


async def calcular_kpis_tiendas(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """Pestana Tiendas: `{meses, hmcl, sucursales, reglas, tiendas, resumen_crecimiento,
    venta_sin_linea}`; cada tienda trae su `crecimiento` y todos sus indicadores."""
    cubo = await q.consultar_cubo(db, filtro, await q.fecha_corte_costos(db), DIM_SUCURSAL)
    tiendas, sin_linea = await _filas_de_tiendas(db, filtro, cubo, completas=True)
    return {
        **_encabezado(filtro),
        "tiendas": tiendas,
        "resumen_crecimiento": resumen_crecimiento(tiendas),
        "venta_sin_linea": float(round(sin_linea, 2)),
    }


async def calcular_kpis_ventas(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """Pestana Ventas: `{meses, hmcl, sucursales, reglas, total, tiendas, venta_sin_linea}`.
    `total` son los indicadores de toda la red (venta, mix, por mes y linea,
    Tecnired por mes y linea, facturas, clientes distintos de la red); `tiendas`,
    una fila liviana por tienda (venta, margen, por mes) para el grafico de cumplimiento."""
    cubo = await q.consultar_cubo(db, filtro, await q.fecha_corte_costos(db), DIM_SUCURSAL)
    tiendas, sin_linea = await _filas_de_tiendas(db, filtro, cubo, completas=False)
    acumulados, _ = t.acumular_cubo(t.filtrar_cubo_por_hmcl(cubo, filtro.modo_hmcl), filtro.reglas)
    facturas = await q.consultar_facturas(db, filtro, dimension=DIM_TOTAL)
    clientes = await q.consultar_clientes(db, filtro, dimension=DIM_TOTAL)
    total = t.indicadores(
        acumulados[t.CLAVE_TOTAL], facturas[0] if facturas else None, clientes[0] if clientes else None,
        list(filtro.meses), filtro.reglas.lineas)
    del total["ranking"], total["tendencia"]
    return {
        **_encabezado(filtro),
        "total": total,
        "tiendas": [
            {k: f[k] for k in ("sucursal_id", "nombre", "venta", "costo")} for f in tiendas
        ],
        "venta_sin_linea": float(round(sin_linea, 2)),
    }
