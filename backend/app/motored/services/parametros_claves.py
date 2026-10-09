"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S4b, ADR-7, decisión
#16): registro tipado de las claves de `parametro_metodologia`.

Módulo PURO (sin base de datos). Cada clave lleva su valor por defecto (el
preset legacy del Excel), su ámbito y su regla de validación.

Contrato de compatibilidad: el registro gobierna sólo las ESCRITURAS nuevas
(`validar_escritura`, llamada desde `POST /parametros`). Las lecturas
(`obtener_vigente`, `resolver`, `obtener_vigentes_motor`) jamás lo consultan
para rechazar: una clave ya guardada que el registro no conoce se sigue
leyendo igual, así que una fila vieja en producción no rompe nada.

Los valores por defecto son JSON nativo (los decimales van como texto, p. ej.
"0.80") para poder guardarse tal cual en el snapshot de la corrida;
`parsear` los convierte a `Fraction` para el motor.
"""
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from app.config import settings
from app.motored.services.corridas import codigos

AMBITO_GLOBAL = "GLOBAL"
AMBITO_GLOBAL_Y_SUCURSAL = "GLOBAL_Y_SUCURSAL"
# F4 (B5a): sólo existe por tienda; un valor global es E-PARAM-004.
AMBITO_SOLO_SUCURSAL = "SOLO_SUCURSAL"

GRUPO_INGESTA = "INGESTA"
GRUPO_MOTOR = "MOTOR"
# F4 (B5a): tope de presupuesto. NO es del motor: jamás entra al
# snapshot de la corrida ni se puede usar como override.
GRUPO_PEDIDO = "PEDIDO"
# Configuración (T1): ajustes de la operación del negocio (avisos,
# retención, indicadores, comisiones). NO es del motor: jamás entra al
# snapshot de la corrida, así que un cambio rige para todos desde su mes.
GRUPO_OPERACION = "OPERACION"

# Bodegas que no son tiendas (bodega central, producto terminado): sus
# líneas se ignoran al cargar ventas e inventario, sin marcar error.
CLAVE_BODEGAS_EXCLUIDAS = "bodegas_excluidas"
CLAVE_VENTAS_TIPOS_EXCLUIDOS = "ventas_tipos_excluidos"
BODEGAS_EXCLUIDAS_DEFAULT = ("99999", "PYM01", "PAF01")

# Pestañas de la pantalla de Configuración, en orden.
SECCIONES = (
    "pedido", "avisos", "cargas", "limpieza", "indicadores", "comisiones",
    "conteos", "ingresos", "topes",
)

# Conteos de inventario (odd/motored-conteos-inventario, WU4): montos en
# pesos que piden reconteo o marcan una diferencia crítica, y la edad
# máxima del inventario de Maestros al iniciar un conteo.
CLAVE_CONTEO_UMBRAL_RECONTEO = "conteo_umbral_reconteo_pesos"
CLAVE_CONTEO_UMBRAL_CRITICO = "conteo_umbral_critico_pesos"
CLAVE_CONTEO_VIGENCIA_HORAS = "conteo_inventario_vigencia_horas"

# Ingresos de facturas (odd/motored-ingresos-responsable-plantilla, T1): el
# umbral de referencias que separa al asesor del analista administrativo y
# los valores fijos de la plantilla "Entradas x Compra" del ERP.
CLAVE_INGRESO_UMBRAL_ASESOR = "ingreso_umbral_referencias_asesor"
CLAVE_PLANTILLA_TIPO_DOC = "ingreso_plantilla_tipo_documento"
CLAVE_PLANTILLA_DESC_GLOBAL = "ingreso_plantilla_descuento_global"
CLAVE_PLANTILLA_PROVEEDOR = "ingreso_plantilla_proveedor_nit"
CLAVE_PLANTILLA_SUC_PROVEEDOR = "ingreso_plantilla_sucursal_proveedor"
CLAVE_PLANTILLA_COMPRADOR = "ingreso_plantilla_comprador"
CLAVE_PLANTILLA_DESC_ITEM = "ingreso_plantilla_descuento_item"
CLAVE_PLANTILLA_UNIDAD_NEGOCIO = "ingreso_plantilla_unidad_negocio"
_SECCION_POR_GRUPO = {
    GRUPO_MOTOR: "pedido", GRUPO_INGESTA: "cargas", GRUPO_PEDIDO: "topes",
}


class ErrorParametro(Exception):
    """Error codificado de parámetros (E-PARAM-nnn o E-CORRIDA-010)."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje


@dataclass(frozen=True)
class EspecClave:
    clave: str
    default: Any
    ambito: str
    grupo: str
    dominio: str
    validar: Callable[[Any], bool]
    convertir: Callable[[Any], Any]
    # F4 (B5a): lo que el catálogo `GET /parametros/claves` (B6) expone.
    # Sólo tuplas: un dataclass congelado con un default mutable no
    # importa en Python 3.11.
    tipo: str = ""
    opciones: Tuple[str, ...] = ()
    # Configuración (T1): lo que la pantalla necesita para dibujar el
    # control. Rango de los números, nombres de los campos de un objeto y
    # pestaña (vacía = la del grupo).
    minimo: Optional[Any] = None
    maximo: Optional[Any] = None
    minimo_exclusivo: bool = False
    campos: Tuple[str, ...] = ()
    seccion: str = ""


def _entero(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _numero(valor: Any) -> Optional[Fraction]:
    """Número exacto de un int, float o texto decimal; None si no lo es."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        return None
    try:
        decimal = Decimal(str(valor).strip())
    except InvalidOperation:
        return None
    return Fraction(decimal) if decimal.is_finite() else None


def _identidad(valor: Any) -> Any:
    return valor


def _booleana(clave: str, default: bool, grupo: str = GRUPO_MOTOR,
              seccion: str = ""):
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo, "verdadero o falso",
        lambda v: isinstance(v, bool), _identidad, tipo="bool",
        seccion=seccion,
    )


def _entera(clave, default, minimo, maximo, grupo=GRUPO_MOTOR,
            ambito=AMBITO_GLOBAL, seccion="", explicacion=""):
    """`explicacion` (opcional) se agrega al dominio que ve la persona."""
    dominio = f"un entero entre {minimo} y {maximo}"
    if explicacion:
        dominio += f" ({explicacion})"
    return EspecClave(
        clave, default, ambito, grupo, dominio,
        lambda v: _entero(v) and minimo <= v <= maximo, _identidad,
        tipo="entero", minimo=minimo, maximo=maximo, seccion=seccion,
    )


def _decimal(clave, default, maximo=None, exclusivo=False,
             grupo=GRUPO_MOTOR, seccion=""):
    """Decimal exacto >= 0 (o > 0 si `exclusivo`), con tope opcional."""
    def valido(valor):
        n = _numero(valor)
        if n is None or n < 0 or (exclusivo and n == 0):
            return False
        return maximo is None or n <= maximo

    limite = "mayor que 0" if exclusivo else "mayor o igual a 0"
    dominio = f"un número {limite}"
    if maximo is not None:
        dominio += f" y hasta {maximo}"
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo, dominio, valido, _numero,
        tipo="decimal", minimo=0, maximo=maximo, minimo_exclusivo=exclusivo,
        seccion=seccion)


def _opcion(clave: str, default: str, opciones: tuple, grupo=GRUPO_MOTOR,
            seccion=""):
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        "uno de " + ", ".join(opciones), lambda v: v in opciones, _identidad,
        tipo="opcion", opciones=tuple(opciones), seccion=seccion,
    )


def texto_de_digitos(clave: str, default: str, maximo: int,
                     grupo: str = GRUPO_OPERACION,
                     seccion: str = "") -> EspecClave:
    """Código de sólo dígitos que conserva los ceros a la izquierda."""
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        f"un texto de 1 a {maximo} dígitos (se conservan los ceros a la "
        "izquierda)",
        lambda v: isinstance(v, str) and v.isascii() and v.isdigit()
        and len(v) <= maximo,
        _identidad, tipo="texto", seccion=seccion,
    )


def lista_de_texto(clave: str, default: list, grupo: str = GRUPO_OPERACION,
                   seccion: str = "") -> EspecClave:
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        "una lista no vacía de textos",
        lambda v: isinstance(v, list) and len(v) > 0
        and all(isinstance(x, str) and x.strip() for x in v),
        _identidad, tipo="lista", seccion=seccion,
    )


def _sin_repetidos(valor: list) -> bool:
    return len(set(valor)) == len(valor)


_HORA = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")


def hora_hhmm(clave: str, default: str, grupo: str = GRUPO_OPERACION,
              seccion: str = "") -> EspecClave:
    """Hora del día como texto "HH:MM" (24 horas)."""
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        "una hora en formato HH:MM, de 00:00 a 23:59",
        lambda v: isinstance(v, str) and _HORA.fullmatch(v) is not None,
        _identidad, tipo="hora", seccion=seccion,
    )


def lista_de_opciones(clave: str, default: list, opciones: tuple,
                      grupo: str = GRUPO_OPERACION,
                      seccion: str = "") -> EspecClave:
    """Lista no vacía y sin repetidos de valores tomados de `opciones`."""
    def valido(valor):
        return isinstance(valor, list) and len(valor) > 0 and all(
            isinstance(x, str) and x in opciones for x in valor
        ) and _sin_repetidos(valor)

    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        "una lista no vacía, sin repetidos, con valores de: "
        + ", ".join(opciones),
        valido, _identidad, tipo="lista_opciones",
        opciones=tuple(opciones), seccion=seccion,
    )


def _lista_texto(clave: str, default: list):
    return lista_de_texto(clave, default, GRUPO_INGESTA)


def lista_de_digitos(clave: str, default: list, grupo: str = GRUPO_OPERACION,
                     seccion: str = "", unicos: bool = False) -> EspecClave:
    """Lista no vacía de textos de sólo dígitos (p. ej. NIT); con `unicos`
    no admite repetidos."""
    def valido(valor):
        return isinstance(valor, list) and len(valor) > 0 and all(
            isinstance(x, str) and re.fullmatch(r"[0-9]+", x) for x in valor
        ) and (not unicos or _sin_repetidos(valor))

    dominio = "una lista no vacía de textos con sólo dígitos"
    if unicos:
        dominio += ", sin repetidos"
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo, dominio, valido,
        _identidad, tipo="lista_digitos", seccion=seccion,
    )


def _normalizado(texto: str) -> bool:
    """Sin espacios sobrantes y en mayúsculas (como se comparan los cargos)."""
    return bool(texto) and texto == texto.strip().upper()


def lista_de_codigos(clave: str, default: list, grupo: str = GRUPO_OPERACION,
                     seccion: str = "") -> EspecClave:
    """Lista no vacía de códigos en mayúsculas y sin espacios al borde,
    sin repetidos (p. ej. códigos de bodega)."""
    def valido(valor):
        return isinstance(valor, list) and len(valor) > 0 and all(
            isinstance(x, str) and _normalizado(x) for x in valor
        ) and _sin_repetidos(valor)

    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        "una lista no vacía de códigos en mayúsculas y sin espacios al "
        "borde, sin repetidos",
        valido, _identidad, tipo="lista", seccion=seccion,
    )


def mapa_a_opcion(clave: str, default: dict, opciones: tuple,
                  grupo: str = GRUPO_OPERACION, seccion: str = "",
                  normalizado: bool = False) -> EspecClave:
    """Objeto texto -> una de `opciones`; vacío es válido (todo implícito).
    Con `normalizado` cada texto va en mayúsculas y sin espacios al borde."""
    def valido(valor):
        return isinstance(valor, dict) and all(
            isinstance(k, str) and k.strip() and v in opciones
            and (not normalizado or _normalizado(k))
            for k, v in valor.items())

    dominio = "un objeto de texto a uno de " + ", ".join(opciones)
    if normalizado:
        dominio += "; los nombres en mayúsculas y sin espacios al borde"
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo, dominio, valido,
        _identidad, tipo="mapa_opcion", opciones=tuple(opciones),
        seccion=seccion,
    )


def objeto_numerico(clave: str, default: dict, campos: Tuple[str, ...],
                    menores: Tuple[Tuple[str, str], ...] = (),
                    grupo: str = GRUPO_OPERACION, seccion: str = "",
                    maximo: Optional[int] = None) -> EspecClave:
    """Objeto con exactamente `campos`, números >= 0 (y <= `maximo` si lo
    hay). Cada par de `menores` (a, b) exige a < b entre campos."""
    def valido(valor):
        if not isinstance(valor, dict) or set(valor) != set(campos):
            return False
        n = {k: _numero(x) for k, x in valor.items()}
        if any(x is None or x < 0 for x in n.values()):
            return False
        if maximo is not None and any(x > maximo for x in n.values()):
            return False
        return all(n[a] < n[b] for a, b in menores)

    dominio = "un objeto con " + ", ".join(campos) + ", números >= 0"
    if maximo is not None:
        dominio += f" y hasta {maximo}"
    for menor, mayor in menores:
        dominio += f"; {menor} debe ser menor que {mayor}"
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo, dominio, valido,
        lambda v: {k: _numero(x) for k, x in v.items()},
        tipo="objeto_numerico", campos=tuple(campos), seccion=seccion,
        minimo=0 if maximo is not None else None, maximo=maximo,
    )


_CAMPOS_TRAMO = ("nombre", "desde_pct", "tasa_pct")


def _tramo_numeros(tramo: Any) -> Optional[Tuple[Fraction, Fraction]]:
    """(desde, tasa) de un tramo bien formado; None si no lo es."""
    if not isinstance(tramo, dict) or set(tramo) != set(_CAMPOS_TRAMO):
        return None
    nombre = tramo["nombre"]
    if not isinstance(nombre, str) or not nombre.strip():
        return None
    desde, tasa = _numero(tramo["desde_pct"]), _numero(tramo["tasa_pct"])
    if desde is None or tasa is None or desde < 0 or tasa < 0:
        return None
    return desde, tasa


def _tramos_validos(valor: Any) -> bool:
    if not isinstance(valor, list) or not valor:
        return False
    pares = [_tramo_numeros(t) for t in valor]
    if any(p is None for p in pares):
        return False
    desdes = [p[0] for p in pares]
    estricto = all(a < b for a, b in zip(desdes, desdes[1:]))
    nombres = [t["nombre"].strip().casefold() for t in valor]
    return desdes[0] == 0 and estricto and _sin_repetidos(nombres)


def tramos_ordenados(clave: str, default: list, grupo: str = GRUPO_OPERACION,
                     seccion: str = "") -> EspecClave:
    """Lista ordenada de {nombre, desde_pct, tasa_pct}: el primer
    `desde_pct` es 0, crecen estrictamente y `tasa_pct` >= 0."""
    def convertir(valor):
        return [{"nombre": t["nombre"], "desde_pct": _numero(t["desde_pct"]),
                 "tasa_pct": _numero(t["tasa_pct"])} for t in valor]

    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        "una lista de tramos con nombre (sin repetir), desde_pct y tasa_pct "
        ">= 0; el primer desde_pct es 0 y los siguientes van de menor a mayor",
        _tramos_validos, convertir, tipo="tramos", campos=_CAMPOS_TRAMO,
        seccion=seccion,
    )


_CAMPOS_BONO = ("linea", "pct_meta", "bono", "activo")
_BONOS_POR_DEFECTO = [
    {"linea": linea, "pct_meta": pct, "bono": bono, "activo": True}
    for linea, pct, bono in (
        ("LUBRICANTES", "21", "35000"), ("CASCOS", "6", "30000"),
        ("ACCESORIOS", "3", "25000"), ("LLANTAS", "1", "25000"),
        ("BATERIAS", "1", "25000"), ("TECNIRED", "6", "25000"))
]


def _linea_normalizada(valor: Any) -> bool:
    """Código de línea: mayúsculas, sin tildes ni espacios al borde."""
    if not isinstance(valor, str) or not valor:
        return False
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", valor)
        if unicodedata.category(c) != "Mn")
    return valor == sin_tildes and _normalizado(valor)


def _pesos_enteros(valor: Any) -> Optional[int]:
    """Pesos enteros >= 0 de un int, un float entero o un texto de dígitos
    (admite un `.0` final, como lo manda la pantalla); None si no lo es."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor >= 0 else None
    if isinstance(valor, float):
        return int(valor) if valor >= 0 and valor == int(valor) else None
    if isinstance(valor, str):
        m = re.fullmatch(r"([0-9]+)(\.0+)?", valor.strip())
        return int(m.group(1)) if m else None
    return None


def _porcentaje_meta(valor: Any) -> Optional[Fraction]:
    n = _numero(valor)
    return n if n is not None and 0 < n <= 100 else None


def _texto_decimal(n: Fraction) -> str:
    """"6" para 6, "6.5" para 13/2 (el decimal exacto más corto)."""
    texto = format(Decimal(n.numerator) / Decimal(n.denominator), "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def _bono_valido(fila: Any) -> bool:
    return (
        isinstance(fila, dict) and set(fila) == set(_CAMPOS_BONO)
        and _linea_normalizada(fila["linea"])
        and _porcentaje_meta(fila["pct_meta"]) is not None
        and _pesos_enteros(fila["bono"]) is not None
        and isinstance(fila["activo"], bool))


def bonos_por_linea(clave: str, default: list, grupo: str = GRUPO_OPERACION,
                    seccion: str = "") -> EspecClave:
    """Lista (puede ser vacía) de {linea, pct_meta, bono, activo}: `linea`
    única y normalizada, `pct_meta` en (0, 100], `bono` en pesos enteros
    >= 0. Que la línea exista en `lineas_comerciales` (o sea TECNIRED) no se
    contrasta aquí: un validador del registro ve una sola clave; una línea
    sin ventas simplemente no gana nada."""
    def valido(valor):
        return (
            isinstance(valor, list) and all(_bono_valido(f) for f in valor)
            and _sin_repetidos([f["linea"] for f in valor]))

    def convertir(valor):
        return [{"linea": f["linea"],
                 "pct_meta": _texto_decimal(_porcentaje_meta(f["pct_meta"])),
                 "bono": str(_pesos_enteros(f["bono"])),
                 "activo": f["activo"]} for f in valor]

    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        "una lista (puede ser vacía) de líneas únicas, en mayúsculas y sin "
        "tildes, con pct_meta mayor que 0 y hasta 100, bono en pesos enteros "
        ">= 0 y activo verdadero o falso",
        valido, convertir, tipo="lista", campos=_CAMPOS_BONO,
        seccion=seccion)


_CAMPOS_TIPO_EXCLUIDO = ("codigo", "modo")
_MODOS_TIPO_EXCLUIDO = ("prefijo", "exacto")
_TIPOS_EXCLUIDOS_POR_DEFECTO = (
    [{"codigo": "IM19", "modo": "prefijo"}]
    + [{"codigo": c, "modo": "exacto"}
       for c in ("VS12", "VS13", *(f"ST00{n}" for n in range(1, 9)),
                 "G01", "OBS2", "RPGOGORO")])


def _tipo_excluido_valido(fila: Any) -> bool:
    return (
        isinstance(fila, dict) and set(fila) == set(_CAMPOS_TIPO_EXCLUIDO)
        and isinstance(fila["codigo"], str) and _normalizado(fila["codigo"])
        and fila["modo"] in _MODOS_TIPO_EXCLUIDO)


def tipos_excluidos(clave: str, default: list, grupo: str = GRUPO_OPERACION,
                    seccion: str = "") -> EspecClave:
    """Lista (puede ser vacía) de {codigo, modo}: códigos de tipo de venta
    del ERP que la carga descarta. `codigo` en mayúsculas y sin espacios al
    borde; `modo` prefijo (empieza por) o exacto; sin pares repetidos."""
    def valido(valor):
        return isinstance(valor, list) and all(
            _tipo_excluido_valido(f) for f in valor
        ) and _sin_repetidos([(f["codigo"], f["modo"]) for f in valor])

    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo,
        "una lista (puede ser vacía) de códigos del ERP en mayúsculas y "
        "sin espacios al borde, cada uno con modo prefijo o exacto, sin "
        "pares repetidos",
        valido, _identidad, tipo="lista", campos=_CAMPOS_TIPO_EXCLUIDO,
        seccion=seccion)


def _tope_por_tienda(clave: str):
    """Decimal > 0 o nulo ("sin tope"), sólo por sucursal (F4, ADR-6)."""
    def valido(valor):
        if valor is None:
            return True
        n = _numero(valor)
        return n is not None and n > 0

    return EspecClave(
        clave, None, AMBITO_SOLO_SUCURSAL, GRUPO_PEDIDO,
        "un número mayor que 0 (o vacío para quitar el tope)", valido,
        _numero, tipo="decimal",
    )


_CLAVES_K_FMS = {"F", "M", "S"}


def _k_fms_valido(valor: Any) -> bool:
    if not isinstance(valor, dict) or set(valor) != _CLAVES_K_FMS:
        return False
    numeros = [_numero(x) for x in valor.values()]
    return all(n is not None and n >= 0 for n in numeros)


def _k_fms_convertido(valor: Mapping) -> Mapping:
    return {k: _numero(v) for k, v in valor.items()}


_K_FMS = EspecClave(
    "k_fms", {"F": "3", "M": "1.5", "S": "1"}, AMBITO_GLOBAL, GRUPO_MOTOR,
    "un objeto con F, M y S, números mayores o iguales a 0",
    _k_fms_valido, _k_fms_convertido, tipo="k_fms", campos=("F", "M", "S"),
)

# Tipos de dato con límite de antigüedad propio (decisión #16).
CLAVES_ANTIGUEDAD = {
    "inventario": "max_dias_antiguedad_inventario",
    "backorder": "max_dias_antiguedad_backorder",
    "facturas": "max_dias_antiguedad_facturas",
    "ingresos": "max_dias_antiguedad_ingresos",
}

CLAVE_MODO_TOPE = "modo_tope_presupuesto"
CLAVE_TOPE_PEDIDO = "presupuesto_maximo_pedido"

_DIAS_ANTIGUEDAD_MAX = 365  # supuesto ajustable (tasks: Open item D)

_GRUPOS_CARGO = ("PERSONA", "COMERCIALES", "OTROS")
_BASES_HMCL = ("sin_hmcl", "con_hmcl")


_MAXIMO_DIAS_INVENTARIO_KPI = 3650


def _claves_indicadores() -> list:
    """T6: lo que el tablero de asesores lee hoy como constantes. Los
    valores por defecto son los de `tablero_asesores`. `lineas_comerciales`
    no se contrasta con `tipos_inventario_incluidos`: un validador del
    registro ve una sola clave y no la base, y esa lista puede cambiar
    después de guardar las líneas."""
    return [
        lista_de_digitos(
            "hmcl_nits", ["900723988", "900883086"], seccion="indicadores",
            unicos=True),
        mapa_a_opcion(
            "grupo_por_cargo",
            {"ASESOR DE REPUESTOS": "PERSONA",
             "ASESOR DE REPUESTOS SUPERNUMERARIO": "PERSONA",
             "CAJERO POSVENTA": "PERSONA",
             "ASESOR COMERCIAL DE SERVICIO POSVENTA": "COMERCIALES"},
            _GRUPOS_CARGO, seccion="indicadores", normalizado=True),
        lista_de_texto(
            "lineas_comerciales",
            ["REPUESTOS", "ACCESORIOS", "LLANTAS", "LUBRICANTES",
             "BATERIAS", "GPS", "CASCOS"], seccion="indicadores"),
        objeto_numerico(
            "kpi_semaforo_cortes", {"verde_desde": 90, "ambar_desde": 70},
            ("verde_desde", "ambar_desde"),
            menores=(("ambar_desde", "verde_desde"),),
            seccion="indicadores", maximo=200),
        _entera(
            "kpi_inventario_dias_meta", 60, 1, _MAXIMO_DIAS_INVENTARIO_KPI,
            GRUPO_OPERACION, seccion="indicadores",
            explicacion="días de inventario objetivo"),
        objeto_numerico(
            "kpi_inventario_dias_cortes", {"verde_hasta": 60, "ambar_hasta": 90},
            ("verde_hasta", "ambar_hasta"),
            menores=(("verde_hasta", "ambar_hasta"),),
            seccion="indicadores", maximo=_MAXIMO_DIAS_INVENTARIO_KPI),
        _entera(
            "kpi_inventario_sin_movimiento_dias", 180, 1,
            _MAXIMO_DIAS_INVENTARIO_KPI, GRUPO_OPERACION,
            seccion="indicadores",
            explicacion="días sin venta para contar como sin movimiento"),
    ]


def _claves_comisiones() -> list:
    """T7: reglas de comisión; la pestaña Comisiones de KPI's las lee
    (tramos, bases, cargos y bonos por línea) para liquidar cada mes con
    las vigentes."""
    return [
        tramos_ordenados(
            "comision_tramos",
            [{"nombre": "BASE", "desde_pct": 0, "tasa_pct": 1.0},
             {"nombre": "PRO", "desde_pct": 90, "tasa_pct": 1.5},
             {"nombre": "ELITE", "desde_pct": 105, "tasa_pct": 1.8}],
            seccion="comisiones"),
        _opcion("comision_base_pago", "sin_hmcl", _BASES_HMCL,
                GRUPO_OPERACION, "comisiones"),
        _opcion("cumplimiento_base", "con_hmcl", _BASES_HMCL,
                GRUPO_OPERACION, "comisiones"),
        lista_de_texto(
            "comision_cargos_asesor",
            ["ASESOR DE REPUESTOS", "ASESOR DE REPUESTOS SUPERNUMERARIO", "CAJERO POSVENTA"],
            seccion="comisiones"),
        bonos_por_linea(
            "comision_lineas", _BONOS_POR_DEFECTO, seccion="comisiones"),
        _decimal(
            "comision_bono_umbral_pct", "95", 200, grupo=GRUPO_OPERACION,
            seccion="comisiones"),
    ]


# Roles web que pueden vincular Telegram y por tanto recibir avisos.
_ROLES_AVISO = ("ADMIN", "COMPRAS")
_MINIMO_DIAS_INVENTARIO = 30
_MINIMO_DIAS_CORRIDAS = 7
_MAXIMO_DIAS_RETENCION = 3650


def _claves_avisos() -> list:
    """T3: horas y destinatarios del aviso de antigüedad de datos. Los
    valores por defecto son las constantes de `avisos_antiguedad` (una
    prueba guarda que no se desvíen)."""
    return [
        hora_hhmm("aviso_hora_vispera", "16:30", seccion="avisos"),
        hora_hhmm("aviso_hora_dia", "08:30", seccion="avisos"),
        lista_de_opciones(
            "aviso_roles_destino", ["COMPRAS"], _ROLES_AVISO,
            seccion="avisos"),
    ] + _claves_reporte_asesor()


def _claves_reporte_asesor() -> list:
    """T3b (odd/motored-reporte-diario-asesor): the daily Lore message
    with each asesor's report link. OFF by default until the owner
    approves a real sample; hours in Bogotá ("HH:MM")."""
    return [
        _booleana("reporte_asesor_envio_activo", False, GRUPO_OPERACION,
                  "avisos"),
        hora_hhmm("reporte_asesor_hora_limite", "10:00", seccion="avisos"),
        hora_hhmm("reporte_asesor_hora_minima", "06:00", seccion="avisos"),
    ]


def _claves_limpieza() -> list:
    """T5: la purga de inventario y de corridas. Los valores por defecto
    son los de las variables de entorno que reemplazan (se usan también
    cuando no hay fila guardada)."""
    def dias(clave, default, minimo, motivo):
        return _entera(
            clave, default, minimo, _MAXIMO_DIAS_RETENCION,
            GRUPO_OPERACION, seccion="limpieza",
            explicacion=f"menos de {minimo} días {motivo}")

    return [
        _booleana("retencion_inventario_habilitada",
                  settings.MOTORED_RETENCION_ENABLED,
                  GRUPO_OPERACION, "limpieza"),
        dias("retencion_inventario_dias", settings.MOTORED_RETENCION_DIAS,
             _MINIMO_DIAS_INVENTARIO,
             "borraría inventario que todavía se consulta"),
        _booleana("retencion_corridas_habilitada",
                  settings.MOTORED_CORRIDA_RETENCION_ENABLED,
                  GRUPO_OPERACION, "limpieza"),
        dias("retencion_corridas_dias",
             settings.MOTORED_CORRIDA_RETENCION_DIAS, _MINIMO_DIAS_CORRIDAS,
             "borraría corridas recién descartadas"),
    ]


_MAXIMO_PESOS_CONTEO = 10_000_000_000
_MAXIMO_HORAS_VIGENCIA = 720


def _claves_conteos() -> list:
    """WU4: los montos se congelan en cada conteo al iniciarlo (ADR-9);
    que el de reconteo sea menor que el crítico lo revisa
    `validar_relaciones`, porque un validador ve una sola clave."""
    def pesos(clave, default):
        return _entera(
            clave, default, 1, _MAXIMO_PESOS_CONTEO, GRUPO_OPERACION,
            seccion="conteos", explicacion="pesos, sin decimales")

    return [
        pesos(CLAVE_CONTEO_UMBRAL_RECONTEO, 100000),
        pesos(CLAVE_CONTEO_UMBRAL_CRITICO, 500000),
        _entera(
            CLAVE_CONTEO_VIGENCIA_HORAS, 6, 1, _MAXIMO_HORAS_VIGENCIA,
            GRUPO_OPERACION, seccion="conteos", explicacion="horas"),
    ]


_MAXIMO_REFERENCIAS_ASESOR = 1000
_MAXIMO_IDENTIFICADOR = 10 ** 13


def _claves_ingresos() -> list:
    """T1: quién ingresa cada factura y los valores fijos de la plantilla.
    Los descuentos son porcentajes que la persona puede editar luego en
    el Excel; los códigos "001"/"003" conservan sus ceros."""
    def identificador(clave, default, maximo):
        return _entera(
            clave, default, 1, maximo, GRUPO_OPERACION, seccion="ingresos")

    def descuento(clave, default):
        return _decimal(clave, default, 100, grupo=GRUPO_OPERACION,
                        seccion="ingresos")

    return [
        _entera(
            CLAVE_INGRESO_UMBRAL_ASESOR, 10, 1, _MAXIMO_REFERENCIAS_ASESOR,
            GRUPO_OPERACION, seccion="ingresos",
            explicacion="referencias; hasta ese número la ingresa el "
            "asesor de la tienda"),
        identificador(CLAVE_PLANTILLA_TIPO_DOC, 16, 99),
        descuento(CLAVE_PLANTILLA_DESC_GLOBAL, 5),
        identificador(CLAVE_PLANTILLA_PROVEEDOR, 900723988,
                      _MAXIMO_IDENTIFICADOR),
        texto_de_digitos(CLAVE_PLANTILLA_SUC_PROVEEDOR, "001", 6,
                         seccion="ingresos"),
        identificador(CLAVE_PLANTILLA_COMPRADOR, 1151943311,
                      _MAXIMO_IDENTIFICADOR),
        descuento(CLAVE_PLANTILLA_DESC_ITEM, 0),
        texto_de_digitos(CLAVE_PLANTILLA_UNIDAD_NEGOCIO, "003", 6,
                         seccion="ingresos"),
    ]


CLAVES_INGRESOS = (
    CLAVE_INGRESO_UMBRAL_ASESOR, CLAVE_PLANTILLA_TIPO_DOC,
    CLAVE_PLANTILLA_DESC_GLOBAL, CLAVE_PLANTILLA_PROVEEDOR,
    CLAVE_PLANTILLA_SUC_PROVEEDOR, CLAVE_PLANTILLA_COMPRADOR,
    CLAVE_PLANTILLA_DESC_ITEM, CLAVE_PLANTILLA_UNIDAD_NEGOCIO,
)
RESPALDOS_INGRESOS = {
    espec.clave: espec.default for espec in _claves_ingresos()}


def _claves_antiguedad_y_tope() -> list:
    """Antigüedad máxima por tipo de dato (motor) y el tope de
    presupuesto (F4, B5a), fuera del motor."""
    return [
        _entera(clave, 7, 1, _DIAS_ANTIGUEDAD_MAX)
        for clave in CLAVES_ANTIGUEDAD.values()
    ] + [
        _booleana(CLAVE_MODO_TOPE, False, GRUPO_PEDIDO),
        _tope_por_tienda(CLAVE_TOPE_PEDIDO),
    ]


def _claves_operacion() -> list:
    """Las pestañas de Configuración que no son del motor."""
    return (
        _claves_indicadores() + _claves_comisiones() + _claves_avisos()
        + _claves_limpieza() + _claves_conteos() + _claves_ingresos())


def _construir_registro() -> Mapping[str, EspecClave]:
    especs = [
        # Claves de la ingesta F2 (ya en uso en producción).
        _lista_texto(
            "tipos_inventario_incluidos",
            ["REPUESTOS", "ACCESORIOS", "LUBRICANTES", "LLANTAS",
             "BATERIAS", "CASCOS", "GPS"],
        ),
        _booleana("crear_referencias_desconocidas", False, GRUPO_INGESTA),
        _lista_texto("estados_backorder_vigentes", ["BACKORDER"]),
        lista_de_codigos(
            CLAVE_BODEGAS_EXCLUIDAS, list(BODEGAS_EXCLUIDAS_DEFAULT),
            seccion="cargas"),
        tipos_excluidos(
            CLAVE_VENTAS_TIPOS_EXCLUIDOS, _TIPOS_EXCLUIDOS_POR_DEFECTO,
            seccion="cargas"),
        _entera("dias_ventana_ingresos", 45, 1, 3650, GRUPO_INGESTA),
        _decimal("tolerancia_ingreso_pct", 2.0, grupo=GRUPO_INGESTA),
        _decimal(
            "periodo_tolerancia_pct",
            settings.MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT, 100,
            grupo=GRUPO_INGESTA),
        # Interruptores y parámetros del motor (preset legacy por defecto).
        _booleana("incluir_demanda_perdida_en_ponderada", False),
        _decimal("factor_demanda_perdida", "1"),
        _booleana("consolidar_sustituidas", False),
        _entera("dias_entre_pedidos", 30, 1, 60,
                ambito=AMBITO_GLOBAL_Y_SUCURSAL),
        _opcion("modo_mes_en_curso", "EXCLUIDO", ("EXCLUIDO", "PONDERADO")),
        _decimal("tope_proyeccion_mes_actual", "3.0"),
        _entera("min_dias_mes_actual", 5, 1, 28),
        _booleana("excluir_transito_vencido", False),
        _opcion("modo_redondeo_empaque", "CERCANO", ("CERCANO", "ARRIBA")),
        _decimal("corte_abc_a", "0.80", 1, exclusivo=True),
        _decimal("corte_abc_b", "0.95", 1, exclusivo=True),
        _entera("umbral_f", 2, 1, 6),
        _entera("umbral_m", 1, 1, 6),
        _K_FMS,
        _decimal("tolerancia_sobrestock", "0.25"),
        _entera("meses_inventario_muerto", 6, 1, 6),
    ]
    especs += _claves_antiguedad_y_tope() + _claves_operacion()
    return {e.clave: e for e in especs}


REGISTRO: Mapping[str, EspecClave] = _construir_registro()


def claves_motor() -> list:
    """Claves que forman parte del snapshot de una corrida."""
    return [c for c, e in REGISTRO.items() if e.grupo == GRUPO_MOTOR]


def catalogo(grupo: str = GRUPO_MOTOR) -> List[Dict[str, Any]]:
    """Las claves de un grupo, en el orden del registro, para que la
    pantalla de escenarios arme sus campos: `clave`, `tipo`, `dominio`,
    `default` (una copia: el registro no se toca) y, sólo en las de
    opciones, `opciones`. Las claves de otros grupos (el tope de
    presupuesto es PEDIDO) no salen: no son overrides válidos."""
    entradas = []
    for espec in REGISTRO.values():
        if espec.grupo != grupo:
            continue
        entrada = {
            "clave": espec.clave, "tipo": espec.tipo,
            "dominio": espec.dominio, "default": deepcopy(espec.default)}
        if espec.opciones:
            entrada["opciones"] = list(espec.opciones)
        entradas.append(entrada)
    return entradas


def _valor_invalido(espec: EspecClave) -> ErrorParametro:
    return ErrorParametro(
        codigos.E_PARAM_VALOR_INVALIDO,
        codigos.mensaje(
            codigos.E_PARAM_VALOR_INVALIDO,
            clave=espec.clave, detalle=f"se esperaba {espec.dominio}",
        ),
    )


def _espec_o_error(clave: str) -> EspecClave:
    espec = REGISTRO.get(clave)
    if espec is None:
        raise ErrorParametro(
            codigos.E_PARAM_CLAVE_DESCONOCIDA,
            codigos.mensaje(codigos.E_PARAM_CLAVE_DESCONOCIDA, clave=clave),
        )
    return espec


def _validar_ambito(espec: EspecClave, sucursal_id: Any) -> None:
    """E-PARAM-003 (sucursal en clave global) o E-PARAM-004 (global en
    clave sólo-sucursal)."""
    codigo = None
    if sucursal_id is not None and espec.ambito == AMBITO_GLOBAL:
        codigo = codigos.E_PARAM_AMBITO_INVALIDO
    elif sucursal_id is None and espec.ambito == AMBITO_SOLO_SUCURSAL:
        codigo = codigos.E_PARAM_SOLO_SUCURSAL
    if codigo is not None:
        raise ErrorParametro(
            codigo, codigos.mensaje(codigo, clave=espec.clave))


def validar_espec(espec: EspecClave, valor: Any) -> None:
    """E-PARAM-002 si `valor` no cumple la regla de `espec`."""
    if not espec.validar(valor):
        raise _valor_invalido(espec)


def validar_escritura(clave: str, valor: Any, sucursal_id: Any = None) -> None:
    """Valida una escritura NUEVA; lanza `ErrorParametro` codificado."""
    espec = _espec_o_error(clave)
    _validar_ambito(espec, sucursal_id)
    validar_espec(espec, valor)


def validar_umbrales_conteo(reconteo: Any, critico: Any) -> None:
    """E-PARAM-002 si el monto de reconteo no es menor que el crítico."""
    menor, mayor = _numero(reconteo), _numero(critico)
    if menor is not None and mayor is not None and menor < mayor:
        return
    raise ErrorParametro(
        codigos.E_PARAM_VALOR_INVALIDO,
        "El monto que pide reconteo ($ "
        f"{reconteo}) debe ser menor que el monto de diferencia crítica "
        f"($ {critico}).")


# Pares (menor, mayor) de claves que deben guardar ese orden entre sí.
RELACIONES_MENOR = (
    (CLAVE_CONTEO_UMBRAL_RECONTEO, CLAVE_CONTEO_UMBRAL_CRITICO),
)


def claves_relacionadas(clave: str) -> Tuple[str, ...]:
    """Las otras claves con las que `clave` debe guardar un orden."""
    return tuple(
        mayor if clave == menor else menor
        for menor, mayor in RELACIONES_MENOR if clave in (menor, mayor))


def validar_relaciones(
        clave: str, valor: Any, vigentes: Mapping[str, Any]) -> None:
    """Revisa `valor` de `clave` contra la otra clave de cada par de
    `RELACIONES_MENOR`. `vigentes` trae el valor efectivo de las otras
    claves; la que falta toma su default del registro."""
    for menor, mayor in RELACIONES_MENOR:
        if clave not in (menor, mayor):
            continue
        otra = mayor if clave == menor else menor
        actual = vigentes.get(otra, REGISTRO[otra].default)
        if clave == menor:
            validar_umbrales_conteo(valor, actual)
        else:
            validar_umbrales_conteo(actual, valor)


def es_snapshotted(clave: str) -> bool:
    """True si la clave entra al snapshot de cada corrida (grupo MOTOR)."""
    espec = REGISTRO.get(clave)
    return espec is not None and espec.grupo == GRUPO_MOTOR


def normalizar_vigencia(clave: str, vigente_desde: date, hoy: date) -> date:
    """Una versión rige desde el día 1 de un mes: normaliza `vigente_desde`
    a ese día. Una clave del motor se congela en cada corrida, así que no
    admite un mes ya pasado (E-PARAM-005 explicando la regla)."""
    inicio = vigente_desde.replace(day=1)
    if es_snapshotted(clave) and inicio < hoy.replace(day=1):
        detalle = (
            "este parámetro del motor se congela en cada corrida y sólo "
            f"puede regir desde el mes en curso ({hoy:%Y-%m}) o uno "
            f"posterior; {inicio:%Y-%m} ya pasó")
        raise ErrorParametro(
            codigos.E_PARAM_VIGENCIA_PASADA,
            codigos.mensaje(codigos.E_PARAM_VIGENCIA_PASADA,
                            clave=clave, detalle=detalle))
    return inicio


def seccion_de(espec: EspecClave) -> str:
    """La pestaña de la clave: la explícita o la de su grupo."""
    return espec.seccion or _SECCION_POR_GRUPO.get(espec.grupo, "")


def ficha(espec: EspecClave) -> Dict[str, Any]:
    """Todo lo que la pantalla de Configuración lee de una clave (sin sus
    valores guardados). El default es una copia: el registro no se toca."""
    return {
        "clave": espec.clave, "seccion": seccion_de(espec),
        "grupo": espec.grupo, "tipo": espec.tipo, "dominio": espec.dominio,
        "ambito": espec.ambito, "default": deepcopy(espec.default),
        "opciones": list(espec.opciones), "minimo": espec.minimo,
        "maximo": espec.maximo, "minimo_exclusivo": espec.minimo_exclusivo,
        "campos": list(espec.campos),
        "snapshotted": espec.grupo == GRUPO_MOTOR,
    }


def parsear(clave: str, valor: Any) -> Any:
    """Valor tipado para el motor (`Fraction` en los decimales).

    Lanza E-PARAM-002 si el valor guardado no cumple la regla actual.
    """
    espec = _espec_o_error(clave)
    validar_espec(espec, valor)
    return espec.convertir(valor)
