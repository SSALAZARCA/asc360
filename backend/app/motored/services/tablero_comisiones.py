"""
KPI's, pestana Comisiones: calculo puro (sin base de datos) de la comision de cada asesor
en UN mes liquidado.

Reglas (Configuracion, claves `comision_*` y `cumplimiento_base`):
- El asesor se mide contra SU presupuesto cargado del mes: cumplimiento = venta
  (`cumplimiento_base`) / presupuesto.
- El tramo que le toca es el mas alto cuyo `desde_pct` alcanza (inclusive, sin dividir: 90 %
  exacto es PRO) y su tasa se paga PLANA sobre toda la base (`comision_base_pago`).
- Solo ganan comision los cargos de `comision_cargos_asesor`; sin presupuesto no hay comision.

Bonos por linea (`comision_lineas`, `comision_bono_umbral_pct`), todo sobre la venta de `cumplimiento_base`:
- Compuerta: solo si el cumplimiento TOTAL del asesor alcanza el umbral (inclusive, sin dividir).
- Pasada la compuerta, cada linea activa paga su bono fijo cuando la venta de esa linea es al menos
  `pct_meta` % de la venta TOTAL del asesor en el mes. La venta total es la misma del cumplimiento: la suma
  de las `lineas_comerciales` (lo que no es una de ellas no cuenta, ni en el total ni en las lineas).
- TECNIRED es la venta a clientes Tecnired en cualquier linea; se solapa con las demas, es aceptado.
- Una linea apagada se muestra (quien la habria ganado) pero no se paga.
"""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Tuple

from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.services import presupuestos as pres
from app.motored.services import tablero_asesores as t

BASES = (t.CUMPLIMIENTO_CON_HMCL, t.CUMPLIMIENTO_SIN_HMCL)
TRAMOS_POR_DEFECTO = (
    {"nombre": "BASE", "desde_pct": 0, "tasa_pct": 1.0},
    {"nombre": "PRO", "desde_pct": 90, "tasa_pct": 1.5},
    {"nombre": "ELITE", "desde_pct": 105, "tasa_pct": 1.8},
)
CARGOS_POR_DEFECTO = ("ASESOR DE REPUESTOS", "ASESOR DE REPUESTOS SUPERNUMERARIO")
BASE_PAGO_POR_DEFECTO = t.CUMPLIMIENTO_SIN_HMCL
# An asesor is "near" the next tier when the gap is at most this many points of cumplimiento.
MARGEN_CERCA_PTS = 15
TECNIRED = "TECNIRED"
UMBRAL_BONO_POR_DEFECTO = Decimal(95)
# Same as the registry default of `comision_lineas` (a test keeps them together).
BONOS_POR_DEFECTO = tuple(
    {"linea": linea, "pct_meta": pct, "bono": bono, "activo": True} for linea, pct, bono in (
        ("LUBRICANTES", "21", "35000"), ("CASCOS", "6", "30000"), ("ACCESORIOS", "3", "25000"),
        ("LLANTAS", "1", "25000"), ("BATERIAS", "1", "25000"), (TECNIRED, "6", "25000")))
ETIQUETA_LINEA = {
    "REPUESTOS": "Repuestos", "ACCESORIOS": "Otros accesorios", "LLANTAS": "Llantas", "LUBRICANTES": "Lubricantes",
    "BATERIAS": "Baterías", "GPS": "GPS", "CASCOS": "Cascos", TECNIRED: "Tecnired (clientes)",
}


class Tramo(NamedTuple):
    nombre: str
    desde_pct: Decimal
    tasa_pct: Decimal


class LineaBono(NamedTuple):
    linea: str
    pct_meta: Decimal
    bono: int
    activo: bool


def _bonos_validos(valor: Any) -> Optional[Tuple[LineaBono, ...]]:
    """The configured bonus lines in config order; None if the list is not valid (empty IS valid)."""
    if not isinstance(valor, (list, tuple)):
        return None
    bonos = []
    for x in valor:
        if not isinstance(x, dict) or not isinstance(x.get("linea"), str) or not isinstance(x.get("activo"), bool):
            return None
        pct, bono = _numero(x.get("pct_meta")), _numero(x.get("bono"))
        if pct is None or not 0 < pct <= 100 or bono is None or bono != bono.to_integral_value():
            return None
        bonos.append(LineaBono(x["linea"], pct, int(bono), x["activo"]))
    return tuple(bonos) if len({b.linea for b in bonos}) == len(bonos) else None


def _umbral_valido(valor: Any) -> Optional[Decimal]:
    numero = _numero(valor)
    return numero if numero is not None and numero <= 200 else None


class ReglasComision(NamedTuple):
    tramos: Tuple[Tramo, ...]
    base_pago: str
    cumplimiento_base: str
    cargos: FrozenSet[str]
    bonos: Tuple[LineaBono, ...] = ()
    umbral_bono_pct: Decimal = UMBRAL_BONO_POR_DEFECTO


def respaldos() -> Dict[str, Any]:
    """The fallbacks `parametros.leer_valores` uses when a key has no valid row."""
    return {
        "comision_tramos": [dict(x) for x in TRAMOS_POR_DEFECTO],
        "comision_base_pago": BASE_PAGO_POR_DEFECTO,
        "cumplimiento_base": t.CUMPLIMIENTO_CON_HMCL,
        "comision_cargos_asesor": list(CARGOS_POR_DEFECTO),
        "comision_lineas": [dict(x) for x in BONOS_POR_DEFECTO],
        "comision_bono_umbral_pct": str(UMBRAL_BONO_POR_DEFECTO),
    }


def _numero(valor: Any) -> Optional[Decimal]:
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str, Decimal)):
        return None
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return None
    return numero if numero.is_finite() and numero >= 0 else None


def _tramos_validos(valor: Any) -> Optional[Tuple[Tramo, ...]]:
    if not isinstance(valor, (list, tuple)) or not valor:
        return None
    tramos = []
    for x in valor:
        if not isinstance(x, dict) or not isinstance(x.get("nombre"), str):
            return None
        desde, tasa = _numero(x.get("desde_pct")), _numero(x.get("tasa_pct"))
        if desde is None or tasa is None:
            return None
        tramos.append(Tramo(x["nombre"], desde, tasa))
    return tuple(sorted(tramos, key=lambda tr: tr.desde_pct))


def _cargos_validos(valor: Any) -> FrozenSet[str]:
    if not isinstance(valor, (list, tuple)) or not all(isinstance(x, str) for x in valor):
        return frozenset(t.texto_de_linea(x) for x in CARGOS_POR_DEFECTO)
    return frozenset(t.texto_de_linea(x) for x in valor if x.strip())


def reglas_desde_valores(valores: Dict[str, Any]) -> ReglasComision:
    """`ReglasComision` from the values read from Configuracion; an invalid key goes back to its default."""
    tramos = _tramos_validos(valores.get("comision_tramos")) or _tramos_validos(list(TRAMOS_POR_DEFECTO))
    base_pago = valores.get("comision_base_pago")
    cumplimiento = valores.get("cumplimiento_base")
    bonos = _bonos_validos(valores.get("comision_lineas", list(BONOS_POR_DEFECTO)))
    if bonos is None:
        bonos = _bonos_validos(BONOS_POR_DEFECTO)
    umbral = _umbral_valido(valores.get("comision_bono_umbral_pct", UMBRAL_BONO_POR_DEFECTO))
    return ReglasComision(
        tramos=tramos,
        base_pago=base_pago if base_pago in BASES else BASE_PAGO_POR_DEFECTO,
        cumplimiento_base=cumplimiento if cumplimiento in BASES else t.CUMPLIMIENTO_CON_HMCL,
        cargos=_cargos_validos(valores.get("comision_cargos_asesor")),
        bonos=bonos,
        umbral_bono_pct=umbral if umbral is not None else UMBRAL_BONO_POR_DEFECTO,
    )


def eco_reglas_comision(reglas: ReglasComision) -> Dict[str, Any]:
    return {
        "comision_tramos": [
            {"nombre": x.nombre, "desde_pct": float(x.desde_pct), "tasa_pct": float(x.tasa_pct)}
            for x in reglas.tramos],
        "comision_base_pago": reglas.base_pago,
        "cumplimiento_base": reglas.cumplimiento_base,
        "comision_cargos_asesor": sorted(reglas.cargos),
        "comision_lineas": [
            {"linea": b.linea, "etiqueta": etiqueta_de(b.linea), "pct_meta": float(b.pct_meta), "bono": b.bono,
             "activo": b.activo} for b in reglas.bonos],
        "comision_bono_umbral_pct": float(reglas.umbral_bono_pct),
    }


def etiqueta_de(linea: str) -> str:
    return ETIQUETA_LINEA.get(linea, linea.capitalize())


def minimo_linea(presupuesto: int, umbral_pct: Decimal, pct_meta: Decimal) -> int:
    """Smallest sale of a line that earns its bonus for a budget: budget x threshold % x target %, in whole pesos
    (half up). It is the sale an asesor that JUST reaches the gate needs; the real rule compares against the
    actual total, never this number."""
    exacto = Decimal(presupuesto) * Decimal(umbral_pct) / 100 * Decimal(pct_meta) / 100
    return int(exacto.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def lineas_con_bono(reglas: ReglasComision) -> List[Dict[str, Any]]:
    """The ACTIVE bonus lines in config order (what the budget screen shows next to each asesor)."""
    return [
        {"linea": b.linea, "etiqueta": etiqueta_de(b.linea), "pct_meta": float(b.pct_meta), "bono": b.bono}
        for b in reglas.bonos if b.activo]


def minimos_de_presupuesto(reglas: ReglasComision, presupuesto: int) -> Dict[str, int]:
    """`{linea: minimum sale}` of the active lines for ONE budget (see `minimo_linea`)."""
    return {b.linea: minimo_linea(presupuesto, reglas.umbral_bono_pct, b.pct_meta) for b in reglas.bonos if b.activo}


def bonos_de_asesor(
    total_venta: Decimal, presupuesto: int, ventas_por_linea: Dict[str, Decimal], venta_tecnired: Decimal,
    lineas: Iterable[LineaBono], umbral_pct: Decimal,
) -> Dict[str, Any]:
    """`{gate: {umbral, cumple}, bonos: [...], bono_total}` of ONE asesor. Both comparisons avoid dividing
    (`venta * 100 >= umbral * presupuesto`, `linea * 100 >= pct * total`) so a boundary is exact. `cumple` says
    the line was met whatever the gate or switch; `paga`/`bono_pagado` need the gate, an active line and `cumple`.
    A line without sales is never met (no total, no bonus for 0 >= 0)."""
    total = Decimal(total_venta)
    cumple_gate = bool(presupuesto) and total * 100 >= Decimal(umbral_pct) * presupuesto
    filas = []
    for b in lineas:
        venta = Decimal(venta_tecnired) if b.linea == TECNIRED else Decimal(ventas_por_linea.get(b.linea, 0))
        cumple = venta > 0 and venta * 100 >= b.pct_meta * total
        paga = cumple_gate and b.activo and cumple
        filas.append({
            "linea": b.linea, "etiqueta": etiqueta_de(b.linea), "venta": _dinero(venta),
            "pct_real": float(venta / total) if total > 0 else None, "pct_meta": float(b.pct_meta),
            "bono": b.bono, "cumple": cumple, "paga": paga, "activo": b.activo,
            "bono_pagado": b.bono if paga else 0,
        })
    return {
        "gate": {"umbral": float(umbral_pct), "cumple": cumple_gate}, "bonos": filas,
        "bono_total": sum(f["bono_pagado"] for f in filas),
    }


def tramo_de(venta: Decimal, presupuesto: int, tramos: Iterable[Tramo]) -> Optional[Tramo]:
    """Highest tier whose `desde_pct` is reached, compared WITHOUT dividing (`venta * 100 >= desde * presupuesto`)
    so a boundary like 105.0 % is exact. None with no budget or below every tier."""
    if not presupuesto:
        return None
    avance = Decimal(venta) * 100
    alcanzados = [x for x in tramos if avance >= x.desde_pct * presupuesto]
    return max(alcanzados, key=lambda x: x.desde_pct) if alcanzados else None


def _siguiente(actual: Optional[Tramo], tramos: Iterable[Tramo]) -> Optional[Tramo]:
    umbral = actual.desde_pct if actual else Decimal(-1)
    mayores = [x for x in tramos if x.desde_pct > umbral]
    return min(mayores, key=lambda x: x.desde_pct) if mayores else None


def _dinero(valor: Decimal) -> float:
    return float(round(valor, 2))


def _fila(
    cedula: str, nombre: Optional[str], linea: pres.LineaPresupuesto, venta_cump: Decimal, venta_com: Decimal,
    reglas: ReglasComision, tienda: Optional[str], por_linea: Optional[Dict[str, Tuple[Decimal, Decimal]]] = None,
) -> Dict[str, Any]:
    presupuesto = linea.monto
    actual = tramo_de(venta_cump, presupuesto, reglas.tramos)
    tasa = actual.tasa_pct if actual else Decimal(0)
    comision = venta_com * tasa / 100
    sig = _siguiente(actual, reglas.tramos)
    falta = max(Decimal(presupuesto) * sig.desde_pct / 100 - venta_cump, Decimal(0)) if sig else None
    base = 0 if reglas.cumplimiento_base == t.CUMPLIMIENTO_CON_HMCL else 1
    por_linea = por_linea or {}
    bonos = bonos_de_asesor(
        venta_cump, presupuesto, {k: v[base] for k, v in por_linea.items()},
        por_linea.get(TECNIRED, (Decimal(0), Decimal(0)))[base], reglas.bonos, reglas.umbral_bono_pct)
    return {
        "cedula": cedula, "nombre": nombre, "sucursal_id": str(linea.sucursal_id), "tienda": tienda,
        "gate": bonos["gate"], "bonos": bonos["bonos"], "bono_total": bonos["bono_total"],
        "total_a_pagar": _dinero(comision + bonos["bono_total"]),
        "presupuesto": presupuesto, "venta_cumplimiento": _dinero(venta_cump), "venta_comision": _dinero(venta_com),
        "cumplimiento_pct": float(venta_cump / Decimal(presupuesto)) if presupuesto else None,
        "tramo": actual.nombre if actual else None, "tasa_pct": float(tasa), "comision": _dinero(comision),
        "sig": None if sig is None else {
            "nombre": sig.nombre, "desde_pct": float(sig.desde_pct), "tasa_pct": float(sig.tasa_pct),
            "falta": _dinero(falta), "gana": _dinero((venta_com + falta) * sig.tasa_pct / 100 - comision),
        },
    }


def _cargo_permitido(cargos: Optional[Iterable[str]], reglas: ReglasComision) -> Optional[bool]:
    """None when the cargo is unknown, else whether any of the person's cargos earns commission."""
    normalizados = {t.texto_de_linea(c) for c in (cargos or ()) if c and c.strip()}
    if not normalizados:
        return None
    return bool(normalizados & reglas.cargos)


def liquidar_mes(
    ventas: Dict[str, Tuple[Decimal, Decimal]], presupuestos: Dict[str, pres.LineaPresupuesto],
    nombres: Dict[str, str], cargos: Dict[str, Iterable[str]], tiendas: Dict[str, str], reglas: ReglasComision,
    ventas_por_linea: Optional[Dict[str, Dict[str, Tuple[Decimal, Decimal]]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """`(asesores, advertencias)` of one month. `ventas` is `{cedula: (venta con HMCL, venta sin HMCL)}`,
    `presupuestos` the month's `{cedula: linea}`. Only commissioned cargos are rated; a person
    with a budget or sales whose cargo is unknown is left out and counted in `cargo_desconocido`.
    `ventas_por_linea` is `{cedula: {linea | TECNIRED: (venta con HMCL, venta sin HMCL)}}` of the month."""
    asesores: List[Dict[str, Any]] = []
    sin_presupuesto: List[Dict[str, Any]] = []
    desconocido = 0
    for cedula in sorted(set(ventas) | set(presupuestos)):
        permitido = _cargo_permitido(cargos.get(cedula), reglas)
        if permitido is None:
            desconocido += 1
            continue
        if not permitido:
            continue
        con, sin = ventas.get(cedula, (Decimal(0), Decimal(0)))
        v_cump = con if reglas.cumplimiento_base == t.CUMPLIMIENTO_CON_HMCL else sin
        v_com = con if reglas.base_pago == t.CUMPLIMIENTO_CON_HMCL else sin
        linea = presupuestos.get(cedula)
        if linea is None:
            sin_presupuesto.append({"cedula": cedula, "nombre": nombres.get(cedula), "venta": _dinero(v_com)})
            continue
        tienda = tiendas.get(str(linea.sucursal_id))
        fila = _fila(
            cedula, nombres.get(cedula), linea, v_cump, v_com, reglas, tienda, (ventas_por_linea or {}).get(cedula))
        fila["cargo"] = " / ".join(sorted(set(cargos[cedula])))
        asesores.append(fila)
    advertencias = {"sin_presupuesto": sin_presupuesto, "cargo_desconocido": desconocido}
    return asesores, advertencias


def _por_linea(asesores: List[Dict[str, Any]], reglas: Optional[ReglasComision]) -> List[Dict[str, Any]]:
    """Per bonus line: asesores that earn it (met + gate + active) and the amount. With `reglas` every configured
    line is listed in config order; without them, the lines found in the asesores."""
    orden = [b.linea for b in reglas.bonos] if reglas else list(dict.fromkeys(
        b["linea"] for a in asesores for b in a["bonos"]))
    filas = []
    for linea in orden:
        pagos = [b for a in asesores for b in a["bonos"] if b["linea"] == linea and b["paga"]]
        filas.append({
            "linea": linea, "etiqueta": etiqueta_de(linea), "ganadores": len(pagos),
            "monto": float(sum(b["bono_pagado"] for b in pagos))})
    return filas


def resumen_de(asesores: List[Dict[str, Any]], reglas: Optional[ReglasComision] = None) -> Dict[str, Any]:
    """Totals of the month: asesores rated, total/average/biggest commission, commission as a fraction of the
    paid base, the bonuses (total and per line) and the amount to pay (commission + bonuses)."""
    total = sum((Decimal(str(a["comision"])) for a in asesores), Decimal(0))
    base = sum((Decimal(str(a["venta_comision"])) for a in asesores), Decimal(0))
    mayor = max(asesores, key=lambda a: (a["comision"], a["cedula"]), default=None)
    bonos = sum((Decimal(a["bono_total"]) for a in asesores), Decimal(0))
    return {
        "asesores": len(asesores), "comision_total": _dinero(total), "venta_base": _dinero(base),
        "comision_promedio": _dinero(total / len(asesores)) if asesores else 0.0,
        "comision_mayor": None if mayor is None else {
            "cedula": mayor["cedula"], "nombre": mayor["nombre"], "comision": mayor["comision"]},
        "comision_pct_venta": float(total / base) if base else None,
        "bonos_total": float(bonos), "total_a_pagar": _dinero(total + bonos),
        "por_linea": _por_linea(asesores, reglas),
    }


def tramos_con_conteo(asesores: List[Dict[str, Any]], reglas: ReglasComision) -> List[Dict[str, Any]]:
    """The configured tiers (ascending) with how many asesores fell in each; `hasta_pct` is the next tier's start."""
    filas = []
    for i, x in enumerate(reglas.tramos):
        siguiente = reglas.tramos[i + 1].desde_pct if i + 1 < len(reglas.tramos) else None
        filas.append({
            "nombre": x.nombre, "desde_pct": float(x.desde_pct), "tasa_pct": float(x.tasa_pct),
            "hasta_pct": None if siguiente is None else float(siguiente),
            "asesores": sum(1 for a in asesores if a["tramo"] == x.nombre),
        })
    return filas


def cerca_de_subir(asesores: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Asesores within `MARGEN_CERCA_PTS` points of the next tier that sold something, smallest gap first.
    `falta` is the sale (cumplimiento base) still missing and `gana` the extra commission it would bring."""
    filas = []
    for a in asesores:
        sig = a["sig"]
        if sig is None or a["venta_cumplimiento"] <= 0 or a["cumplimiento_pct"] is None:
            continue
        brecha = sig["desde_pct"] - a["cumplimiento_pct"] * 100
        if brecha <= MARGEN_CERCA_PTS:
            filas.append({
                "cedula": a["cedula"], "nombre": a["nombre"], "tienda": a["tienda"], "tramo": a["tramo"],
                "cumplimiento_pct": a["cumplimiento_pct"], "siguiente": sig["nombre"],
                "brecha_pts": round(brecha, 2), "falta": sig["falta"], "gana": sig["gana"],
            })
    return sorted(filas, key=lambda f: (f["brecha_pts"], f["cedula"]))


def ventas_por_cedula_mes(
    cubo: Iterable[t.FilaCubo], lineas: Iterable[str],
) -> Tuple[Dict[Tuple[str, str], Tuple[Decimal, Decimal]], Dict[str, str], Dict[str, Dict[str, Decimal]]]:
    """`({(cedula, mes): (venta con HMCL, venta sin HMCL)}, {cedula: clave}, {mes: {clave: venta con HMCL}})`.
    Both bases are accumulated so each month can pick its own `cumplimiento_base` and `comision_base_pago`;
    the last map is the sales of people without a valid cedula (they cannot match a budget)."""
    lineas = tuple(lineas)
    con: Dict[Tuple[str, str], Decimal] = defaultdict(Decimal)
    sin: Dict[Tuple[str, str], Decimal] = defaultdict(Decimal)
    claves: Dict[str, str] = {}
    sin_cedula: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for f in cubo:
        if not t.es_clave_persona(f.clave) or f.linea is None or f.linea not in lineas:
            continue
        try:
            cedula = limpiar_cedula(f.clave[len(t.PREFIJO_PERSONA):])
        except ValueError:
            sin_cedula[f.mes][f.clave] += f.venta
            continue
        con[(cedula, f.mes)] += f.venta
        if not f.es_hmcl:
            sin[(cedula, f.mes)] += f.venta
        claves.setdefault(cedula, f.clave)
    ventas = {k: (v, sin.get(k, Decimal(0))) for k, v in con.items()}
    return ventas, claves, {m: dict(v) for m, v in sin_cedula.items()}


def ventas_por_linea_cedula_mes(
    cubo: Iterable[t.FilaCubo], lineas: Iterable[str],
) -> Dict[Tuple[str, str], Dict[str, Tuple[Decimal, Decimal]]]:
    """`{(cedula, mes): {linea | TECNIRED: (venta con HMCL, venta sin HMCL)}}` with the same filter as
    `ventas_por_cedula_mes` (people with a valid cedula, only the configured lines), so the line sales add up to
    the same total the cumplimiento uses. TECNIRED is the sale to Tecnired customers across every line."""
    lineas = tuple(lineas)
    acumulado: Dict[Tuple[str, str], Dict[str, List[Decimal]]] = defaultdict(dict)
    for f in cubo:
        if not t.es_clave_persona(f.clave) or f.linea is None or f.linea not in lineas:
            continue
        try:
            cedula = limpiar_cedula(f.clave[len(t.PREFIJO_PERSONA):])
        except ValueError:
            continue
        claves = [f.linea] + ([TECNIRED] if f.es_tecnired else [])
        for clave in claves:
            con_sin = acumulado[(cedula, f.mes)].setdefault(clave, [Decimal(0), Decimal(0)])
            con_sin[0] += f.venta
            if not f.es_hmcl:
                con_sin[1] += f.venta
    return {
        cedula_mes: {linea: (v[0], v[1]) for linea, v in por_linea.items()}
        for cedula_mes, por_linea in acumulado.items()}
