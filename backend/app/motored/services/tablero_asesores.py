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
import logging
import math
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Tuple

logger = logging.getLogger(__name__)

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
# What a cube row is keyed by: the asesor/group of the tablero, the store of the
# sale (`VentaDetalle.sucursal_id`) or nothing (one TOTAL row for the network).
DIM_ASESOR, DIM_SUCURSAL, DIM_TOTAL = "asesor", "sucursal", "total"
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

CUMPLIMIENTO_CON_HMCL, CUMPLIMIENTO_SIN_HMCL = "con_hmcl", "sin_hmcl"
SEMAFORO_POR_DEFECTO: Dict[str, float] = {"verde_desde": 90, "ambar_desde": 70}


class Reglas(NamedTuple):
    """Reglas de negocio del tablero que vienen de Configuracion (vigentes en
    el ultimo mes elegido). Los valores por defecto (`REGLAS_POR_DEFECTO`) son
    las constantes historicas de este modulo."""
    lineas: Tuple[str, ...] = LINEAS
    hmcl_nits: Tuple[str, ...] = HMCL_NITS
    grupo_por_cargo: Dict[str, str] = GRUPO_POR_CARGO
    semaforo: Dict[str, float] = SEMAFORO_POR_DEFECTO
    cumplimiento_base: str = CUMPLIMIENTO_CON_HMCL


REGLAS_POR_DEFECTO = Reglas()

GRUPOS_VALIDOS = (TIPO_PERSONA, GRUPO_COMERCIALES)
BASES_CUMPLIMIENTO = (CUMPLIMIENTO_CON_HMCL, CUMPLIMIENTO_SIN_HMCL)


def texto_de_linea(texto: str) -> str:
    """Recorta, pasa a mayusculas y quita tildes (la misma regla que la CTE de
    lineas aplica a `referencia.linea_comercial`)."""
    descompuesto = unicodedata.normalize("NFD", texto.strip())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").upper()


def _lineas_validas(valor: Any) -> Optional[Tuple[str, ...]]:
    if not isinstance(valor, (list, tuple)) or not valor or not all(isinstance(x, str) for x in valor):
        return None
    lineas = tuple(dict.fromkeys(texto_de_linea(x) for x in valor))
    return lineas if all(lineas) else None


def _nits_validos(valor: Any) -> Optional[Tuple[str, ...]]:
    if not isinstance(valor, (list, tuple)) or not all(isinstance(x, str) and x.strip() for x in valor):
        return None
    return tuple(x.strip() for x in valor)


def _grupos_validos(valor: Any) -> Optional[Dict[str, str]]:
    """Un grupo que no sea PERSONA o COMERCIALES (nunca debe llegar a SQL como
    literal) cuenta como OTROS, el grupo de los cargos sin regla."""
    if not isinstance(valor, dict) or not all(isinstance(c, str) and isinstance(g, str) for c, g in valor.items()):
        return None
    return {c: (g if g in GRUPOS_VALIDOS else GRUPO_OTROS) for c, g in valor.items()}


def _numero_de_corte(valor: Any) -> Optional[float]:
    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _semaforo_valido(valor: Any) -> Optional[Dict[str, float]]:
    if not isinstance(valor, dict):
        return None
    verde, ambar = _numero_de_corte(valor.get("verde_desde")), _numero_de_corte(valor.get("ambar_desde"))
    if verde is None or ambar is None or ambar >= verde:
        return None
    return {"verde_desde": verde, "ambar_desde": ambar}


def _base_valida(valor: Any) -> Optional[str]:
    return valor if valor in BASES_CUMPLIMIENTO else None


def reglas_desde_valores(valores: Dict[str, Any]) -> Reglas:
    """`Reglas` desde los valores leidos de Configuracion. Cada clave se revisa
    por separado: la que tenga una forma invalida (tipo, vacia, grupo o base
    desconocidos) vuelve a su valor por defecto y se avisa en el log; las demas
    se conservan. Las lineas se normalizan como las de la referencia."""
    defecto = REGLAS_POR_DEFECTO

    def tomar(clave: str, validar, respaldo):
        resultado = validar(valores.get(clave))
        if resultado is None:
            logger.warning("tablero: el valor de Configuración %s no tiene la forma esperada (%r); "
                           "se usa el valor por defecto", clave, valores.get(clave))
            return respaldo
        return resultado

    return Reglas(
        lineas=tomar("lineas_comerciales", _lineas_validas, defecto.lineas),
        hmcl_nits=tomar("hmcl_nits", _nits_validos, defecto.hmcl_nits),
        grupo_por_cargo=tomar("grupo_por_cargo", _grupos_validos, defecto.grupo_por_cargo),
        semaforo=tomar("kpi_semaforo_cortes", _semaforo_valido, defecto.semaforo),
        cumplimiento_base=tomar("cumplimiento_base", _base_valida, defecto.cumplimiento_base),
    )


class Filtro(NamedTuple):
    """Todo lo que acota las consultas del tablero: los rangos de fechas
    `[inicio, fin)` (meses consecutivos ya fusionados), el modo HMCL, las
    sucursales de la venta (None = todas), las reglas de Configuracion y los
    meses elegidos (los `rangos` son solo su forma para SQL)."""
    rangos: Tuple[Tuple[datetime.date, datetime.date], ...]
    modo_hmcl: str = HMCL_INCLUIR
    sucursal_ids: Optional[FrozenSet[Any]] = None
    reglas: Reglas = REGLAS_POR_DEFECTO
    meses: Tuple[str, ...] = ()  # the selected months AAAA-MM, sorted


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
    costo_estimado: Decimal = Decimal(0)  # la parte de `costo` valorada con `precio_normal`


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


def normalizar_linea(texto: Optional[str], lineas: Iterable[str] = LINEAS) -> Optional[str]:
    """Recorta, pasa a mayusculas y quita tildes; devuelve la linea solo si es
    una de `lineas` (por defecto las 7; cualquier otra cosa, incluida la vacia,
    es None)."""
    if not texto:
        return None
    limpio = texto_de_linea(texto)
    return limpio if limpio in tuple(lineas) else None


def grupo_de_cargo(cargo: str, grupo_por_cargo: Dict[str, str] = GRUPO_POR_CARGO) -> str:
    """Grupo de una persona registrada y activa segun su cargo."""
    return grupo_por_cargo.get(cargo, GRUPO_OTROS)


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


_FORMATO_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validar_meses(meses: Iterable[str]) -> List[str]:
    """Lista de meses AAAA-MM sin repetidos y ordenada, o `ValueError` (mensaje
    para el usuario) si esta vacia, algun mes es invalido o pasa de `MAX_MESES`."""
    vistos = set()
    for texto in meses:
        if not isinstance(texto, str) or not _FORMATO_MES.match(texto.strip()):
            raise ValueError(f"Mes inválido: '{texto}' (use AAAA-MM).")
        vistos.add(texto.strip())
    if not vistos:
        raise ValueError("Elija al menos un mes.")
    if len(vistos) > MAX_MESES:
        raise ValueError(f"No se pueden elegir más de {MAX_MESES} meses.")
    return sorted(vistos)


def rangos_de_meses(meses: List[str]) -> List[Tuple[datetime.date, datetime.date]]:
    """Meses (ya validados y ordenados) a rangos `[inicio, fin)`: los meses
    consecutivos se funden en un solo rango, los demas quedan separados."""
    rangos: List[Tuple[datetime.date, datetime.date]] = []
    for mes in meses:
        inicio, fin = limites_de_fecha(mes, mes)
        if rangos and rangos[-1][1] == inicio:
            rangos[-1] = (rangos[-1][0], fin)
        else:
            rangos.append((inicio, fin))
    return rangos


def filtro_de_meses(
    meses: List[str],
    modo_hmcl: str = HMCL_INCLUIR,
    sucursal_ids: Optional[Iterable[Any]] = None,
    reglas: Reglas = REGLAS_POR_DEFECTO,
) -> Filtro:
    ids = frozenset(sucursal_ids) if sucursal_ids else None
    ordenados = sorted(set(meses))
    return Filtro(tuple(rangos_de_meses(ordenados)), modo_hmcl, ids, reglas, tuple(ordenados))


def filtrar_cubo_por_hmcl(cubo: Iterable[FilaCubo], modo_hmcl: str) -> List[FilaCubo]:
    """El cubo se consulta SIEMPRE con HMCL incluido (el cumplimiento necesita la
    venta con HMCL); el modo `solo`/`excluir` se aplica aqui con la bandera
    `es_hmcl` de cada fila, igual que el filtro SQL."""
    if modo_hmcl == HMCL_SOLO:
        return [f for f in cubo if f.es_hmcl]
    if modo_hmcl == HMCL_EXCLUIR:
        return [f for f in cubo if not f.es_hmcl]
    return list(cubo)


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


def mes_desplazado(mes: str, cantidad: int) -> str:
    """`mes` (AAAA-MM) movido `cantidad` meses de calendario (negativo = antes)."""
    anio, numero = _partir_mes(mes)
    indice = anio * 12 + (numero - 1) + cantidad
    return f"{indice // 12:04d}-{indice % 12 + 1:02d}"


CRECE, CAE, NUEVA = "crece", "cae", "nueva"
MESES_VENTANA_CRECIMIENTO = 6


def crecimiento_3m(
    venta_por_mes: Dict[str, Decimal], ultimo_mes: str, fecha_apertura: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """Crecimiento de una tienda con MESES DE CALENDARIO (como la hoja
    "VAR % 3M VS 3M" del Excel): los 3 meses que terminan en `ultimo_mes` contra
    los 3 anteriores, sin importar que otros meses se hayan elegido (por eso
    `venta_por_mes` viene de la ventana de 6 meses, no del cubo elegido).
    `clasificacion`: `nueva` si abrio dentro de esos 6 meses o no vendio nada en
    los 3 primeros; si no, `crece` (venta de los ultimos 3 > la de los previos)
    o `cae` (menor o igual)."""
    ultimos = sum((venta_por_mes.get(mes_desplazado(ultimo_mes, -i), Decimal(0)) for i in range(3)), Decimal(0))
    previos = sum((venta_por_mes.get(mes_desplazado(ultimo_mes, -i), Decimal(0)) for i in range(3, 6)), Decimal(0))
    inicio_ventana = datetime.date(*_partir_mes(mes_desplazado(ultimo_mes, -(MESES_VENTANA_CRECIMIENTO - 1))), 1)
    es_nueva = previos == 0 or (fecha_apertura is not None and fecha_apertura >= inicio_ventana)
    pct = ratio(ultimos, previos)
    return {
        "ultimos_3m": _dinero(ultimos),
        "previos_3m": _dinero(previos),
        "diferencia": _dinero(ultimos - previos),
        "pct": None if pct is None else pct - 1,
        "clasificacion": NUEVA if es_nueva else (CRECE if ultimos > previos else CAE),
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
        self.venta_por_mes_linea: Dict[Tuple[str, str], Decimal] = defaultdict(Decimal)
        self.tecnired_por_mes: Dict[str, Decimal] = defaultdict(Decimal)
        self.tecnired_por_linea: Dict[str, Decimal] = defaultdict(Decimal)
        self.descuento_por_mes: Dict[str, Decimal] = defaultdict(Decimal)
        self.hmcl = self.tecnired = self.mostrador = Decimal(0)
        self.con_costo = self.costo = self.costo_estimado = self.bruto = self.cantidad = Decimal(0)
        self.lineas = 0

    def sumar(self, f: FilaCubo) -> None:
        self.venta_por_mes[f.mes] += f.venta
        self.venta_por_linea[f.linea] += f.venta
        self.venta_por_mes_linea[(f.mes, f.linea)] += f.venta
        self.descuento_por_mes[f.mes] += f.descuentos
        if f.es_hmcl:
            self.hmcl += f.venta
        if f.es_tecnired:
            self.tecnired += f.venta
            self.tecnired_por_mes[f.mes] += f.venta
            self.tecnired_por_linea[f.linea] += f.venta
        if f.es_mostrador:
            self.mostrador += f.venta
        if f.con_costo:
            self.con_costo += f.venta
            self.costo += f.costo
            self.costo_estimado += f.costo_estimado
        self.bruto += f.bruto
        self.cantidad += f.cantidad
        self.lineas += f.lineas

    @property
    def venta(self) -> Decimal:
        return sum(self.venta_por_mes.values(), Decimal(0))

    @property
    def descuentos(self) -> Decimal:
        return sum(self.descuento_por_mes.values(), Decimal(0))


def _bloque_venta(acum: _Acumulado, meses: List[str], lineas: Tuple[str, ...]) -> Dict[str, Any]:
    venta, cero = acum.venta, Decimal(0)
    return {
        "total": _dinero(venta),
        "hmcl": _dinero(acum.hmcl),
        "sin_hmcl": _dinero(venta - acum.hmcl),
        "pct_hmcl": ratio(acum.hmcl, venta),
        "por_mes": {m: _dinero(acum.venta_por_mes.get(m, cero)) for m in meses},
        "por_linea": {linea: _dinero(acum.venta_por_linea.get(linea, cero)) for linea in lineas},
        "mix": {linea: ratio(acum.venta_por_linea.get(linea, cero), venta) for linea in lineas},
        "por_mes_linea": {
            m: {linea: _dinero(acum.venta_por_mes_linea.get((m, linea), cero)) for linea in lineas}
            for m in meses
        },
    }


def _bloque_costo(acum: _Acumulado) -> Dict[str, Any]:
    return {
        "costo_venta": _dinero(acum.costo),
        "costo_estimado": _dinero(acum.costo_estimado),
        "pct_costo_estimado": ratio(acum.costo_estimado, acum.costo) or 0.0,
        "venta_con_costo": _dinero(acum.con_costo),
        "utilidad_bruta": _dinero(acum.con_costo - acum.costo),
        "pct_margen": ratio(acum.con_costo - acum.costo, acum.con_costo),
        "pct_venta_con_costo": ratio(acum.con_costo, acum.venta),
    }


def _bloque_facturas(
    acum: _Acumulado, facturas: Optional[FilaFacturas], lineas: Tuple[str, ...],
) -> Dict[str, Any]:
    n_facturas = Decimal(facturas.facturas if facturas else 0)
    con_linea = facturas.con_linea if facturas else (0,) * len(lineas)
    venta_linea = acum.venta_por_linea
    return {
        "facturas": int(n_facturas),
        "ticket_promedio": ratio(acum.venta, n_facturas),
        "unidades": _dinero(acum.cantidad),
        "items_por_factura": ratio(Decimal(acum.lineas), n_facturas),
        "pct_con_linea": {linea: ratio(Decimal(n), n_facturas) for linea, n in zip(lineas, con_linea)},
        "facturas_con_linea": {linea: int(n) for linea, n in zip(lineas, con_linea)},
        # venta de la linea / facturas con al menos un item de esa linea (None sin facturas)
        "ticket_por_linea": {
            linea: ratio(venta_linea.get(linea, Decimal(0)), Decimal(n)) for linea, n in zip(lineas, con_linea)
        },
        "pct_multilinea": ratio(Decimal(facturas.multilinea if facturas else 0), n_facturas),
    }


def _bloque_descuentos(acum: _Acumulado) -> Dict[str, Any]:
    descuentos = acum.descuentos
    mes_mayor = None
    if descuentos > 0:
        mes_mayor = min(
            (m for m, d in acum.descuento_por_mes.items() if d > 0),
            key=lambda m: (-acum.descuento_por_mes[m], m),
        )
    return {
        "total": _dinero(descuentos),
        "mes_mayor": mes_mayor,
        "pct_en_mes_mayor": ratio(acum.descuento_por_mes[mes_mayor], descuentos) if mes_mayor else None,
        "pct_descuento": ratio(descuentos, acum.bruto),
    }


def _bloque_clientes(
    acum: _Acumulado, clientes: Optional[FilaClientes], meses: List[str], lineas: Tuple[str, ...],
) -> Dict[str, Any]:
    venta, cero = acum.venta, Decimal(0)
    return {
        "pct_mostrador": ratio(acum.mostrador, venta),
        "venta_tecnired": _dinero(acum.tecnired),
        "tecnired_por_mes": {m: _dinero(acum.tecnired_por_mes.get(m, cero)) for m in meses},
        "tecnired_por_linea": {linea: _dinero(acum.tecnired_por_linea.get(linea, cero)) for linea in lineas},
        "pct_tecnired": ratio(acum.tecnired, venta),
        "clientes_unicos": clientes.clientes if clientes else 0,
        "pct_top5": ratio(clientes.venta_top5, venta) if clientes else None,
    }


def indicadores(
    acum: _Acumulado,
    facturas: Optional[FilaFacturas],
    clientes: Optional[FilaClientes],
    meses: List[str],
    lineas: Tuple[str, ...] = LINEAS,
) -> Dict[str, Any]:
    return {
        "venta": _bloque_venta(acum, meses, lineas),
        "costo": _bloque_costo(acum),
        "tendencia": variacion_3m(acum.venta_por_mes, meses),
        "facturas": _bloque_facturas(acum, facturas, lineas),
        "descuentos": _bloque_descuentos(acum),
        "clientes": _bloque_clientes(acum, clientes, meses, lineas),
        "ranking": None,
    }


def _por_clave(filas: Iterable[Any]) -> Dict[str, Any]:
    return {f.clave: f for f in filas}


def _orden_de_fila(fila: Dict[str, Any]) -> Tuple:
    if fila["tipo"] == "PERSONA":
        return (0, (fila["punto_venta"] or "").upper(), fila["nombre"].upper())
    return (1, ORDEN_GRUPOS.index(fila["clave"]), "")


ORDEN_GRUPOS = (GRUPO_COMERCIALES, GRUPO_OTROS, GRUPO_RESTO)


def _fila_total(acum, facturas, clientes, personas, meses, lineas=LINEAS) -> Dict[str, Any]:
    fila = {"clave": CLAVE_TOTAL, "tipo": "TOTAL", "nombre": "TOTAL", "cargo": None,
            "punto_venta": None, "cargos": [], "cargo_conflicto": False, "personas": personas}
    fila.update(indicadores(acum, facturas, clientes, meses, lineas))
    return fila


def acumular_cubo(
    cubo: Iterable[FilaCubo], reglas: Reglas = REGLAS_POR_DEFECTO,
) -> Tuple[Dict[str, _Acumulado], Decimal]:
    """Acumulado por clave del cubo (mas la clave TOTAL con todo) y la venta
    excluida por no tener una de las lineas de `reglas`."""
    acumulados: Dict[str, _Acumulado] = {CLAVE_TOTAL: _Acumulado()}
    sin_linea = Decimal(0)
    for f in cubo:
        if f.linea is None or f.linea not in reglas.lineas:
            sin_linea += f.venta
            continue
        acumulados.setdefault(f.clave, _Acumulado()).sumar(f)
        acumulados[CLAVE_TOTAL].sumar(f)
    return acumulados, sin_linea


def construir_tablero(
    cubo: Iterable[FilaCubo],
    facturas: Iterable[FilaFacturas],
    clientes: Iterable[FilaClientes],
    personas: Iterable[FilaPersona],
    meses: List[str],
    reglas: Reglas = REGLAS_POR_DEFECTO,
) -> Dict[str, Any]:
    """Filas del tablero (personas, grupos), fila TOTAL y la venta excluida por
    no tener linea comercial reconocida."""
    acumulados, sin_linea = acumular_cubo(cubo, reglas)

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
        fila.update(indicadores(acum, facturas_por.get(clave), clientes_por.get(clave), meses, reglas.lineas))
        filas.append(fila)
    filas.sort(key=_orden_de_fila)

    _agregar_ranking([f for f in filas if f["tipo"] == "PERSONA"])

    venta_total = acumulados[CLAVE_TOTAL].venta
    return {
        "filas": filas,
        "total": _fila_total(
            acumulados[CLAVE_TOTAL], facturas_por.get(CLAVE_TOTAL), clientes_por.get(CLAVE_TOTAL),
            sum(f["personas"] for f in filas), meses, reglas.lineas),
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
        campo: rankear({f["clave"]: Decimal(str(f["venta"]["por_linea"].get(linea, 0))) for f in personas})
        for campo, linea in _RANKINGS_POR_LINEA.items()
    }
    for f in personas:
        f["ranking"] = {
            "indice_vs_promedio": ratio(ventas[f["clave"]], promedio),
            "rank_total": rank_total[f["clave"]],
            **{campo: rank[f["clave"]] for campo, rank in rank_linea.items()},
        }
