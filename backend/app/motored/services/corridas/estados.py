"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6a, ADR-3/ADR-5/
ADR-11): estados de la corrida y de sus sucursales, y qué transiciones y
guardas los usan.

`EN_REVISION` y `ENVIADA` existen en el CHECK de la tabla pero no son
alcanzables: F4 (sdd/motored-pedidos-ui, ADR-1, decisión F4-14) los deja sin
usar a propósito. La corrida sólo lleva el ciclo del CÁLCULO (PENDIENTE,
CALCULANDO, FALLIDA, BORRADOR = "calculada", ANULADA); el pedido de cada
tienda tiene su propio estado en `corrida_sucursal.estado_pedido`. Una
corrida que F3 dejó `CERRADA` se trata como calculada (`CALCULADAS`) y el
código nuevo ya no escribe `CERRADA` en la corrida.
"""
from app.motored.services.motor.tipos import ESTADO_OK, ESTADO_OMITIDA

PENDIENTE = "PENDIENTE"
CALCULANDO = "CALCULANDO"
FALLIDA = "FALLIDA"
BORRADOR = "BORRADOR"
CERRADA = "CERRADA"
ANULADA = "ANULADA"

# Corridas cuyo cálculo terminó y cuyos pedidos se pueden operar: BORRADOR
# más la CERRADA heredada de F3 (que M1 migra a tiendas CERRADO).
CALCULADAS = frozenset({BORRADOR, CERRADA})

# `anular` (tasks S6a-1): una corrida cerrada no se anula en F3.
ANULABLES = frozenset({PENDIENTE, CALCULANDO, FALLIDA, BORRADOR})
# Estados vivos que una carga anulada invalida (ADR-11 paso 3).
INVALIDABLES = frozenset({PENDIENTE, CALCULANDO, BORRADOR, FALLIDA})

# Estado del pedido de cada tienda (`corrida_sucursal.estado_pedido`);
# NULL = la tienda no tiene pedido.
PEDIDO_BORRADOR = "BORRADOR"
PEDIDO_CERRADO = "CERRADO"
PEDIDO_ENVIADO = "ENVIADO"
PEDIDOS = frozenset({PEDIDO_BORRADOR, PEDIDO_CERRADO, PEDIDO_ENVIADO})

SUC_PENDIENTE = "PENDIENTE"
SUC_OK = ESTADO_OK
SUC_OMITIDA = ESTADO_OMITIDA
SUC_FALLIDA = "FALLIDA"

ESTADO_CARGA_ANULADO = "ANULADO"
