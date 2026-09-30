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
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Callable, Mapping, Optional

from app.motored.services.corridas import codigos

AMBITO_GLOBAL = "GLOBAL"
AMBITO_GLOBAL_Y_SUCURSAL = "GLOBAL_Y_SUCURSAL"

GRUPO_INGESTA = "INGESTA"
GRUPO_MOTOR = "MOTOR"


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


def _booleana(clave: str, default: bool, grupo: str = GRUPO_MOTOR):
    return EspecClave(
        clave, default, AMBITO_GLOBAL, grupo, "verdadero o falso",
        lambda v: isinstance(v, bool), _identidad,
    )


def _entera(clave, default, minimo, maximo, grupo=GRUPO_MOTOR,
            ambito=AMBITO_GLOBAL):
    return EspecClave(
        clave, default, ambito, grupo,
        f"un entero entre {minimo} y {maximo}",
        lambda v: _entero(v) and minimo <= v <= maximo, _identidad,
    )


def _decimal(clave, default, maximo=None, exclusivo=False,
             grupo=GRUPO_MOTOR):
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
        clave, default, AMBITO_GLOBAL, grupo, dominio, valido, _numero)


def _opcion(clave: str, default: str, opciones: tuple):
    return EspecClave(
        clave, default, AMBITO_GLOBAL, GRUPO_MOTOR,
        "uno de " + ", ".join(opciones), lambda v: v in opciones, _identidad,
    )


def _lista_texto(clave: str, default: list):
    return EspecClave(
        clave, default, AMBITO_GLOBAL, GRUPO_INGESTA,
        "una lista no vacía de textos",
        lambda v: isinstance(v, list) and len(v) > 0
        and all(isinstance(x, str) and x.strip() for x in v),
        _identidad,
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
    _k_fms_valido, _k_fms_convertido,
)

# Tipos de dato con límite de antigüedad propio (decisión #16).
CLAVES_ANTIGUEDAD = {
    "inventario": "max_dias_antiguedad_inventario",
    "backorder": "max_dias_antiguedad_backorder",
    "facturas": "max_dias_antiguedad_facturas",
    "ingresos": "max_dias_antiguedad_ingresos",
}

_DIAS_ANTIGUEDAD_MAX = 365  # supuesto ajustable (tasks: Open item D)


def _construir_registro() -> Mapping[str, EspecClave]:
    especs = [
        # Claves de la ingesta F2 (ya en uso en producción).
        _lista_texto("tipos_inventario_incluidos", ["0002 - REPUESTOS"]),
        _booleana("crear_referencias_desconocidas", False, GRUPO_INGESTA),
        _lista_texto("estados_backorder_vigentes", ["BACKORDER"]),
        _entera("dias_ventana_ingresos", 45, 1, 3650, GRUPO_INGESTA),
        _decimal("tolerancia_ingreso_pct", 2.0, grupo=GRUPO_INGESTA),
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
    especs += [
        _entera(clave, 7, 1, _DIAS_ANTIGUEDAD_MAX)
        for clave in CLAVES_ANTIGUEDAD.values()
    ]
    return {e.clave: e for e in especs}


REGISTRO: Mapping[str, EspecClave] = _construir_registro()


def claves_motor() -> list:
    """Claves que forman parte del snapshot de una corrida."""
    return [c for c, e in REGISTRO.items() if e.grupo == GRUPO_MOTOR]


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


def validar_escritura(clave: str, valor: Any, sucursal_id: Any = None) -> None:
    """Valida una escritura NUEVA; lanza `ErrorParametro` codificado."""
    espec = _espec_o_error(clave)
    if sucursal_id is not None and espec.ambito == AMBITO_GLOBAL:
        raise ErrorParametro(
            codigos.E_PARAM_AMBITO_INVALIDO,
            codigos.mensaje(codigos.E_PARAM_AMBITO_INVALIDO, clave=clave),
        )
    if not espec.validar(valor):
        raise _valor_invalido(espec)


def parsear(clave: str, valor: Any) -> Any:
    """Valor tipado para el motor (`Fraction` en los decimales).

    Lanza E-PARAM-002 si el valor guardado no cumple la regla actual.
    """
    espec = _espec_o_error(clave)
    if not espec.validar(valor):
        raise _valor_invalido(espec)
    return espec.convertir(valor)
