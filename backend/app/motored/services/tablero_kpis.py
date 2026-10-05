"""
KPI's de Motored (feature motored-kpis, B3): constructores por pestana.

Capa por encima del tablero de asesores: las consultas viven en
`tablero_asesores_consultas.py` y los indicadores por fila en
`tablero_asesores.py` (puros). Aqui se arman las filas de TIENDA (dimension
sucursal: TODA la venta de la tienda, tambien RESTO y COMERCIALES) con su
crecimiento de 3 meses de calendario, y los puntos de entrada que llamaran los
endpoints de cada pestana (`calcular_kpis_ventas`, `calcular_kpis_tiendas`).

Cumplimiento (B4): venta CON HMCL (segun `cumplimiento_base`) de cada asesor en los
meses que tienen presupuesto para el, dividida por ese presupuesto. La venta de
un asesor cuenta para la TIENDA de su linea de presupuesto de ese mes (un asesor
reasignado entre tiendas reparte su venta mes a mes). Semaforo: `verde` desde
`kpi_semaforo_cortes.verde_desde` (%), `ambar` desde `ambar_desde`, `violeta` por
debajo; `estado` es lo mismo en palabras (`cumple`, `en_camino`, `atrasado`) o
`sin_presupuesto`. `cumplimiento_pct` es una FRACCION (0.93 = 93 %), como todo `pct_*`.

Crecimiento (`tablero_asesores.crecimiento_3m`): necesita la venta de los 6 meses
de calendario que terminan en el ultimo mes elegido, ELIJA LO QUE ELIJA el
usuario. Se trae con una consulta liviana aparte (venta mensual por tienda en
esa ventana, mismos filtros de sucursal y HMCL) y no ampliando el cubo, que
arrastraria hasta 6 meses de mas por linea y bandera.
"""
import datetime
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import presupuestos as pres
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis_consultas as qk
from app.motored.services.sucursal_grupo import principal_de
from app.motored.services.tablero_asesores import DIM_ASESOR, DIM_SUCURSAL, DIM_TOTAL, Filtro


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


# --- Cumplimiento del presupuesto (B4) ----------------------------------------------------------

VERDE, AMBAR, VIOLETA = "verde", "ambar", "violeta"
CUMPLE, EN_CAMINO, ATRASADO, SIN_PRESUPUESTO = "cumple", "en_camino", "atrasado", "sin_presupuesto"
_ESTADO_DE_SEMAFORO = {VERDE: CUMPLE, AMBAR: EN_CAMINO, VIOLETA: ATRASADO}


def semaforo_de(venta: Decimal, presupuesto: int, cortes: Dict[str, float]) -> Optional[str]:
    """Color segun los cortes de Configuracion (en %) comparando `venta / presupuesto`
    contra cada corte SIN dividir (asi 90 % exacto es verde, sin errores de
    redondeo de coma flotante). None si no hay presupuesto."""
    if not presupuesto:
        return None
    avance = Decimal(venta) * 100
    if avance >= Decimal(str(cortes["verde_desde"])) * presupuesto:
        return VERDE
    return AMBAR if avance >= Decimal(str(cortes["ambar_desde"])) * presupuesto else VIOLETA


def cedula_limpia(valor: Any) -> Optional[str]:
    """La cedula como la guardan los presupuestos (solo digitos); None si no tiene una valida."""
    try:
        return limpiar_cedula(valor)
    except ValueError:
        return None


def _resultado(presupuesto: int, venta: Decimal, cortes: Dict[str, float]) -> Dict[str, Any]:
    pct = t.ratio(venta, Decimal(presupuesto)) if presupuesto else None
    color = semaforo_de(venta, presupuesto, cortes)
    return {
        "presupuesto": presupuesto,
        "venta_cumplimiento": float(round(venta, 2)),
        "cumplimiento_pct": pct,
        "semaforo": color,
        "estado": _ESTADO_DE_SEMAFORO.get(color, SIN_PRESUPUESTO),
        "cumple": color == VERDE,
    }


def venta_para_cumplimiento(
    cubo: Iterable[t.FilaCubo], reglas: t.Reglas,
) -> Tuple[Dict[Tuple[str, str], Decimal], Dict[str, str], Dict[str, Decimal]]:
    """Venta de las personas por (cedula limpia, mes), segun `cumplimiento_base`:
    `con_hmcl` suma todo; `sin_hmcl` deja fuera las lineas de clientes HMCL. El
    cubo debe traer HMCL incluido. Devuelve tambien `{cedula: clave}` y la venta
    de las personas SIN cedula valida (no pueden cruzar con un presupuesto),
    por clave."""
    ventas: Dict[Tuple[str, str], Decimal] = defaultdict(Decimal)
    claves: Dict[str, str] = {}
    sin_cedula: Dict[str, Decimal] = defaultdict(Decimal)
    for f in cubo:
        if not t.es_clave_persona(f.clave) or f.linea is None or f.linea not in reglas.lineas:
            continue
        if reglas.cumplimiento_base == t.CUMPLIMIENTO_SIN_HMCL and f.es_hmcl:
            continue
        cedula = cedula_limpia(f.clave[len(t.PREFIJO_PERSONA):])
        if cedula is None:
            sin_cedula[f.clave] += f.venta
            continue
        ventas[(cedula, f.mes)] += f.venta
        claves.setdefault(cedula, f.clave)
    return ventas, claves, sin_cedula


def presupuestos_del_rango(
    crudos: Dict[tuple, pres.LineaPresupuesto], meses: Iterable[str], sucursal_ids: Optional[Iterable[Any]] = None,
    principales: Optional[Dict[Any, Any]] = None,
) -> Dict[Tuple[str, str], pres.LineaPresupuesto]:
    """`{(mes AAAA-MM, cedula limpia): linea}` solo de los meses elegidos (la
    lectura trae de el menor al mayor) y, si hay filtro, de las lineas asignadas a esas tiendas.
    Una linea asignada a una tienda asociada cuenta en su principal (`principales`, ver
    `sucursal_grupo`): la linea devuelta ya trae la sucursal principal."""
    elegidos = set(meses)
    tiendas = {str(s) for s in sucursal_ids} if sucursal_ids else None
    mapa = principales or {}
    resultado: Dict[Tuple[str, str], pres.LineaPresupuesto] = {}
    for (mes, cedula), linea in crudos.items():
        texto, limpia = f"{mes:%Y-%m}", cedula_limpia(cedula)
        linea = linea._replace(sucursal_id=mapa.get(linea.sucursal_id, linea.sucursal_id))
        if texto in elegidos and limpia and (tiendas is None or str(linea.sucursal_id) in tiendas):
            resultado[(texto, limpia)] = linea
    return resultado


def _filas_de_asesores(
    ventas, claves, sin_cedula, presupuestos, nombres, nombres_por_clave, cortes,
) -> List[Dict[str, Any]]:
    por_cedula: Dict[str, Dict[str, pres.LineaPresupuesto]] = defaultdict(dict)
    for (mes, cedula), linea in presupuestos.items():
        por_cedula[cedula][mes] = linea
    filas: List[Dict[str, Any]] = []
    for cedula in sorted(set(por_cedula) | set(claves)):
        meses_pres = por_cedula.get(cedula, {})
        presupuesto = sum(linea.monto for linea in meses_pres.values())
        venta = sum((ventas.get((cedula, mes), Decimal(0)) for mes in meses_pres), Decimal(0))
        clave = claves.get(cedula, f"{t.PREFIJO_PERSONA}{cedula}")
        ultima = meses_pres[max(meses_pres)] if meses_pres else None
        filas.append({
            "clave": clave, "cedula": cedula,
            "nombre": nombres_por_clave.get(clave) or nombres.get(cedula),
            "sucursal_id": str(ultima.sucursal_id) if ultima else None,
            "meses_con_presupuesto": len(meses_pres),
            **_resultado(presupuesto, venta, cortes),
        })
    for clave in sorted(sin_cedula):
        filas.append({
            "clave": clave, "cedula": None, "nombre": nombres_por_clave.get(clave), "sucursal_id": None,
            "meses_con_presupuesto": 0, **_resultado(0, Decimal(0), cortes),
        })
    return filas


def _filas_de_tiendas_cumplimiento(ventas, presupuestos, sucursales, cortes) -> List[Dict[str, Any]]:
    presupuesto: Dict[str, int] = defaultdict(int)
    venta: Dict[str, Decimal] = defaultdict(Decimal)
    asesores: Dict[str, Set[str]] = defaultdict(set)
    for (mes, cedula), linea in presupuestos.items():
        tienda = str(linea.sucursal_id)
        presupuesto[tienda] += linea.monto
        venta[tienda] += ventas.get((cedula, mes), Decimal(0))
        asesores[tienda].add(cedula)
    filas = [
        {"sucursal_id": tienda, "nombre": sucursales.get(tienda, (tienda, None))[0],
         "asesores_con_presupuesto": len(asesores[tienda]), **_resultado(presupuesto[tienda], venta[tienda], cortes)}
        for tienda in presupuesto
    ]
    return sorted(filas, key=lambda f: (f["nombre"].upper(), f["sucursal_id"]))


def _conteo(filas: Iterable[Dict[str, Any]], con_sin_presupuesto: bool) -> Dict[str, int]:
    conteo = {VERDE: 0, AMBAR: 0, VIOLETA: 0}
    if con_sin_presupuesto:
        conteo[SIN_PRESUPUESTO] = 0
    for f in filas:
        conteo[f["semaforo"] or SIN_PRESUPUESTO] += 1
    return conteo


def construir_cumplimiento(
    cubo: Iterable[t.FilaCubo],
    presupuestos: Dict[Tuple[str, str], pres.LineaPresupuesto],
    reglas: t.Reglas,
    *,
    sucursales: Optional[Dict[str, Tuple[str, Optional[datetime.date]]]] = None,
    nombres: Optional[Dict[str, str]] = None,
    nombres_por_clave: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Cumplimiento por asesor, por tienda y de la red (suma de las tiendas).
    `cubo` es el de asesores con HMCL incluido y `presupuestos` sale de
    `presupuestos_del_rango`. Un asesor con presupuesto y sin ventas aparece con
    venta 0 (0 %); quien vendio y no tiene presupuesto (o no tiene cedula) queda
    `sin_presupuesto`. Cada asesor se mide solo en los meses con presupuesto suyo."""
    cortes = reglas.semaforo
    ventas, claves, sin_cedula = venta_para_cumplimiento(cubo, reglas)
    asesores = _filas_de_asesores(
        ventas, claves, sin_cedula, presupuestos, nombres or {}, nombres_por_clave or {}, cortes)
    tiendas = _filas_de_tiendas_cumplimiento(ventas, presupuestos, sucursales or {}, cortes)
    red = _resultado(
        sum(f["presupuesto"] for f in tiendas),
        sum((Decimal(str(f["venta_cumplimiento"])) for f in tiendas), Decimal(0)), cortes)
    return {
        "asesores": asesores,
        "tiendas": tiendas,
        "red": red,
        "conteos": {"asesores": _conteo(asesores, True), "tiendas": _conteo(tiendas, False)},
        "advertencias": {
            "personas_sin_cedula": len(sin_cedula),
            "venta_sin_cedula": float(round(sum(sin_cedula.values(), Decimal(0)), 2)),
        },
    }


async def cargar_cumplimiento(
    db: AsyncSession, filtro: Filtro, cubo_asesores: Optional[List[t.FilaCubo]] = None,
    nombres_por_clave: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Lee presupuestos (ultima version de cada mes), nombres y, si hace falta,
    el cubo de asesores, y arma `construir_cumplimiento`. El cubo debe ser el de
    asesores con HMCL incluido; si hay filtro de tiendas se vuelve a consultar sin
    el, porque el filtro de tiendas acota los PRESUPUESTOS (a las tiendas elegidas)
    y no la venta del asesor, que cuenta completa."""
    if cubo_asesores is None or filtro.sucursal_ids:
        # Cost is not needed here: a NULL cut-off date joins no inventory.
        cubo_asesores = await lectura.cubo(db, filtro._replace(sucursal_ids=None), None, DIM_ASESOR)
    primero, ultimo = (datetime.date(int(m[:4]), int(m[5:]), 1) for m in (filtro.meses[0], filtro.meses[-1]))
    presupuestos = presupuestos_del_rango(
        await pres.presupuesto_por_asesor(db, primero, ultimo), filtro.meses, filtro.sucursal_ids,
        await principal_de(db))
    sucursales = await q.consultar_sucursales(db, {str(linea.sucursal_id) for linea in presupuestos.values()})
    nombres = await q.consultar_nombres_por_cedula(db, {cedula for _, cedula in presupuestos})
    return construir_cumplimiento(
        cubo_asesores, presupuestos, filtro.reglas,
        sucursales=sucursales, nombres=nombres, nombres_por_clave=nombres_por_clave)


# --- Tecnired y dias de inventario (B5) ----------------------------------------------------------


def construir_tecnired(
    clientes: Dict[str, Any], distintos: int, distintos_por_mes: Dict[str, int],
    top: Iterable[qk.FilaTopTecnired], meses: Iterable[str],
) -> Dict[str, Any]:
    """Bloque Tecnired de la red: `clientes` es el bloque `clientes` del total
    (venta, pct, por mes y por linea), `distintos` los clientes Tecnired distintos
    y `venta_por_cliente` el promedio de la red (None sin clientes). `top5` rotula
    con la razon social, o el NIT si la lista no la trae; `pct` es la parte de la venta Tecnired."""
    venta = clientes["venta_tecnired"]
    por_mes = clientes["tecnired_por_mes"]
    return {
        "venta": venta,
        "pct": clientes["pct_tecnired"],
        "clientes": distintos,
        "venta_por_cliente": venta / distintos if distintos else None,
        "por_mes": {m: {"venta": por_mes.get(m, 0.0), "clientes": distintos_por_mes.get(m, 0)} for m in meses},
        "por_linea": clientes["tecnired_por_linea"],
        "top5": [
            {"nit": f.nit, "razon_social": f.razon_social or f.nit, "venta": float(round(f.venta, 2)),
             "pct": t.ratio(f.venta, Decimal(str(venta)))}
            for f in top
        ],
    }


def dias_de_inventario(valor: Decimal, costo_venta: Optional[Decimal], dias_ventana: int) -> Optional[float]:
    """Dias que dura el inventario: valor / (costo de venta / dias de la ventana).
    None si no hubo costo de venta (no se puede dividir)."""
    if not costo_venta or costo_venta <= 0:
        return None
    return float(Decimal(valor) * dias_ventana / costo_venta)


def _inventario_de(
    valor: Decimal, costo_venta: Decimal, dias_ventana: int, sin_costo: int, corte: Optional[str],
    costo_maestro: int = 0,
) -> Dict[str, Any]:
    return {
        "valor_inventario": float(round(valor, 2)),
        "costo_venta_diario": float(costo_venta / dias_ventana),
        "dias": dias_de_inventario(valor, costo_venta, dias_ventana),
        "lineas_sin_costo": sin_costo,
        "lineas_costo_maestro": costo_maestro,
        "fecha_corte": corte,
    }


def construir_inventario(
    filas: Iterable[qk.FilaInventario], costo_venta: Dict[str, Decimal], dias_ventana: int,
    fecha_corte: Optional[datetime.date],
) -> Dict[str, Any]:
    """Dias de inventario por tienda (solo las que tienen inventario cargado) y de
    la red, que suma esas mismas tiendas. Sin inventario: `tiendas` vacio y
    `fecha_corte` None."""
    corte = fecha_corte.isoformat() if fecha_corte else None
    filas = list(filas)
    tiendas = {
        f.sucursal_id: _inventario_de(f.valor, costo_venta.get(f.sucursal_id, Decimal(0)), dias_ventana,
                                      f.sin_costo, corte, f.costo_maestro)
        for f in filas
    }
    red = _inventario_de(
        sum((f.valor for f in filas), Decimal(0)),
        sum((costo_venta.get(f.sucursal_id, Decimal(0)) for f in filas), Decimal(0)),
        dias_ventana, sum(f.sin_costo for f in filas), corte, sum(f.costo_maestro for f in filas))
    return {"fecha_corte": corte, "dias_ventana": dias_ventana, "tiendas": tiendas, "red": red}


async def cargar_inventario(db: AsyncSession, filtro: Filtro, fecha_corte: Optional[datetime.date]) -> Dict[str, Any]:
    """Dias de inventario por tienda con su corte, ver `construir_inventario`."""
    _, dias = qk.filtro_costo_venta(filtro)
    if fecha_corte is None:
        return construir_inventario([], {}, dias, None)
    filas = await lectura.inventario(db, filtro, fecha_corte)
    costo_venta, dias = await lectura.costo_venta(db, filtro, fecha_corte)
    return construir_inventario(filas, costo_venta, dias, fecha_corte)


async def cargar_tecnired(db: AsyncSession, filtro: Filtro, clientes: Dict[str, Any]) -> Dict[str, Any]:
    distintos, por_mes = await lectura.clientes_tecnired(db, filtro)
    top = await lectura.top_tecnired(db, filtro)
    return construir_tecnired(clientes, distintos, por_mes, top, filtro.meses)


def _recortar(cumplimiento: Dict[str, Any], claves: Iterable[str]) -> Dict[str, Any]:
    return {k: cumplimiento[k] for k in claves}


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
        facturas = await lectura.facturas(db, filtro, dimension=DIM_SUCURSAL)
        clientes = await lectura.clientes(db, filtro, dimension=DIM_SUCURSAL)
        ventana = ventana_por_clave(
            await lectura.ventana_mensual(db, filtro_de_ventana(filtro), DIM_SUCURSAL), filtro.modo_hmcl)
    sucursales = await q.consultar_sucursales(db, {f.clave for f in cubo})
    return construir_filas_sucursal(
        t.filtrar_cubo_por_hmcl(cubo, filtro.modo_hmcl), facturas, clientes, ventana, sucursales,
        list(filtro.meses), filtro.reglas)


async def calcular_kpis_tiendas(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """Pestana Tiendas: `{meses, hmcl, sucursales, reglas, tiendas, cumplimiento,
    resumen_crecimiento, venta_sin_linea}`. Cada tienda con ventas trae todos sus
    indicadores, su `crecimiento` y su `cumplimiento` (None si no tiene presupuesto);
    `cumplimiento` agrega `tiendas` (TODAS las que tienen presupuesto, vendan o no),
    `red` y `conteos` por semaforo."""
    corte = await lectura.fecha_corte_costos(db)
    cubo = await lectura.cubo(db, filtro, corte, DIM_SUCURSAL)
    tiendas, sin_linea = await _filas_de_tiendas(db, filtro, cubo, completas=True)
    cumplimiento = await cargar_cumplimiento(db, filtro)
    por_tienda = {f["sucursal_id"]: f for f in cumplimiento["tiendas"]}
    inventario = await cargar_inventario(db, filtro, corte)
    for fila in tiendas:
        fila["cumplimiento"] = por_tienda.get(fila["sucursal_id"])
        fila["dias_inventario"] = inventario["tiendas"].get(fila["sucursal_id"])
    return {
        **_encabezado(filtro),
        "tiendas": tiendas,
        "inventario": inventario,
        "cumplimiento": _recortar(cumplimiento, ("tiendas", "red", "conteos")),
        "resumen_crecimiento": resumen_crecimiento(tiendas),
        "venta_sin_linea": float(round(sin_linea, 2)),
    }


async def calcular_kpis_ventas(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """Pestana Ventas: `{meses, hmcl, sucursales, reglas, total, tiendas, cumplimiento,
    venta_sin_linea}`; `cumplimiento` trae `red` (el medidor), `tiendas` y `conteos`.
    `total` son los indicadores de toda la red (venta, mix, por mes y linea,
    Tecnired por mes y linea, facturas, clientes distintos de la red); `tiendas`,
    una fila liviana por tienda (venta, margen, por mes) para el grafico de cumplimiento."""
    cubo = await lectura.cubo(db, filtro, await lectura.fecha_corte_costos(db), DIM_SUCURSAL)
    tiendas, sin_linea = await _filas_de_tiendas(db, filtro, cubo, completas=False)
    acumulados, _ = t.acumular_cubo(t.filtrar_cubo_por_hmcl(cubo, filtro.modo_hmcl), filtro.reglas)
    facturas = await lectura.facturas(db, filtro, dimension=DIM_TOTAL)
    clientes = await lectura.clientes(db, filtro, dimension=DIM_TOTAL)
    total = t.indicadores(
        acumulados[t.CLAVE_TOTAL], facturas[0] if facturas else None, clientes[0] if clientes else None,
        list(filtro.meses), filtro.reglas.lineas)
    del total["ranking"], total["tendencia"]
    cumplimiento = await cargar_cumplimiento(db, filtro)
    return {
        **_encabezado(filtro),
        "total": total,
        "tecnired": await cargar_tecnired(db, filtro, total["clientes"]),
        "cumplimiento": _recortar(cumplimiento, ("red", "tiendas", "conteos")),
        "tiendas": [
            {k: f[k] for k in ("sucursal_id", "nombre", "venta", "costo")} for f in tiendas
        ],
        "venta_sin_linea": float(round(sin_linea, 2)),
    }


async def calcular_kpis_asesores(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """Pestana Asesores: el tablero de asesores (`q.calcular_tablero_por_meses`) mas
    `cumplimiento = {asesores, conteos, advertencias}`: una fila por asesor con
    presupuesto o con ventas (ver `construir_cumplimiento`), cruzada con las filas
    del tablero por `clave`."""
    tablero, cubo = await q.tablero_de_filtro(db, filtro)
    nombres = {f["clave"]: f["nombre"] for f in tablero["filas"] if f["tipo"] == "PERSONA"}
    cumplimiento = await cargar_cumplimiento(db, filtro, cubo, nombres)
    tablero["cumplimiento"] = _recortar(cumplimiento, ("asesores", "conteos", "advertencias"))
    return tablero


async def calcular_opciones(db: AsyncSession) -> Dict[str, Any]:
    """Datos de los filtros: `{meses_disponibles, ultimo_mes, tiendas}`. El
    `ultimo_mes` (el ultimo con ventas, None si no hay) permite proponer "ano
    corrido": de enero de ese ano a ese mes."""
    meses = await lectura.meses(db)
    return {
        "meses_disponibles": meses,
        "ultimo_mes": meses[-1] if meses else None,
        "tiendas": await qk.consultar_tiendas_activas(db),
    }
