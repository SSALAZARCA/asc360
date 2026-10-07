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
from app.motored.services import kpi_resumen
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import presupuestos as pres
from app.motored.services import tablero_asesor_detalle as detalle
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_comisiones as c
from app.motored.services import tablero_kpis_consultas as qk
from app.motored.services.sucursal_grupo import principal_de
from app.motored.services.tablero_asesores import DIM_ASESOR, DIM_SUCURSAL, DIM_TOTAL, HMCL_INCLUIR, Filtro


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


GRUPOS_COMPANIA = (
    ("asesores", "Asesores de repuestos"), (t.GRUPO_COMERCIALES, "Comerciales"),
    (t.GRUPO_OTROS, "Otros roles de posventa"), (t.GRUPO_RESTO, "Resto de compañía"),
)


def _grupo_compania(clave: str) -> str:
    """Grupo de la venta de la compania; una clave inesperada cae en OTROS (nunca KeyError)."""
    if t.es_clave_persona(clave):
        return "asesores"
    return clave if clave in _CLAVES_GRUPO_COMPANIA else t.GRUPO_OTROS


_CLAVES_GRUPO_COMPANIA = frozenset(grupo for grupo, _ in GRUPOS_COMPANIA)


def construir_compania(
    cubo_compania: Iterable[t.FilaCubo], presupuestos: Dict[Tuple[str, str], pres.LineaPresupuesto],
    reglas: t.Reglas, red: Dict[str, Any],
) -> Dict[str, Any]:
    """Cumplimiento de la COMPANIA: toda la venta de la red (cubo de asesores con el filtro
    de tiendas, que trae tambien RESTO, COMERCIALES, OTROS y asesores sin presupuesto; mismas
    lineas que el indicador `venta`) contra la suma de TODAS las lineas de presupuesto.
    Se mide segun `cumplimiento_base` y solo en los meses con algun presupuesto (los demas
    quedan fuera de la venta y del presupuesto). `por_grupo` reparte esa venta entre los
    cuatro grupos de vendedores (suman la venta de la compania) y `asesores` es el
    cumplimiento propio de los asesores de repuestos (`red`), los unicos con presupuesto."""
    meses_pres = {mes for mes, _ in presupuestos}
    por_grupo: Dict[str, Decimal] = {grupo: Decimal(0) for grupo, _ in GRUPOS_COMPANIA}
    for f in cubo_compania:
        if f.mes not in meses_pres or f.linea is None or f.linea not in reglas.lineas:
            continue
        if reglas.cumplimiento_base == t.CUMPLIMIENTO_SIN_HMCL and f.es_hmcl:
            continue
        por_grupo[_grupo_compania(f.clave)] += f.venta
    venta = sum(por_grupo.values(), Decimal(0))
    presupuesto = sum(linea.monto for linea in presupuestos.values())
    return {
        "venta": float(round(venta, 2)),
        "presupuesto": presupuesto,
        "pct": t.ratio(venta, Decimal(presupuesto)) if presupuesto else None,
        "semaforo": semaforo_de(venta, presupuesto, reglas.semaforo),
        "meses_con_presupuesto": len(meses_pres),
        "por_grupo": [
            {"grupo": rotulo, "venta": float(round(por_grupo[grupo], 2)), "pct": t.ratio(por_grupo[grupo], venta)}
            for grupo, rotulo in GRUPOS_COMPANIA
        ],
        "asesores": {k: red[k] for k in ("presupuesto", "venta_cumplimiento", "cumplimiento_pct", "semaforo")},
    }


def construir_tiendas_total(
    cubo_sucursal: Iterable[t.FilaCubo], presupuestos: Dict[Tuple[str, str], pres.LineaPresupuesto],
    sucursales: Dict[str, Tuple[str, Optional[datetime.date]]], reglas: t.Reglas,
) -> List[Dict[str, Any]]:
    """Cumplimiento por tienda con la venta TOTAL de la tienda (todos los vendedores, tambien
    RESTO, COMERCIALES y OTROS; cubo por sucursal con la sucursal principal ya aplicada)
    contra la suma de las lineas de presupuesto asignadas a la tienda. Cada tienda se mide
    solo en los meses en que tiene presupuesto; sin presupuesto no aparece (queda
    `sin_presupuesto` en el cliente)."""
    presupuesto: Dict[str, int] = defaultdict(int)
    meses: Dict[str, Set[str]] = defaultdict(set)
    asesores: Dict[str, Set[str]] = defaultdict(set)
    for (mes, cedula), linea in presupuestos.items():
        tienda = str(linea.sucursal_id)
        presupuesto[tienda] += linea.monto
        meses[tienda].add(mes)
        asesores[tienda].add(cedula)
    venta: Dict[str, Decimal] = defaultdict(Decimal)
    for f in cubo_sucursal:
        if f.clave not in presupuesto or f.mes not in meses[f.clave]:
            continue
        if f.linea is None or f.linea not in reglas.lineas:
            continue
        if reglas.cumplimiento_base == t.CUMPLIMIENTO_SIN_HMCL and f.es_hmcl:
            continue
        venta[f.clave] += f.venta
    filas = [
        {"sucursal_id": tienda, "nombre": sucursales.get(tienda, (tienda, None))[0],
         "asesores_con_presupuesto": len(asesores[tienda]),
         **_resultado(presupuesto[tienda], venta[tienda], reglas.semaforo)}
        for tienda in presupuesto
    ]
    return sorted(filas, key=lambda f: (f["nombre"].upper(), f["sucursal_id"]))


def construir_cumplimiento(
    cubo: Iterable[t.FilaCubo],
    presupuestos: Dict[Tuple[str, str], pres.LineaPresupuesto],
    reglas: t.Reglas,
    *,
    sucursales: Optional[Dict[str, Tuple[str, Optional[datetime.date]]]] = None,
    nombres: Optional[Dict[str, str]] = None,
    nombres_por_clave: Optional[Dict[str, str]] = None,
    cubo_compania: Optional[Iterable[t.FilaCubo]] = None,
    cubo_sucursal: Optional[Iterable[t.FilaCubo]] = None,
) -> Dict[str, Any]:
    """Cumplimiento por asesor, por tienda y de la red (suma de las tiendas).
    Con `cubo_compania` (cubo de asesores CON el filtro de tiendas, HMCL incluido) agrega `compania`;
    con `cubo_sucursal` (cubo por sucursal, HMCL incluido) `tiendas` (y sus conteos) se miden con la venta
    TOTAL de la tienda en vez de la de sus asesores (pestanas Ventas y Tiendas). `red` y `asesores`
    siguen siendo de los asesores con presupuesto.
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
    extra = {}
    if cubo_compania is not None:
        extra["compania"] = construir_compania(cubo_compania, presupuestos, reglas, red)
    if cubo_sucursal is not None:
        tiendas = construir_tiendas_total(cubo_sucursal, presupuestos, sucursales or {}, reglas)
    return {
        **extra,
        "asesores": asesores,
        "tiendas": tiendas,
        "red": red,
        "conteos": {"asesores": _conteo(asesores, True), "tiendas": _conteo(tiendas, False)},
        "advertencias": {
            "personas_sin_cedula": len(sin_cedula),
            "venta_sin_cedula": float(round(sum(sin_cedula.values(), Decimal(0)), 2)),
        },
    }


def cumplimiento_por_mes(
    cubo: Iterable[t.FilaCubo], presupuestos: Dict[Tuple[str, str], pres.LineaPresupuesto], reglas: t.Reglas,
    meses: Iterable[str], **extra: Any,
) -> Dict[str, Dict[str, Any]]:
    """`{mes: construir_cumplimiento de ese mes}`: cada mes se mide solo contra los presupuestos
    de ese mes (por eso un asesor sin presupuesto en un mes queda `sin_presupuesto` en el)."""
    cubo = list(cubo)
    return {
        mes: construir_cumplimiento(
            cubo, {clave: linea for clave, linea in presupuestos.items() if clave[0] == mes}, reglas, **extra)
        for mes in meses
    }


async def _cubo_de_cumplimiento(
    db: AsyncSession, filtro: Filtro, cubo_asesores: Optional[List[t.FilaCubo]] = None,
) -> List[t.FilaCubo]:
    """The asesores cube with HMCL included that cumplimiento measures. A store filter limits the
    PRESUPUESTOS (to the chosen stores) and not the asesor's sale, which counts in full, so
    with one the cube is queried again without it."""
    if cubo_asesores is None or filtro.sucursal_ids:
        # Cost is not needed here: a NULL cut-off date joins no inventory.
        return await lectura.cubo(db, filtro._replace(sucursal_ids=None), None, DIM_ASESOR)
    return cubo_asesores


async def _presupuestos_del_filtro(db: AsyncSession, filtro: Filtro) -> Dict[Tuple[str, str], pres.LineaPresupuesto]:
    """`{(mes, cedula): linea}` of the filter's months (latest version of each) and stores."""
    primero, ultimo = (datetime.date(int(m[:4]), int(m[5:]), 1) for m in (filtro.meses[0], filtro.meses[-1]))
    return presupuestos_del_rango(
        await pres.presupuesto_por_asesor(db, primero, ultimo), filtro.meses, filtro.sucursal_ids,
        await principal_de(db))


async def cargar_cumplimiento(
    db: AsyncSession, filtro: Filtro, cubo_asesores: Optional[List[t.FilaCubo]] = None,
    nombres_por_clave: Optional[Dict[str, str]] = None, cubo_compania: Optional[List[t.FilaCubo]] = None,
    cubo_sucursal: Optional[List[t.FilaCubo]] = None,
) -> Dict[str, Any]:
    """Lee presupuestos (ultima version de cada mes), nombres y, si hace falta,
    el cubo de asesores, y arma `construir_cumplimiento`. El cubo debe ser el de
    asesores con HMCL incluido (ver `_cubo_de_cumplimiento`)."""
    cubo_asesores = await _cubo_de_cumplimiento(db, filtro, cubo_asesores)
    presupuestos = await _presupuestos_del_filtro(db, filtro)
    sucursales = await q.consultar_sucursales(db, {str(linea.sucursal_id) for linea in presupuestos.values()})
    nombres = await q.consultar_nombres_por_cedula(db, {cedula for _, cedula in presupuestos})
    return construir_cumplimiento(
        cubo_asesores, presupuestos, filtro.reglas,
        sucursales=sucursales, nombres=nombres, nombres_por_clave=nombres_por_clave,
        cubo_compania=cubo_compania, cubo_sucursal=cubo_sucursal)


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
    cumplimiento = await cargar_cumplimiento(db, filtro, cubo_sucursal=cubo)
    por_tienda = {f["sucursal_id"]: f for f in cumplimiento["tiendas"]}
    inventario = await cargar_inventario(db, filtro, corte)
    for fila in tiendas:
        fila["cumplimiento"] = por_tienda.get(fila["sucursal_id"])
        fila["dias_inventario"] = inventario["tiendas"].get(fila["sucursal_id"])
    return {
        **_encabezado(filtro),
        **await lectura.frescura(db),
        "tiendas": tiendas,
        "inventario": inventario,
        "cumplimiento": _recortar(cumplimiento, ("tiendas", "red", "conteos")),
        "resumen_crecimiento": resumen_crecimiento(tiendas),
        "venta_sin_linea": float(round(sin_linea, 2)),
    }


async def calcular_kpis_ventas(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """Pestana Ventas: `{meses, hmcl, sucursales, reglas, total, tiendas, cumplimiento,
    venta_sin_linea}`; `cumplimiento` trae `compania` (el medidor), `red`, `tiendas` y `conteos`.
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
    cubo_compania = await lectura.cubo(db, filtro, None, DIM_ASESOR)
    cumplimiento = await cargar_cumplimiento(
        db, filtro, cubo_compania=cubo_compania, cubo_sucursal=cubo)
    return {
        **_encabezado(filtro),
        **await lectura.frescura(db),
        "total": total,
        "tecnired": await cargar_tecnired(db, filtro, total["clientes"]),
        "cumplimiento": _recortar(cumplimiento, ("compania", "red", "tiendas", "conteos")),
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
    tablero.update(await lectura.frescura(db))
    return tablero


async def calcular_kpis_asesor_detalle(db: AsyncSession, filtro: Filtro, cedula: str) -> Optional[Dict[str, Any]]:
    """Vista de UN asesor (`cedula` limpia): `{meses, hmcl, sucursales, reglas, asesor, puestos,
    cumplimiento_mes, comision, tiles, tendencia, lineas, strip, comparacion, tecnired}` (ver
    `tablero_asesor_detalle`), o None si la cedula no tiene ventas, presupuesto ni fila en el maestro
    dentro del filtro. Todo sale de los mismos constructores de la pestana (tablero, cumplimiento,
    comisiones) y de las lecturas con interruptor, asi que vivo y resumen dan lo mismo."""
    tablero, cubo = await q.tablero_de_filtro(db, filtro)
    cubo = await _cubo_de_cumplimiento(db, filtro, cubo)
    presupuestos = await _presupuestos_del_filtro(db, filtro)
    nombres_por_clave = {f["clave"]: f["nombre"] for f in tablero["filas"] if f["tipo"] == t.TIPO_PERSONA}
    extra = {
        "sucursales": await q.consultar_sucursales(db, {str(x.sucursal_id) for x in presupuestos.values()}),
        "nombres": await q.consultar_nombres_por_cedula(db, {ced for _, ced in presupuestos}),
        "nombres_por_clave": nombres_por_clave,
    }
    periodo = construir_cumplimiento(cubo, presupuestos, filtro.reglas, **extra)
    por_mes = cumplimiento_por_mes(cubo, presupuestos, filtro.reglas, filtro.meses, **extra)
    maestro = next((m for m in await q.consultar_asesores_maestro(db) if m.cedula == cedula), None)
    if maestro and filtro.sucursal_ids and maestro.sucursal_id not in {str(s) for s in filtro.sucursal_ids}:
        maestro = None  # out of the chosen stores
    clave = detalle.clave_de_asesor(tablero, cedula)
    clientes, top = 0, []
    if clave is not None:
        clientes = await lectura.clientes_tecnired_de_asesor(db, filtro, clave)
        top = await lectura.top_tecnired_de_asesor(db, filtro, clave)
    fecha_datos = await q.ultima_fecha_venta(db, filtro.meses[-1], filtro.sucursal_ids)
    resultado = detalle.construir_detalle(
        cedula, tablero, periodo, por_mes, await calcular_kpis_comisiones(db, filtro), clientes, top,
        None if maestro is None else {
            "nombre": maestro.nombre, "cargo": maestro.cargo, "tienda": maestro.tienda,
            "sucursal_id": maestro.sucursal_id},
        {i: nombre for i, (nombre, _) in extra["sucursales"].items()}, fecha_datos)
    if resultado is None:
        return None
    return {**_encabezado(filtro), **await lectura.frescura(db), **resultado}


async def calcular_opciones_asesores(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """Opciones del filtro "Asesor": `{asesores: [{cedula, nombre, tienda, sucursal_id, venta}]}` de
    quienes VENDIERON en el periodo y las tiendas del filtro, la de mayor venta primero (es la seleccion
    por defecto). Sale del mismo tablero de la pestana (ver `tablero_asesor_detalle.construir_opciones`),
    asi que vivo y resumen dan lo mismo. Una tienda asociada cuenta como su principal."""
    tablero, _ = await q.tablero_de_filtro(db, filtro)
    tiendas = None
    if filtro.sucursal_ids:
        mapa = await principal_de(db)
        tiendas = {str(mapa.get(i, i)) for i in filtro.sucursal_ids}
    maestro = {
        m.cedula: {"nombre": m.nombre, "tienda": m.tienda, "sucursal_id": m.sucursal_id}
        for m in await q.consultar_asesores_maestro(db)
    }
    return {"asesores": detalle.construir_opciones(tablero, maestro, tiendas)}


async def _cargos_del_mes(
    db: AsyncSession, filtro: Filtro, mes: str, claves: Dict[str, str], cedulas: Iterable[str],
) -> Dict[str, Iterable[str]]:
    """`{cedula: cargos}` of the people of `mes`; whoever has no sales that month (a budget only)
    is looked up in the vendedores master."""
    personas = await lectura.personas(db, t.filtro_de_meses([mes], HMCL_INCLUIR, None, filtro.reglas))
    por_clave = {p.clave: set(p.cargos) | ({p.cargo} if p.cargo else set()) for p in personas}
    cargos = {ced: por_clave[claves[ced]] for ced in cedulas if claves.get(ced) in por_clave}
    faltan = [ced for ced in cedulas if ced not in cargos]
    cargos.update(await q.consultar_cargos_por_cedula(db, faltan))
    return cargos


async def _liquidar(
    db: AsyncSession, filtro: Filtro, mes: str, ventas, claves, presupuestos, por_linea=None,
) -> Tuple[c.ReglasComision, List[Dict[str, Any]], Dict[str, Any]]:
    """Liquidates ONE month with the rules in force that month."""
    reglas = await q.cargar_reglas_comision(db, mes)
    ventas_mes = {ced: v for (ced, m), v in ventas.items() if m == mes}
    pres_mes = {ced: linea for (m, ced), linea in presupuestos.items() if m == mes}
    cedulas = sorted(set(ventas_mes) | set(pres_mes))
    cargos = await _cargos_del_mes(db, filtro, mes, claves, cedulas)
    nombres = await q.consultar_nombres_por_cedula(db, cedulas)
    sucursales = await q.consultar_sucursales(db, {str(x.sucursal_id) for x in pres_mes.values()})
    tiendas = {i: nombre for i, (nombre, _) in sucursales.items()}
    lineas_mes = {ced: v for (ced, m), v in (por_linea or {}).items() if m == mes}
    asesores, advertencias = c.liquidar_mes(ventas_mes, pres_mes, nombres, cargos, tiendas, reglas, lineas_mes)
    advertencias["sin_presupuestos"] = not pres_mes
    return reglas, asesores, advertencias


async def liquidar_cubo_del_mes(
    db: AsyncSession, filtro: Filtro, mes: str, cubo, presupuestos,
) -> Tuple[c.ReglasComision, List[Dict[str, Any]], Dict[str, Any], Dict[str, Decimal]]:
    """Liquidates `mes` from an asesores cube (HMCL included) and the month's budgets, with the rules in
    force that month: `(reglas, asesores, advertencias, {clave: venta})`, the last one being the sale of the
    people without a valid cedula. The commissions tab and the daily asesor report both go through here."""
    ventas, claves, sin_cedula = c.ventas_por_cedula_mes(cubo, filtro.reglas.lineas)
    por_linea = c.ventas_por_linea_cedula_mes(cubo, filtro.reglas.lineas)
    reglas, asesores, advertencias = await _liquidar(db, filtro, mes, ventas, claves, presupuestos, por_linea)
    sin_cedula_mes = sin_cedula.get(mes, {})
    advertencias["sin_cedula"] = {
        "personas": len(sin_cedula_mes),
        "venta": float(round(sum(sin_cedula_mes.values(), Decimal(0)), 2)),
    }
    return reglas, asesores, advertencias, sin_cedula_mes


async def calcular_kpis_comisiones(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    """Pestana Comisiones: liquida el ULTIMO mes del filtro con las reglas vigentes ese mes; el filtro
    de tiendas acota los presupuestos y el periodo no cambia las cifras. La venta cuenta completa (HMCL
    incluido en la consulta; cada base decide) y no depende del selector HMCL. Vivo y resumen dan lo
    mismo (`lectura.cubo`)."""
    mes = filtro.meses[-1]
    solo_mes = filtro._replace(
        sucursal_ids=None, modo_hmcl=HMCL_INCLUIR, meses=(mes,), rangos=t.rangos_de_meses([mes]))
    cubo = await lectura.cubo(db, solo_mes, None, DIM_ASESOR)
    primero = datetime.date(int(mes[:4]), int(mes[5:]), 1)
    presupuestos = presupuestos_del_rango(
        await pres.presupuesto_por_asesor(db, primero, primero), [mes], filtro.sucursal_ids,
        await principal_de(db))
    reglas, asesores, advertencias, _ = await liquidar_cubo_del_mes(db, filtro, mes, cubo, presupuestos)
    return {
        **_encabezado(filtro),
        **await lectura.frescura(db),
        "mes_liquidado": mes,
        "reglas": {**q.eco_reglas(filtro.reglas, mes), **c.eco_reglas_comision(reglas)},
        "resumen": c.resumen_de(asesores, reglas),
        "tramos": c.tramos_con_conteo(asesores, reglas),
        "asesores": sorted(asesores, key=lambda a: (-a["comision"], a["cedula"])),
        "cerca_de_subir": c.cerca_de_subir(asesores),
        "advertencias": advertencias,
    }


def _en_iso(valor: Optional[datetime.datetime]) -> Optional[str]:
    return None if valor is None else valor.isoformat()


async def calcular_estado(db: AsyncSession) -> Dict[str, Any]:
    """Freshness of the summaries: `{actualizado_en, sucio, reconstruyendo,
    ultima_reconstruccion_total, usando_resumen}` (timestamps in ISO, None when never). A
    summary that was never built counts as dirty."""
    estado = await kpi_resumen.estado(db)
    return {
        "actualizado_en": _en_iso(estado and estado.actualizado_en),
        "sucio": True if estado is None else estado.sucio,
        "reconstruyendo": bool(estado and estado.reconstruyendo),
        "ultima_reconstruccion_total": _en_iso(estado and estado.ultima_reconstruccion_total),
        "usando_resumen": (await lectura.frescura(db))["usando_resumen"],
    }


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
