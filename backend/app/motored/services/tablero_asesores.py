"""
Tablero de asesores (feature motored-tablero-asesores, T4): calculos PUROS.

La consulta (`tablero_asesores_consultas.py`) hace todo el trabajo pesado con
GROUP BY en la base y devuelve pocas filas agregadas: un "cubo" por
(fila del tablero, mes, linea, banderas), mas los conteos que no se pueden sumar
(facturas, clientes distintos). Este modulo no toca la base: reparte esas filas
en las filas del tablero y calcula cada indicador.

Convenciones del resultado:
- Dinero en pesos como `float` redondeado a 2 decimales.
- Todo `pct_*`, `mix` e `indice` es una FRACCION (0.25 = 25 %); el frontend la
  multiplica por 100. Un cociente cuyo denominador es 0 es `None`, nunca 0.
- Solo cuentan las 7 lineas comerciales de `LINEAS`; la venta de cualquier otra
  (nula, NO APLICA, ...) se excluye de todo indicador y se informa aparte.
"""
import datetime
import unicodedata
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple

LINEAS: Tuple[str, ...] = (
    "REPUESTOS", "ACCESORIOS", "LLANTAS", "LUBRICANTES", "BATERIAS", "GPS", "CASCOS",
)

# NITs de la linea HMCL (se comparan contra `cliente_factura` normalizado).
HMCL_NITS: Tuple[str, ...] = ("900723988", "900883086")

HMCL_INCLUIR, HMCL_EXCLUIR, HMCL_SOLO = "incluir", "excluir", "solo"
MODOS_HMCL = (HMCL_INCLUIR, HMCL_EXCLUIR, HMCL_SOLO)

MAX_MESES = 12
MESES_MINIMOS_TENDENCIA = 6

TIPO_PERSONA = "PERSONA"
GRUPO_COMERCIALES = "COMERCIALES"
GRUPO_OTROS = "OTROS"
GRUPO_RESTO = "RESTO"
CLAVE_TOTAL = "TOTAL"
PREFIJO_PERSONA = "P:"

# UNICO lugar donde un cargo decide como se agrupa (regla de la hoja MAESTRO
# PERSONAS del Excel). Cargo ausente de este mapa = "otros roles"; quien no esta
# en el maestro (o esta inactivo) es "resto de compania". Cuando esto sea
# configurable en la app, solo cambia esta constante.
GRUPO_POR_CARGO: Dict[str, str] = {
    "ASESOR DE REPUESTOS": TIPO_PERSONA,
    "ASESOR DE REPUESTOS SUPERNUMERARIO": TIPO_PERSONA,
    "ASESOR COMERCIAL DE SERVICIO POSVENTA": GRUPO_COMERCIALES,
}

TILDES_ORIGEN = "ÁÉÍÓÚÜáéíóúü"
TILDES_DESTINO = "AEIOUUaeiouu"


class FilaCubo(NamedTuple):
    """Venta agregada de UNA fila del tablero en un mes y una linea. `linea`
    es None cuando la linea comercial no es una de las 7 (se excluye)."""
    clave: str
    mes: str
    linea: Optional[str]
    es_hmcl: bool
    es_tecnired: bool
    es_mostrador: bool
    con_costo: bool
    venta: Decimal
    bruto: Decimal
    descuentos: Decimal
    cantidad: Decimal
    lineas: int
    costo: Decimal


class FilaFacturas(NamedTuple):
    clave: str
    facturas: int
    multilinea: int
    con_linea: Tuple[int, ...]  # facturas con al menos una linea de cada una de LINEAS


class FilaClientes(NamedTuple):
    clave: str
    clientes: int
    venta_top5: Decimal


class FilaPersona(NamedTuple):
    clave: str
    personas: int
    nombre: Optional[str]
    cargo: Optional[str]
    punto_venta: Optional[str]
    cargos: Tuple[str, ...] = ()  # todos los cargos de los nombres del ERP de la persona


class FilaVendedorVenta(NamedTuple):
    """Venta (de las 7 lineas) de UN nombre del ERP dentro de una fila del
    tablero, con los datos del maestro de ese nombre. `identidad` dice quien es
    la persona: su cedula o, sin cedula, el propio vendedor."""
    clave: str
    identidad: str
    nombre: Optional[str]
    cargo: Optional[str]
    punto_venta: Optional[str]
    venta: Decimal


# --- Normalizacion y claves ----------------------------------------------------------------


def normalizar_linea(texto: Optional[str]) -> Optional[str]:
    """Recorta, pasa a mayusculas y quita tildes; devuelve la linea solo si es
    una de las 7 (cualquier otra cosa, incluida la vacia, es None)."""
    if not texto:
        return None
    descompuesto = unicodedata.normalize("NFD", texto.strip())
    limpio = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").upper()
    return limpio if limpio in LINEAS else None


def grupo_de_cargo(cargo: str) -> str:
    """Grupo de una persona registrada y activa segun su cargo."""
    return GRUPO_POR_CARGO.get(cargo, GRUPO_OTROS)


def clave_persona(vendedor_id: Any) -> str:
    return f"{PREFIJO_PERSONA}{vendedor_id}"


def es_clave_persona(clave: str) -> bool:
    return clave.startswith(PREFIJO_PERSONA)


def identidad_de_vendedor(cedula: Optional[str], respaldo: str) -> str:
    """Una persona puede estar en el maestro con varios nombres del ERP (una fila
    por nombre) y todos comparten su cedula: ESA es su identidad. Una fila sin
    cedula (legado) es su propia persona (`respaldo`: su id o su nombre)."""
    limpia = (cedula or "").strip()
    return limpia or respaldo


def construir_personas(filas: Iterable[FilaVendedorVenta]) -> List[FilaPersona]:
    """Quienes hay detras de cada fila del tablero. Una fila de persona junta
    todos los nombres del ERP con la misma cedula: muestra el nombre (con su
    cargo y punto de venta) de la que mas vendio -- a igual venta, el primero
    alfabeticamente -- y lista los cargos de todas. Una fila de grupo cuenta
    personas distintas, no nombres."""
    por_clave: Dict[str, List[FilaVendedorVenta]] = defaultdict(list)
    for f in filas:
        por_clave[f.clave].append(f)

    resultado: List[FilaPersona] = []
    for clave, miembros in por_clave.items():
        if es_clave_persona(clave):
            principal = min(miembros, key=lambda m: (-m.venta, (m.nombre or "").upper(), m.nombre or ""))
            cargos = tuple(sorted({m.cargo for m in miembros if m.cargo}))
            resultado.append(FilaPersona(
                clave, 1, principal.nombre, principal.cargo, principal.punto_venta, cargos))
        else:
            resultado.append(FilaPersona(clave, len({m.identidad for m in miembros}), None, None, None))
    return resultado


def nombre_de_grupo(clave: str, personas: int) -> str:
    plural = personas != 1
    if clave == GRUPO_COMERCIALES:
        return f"ASESORES COMERCIALES DE SERVICIO POSVENTA ({personas} {'personas' if plural else 'persona'})"
    if clave == GRUPO_OTROS:
        return f"OTROS ROLES POSVENTA ({personas} {'personas' if plural else 'persona'})"
    return f"RESTO COMPAÑÍA ({personas} {'vendedores' if plural else 'vendedor'})"


# --- Rango de meses --------------------------------------------------------------------------


def _partir_mes(texto: str) -> Tuple[int, int]:
    try:
        anio, mes = texto.split("-")
        resultado = int(anio), int(mes)
    except (AttributeError, ValueError):
        raise ValueError(f"Mes inválido: '{texto}' (use AAAA-MM).")
    if len(anio) != 4 or not 1 <= resultado[1] <= 12:
        raise ValueError(f"Mes inválido: '{texto}' (use AAAA-MM).")
    return resultado


def meses_del_rango(desde: str, hasta: str) -> List[str]:
    anio, mes = _partir_mes(desde)
    anio_fin, mes_fin = _partir_mes(hasta)
    meses: List[str] = []
    while (anio, mes) <= (anio_fin, mes_fin):
        meses.append(f"{anio:04d}-{mes:02d}")
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return meses


def validar_rango(desde: str, hasta: str) -> List[str]:
    """Meses del rango, o `ValueError` (mensaje para el usuario) si `desde` es
    posterior a `hasta` o el rango pasa de `MAX_MESES`."""
    meses = meses_del_rango(desde, hasta)
    if not meses:
        raise ValueError("El mes 'desde' no puede ser posterior al mes 'hasta'.")
    if len(meses) > MAX_MESES:
        raise ValueError(f"El rango no puede pasar de {MAX_MESES} meses.")
    return meses


def limites_de_fecha(desde: str, hasta: str) -> Tuple[datetime.date, datetime.date]:
    """`[inicio, fin)`: primer dia de `desde` y primer dia del mes siguiente a `hasta`."""
    anio, mes = _partir_mes(desde)
    anio_fin, mes_fin = _partir_mes(hasta)
    siguiente = (anio_fin + 1, 1) if mes_fin == 12 else (anio_fin, mes_fin + 1)
    return datetime.date(anio, mes, 1), datetime.date(siguiente[0], siguiente[1], 1)


# --- Razones, tendencia y ranking ----------------------------------------------------------------


def _dinero(valor: Decimal) -> float:
    return float(round(valor, 2))


def ratio(numerador: Optional[Decimal], denominador: Optional[Decimal]) -> Optional[float]:
    """`numerador / denominador` o None si el denominador es 0 o falta."""
    if not denominador:
        return None
    return float(Decimal(numerador or 0) / Decimal(denominador))


TENDENCIA_VACIA: Dict[str, Optional[float]] = {
    "ultimos_3m": None, "previos_3m": None, "diferencia": None, "pct": None,
}


def variacion_3m(venta_por_mes: Dict[str, Decimal], meses: List[str]) -> Dict[str, Optional[float]]:
    """Venta de los ultimos 3 meses del rango contra los 3 anteriores. Solo con
    un rango de al menos 6 meses (como el `SI(hasta-5 < desde; "")` del Excel);
    un mes sin venta cuenta como 0."""
    if len(meses) < MESES_MINIMOS_TENDENCIA:
        return dict(TENDENCIA_VACIA)
    ultimos = sum((venta_por_mes.get(m, Decimal(0)) for m in meses[-3:]), Decimal(0))
    previos = sum((venta_por_mes.get(m, Decimal(0)) for m in meses[-6:-3]), Decimal(0))
    pct = ratio(ultimos, previos)
    return {
        "ultimos_3m": _dinero(ultimos),
        "previos_3m": _dinero(previos),
        "diferencia": _dinero(ultimos - previos),
        "pct": None if pct is None else pct - 1,
    }


def rankear(valores: Dict[str, Decimal]) -> Dict[str, int]:
    """Posicion 1 = mayor valor. Los empates comparten posicion y la siguiente
    se salta (igual que RANK de Excel)."""
    ordenados = sorted(valores.values(), reverse=True)
    return {clave: ordenados.index(valor) + 1 for clave, valor in valores.items()}


# --- Acumulado por fila ------------------------------------------------------------------------


class _Acumulado:
    def __init__(self) -> None:
        self.venta_por_mes: Dict[str, Decimal] = defaultdict(Decimal)
        self.venta_por_linea: Dict[str, Decimal] = defaultdict(Decimal)
        self.descuento_por_mes: Dict[str, Decimal] = defaultdict(Decimal)
        self.hmcl = self.tecnired = self.mostrador = Decimal(0)
        self.con_costo = self.costo = self.bruto = self.cantidad = Decimal(0)
        self.lineas = 0

    def sumar(self, f: FilaCubo) -> None:
        self.venta_por_mes[f.mes] += f.venta
        self.venta_por_linea[f.linea] += f.venta
        self.descuento_por_mes[f.mes] += f.descuentos
        if f.es_hmcl:
            self.hmcl += f.venta
        if f.es_tecnired:
            self.tecnired += f.venta
        if f.es_mostrador:
            self.mostrador += f.venta
        if f.con_costo:
            self.con_costo += f.venta
            self.costo += f.costo
        self.bruto += f.bruto
        self.cantidad += f.cantidad
        self.lineas += f.lineas

    @property
    def venta(self) -> Decimal:
        return sum(self.venta_por_mes.values(), Decimal(0))

    @property
    def descuentos(self) -> Decimal:
        return sum(self.descuento_por_mes.values(), Decimal(0))


def _indicadores(
    acum: _Acumulado,
    facturas: Optional[FilaFacturas],
    clientes: Optional[FilaClientes],
    meses: List[str],
) -> Dict[str, Any]:
    venta = acum.venta
    n_facturas = facturas.facturas if facturas else 0
    descuentos = acum.descuentos
    mes_mayor = None
    if descuentos > 0:
        mes_mayor = min(
            (m for m, d in acum.descuento_por_mes.items() if d > 0),
            key=lambda m: (-acum.descuento_por_mes[m], m),
        )
    con_linea = facturas.con_linea if facturas else (0,) * len(LINEAS)
    return {
        "venta": {
            "total": _dinero(venta),
            "hmcl": _dinero(acum.hmcl),
            "sin_hmcl": _dinero(venta - acum.hmcl),
            "pct_hmcl": ratio(acum.hmcl, venta),
            "por_mes": {m: _dinero(acum.venta_por_mes.get(m, Decimal(0))) for m in meses},
            "por_linea": {linea: _dinero(acum.venta_por_linea.get(linea, Decimal(0))) for linea in LINEAS},
            "mix": {linea: ratio(acum.venta_por_linea.get(linea, Decimal(0)), venta) for linea in LINEAS},
        },
        "costo": {
            "costo_venta": _dinero(acum.costo),
            "venta_con_costo": _dinero(acum.con_costo),
            "utilidad_bruta": _dinero(acum.con_costo - acum.costo),
            "pct_margen": ratio(acum.con_costo - acum.costo, acum.con_costo),
            "pct_venta_con_costo": ratio(acum.con_costo, venta),
        },
        "tendencia": variacion_3m(acum.venta_por_mes, meses),
        "facturas": {
            "facturas": n_facturas,
            "ticket_promedio": ratio(venta, Decimal(n_facturas)),
            "unidades": _dinero(acum.cantidad),
            "items_por_factura": ratio(Decimal(acum.lineas), Decimal(n_facturas)),
            "pct_con_linea": {linea: ratio(Decimal(n), Decimal(n_facturas)) for linea, n in zip(LINEAS, con_linea)},
            "pct_multilinea": ratio(Decimal(facturas.multilinea if facturas else 0), Decimal(n_facturas)),
        },
        "descuentos": {
            "total": _dinero(descuentos),
            "mes_mayor": mes_mayor,
            "pct_en_mes_mayor": ratio(acum.descuento_por_mes[mes_mayor], descuentos) if mes_mayor else None,
            "pct_descuento": ratio(descuentos, acum.bruto),
        },
        "clientes": {
            "pct_mostrador": ratio(acum.mostrador, venta),
            "venta_tecnired": _dinero(acum.tecnired),
            "pct_tecnired": ratio(acum.tecnired, venta),
            "clientes_unicos": clientes.clientes if clientes else 0,
            "pct_top5": ratio(clientes.venta_top5, venta) if clientes else None,
        },
        "ranking": None,
    }


def _por_clave(filas: Iterable[Any]) -> Dict[str, Any]:
    return {f.clave: f for f in filas}


def _orden_de_fila(fila: Dict[str, Any]) -> Tuple:
    if fila["tipo"] == "PERSONA":
        return (0, (fila["punto_venta"] or "").upper(), fila["nombre"].upper())
    return (1, ORDEN_GRUPOS.index(fila["clave"]), "")


ORDEN_GRUPOS = (GRUPO_COMERCIALES, GRUPO_OTROS, GRUPO_RESTO)


def _fila_total(acum, facturas, clientes, personas, meses) -> Dict[str, Any]:
    fila = {"clave": CLAVE_TOTAL, "tipo": "TOTAL", "nombre": "TOTAL", "cargo": None,
            "punto_venta": None, "cargos": [], "cargo_conflicto": False, "personas": personas}
    fila.update(_indicadores(acum, facturas, clientes, meses))
    return fila


def construir_tablero(
    cubo: Iterable[FilaCubo],
    facturas: Iterable[FilaFacturas],
    clientes: Iterable[FilaClientes],
    personas: Iterable[FilaPersona],
    meses: List[str],
) -> Dict[str, Any]:
    """Filas del tablero (personas, grupos), fila TOTAL y la venta excluida por
    no tener linea comercial reconocida."""
    acumulados: Dict[str, _Acumulado] = {CLAVE_TOTAL: _Acumulado()}
    sin_linea = Decimal(0)
    for f in cubo:
        if f.linea is None:
            sin_linea += f.venta
            continue
        acumulados.setdefault(f.clave, _Acumulado()).sumar(f)
        acumulados[CLAVE_TOTAL].sumar(f)

    facturas_por = _por_clave(facturas)
    clientes_por = _por_clave(clientes)
    personas_por = _por_clave(personas)

    filas: List[Dict[str, Any]] = []
    for clave, acum in acumulados.items():
        if clave == CLAVE_TOTAL:
            continue
        info = personas_por.get(clave)
        fila: Dict[str, Any] = {"clave": clave}
        if es_clave_persona(clave):
            fila.update(
                tipo="PERSONA",
                nombre=(info.nombre if info and info.nombre else clave),
                cargo=info.cargo if info else None,
                punto_venta=info.punto_venta if info else None,
                cargos=list(info.cargos) if info else [],
                cargo_conflicto=bool(info and len(info.cargos) > 1),
                personas=1,
            )
        else:
            n = info.personas if info else 0
            fila.update(
                tipo="GRUPO", nombre=nombre_de_grupo(clave, n), cargo=None, punto_venta=None,
                cargos=[], cargo_conflicto=False, personas=n,
            )
        fila.update(_indicadores(acum, facturas_por.get(clave), clientes_por.get(clave), meses))
        filas.append(fila)
    filas.sort(key=_orden_de_fila)

    _agregar_ranking([f for f in filas if f["tipo"] == "PERSONA"])

    venta_total = acumulados[CLAVE_TOTAL].venta
    return {
        "filas": filas,
        "total": _fila_total(
            acumulados[CLAVE_TOTAL], facturas_por.get(CLAVE_TOTAL), clientes_por.get(CLAVE_TOTAL),
            sum(f["personas"] for f in filas), meses),
        "venta_sin_linea": _dinero(sin_linea),
        "pct_venta_sin_linea": ratio(sin_linea, sin_linea + venta_total),
    }


_RANKINGS_POR_LINEA = {"rank_repuestos": "REPUESTOS", "rank_accesorios": "ACCESORIOS", "rank_lubricantes": "LUBRICANTES"}


def _agregar_ranking(personas: List[Dict[str, Any]]) -> None:
    """Indice contra el promedio y posiciones, solo entre las filas de persona."""
    if not personas:
        return
    ventas = {f["clave"]: Decimal(str(f["venta"]["total"])) for f in personas}
    promedio = sum(ventas.values(), Decimal(0)) / len(ventas)
    rank_total = rankear(ventas)
    rank_linea = {
        campo: rankear({f["clave"]: Decimal(str(f["venta"]["por_linea"][linea])) for f in personas})
        for campo, linea in _RANKINGS_POR_LINEA.items()
    }
    for f in personas:
        f["ranking"] = {
            "indice_vs_promedio": ratio(ventas[f["clave"]], promedio),
            "rank_total": rank_total[f["clave"]],
            **{campo: rank[f["clave"]] for campo, rank in rank_linea.items()},
        }
