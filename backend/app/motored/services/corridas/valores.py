"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2,
ADR-3, ADR-4): reglas PURAS del valor y de la cantidad a pedir.

- `valor` repite la cuantización del motor (`cantidad x precio`, mitad lejos
  de cero a 2 decimales, 0.00 si falta el precio): una edición deja
  `valor_pedido` igual a lo que habría calculado el motor con esa cantidad.
- `valor_sugerido` lo deriva del sugerido guardado: `valor_pedido` ya no es
  una salida del motor desde que el comprador edita la cantidad.
- `validar_cantidad` es la regla de E-CORRIDA-053.
- `fuera_de_empaque` es el aviso de múltiplo del empaque: nunca corrige ni
  bloquea.
- `escapar_like` hace literales los comodines del filtro `q`.

Sin base de datos ni HTTP.
"""
from decimal import Decimal
from typing import Any, Optional

from app.motored.services.corridas import codigos
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.motor.aritmetica import a_fraccion, cuantizar

CANTIDAD_MAXIMA = 9_999_999
_CERO = Decimal("0.00")


def valor(cantidad: Any, precio: Any) -> Decimal:
    """`cantidad x precio` a 2 decimales (mitad lejos de cero); 0.00 sin
    precio."""
    if precio is None:
        return _CERO
    return cuantizar(a_fraccion(cantidad) * a_fraccion(precio), 2)


def valor_sugerido(linea: Any) -> Decimal:
    """El valor del pedido SUGERIDO por el motor (0.00 sin sugerido o sin
    precio, como en las líneas excluidas)."""
    if linea.pedido_sugerido is None:
        return _CERO
    return valor(linea.pedido_sugerido, linea.precio)


def validar_cantidad(bruto: Any) -> int:
    """La cantidad a pedir: un entero entre 0 y 9.999.999.

    Todo lo demás (negativos, decimales, texto, `null`, booleanos, listas)
    es E-CORRIDA-053. Un `float` se rechaza aunque sea entero: la pantalla
    manda enteros y aceptar `60.0` abriría la puerta a `2.5`."""
    if isinstance(bruto, bool) or not isinstance(bruto, int) \
            or not 0 <= bruto <= CANTIDAD_MAXIMA:
        raise ErrorCorrida(
            codigos.E_CORRIDA_CANTIDAD_INVALIDA,
            codigos.mensaje(codigos.E_CORRIDA_CANTIDAD_INVALIDA))
    return bruto


def fuera_de_empaque(cantidad: Optional[Decimal], empaque: Any) -> bool:
    """Cantidad positiva que no es múltiplo del empaque (aviso, no error)."""
    if cantidad is None or not empaque or empaque <= 0 or cantidad <= 0:
        return False
    return cantidad % empaque != 0


def escapar_like(texto: str) -> str:
    """Escapa `\\`, `%` y `_` para un `LIKE ... ESCAPE '\\'` literal."""
    for caracter in ("\\", "%", "_"):
        texto = texto.replace(caracter, "\\" + caracter)
    return texto
