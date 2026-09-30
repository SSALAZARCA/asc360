"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6a, ADR-3/ADR-5/
ADR-11): estados de la corrida y de sus sucursales, y qué transiciones y
guardas los usan.

`EN_REVISION` y `ENVIADA` existen en el CHECK de la tabla pero no son
alcanzables en F3 (los cablea F4).
"""
from app.motored.services.motor.tipos import ESTADO_OK, ESTADO_OMITIDA

PENDIENTE = "PENDIENTE"
CALCULANDO = "CALCULANDO"
FALLIDA = "FALLIDA"
BORRADOR = "BORRADOR"
CERRADA = "CERRADA"
ANULADA = "ANULADA"

# `anular` (tasks S6a-1): una corrida cerrada no se anula en F3.
ANULABLES = frozenset({PENDIENTE, CALCULANDO, FALLIDA, BORRADOR})
# Estados vivos que una carga anulada invalida (ADR-11 paso 3).
INVALIDABLES = frozenset({PENDIENTE, CALCULANDO, BORRADOR, FALLIDA})

SUC_PENDIENTE = "PENDIENTE"
SUC_OK = ESTADO_OK
SUC_OMITIDA = ESTADO_OMITIDA
SUC_FALLIDA = "FALLIDA"

ESTADO_CARGA_ANULADO = "ANULADO"
