"""
KPI's, pestana Asesores, vista de UN asesor: armado PURO (sin base de datos).

Recibe lo que ya calculan los constructores existentes y lo reparte en los bloques
que pinta la vista de un asesor; no vuelve a consultar ni a calcular ventas:
- `tablero`: el tablero de asesores del periodo (`tablero_asesores.construir_tablero`).
- `cumplimiento`: el cumplimiento del periodo (`tablero_kpis.construir_cumplimiento`).
- `por_mes`: `{mes: construir_cumplimiento de ESE mes}` (`tablero_kpis.cumplimiento_por_mes`).
- `comision`: la liquidacion del ultimo mes (`tablero_kpis.calcular_kpis_comisiones`).

Convenciones (las del tablero): dinero en pesos, todo `pct`/`red_pct` es una FRACCION
(0.93 = 93 %) y un cociente sin denominador es `None`, nunca 0.

- Puestos: 1 = el mayor valor; los empates comparten puesto y el siguiente se salta (como
  `tablero_asesores.rankear`). El cumplimiento es el del ULTIMO mes del periodo, entre los
  asesores con presupuesto ese mes; venta y Tecnired son las del periodo, entre las filas
  de persona del tablero.
- Cada tile compara el volumen (venta, facturas, clientes) con el PROMEDIO de los asesores
  y las razones (ticket, margen, % Tecnired) con la RED (la fila TOTAL del tablero).
- La tienda del asesor es la de su presupuesto mas reciente del periodo (la del maestro si no
  tiene presupuesto). Su promedio de tienda promedia a los asesores de esa tienda (el propio
  incluido) en venta y cumplimiento, y pesa por facturas, venta con costo y venta en las
  razones (ticket, margen, % Tecnired).
"""
from typing import Any, Dict, Iterable, List, Optional

from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.services import tablero_asesores as t


def _cedula_de(clave: str) -> Optional[str]:
    try:
        return limpiar_cedula(clave[len(t.PREFIJO_PERSONA):])
    except ValueError:
        return None


def _promedio(valores: Iterable[Optional[float]]) -> Optional[float]:
    validos = [v for v in valores if v is not None]
    return sum(validos) / len(validos) if validos else None


def _razon(numerador: float, denominador: float) -> Optional[float]:
    return numerador / denominador if denominador else None


def _puesto(valores: Iterable[float], propio: Optional[float]) -> Dict[str, Optional[int]]:
    valores = list(valores)
    puesto = None if propio is None else 1 + sum(1 for v in valores if v > propio)
    return {"puesto": puesto, "de": len(valores)}


def _fila_de(personas: List[Dict[str, Any]], cedula: str) -> Optional[Dict[str, Any]]:
    """The tablero row of the asesor; if one person shows up under several keys, the one that sold most."""
    propias = [f for f in personas if _cedula_de(f["clave"]) == cedula]
    return max(propias, key=lambda f: f["venta"]["total"], default=None)


def clave_de_asesor(tablero: Dict[str, Any], cedula: str) -> Optional[str]:
    """The tablero key (`P:...`) of the asesor's row, None when she has no sales in the tablero."""
    fila = _fila_de([f for f in tablero["filas"] if f["tipo"] == t.TIPO_PERSONA], cedula)
    return None if fila is None else fila["clave"]


def _fila_cumplimiento(bloque: Optional[Dict[str, Any]], cedula: str) -> Optional[Dict[str, Any]]:
    return next((a for a in (bloque or {}).get("asesores", ()) if a["cedula"] == cedula), None)


def _dif(valor: Optional[float], ref: Optional[float], tipo: str) -> Optional[float]:
    if valor is None or ref is None:
        return None
    if tipo == "pts":
        return valor - ref
    return valor / ref - 1 if ref else None


def _tile(id_: str, valor, ref, ref_de: str, tipo: str) -> Dict[str, Any]:
    return {"id": id_, "valor": valor, "ref": ref, "ref_de": ref_de, "dif_tipo": tipo, "dif": _dif(valor, ref, tipo)}


def _tiles(fila: Optional[Dict[str, Any]], personas: List[Dict[str, Any]], total: Dict[str, Any]) -> List[Dict[str, Any]]:
    def propio(bloque, campo, vacio=None):
        return fila[bloque][campo] if fila else vacio

    return [
        _tile("venta", propio("venta", "total", 0.0), _promedio(f["venta"]["total"] for f in personas),
              "asesores", "pct"),
        _tile("ticket", propio("facturas", "ticket_promedio"), total["facturas"]["ticket_promedio"], "red", "pct"),
        _tile("facturas", propio("facturas", "facturas", 0), _promedio(f["facturas"]["facturas"] for f in personas),
              "asesores", "pct"),
        _tile("clientes_unicos", propio("clientes", "clientes_unicos", 0),
              _promedio(f["clientes"]["clientes_unicos"] for f in personas), "asesores", "pct"),
        _tile("margen", propio("costo", "pct_margen"), total["costo"]["pct_margen"], "red", "pts"),
        _tile("pct_tecnired", propio("clientes", "pct_tecnired"), total["clientes"]["pct_tecnired"], "red", "pts"),
    ]


def _comision(comision: Optional[Dict[str, Any]], cedula: str) -> Optional[Dict[str, Any]]:
    fila = next((a for a in (comision or {}).get("asesores", ()) if a["cedula"] == cedula), None)
    if fila is None:
        return None
    sig = fila["sig"]
    return {
        "mes": comision["mes_liquidado"], "tramo": fila["tramo"], "tasa_pct": fila["tasa_pct"],
        "comision": fila["comision"], "venta_base": fila["venta_comision"],
        "base_pago": comision["reglas"]["comision_base_pago"], "presupuesto": fila["presupuesto"],
        "promedio_red": comision["resumen"]["comision_promedio"],
        "sig": None if sig is None else {
            "tramo": sig["nombre"], "desde_pct": sig["desde_pct"], "tasa_pct": sig["tasa_pct"],
            "falta": sig["falta"], "gana": sig["gana"], "meta": fila["presupuesto"] * sig["desde_pct"] / 100,
        },
    }


def _comparacion(
    cedula: str, fila: Optional[Dict[str, Any]], personas: List[Dict[str, Any]], total: Dict[str, Any],
    sucursal_de: Dict[str, Optional[str]], mi_sucursal: Optional[str], nombre_tienda: Optional[str],
    ultimo_mes: str, pct_del_mes: Dict[str, Optional[float]], red_pct: Optional[float],
) -> Dict[str, Any]:
    companeras = [f for f in personas if mi_sucursal is not None and sucursal_de.get(_cedula_de(f["clave"])) == mi_sucursal]

    def venta_mes(f):
        return f["venta"]["por_mes"].get(ultimo_mes, 0.0)

    def ponderada(filas, numerador, denominador):
        return _razon(sum(numerador(f) for f in filas), sum(denominador(f) for f in filas))

    propia_pct = pct_del_mes.get(cedula)
    bloques = {
        "ticket": (lambda f: f["venta"]["total"], lambda f: f["facturas"]["facturas"],
                   lambda f: f["facturas"]["ticket_promedio"], total["facturas"]["ticket_promedio"]),
        "margen": (lambda f: f["costo"]["utilidad_bruta"], lambda f: f["costo"]["venta_con_costo"],
                   lambda f: f["costo"]["pct_margen"], total["costo"]["pct_margen"]),
        "pct_tecnired": (lambda f: f["clientes"]["venta_tecnired"], lambda f: f["venta"]["total"],
                         lambda f: f["clientes"]["pct_tecnired"], total["clientes"]["pct_tecnired"]),
    }
    resultado: Dict[str, Any] = {
        "tienda": {"nombre": nombre_tienda, "asesores": len(companeras)},
        "venta_mes": {
            "yo": venta_mes(fila) if fila else 0.0,
            "tienda": _promedio(venta_mes(f) for f in companeras),
            "red": _promedio(venta_mes(f) for f in personas),
        },
        "cumplimiento_mes": {
            "yo": propia_pct,
            "tienda": _promedio(pct_del_mes.get(_cedula_de(f["clave"])) for f in companeras),
            "red": red_pct,
        },
    }
    for nombre, (numerador, denominador, propio, red) in bloques.items():
        resultado[nombre] = {
            "yo": propio(fila) if fila else None,
            "tienda": ponderada(companeras, numerador, denominador) if companeras else None,
            "red": red,
        }
    return resultado


def _puestos(
    fila: Optional[Dict[str, Any]], personas: List[Dict[str, Any]], con_pct: Dict[str, float], cedula: str,
) -> Dict[str, Any]:
    return {
        "cumplimiento": _puesto(con_pct.values(), con_pct.get(cedula)),
        "venta": _puesto((f["venta"]["total"] for f in personas), fila["venta"]["total"] if fila else None),
        "tecnired": _puesto(
            (f["clientes"]["venta_tecnired"] for f in personas), fila["clientes"]["venta_tecnired"] if fila else None),
    }


def _cumplimiento_mes(
    propia: Optional[Dict[str, Any]], mes: str, red_pct: Optional[float], base: str,
) -> Dict[str, Any]:
    propia = propia or {}
    return {
        "mes": mes, "venta": propia.get("venta_cumplimiento", 0.0), "presupuesto": propia.get("presupuesto", 0),
        "pct": propia.get("cumplimiento_pct"), "semaforo": propia.get("semaforo"), "red_pct": red_pct, "base": base,
    }


def _tendencia(por_mes: Dict[str, Dict[str, Any]], meses: List[str], cedula: str) -> List[Dict[str, Any]]:
    return [
        {
            "mes": mes,
            "pct": (_fila_cumplimiento(por_mes.get(mes), cedula) or {}).get("cumplimiento_pct"),
            "red_pct": ((por_mes.get(mes) or {}).get("red") or {}).get("cumplimiento_pct"),
        }
        for mes in meses
    ]


def _lineas(fila: Optional[Dict[str, Any]], total: Dict[str, Any]) -> List[Dict[str, Any]]:
    mix_red = total["venta"]["mix"]
    return [
        {"linea": linea, "pct": fila["venta"]["mix"].get(linea) if fila else None, "red_pct": mix_red.get(linea)}
        for linea in mix_red
    ]


def _strip(con_pct: Dict[str, float], cedula: str, comision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "otros": [p for c, p in con_pct.items() if c != cedula],
        "yo": con_pct.get(cedula),
        "tramos": [{"nombre": x["nombre"], "desde_pct": x["desde_pct"]} for x in (comision or {}).get("tramos", ())],
    }


def _tecnired(
    fila: Optional[Dict[str, Any]], total: Dict[str, Any], clientes: int, top: Iterable[Any],
) -> Dict[str, Any]:
    return {
        "venta": fila["clientes"]["venta_tecnired"] if fila else 0.0,
        "pct": fila["clientes"]["pct_tecnired"] if fila else None,
        "red_pct": total["clientes"]["pct_tecnired"],
        "clientes": clientes,
        "top": [{"cliente": f.razon_social or f.nit, "nit": f.nit, "venta": float(round(f.venta, 2))} for f in top],
    }


def _ficha(
    cedula: str, fila: Optional[Dict[str, Any]], en_periodo: Optional[Dict[str, Any]],
    maestro: Optional[Dict[str, Any]], nombre_tienda: Optional[str], sucursal_id: Optional[str],
) -> Dict[str, Any]:
    maestro = maestro or {}
    return {
        "cedula": cedula,
        "nombre": (fila or {}).get("nombre") or (en_periodo or {}).get("nombre") or maestro.get("nombre"),
        "cargo": (fila or {}).get("cargo") or maestro.get("cargo"),
        "tienda": nombre_tienda,
        "sucursal_id": sucursal_id,
    }


def construir_detalle(
    cedula: str,
    tablero: Dict[str, Any],
    cumplimiento: Dict[str, Any],
    por_mes: Dict[str, Dict[str, Any]],
    comision: Optional[Dict[str, Any]],
    tecnired_clientes: int,
    tecnired_top: Iterable[Any],
    maestro: Optional[Dict[str, Any]],
    tiendas: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """El detalle del asesor de `cedula` (limpia), o None si no aparece ni en el tablero, ni en los
    presupuestos del filtro ni en el maestro (`maestro`: `{nombre, cargo, tienda, sucursal_id}`).
    `tiendas` es `{sucursal_id: nombre}` de las tiendas de los presupuestos."""
    personas = [f for f in tablero["filas"] if f["tipo"] == t.TIPO_PERSONA]
    fila = _fila_de(personas, cedula)
    en_periodo = _fila_cumplimiento(cumplimiento, cedula)
    # Her sale counts in full for cumplimiento whatever the store filter says, so a row there does
    # not mean she is in scope: a budget of the filter does.
    con_presupuesto = bool(en_periodo and en_periodo["meses_con_presupuesto"])
    if fila is None and not con_presupuesto and maestro is None:
        return None

    meses = list(tablero["meses"])
    ultimo, del_mes, total = meses[-1], por_mes.get(meses[-1]), tablero["total"]
    pct_del_mes = {a["cedula"]: a["cumplimiento_pct"] for a in (del_mes or {}).get("asesores", ()) if a["cedula"]}
    con_pct = {c: p for c, p in pct_del_mes.items() if p is not None}
    red_mes = ((del_mes or {}).get("red") or {}).get("cumplimiento_pct")
    sucursal_id = (en_periodo or {}).get("sucursal_id") or (maestro or {}).get("sucursal_id")
    nombre_tienda = tiendas.get(sucursal_id) or (maestro or {}).get("tienda") or (fila or {}).get("punto_venta")
    sucursal_de = {a["cedula"]: a["sucursal_id"] for a in cumplimiento["asesores"] if a["cedula"]}
    sucursal_de[cedula] = sucursal_id

    return {
        "asesor": _ficha(cedula, fila, en_periodo, maestro, nombre_tienda, sucursal_id),
        "puestos": _puestos(fila, personas, con_pct, cedula),
        "cumplimiento_mes": _cumplimiento_mes(
            _fila_cumplimiento(del_mes, cedula), ultimo, red_mes, tablero["reglas"]["cumplimiento_base"]),
        "comision": _comision(comision, cedula),
        "tiles": _tiles(fila, personas, total),
        "tendencia": _tendencia(por_mes, meses, cedula),
        "lineas": _lineas(fila, total),
        "strip": _strip(con_pct, cedula, comision),
        "comparacion": _comparacion(
            cedula, fila, personas, total, sucursal_de, sucursal_id, nombre_tienda, ultimo, pct_del_mes, red_mes),
        "tecnired": _tecnired(fila, total, tecnired_clientes, tecnired_top),
    }


def construir_opciones(
    tablero: Dict[str, Any], maestro: Dict[str, Dict[str, Any]], tiendas: Optional[Iterable[str]],
) -> List[Dict[str, Any]]:
    """Options of the "Asesor" filter: whoever SOLD in the tablero's period, most sales first (ties by
    name). `maestro` is `{cedula: {nombre, tienda, sucursal_id}}`; it names the asesor when she is in
    it. With `tiendas` (the principal stores chosen), an asesor whose master store is another one is left
    out, as the detail does; one that is not in the master stays (the tablero already scoped her sales).
    The first item is the default selection."""
    ventas: Dict[str, Dict[str, Any]] = {}
    for fila in tablero["filas"]:
        cedula = _cedula_de(fila["clave"]) if fila["tipo"] == t.TIPO_PERSONA else None
        if cedula is None or fila["venta"]["total"] <= 0:
            continue
        acumulado = ventas.setdefault(cedula, {"venta": 0.0, "mayor": -1.0, "fila": fila})
        acumulado["venta"] += fila["venta"]["total"]
        if fila["venta"]["total"] > acumulado["mayor"]:
            acumulado["mayor"], acumulado["fila"] = fila["venta"]["total"], fila
    elegidas = None if tiendas is None else {str(i) for i in tiendas}
    opciones = []
    for cedula, acumulado in ventas.items():
        propia = maestro.get(cedula)
        if propia and elegidas is not None and propia["sucursal_id"] not in elegidas:
            continue
        fila = acumulado["fila"]
        opciones.append({
            "cedula": cedula,
            "nombre": propia["nombre"] if propia else fila["nombre"],
            "tienda": propia["tienda"] if propia else fila.get("punto_venta"),
            "sucursal_id": propia["sucursal_id"] if propia else None,
            "venta": acumulado["venta"],
        })
    return sorted(opciones, key=lambda o: (-o["venta"], (o["nombre"] or "").upper(), o["cedula"]))
