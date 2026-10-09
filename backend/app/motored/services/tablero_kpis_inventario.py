"""
KPI's de Motored, pestana Inventario: las piezas puras y el armado de la respuesta.

Las consultas viven en `tablero_kpis_inventario_consultas.py`. `analizar` y las piezas de arriba no tocan
la base de datos (reciben filas ya leidas); `calcular_inventario` las orquesta y `tablero_kpis`
expone `calcular_kpis_inventario`.

Definiciones (todas por PAR tienda principal x referencia; una tienda asociada suma en su principal):
- Corte: el ultimo corte valorizado (no ANULADO) en o antes del fin del ULTIMO mes elegido; si no hay
  uno, el ultimo que exista.
- Dias de inventario: valor / (costo de venta de 3 meses de calendario / dias de la ventana), con las
  mismas tiendas que tienen inventario en el corte (la regla de la pestana Tiendas). Rotacion = 365 / dias.
- Antiguedad: dias desde el ULTIMO mes con venta (`venta_mensual.unidades > 0`, hasta el mes del corte) de
  cada par con existencia; el dia es el ultimo del mes (nunca menos de 0). Un par sin venta en toda la
  historia cuenta desde el primer dia del primer mes con venta de la historia (`historial_desde`).
- Sin movimiento: valor de los pares con existencia cuyos dias sin venta superan el umbral.
- Demanda = unidades vendidas (neto del periodo, solo si es > 0) + ventas perdidas, en los ultimos 3 meses.
  Disponibilidad = pares con demanda que tienen existencia > 0 / pares con demanda. Agotada con demanda =
  par con demanda y sin existencia en el corte.
- Todos los `pct` son FRACCIONES (0.107 = 10,7 %).
"""
import calendar
import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.services import ingresos_pendientes
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import parametros
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis_consultas as qk
from app.motored.services import tablero_kpis_inventario_consultas as qi
from app.motored.services.tablero_asesores import Filtro
from app.motored.services.tablero_kpis import dias_de_inventario

MESES_TENDENCIA = 12
TOP_SIN_MOVIMIENTO = 8
TOP_AGOTADAS = 20
UMBRAL_SIN_MOVIMIENTO_POR_DEFECTO = 180
DIAS_META_POR_DEFECTO = 60
CORTES_POR_DEFECTO = {"verde_hasta": 60, "ambar_hasta": 90}
BANDAS = ((0, 90), (91, 180), (181, 365), (366, None))
_TODAS = object()


# --- Months and cuts ----------------------------------------------------------------------------


def indice_mes(fecha: datetime.date) -> int:
    return fecha.year * 12 + fecha.month - 1


def _mes_texto(indice: int) -> str:
    return f"{indice // 12:04d}-{indice % 12 + 1:02d}"


def _primer_dia(indice: int) -> datetime.date:
    return datetime.date(indice // 12, indice % 12 + 1, 1)


def _ultimo_dia(indice: int) -> datetime.date:
    anio, mes = indice // 12, indice % 12 + 1
    return datetime.date(anio, mes, calendar.monthrange(anio, mes)[1])


def _indice_de_texto(mes: str) -> int:
    return int(mes[:4]) * 12 + int(mes[5:7]) - 1


def fin_de_mes(mes: str) -> datetime.date:
    return _ultimo_dia(_indice_de_texto(mes))


def elegir_corte(cortes: Iterable[datetime.date], limite: datetime.date) -> Optional[datetime.date]:
    """El ultimo corte en o antes de `limite`; sin ninguno, el ultimo que exista (None si no hay cortes)."""
    cortes = sorted(cortes)
    antes = [c for c in cortes if c <= limite]
    return antes[-1] if antes else (cortes[-1] if cortes else None)


def cortes_de_tendencia(
    cortes: Iterable[datetime.date], ultimo_mes: str, cantidad: int = MESES_TENDENCIA,
) -> List[Tuple[str, datetime.date]]:
    """`[(mes, corte)]` de los ultimos `cantidad` meses que terminan en `ultimo_mes` y SI tienen un corte
    dentro del mes (el ultimo de ellos), del mas viejo al mas nuevo."""
    ultimo = _indice_de_texto(ultimo_mes)
    por_mes: Dict[int, datetime.date] = {}
    for corte in sorted(cortes):
        indice = indice_mes(corte)
        if ultimo - cantidad < indice <= ultimo:
            por_mes[indice] = corte
    return [(_mes_texto(i), por_mes[i]) for i in sorted(por_mes)]


def corte_anterior(
    cortes: Iterable[datetime.date], ultimo_mes: str, corte: datetime.date,
) -> Optional[datetime.date]:
    """El corte de cierre del mes anterior: el ultimo en o antes del fin del mes previo a `ultimo_mes`, y
    distinto de `corte` (None si no hay o si el corte ya es de un mes anterior al elegido)."""
    fin_previo = _ultimo_dia(_indice_de_texto(ultimo_mes) - 1)
    candidatos = [c for c in cortes if c <= fin_previo and c < corte]
    return max(candidatos) if candidatos else None


# --- Config, rotation, coverage -----------------------------------------------------------------


def rotacion(dias: Optional[float]) -> Optional[float]:
    """Veces al ano que se vende el inventario: 365 / dias (None sin dias)."""
    return 365 / dias if dias else None


def _numero(valor: Any) -> Optional[float]:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def cortes_color(valor: Any) -> Dict[str, float]:
    """`{verde_hasta, ambar_hasta}` como numeros; lo invalido (o con el verde no menor al ambar) vuelve al defecto."""
    if isinstance(valor, dict):
        verde, ambar = _numero(valor.get("verde_hasta")), _numero(valor.get("ambar_hasta"))
        if verde is not None and ambar is not None and 0 <= verde < ambar:
            return {"verde_hasta": _entero_si_cabe(verde), "ambar_hasta": _entero_si_cabe(ambar)}
    return dict(CORTES_POR_DEFECTO)


def _entero_si_cabe(valor: float):
    return int(valor) if valor == int(valor) else valor


def cobertura(transito: Decimal, demanda: Decimal) -> Optional[float]:
    """Que parte de la demanda cubre lo que viene en transito (0 a 1; None sin demanda)."""
    if not demanda or demanda <= 0:
        return None
    return float(min(Decimal(1), Decimal(transito) / Decimal(demanda)))


def _unidades(valor: Decimal):
    valor = Decimal(valor)
    return int(valor) if valor == valor.to_integral_value() else float(valor)


def _dinero(valor: Decimal) -> float:
    return float(round(Decimal(valor), 2))


# --- Age ------------------------------------------------------------------------------------------


def dias_sin_venta(corte: datetime.date, ultimo_ym: Optional[int], historial_ym: Optional[int]) -> int:
    """Dias entre el ultimo dia del ultimo mes con venta y el corte (0 si vendio en el mes del corte). Sin
    venta nunca: desde el primer dia del primer mes de la historia (o del mes del corte sin historia)."""
    if ultimo_ym is not None:
        desde = _ultimo_dia(ultimo_ym)
    else:
        desde = _primer_dia(historial_ym if historial_ym is not None else indice_mes(corte))
    return max(0, (corte - desde).days)


def indice_de_banda(dias: int) -> int:
    for posicion, (_, hasta) in enumerate(BANDAS):
        if hasta is None or dias <= hasta:
            return posicion
    return len(BANDAS) - 1


def armar_antiguedad(pares: Iterable[Tuple[Decimal, int]], historial_ym: Optional[int]) -> Dict[str, Any]:
    """`{historial_desde, bandas}`: el valor de los `(valor, dias sin venta)` en cada banda y su parte del total."""
    suma = [Decimal(0)] * len(BANDAS)
    for valor, dias in pares:
        suma[indice_de_banda(dias)] += Decimal(valor)
    total = sum(suma, Decimal(0))
    return {
        "historial_desde": _mes_texto(historial_ym) if historial_ym is not None else None,
        "bandas": [
            {"desde": desde, "hasta": hasta, "valor": _dinero(suma[i]), "pct": t.ratio(suma[i], total)}
            for i, (desde, hasta) in enumerate(BANDAS)
        ],
    }


# --- Demand ---------------------------------------------------------------------------------------


class Demanda(NamedTuple):
    vendidas: Decimal
    perdidas: Decimal
    linea: Optional[str]


class Evaluada(NamedTuple):
    """Un par con demanda: `disponible` si tiene existencia > 0 en el corte."""
    tienda: str
    referencia_id: Any
    linea: Optional[str]
    vendidas: Decimal
    perdidas: Decimal
    demanda: Decimal
    transito: Decimal
    disponible: bool


def evaluar_demanda(
    demanda: Dict[Tuple[str, Any], Demanda], con_existencia: Set[Tuple[str, Any]],
    transito: Dict[Tuple[str, Any], Decimal],
) -> List[Evaluada]:
    """Los pares con demanda > 0 (vendidas netas solo si son positivas, mas ventas perdidas)."""
    salida = []
    for (tienda, referencia), d in demanda.items():
        vendidas = max(Decimal(d.vendidas), Decimal(0))
        perdidas = max(Decimal(d.perdidas), Decimal(0))
        if vendidas + perdidas <= 0:
            continue
        salida.append(Evaluada(
            tienda, referencia, d.linea, vendidas, perdidas, vendidas + perdidas,
            max(Decimal(transito.get((tienda, referencia), 0)), Decimal(0)),
            (tienda, referencia) in con_existencia))
    return salida


def disponibilidad(evaluadas: Sequence[Evaluada]) -> Dict[str, Any]:
    """`{pct, agotadas}`: pares con demanda y existencia / pares con demanda, y cuantos no la tienen."""
    total = len(evaluadas)
    con = sum(1 for e in evaluadas if e.disponible)
    return {"pct": (con / total) if total else None, "agotadas": total - con}


# --- The payload ----------------------------------------------------------------------------------


class Par(NamedTuple):
    """Un par (tienda principal, referencia) con existencia > 0 en el corte, tal como sale de la consulta."""
    tienda: str
    referencia_id: Any
    linea: Optional[str]
    existencia: Decimal
    valor: Decimal
    ultimo_ym: Optional[int]


class Entradas(NamedTuple):
    corte: datetime.date
    ultimo_mes: str
    valores_por_corte: Dict[datetime.date, Dict[str, Decimal]]  # corte -> {tienda: valor}; incluye el corte
    cortes_tendencia: List[Tuple[str, datetime.date]]
    corte_anterior: Optional[datetime.date]
    costos: List[Tuple[str, str, Optional[str], Decimal]]  # (mes, tienda, linea, costo de venta)
    pares: List[Par]
    demanda: Dict[Tuple[str, Any], Demanda]
    transito: Dict[Tuple[str, Any], Decimal]
    historial_ym: Optional[int]
    lineas: Tuple[str, ...]
    umbral: int
    dias_meta: int
    cortes_color: Dict[str, float]
    pendientes: Tuple[float, int]  # (valor, facturas) pendientes de ingreso
    nombres_tienda: Dict[str, str]


class Resultado(NamedTuple):
    datos: Dict[str, Any]
    sin_movimiento: List[Dict[str, Any]]  # TODOS los pares inactivos, mayor valor primero
    agotadas: List[Dict[str, Any]]  # TODAS las agotadas con demanda, mayor demanda primero


def dias_de_ventana(mes_fin: str) -> int:
    inicio, fin = t.limites_de_fecha(t.mes_desplazado(mes_fin, -(qk.MESES_COSTO_VENTA - 1)), mes_fin)
    return (fin - inicio).days


def costo_ventana(
    costos: Iterable[Tuple[str, str, Optional[str], Decimal]], mes_fin: str,
    tiendas: Optional[Set[str]] = None, linea: Any = _TODAS,
) -> Decimal:
    """Costo de venta de los 3 meses de calendario que terminan en `mes_fin`, de las `tiendas` (None = todas)
    y de una `linea` (None = sin linea; por defecto, todas)."""
    meses = {t.mes_desplazado(mes_fin, -i) for i in range(qk.MESES_COSTO_VENTA)}
    total = Decimal(0)
    for mes, tienda, ln, costo in costos:
        if mes in meses and (tiendas is None or tienda in tiendas) and (linea is _TODAS or ln == linea):
            total += Decimal(costo)
    return total


def _dias(valor: Decimal, costo: Decimal, mes_fin: str) -> Optional[float]:
    return dias_de_inventario(valor, costo, dias_de_ventana(mes_fin))


def _orden_por_dias(fila: Dict[str, Any]):
    dias = fila["dias"]
    return (dias is None, -(dias or 0), fila["nombre"])


def _suma(valores: Iterable[Decimal]) -> Decimal:
    return sum(valores, Decimal(0))


def _tarjetas(
    e: Entradas, valor: Decimal, valor_inactivo: Decimal, valor_pares: Decimal, dispo: Dict[str, Any],
) -> Dict[str, Any]:
    valores = e.valores_por_corte.get(e.corte, {})
    dias = _dias(valor, costo_ventana(e.costos, e.ultimo_mes, set(valores)), e.ultimo_mes)
    previo = e.valores_por_corte.get(e.corte_anterior) if e.corte_anterior else None
    return {
        "valor": _dinero(valor),
        "valor_mes_anterior": _dinero(_suma(previo.values())) if previo is not None else None,
        "dias": dias, "dias_meta": e.dias_meta, "rotacion": rotacion(dias),
        "sin_movimiento": {"valor": _dinero(valor_inactivo), "pct": t.ratio(valor_inactivo, valor_pares)},
        "disponibilidad": dispo,
        "transito": {"valor": _dinero(Decimal(str(e.pendientes[0]))), "facturas": e.pendientes[1]},
    }


def _tendencia(e: Entradas) -> List[Dict[str, Any]]:
    """Un punto por mes con corte: su valor y los dias de SU ventana de costo (tiendas con inventario ese corte)."""
    puntos = []
    for mes, corte in e.cortes_tendencia:
        por_tienda = e.valores_por_corte.get(corte, {})
        valor = _suma(por_tienda.values())
        puntos.append({
            "mes": mes, "corte": corte.isoformat(), "valor": _dinero(valor),
            "dias": _dias(valor, costo_ventana(e.costos, mes, set(por_tienda)), mes)})
    return puntos


def _lineas(e: Entradas, pares: Sequence[Par], evaluadas: Sequence[Evaluada]) -> List[Dict[str, Any]]:
    """Una fila por linea configurada y, si no esta vacia, la de "Sin línea" (la linea no reconocida)."""
    por_linea: Dict[Optional[str], Decimal] = {}
    for p in pares:
        por_linea[p.linea] = por_linea.get(p.linea, Decimal(0)) + p.valor
    total = _suma(por_linea.values())
    con_inventario = set(e.valores_por_corte.get(e.corte, {}))
    filas = []
    for linea in (*e.lineas, None):
        ev = [x for x in evaluadas if x.linea == linea]
        valor = por_linea.get(linea, Decimal(0))
        if linea is None and not valor and not ev:
            continue
        dias = _dias(valor, costo_ventana(e.costos, e.ultimo_mes, con_inventario, linea), e.ultimo_mes)
        filas.append({
            "linea": linea if linea is not None else "Sin línea", "valor": _dinero(valor),
            "pct": t.ratio(valor, total), "dias": dias, "rotacion": rotacion(dias),
            "disponibilidad_pct": disponibilidad(ev)["pct"]})
    return filas


def _tiendas(
    e: Entradas, inactivos: Sequence[Tuple[Par, int]], evaluadas: Sequence[Evaluada],
) -> List[Dict[str, Any]]:
    filas = []
    for tienda, valor in e.valores_por_corte.get(e.corte, {}).items():
        dias = _dias(valor, costo_ventana(e.costos, e.ultimo_mes, {tienda}), e.ultimo_mes)
        dispo = disponibilidad([x for x in evaluadas if x.tienda == tienda])
        filas.append({
            "sucursal_id": tienda, "nombre": e.nombres_tienda.get(tienda, ""), "valor": _dinero(valor),
            "dias": dias, "rotacion": rotacion(dias),
            "sin_movimiento_valor": _dinero(_suma(p.valor for p, _ in inactivos if p.tienda == tienda)),
            "disponibilidad_pct": dispo["pct"], "agotadas": dispo["agotadas"]})
    filas.sort(key=_orden_por_dias)
    return filas


def _inicio_de_costo(ultimo_mes: str) -> datetime.date:
    return t.limites_de_fecha(t.mes_desplazado(ultimo_mes, -(qk.MESES_COSTO_VENTA - 1)), ultimo_mes)[0]


def analizar(e: Entradas) -> Resultado:
    """Arma la respuesta de la pestana a partir de las filas leidas. Las referencias quedan con su
    `referencia_id` (el servicio las rotula con codigo y nombre)."""
    con_dias = [(p, dias_sin_venta(e.corte, p.ultimo_ym, e.historial_ym)) for p in e.pares]
    inactivos = [(p, d) for p, d in con_dias if d > e.umbral]
    evaluadas = evaluar_demanda(e.demanda, {(p.tienda, p.referencia_id) for p in e.pares}, e.transito)
    agotadas_ev = [x for x in evaluadas if not x.disponible]
    en_transito = sum(1 for x in agotadas_ev if x.transito > 0)
    valor = _suma(e.valores_por_corte.get(e.corte, {}).values())
    tarjetas = _tarjetas(
        e, valor, _suma(p.valor for p, _ in inactivos), _suma(p.valor for p in e.pares), disponibilidad(evaluadas))
    sin_movimiento = [
        {"referencia_id": p.referencia_id, "sucursal_id": p.tienda, "tienda": e.nombres_tienda.get(p.tienda, ""),
         "existencia": _unidades(p.existencia), "valor": _dinero(p.valor), "dias_sin_venta": d}
        for p, d in sorted(inactivos, key=lambda x: (-x[0].valor, -x[1], x[0].tienda, str(x[0].referencia_id)))]
    agotadas = [
        {"referencia_id": x.referencia_id, "sucursal_id": x.tienda, "tienda": e.nombres_tienda.get(x.tienda, ""),
         "vendidas": _unidades(x.vendidas), "perdidas": _unidades(x.perdidas), "demanda": _unidades(x.demanda),
         "transito": _unidades(x.transito), "cobertura": cobertura(x.transito, x.demanda)}
        for x in sorted(agotadas_ev, key=lambda x: (-x.demanda, x.tienda, str(x.referencia_id)))]
    datos = {
        "corte": e.corte.isoformat(),
        "costo_desde": _inicio_de_costo(e.ultimo_mes).isoformat(),
        "costo_hasta": fin_de_mes(e.ultimo_mes).isoformat(),
        "dias_ventana": dias_de_ventana(e.ultimo_mes),
        "tarjetas": tarjetas,
        "cortes_color": e.cortes_color,
        "tendencia": _tendencia(e),
        "antiguedad": armar_antiguedad([(p.valor, d) for p, d in con_dias], e.historial_ym),
        "lineas": _lineas(e, e.pares, evaluadas),
        "tiendas": _tiendas(e, inactivos, evaluadas),
        "sin_movimiento_umbral_dias": e.umbral,
        "sin_movimiento_top": [],  # the service fills the top with names
        "agotadas": {
            "total": len(agotadas_ev), "en_transito": en_transito, "sin_pedir": len(agotadas_ev) - en_transito,
            "items": []},
    }
    return Resultado(datos, sin_movimiento, agotadas)


# --- Orchestration --------------------------------------------------------------------------------

CLAVES = {
    "kpi_inventario_dias_meta": DIAS_META_POR_DEFECTO,
    "kpi_inventario_dias_cortes": CORTES_POR_DEFECTO,
    "kpi_inventario_sin_movimiento_dias": UMBRAL_SIN_MOVIMIENTO_POR_DEFECTO,
    "excluir_transito_vencido": False,
    "dias_ventana_ingresos": parametros.DEFAULT_DIAS_VENTANA_INGRESOS,
    "tolerancia_ingreso_pct": parametros.DEFAULT_TOLERANCIA_INGRESO_PCT,
}


async def _pendientes_de_ingreso(db: AsyncSession, filtro: Filtro) -> Tuple[float, int]:
    """`(valor, facturas)` de las facturas de proveedor sin ingresar de las tiendas del filtro."""
    items = await ingresos_pendientes.pendientes(db, list(filtro.sucursal_ids) if filtro.sucursal_ids else None)
    return round(sum(i["valor"] for i in items), 2), len(items)


def _demanda(ventas, perdidas) -> Dict[Tuple[str, Any], Demanda]:
    salida: Dict[Tuple[str, Any], Demanda] = {}
    for tienda, referencia, linea, vendidas, _ in ventas:
        if vendidas:
            salida[(tienda, referencia)] = Demanda(vendidas, Decimal(0), linea)
    for tienda, referencia, linea, cantidad in perdidas:
        previa = salida.get((tienda, referencia))
        salida[(tienda, referencia)] = (
            Demanda(previa.vendidas, cantidad, previa.linea) if previa else Demanda(Decimal(0), cantidad, linea))
    return salida


def _primer_dia_de_mes(mes: str) -> datetime.date:
    return datetime.date(int(mes[:4]), int(mes[5:7]), 1)


async def _valores_y_costos(
    db: AsyncSession, filtro: Filtro, corte: datetime.date, en_tendencia: List[Tuple[str, datetime.date]],
    anterior: Optional[datetime.date],
) -> Tuple[Dict[datetime.date, Dict[str, Decimal]], List[Tuple[str, str, Optional[str], Decimal]]]:
    """Valor por corte y tienda, y costo de venta por mes x tienda x linea de todas las ventanas que se muestran."""
    # The chosen corte comes from the summary-aware reader (the Tiendas tab's number).
    valores = {corte: {f.sucursal_id: f.valor for f in await lectura.inventario(db, filtro, corte)}}
    otros = {c for _, c in en_tendencia} | ({anterior} if anterior else set())
    valores.update(await qi.consultar_valor_por_corte(db, filtro, otros - {corte}))
    ultimo = filtro.meses[-1]
    primero = min([m for m, _ in en_tendencia] + [ultimo])
    desde = t.mes_desplazado(primero, -(qk.MESES_COSTO_VENTA - 1))
    return valores, await qi.consultar_costos_por_mes(db, filtro, corte, desde, ultimo)


async def _pares_y_demanda(
    db: AsyncSession, filtro: Filtro, corte: datetime.date,
) -> Tuple[List[Par], Dict[Tuple[str, Any], Demanda]]:
    ultimo = filtro.meses[-1]
    fin_ym = indice_mes(fin_de_mes(ultimo))
    ventana = (fin_ym - (qk.MESES_COSTO_VENTA - 1), fin_ym)
    ventas = await qi.consultar_ventas_por_par(db, filtro, indice_mes(corte), ventana)
    inicio, fin = t.limites_de_fecha(t.mes_desplazado(ultimo, -(qk.MESES_COSTO_VENTA - 1)), ultimo)
    perdidas = await qi.consultar_perdidas_por_par(db, filtro, inicio, fin)
    ultimo_por_par = {(s, r): u for s, r, _, _, u in ventas}
    pares = [
        Par(s, r, ln, e, v, ultimo_por_par.get((s, r)))
        for s, r, ln, e, v in await qi.consultar_pares_con_existencia(db, filtro, corte)]
    return pares, _demanda(ventas, perdidas)


async def _entradas(db: AsyncSession, filtro: Filtro, cortes: List[datetime.date], corte: datetime.date) -> Entradas:
    ultimo_mes = filtro.meses[-1]
    config = await parametros.leer_valores(db, _primer_dia_de_mes(ultimo_mes), CLAVES)
    en_tendencia = cortes_de_tendencia(cortes, ultimo_mes)
    anterior = corte_anterior(cortes, ultimo_mes, corte)
    valores, costos = await _valores_y_costos(db, filtro, corte, en_tendencia, anterior)
    pares, demanda = await _pares_y_demanda(db, filtro, corte)
    transito = await qi.consultar_transito_por_par(
        db, filtro, corte, await lectura.principales(db),
        excluir_vencido=bool(config["excluir_transito_vencido"]),
        dias_ventana_ingresos=int(config["dias_ventana_ingresos"]),
        tolerancia_ingreso_pct=float(config["tolerancia_ingreso_pct"]))
    ids_tienda = ({s for v in valores.values() for s in v} | {p.tienda for p in pares}
                  | {s for s, _ in demanda} | {s for s, _ in transito})
    nombres = {i: nombre for i, (nombre, _) in (await q.consultar_sucursales(db, ids_tienda)).items()}
    return Entradas(
        corte=corte, ultimo_mes=ultimo_mes, valores_por_corte=valores, cortes_tendencia=en_tendencia,
        corte_anterior=anterior, costos=costos, pares=pares, demanda=demanda, transito=transito,
        historial_ym=await qi.consultar_primer_mes_con_venta(db), lineas=tuple(filtro.reglas.lineas),
        umbral=int(config["kpi_inventario_sin_movimiento_dias"]), dias_meta=int(config["kpi_inventario_dias_meta"]),
        cortes_color=cortes_color(config["kpi_inventario_dias_cortes"]),
        pendientes=await _pendientes_de_ingreso(db, filtro), nombres_tienda=nombres)


async def _rotular(db: AsyncSession, filas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cambia `referencia_id` por `referencia` (codigo) y `nombre`."""
    nombres = await qi.consultar_referencias(db, (f["referencia_id"] for f in filas))
    salida = []
    for fila in filas:
        codigo, nombre = nombres.get(fila["referencia_id"], (str(fila["referencia_id"]), None))
        resto = {k: v for k, v in fila.items() if k != "referencia_id"}
        salida.append({"referencia": codigo, "nombre": nombre, **resto})
    return salida


async def calcular_inventario(db: AsyncSession, filtro: Filtro, *, completo: bool = False) -> Resultado:
    """La respuesta de la pestana y las listas largas. Con `completo`, `sin_movimiento` y `agotadas` traen TODOS
    los pares (con codigo y nombre) para el Excel; si no, el top de la respuesta (8 y 20) en `datos`."""
    cortes = await qi.consultar_cortes(db)
    ultimo_mes = filtro.meses[-1]
    corte = elegir_corte(cortes, fin_de_mes(ultimo_mes))
    if corte is None:
        pendientes = await _pendientes_de_ingreso(db, filtro)
        vacio = analizar(Entradas(
            corte=fin_de_mes(ultimo_mes), ultimo_mes=ultimo_mes, valores_por_corte={}, cortes_tendencia=[],
            corte_anterior=None, costos=[], pares=[], demanda={}, transito={}, historial_ym=None,
            lineas=tuple(filtro.reglas.lineas), umbral=UMBRAL_SIN_MOVIMIENTO_POR_DEFECTO,
            dias_meta=DIAS_META_POR_DEFECTO, cortes_color=dict(CORTES_POR_DEFECTO), pendientes=pendientes,
            nombres_tienda={}))
        vacio.datos["corte"] = None
        return vacio
    resultado = analizar(await _entradas(db, filtro, cortes, corte))
    sin_mov = resultado.sin_movimiento if completo else resultado.sin_movimiento[:TOP_SIN_MOVIMIENTO]
    agotadas = resultado.agotadas if completo else resultado.agotadas[:TOP_AGOTADAS]
    sin_mov, agotadas = await _rotular(db, sin_mov), await _rotular(db, agotadas)
    resultado.datos["sin_movimiento_top"] = sin_mov[:TOP_SIN_MOVIMIENTO]
    resultado.datos["agotadas"]["items"] = agotadas[:TOP_AGOTADAS]
    return Resultado(resultado.datos, sin_mov, agotadas)


async def calcular(db: AsyncSession, filtro: Filtro) -> Dict[str, Any]:
    return (await calcular_inventario(db, filtro)).datos
