"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6a, ADR-11, spec
"Anulación guard for cargas"): gancho de la guarda de anulación de cargas.

F2 llama a `aplicar_guard_anulacion` desde la anulación de una carga EXCEL
(el cableado en `api/cargas.py` es de S7):

1. bloquea la fila de la carga (`FOR UPDATE`), así espera a un `cerrar` que
   la tenga tomada `FOR SHARE` y ninguna corrida se cierra a mitad de camino;
2. si una corrida CERRADA usó la carga, rechaza con E-CARGA-050 nombrando el
   código de la corrida (la carga queda intacta);
3. las corridas vivas que la usaron (PENDIENTE, CALCULANDO, BORRADOR,
   FALLIDA) quedan `invalidada = true` con el motivo, y la anulación sigue.

Sin corridas vinculadas no hace nada (regresión de F2). Nunca commitea: la
transacción es de quien anula. La carrera residual (un paso de sucursal que
leyó la carga antes de anularse y se vincula después) la cierra la
verificación de `finalizar_corrida` y el filtro ANULADO del cargador.
"""
from typing import List

from sqlalchemy import select, update

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.services.corridas import codigos, estados
from app.motored.services.corridas.codigos import ErrorCorrida

MOTIVO_CARGA_ANULADA = "CARGA_ANULADA"


def _corridas_de(carga_id):
    return select(CorridaCarga.corrida_id).where(
        CorridaCarga.carga_id == carga_id)


async def _corrida_cerrada(db, carga_id):
    resultado = await db.execute(
        select(Corrida.codigo)
        .join(CorridaCarga, CorridaCarga.corrida_id == Corrida.id)
        .where(CorridaCarga.carga_id == carga_id,
               Corrida.estado == estados.CERRADA)
        .order_by(Corrida.codigo)
        .limit(1))
    return resultado.scalars().first()


async def aplicar_guard_anulacion(db, carga) -> List[str]:
    """Aplica la guarda; devuelve los códigos de las corridas invalidadas."""
    await db.execute(
        select(CargaArchivo.id)
        .where(CargaArchivo.id == carga.id)
        .with_for_update())
    cerrada = await _corrida_cerrada(db, carga.id)
    if cerrada is not None:
        raise ErrorCorrida(
            codigos.E_CARGA_ANULACION_BLOQUEADA,
            codigos.mensaje(
                codigos.E_CARGA_ANULACION_BLOQUEADA, corrida=cerrada))
    invalidadas = await db.execute(
        update(Corrida)
        .where(Corrida.id.in_(_corridas_de(carga.id)),
               Corrida.estado.in_(sorted(estados.INVALIDABLES)))
        .values(
            invalidada=True,
            motivo_invalidacion={
                "tipo": MOTIVO_CARGA_ANULADA, "carga_id": str(carga.id)})
        .returning(Corrida.codigo)
        .execution_options(synchronize_session=False))
    return list(invalidadas.scalars().all())
