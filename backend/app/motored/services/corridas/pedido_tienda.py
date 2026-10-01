"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B1,
ADR-1, decisión F4-14): el pedido de cada tienda de una corrida.

La corrida es sólo el lote de cálculo; cada `(corrida, sucursal)` con pedido
tiene su propio estado en `corrida_sucursal.estado_pedido`. Este módulo
reúne las reglas del ciclo de vida por tienda. Por ahora sólo trae el
arranque: `iniciar_pedidos` deja BORRADOR el pedido de las tiendas OK de una
corrida real recién calculada. Cerrar, reabrir y enviar llegan en B3a y B3b.

Ningún commit acá: la transacción es del llamador.
"""
from uuid import UUID

from sqlalchemy import select, update

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services.corridas import estados


async def iniciar_pedidos(db, corrida_id: UUID) -> None:
    """NULL -> BORRADOR en las tiendas OK de la corrida, salvo escenario.

    Una tienda FALLIDA u OMITIDA no tiene pedido (queda NULL) y un
    escenario nunca lo tiene (es sólo de prueba). Se corre en la misma
    transacción que cierra el cálculo (CALCULANDO -> BORRADOR)."""
    es_escenario = select(Corrida.id).where(
        Corrida.id == corrida_id, Corrida.es_escenario.is_(True))
    await db.execute(
        update(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida_id,
               CorridaSucursal.estado == estados.SUC_OK,
               ~es_escenario.exists())
        .values(estado_pedido=estados.PEDIDO_BORRADOR)
        .execution_options(synchronize_session=False))
