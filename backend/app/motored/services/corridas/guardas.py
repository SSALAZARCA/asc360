"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6a, ADR-11, spec
"Anulación guard for cargas") y F4 B3b (sdd/motored-pedidos-ui, ADR-5, spec
DM-09..DM-12, CI-37): guardas de anulación.

F2 llama a `aplicar_guard_anulacion` desde la anulación de una carga EXCEL
(`api/cargas.py::anular_carga`, cableado en S7):

1. bloquea la fila de la carga (`FOR UPDATE`), así espera a un `cerrar` que
   la tenga tomada `FOR SHARE` y ninguna tienda se cierra a mitad de camino;
2. si el pedido de alguna tienda CERRADO o ENVIADO de una corrida que usó la
   carga (o una corrida que F3 dejó CERRADA, aunque no tenga tienda
   cerrada) depende de ella, rechaza con E-CARGA-050 nombrando la tienda y
   la corrida (la carga queda intacta);
3. las corridas vivas que la usaron (PENDIENTE, CALCULANDO, BORRADOR,
   FALLIDA) quedan `invalidada = true` con el motivo, y la anulación sigue.
   Una tienda reabierta a BORRADOR ya no protege la carga: si era la última
   cerrada, la corrida queda invalidada y la anulación sigue (DM-11).

`exigir_sin_pedidos_cerrados` es la regla de anular una corrida
(E-CORRIDA-051, A6): se rechaza mientras alguna tienda esté CERRADO o
ENVIADO; no hay anulación por tienda.

Sin corridas vinculadas la guarda no hace nada (regresión de F2). Nunca
commitea: la transacción es de quien anula. La carrera residual (un paso de
sucursal que leyó la carga antes de anularse y se vincula después) la cierra
la verificación de `finalizar_corrida` y el filtro ANULADO del cargador.
"""
from typing import List

from sqlalchemy import and_, or_, select, update

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.services.corridas import codigos, estados
from app.motored.services.corridas.codigos import ErrorCorrida

MOTIVO_CARGA_ANULADA = "CARGA_ANULADA"
# Los pedidos que ya no se pueden perder: cerrados (listos para el
# proveedor) o enviados.
_BLOQUEANTES = [estados.PEDIDO_CERRADO, estados.PEDIDO_ENVIADO]
_TIENDAS_EN_MENSAJE = 5


def _corridas_de(carga_id):
    return select(CorridaCarga.corrida_id).where(
        CorridaCarga.carga_id == carga_id)


async def _pedido_bloqueante(db, carga_id):
    """La primera `(corrida, tienda, estado_pedido)` (por código y nombre)
    de una corrida vinculada a la carga que tenga una tienda CERRADO o
    ENVIADO, o que F3 dejó CERRADA (entonces sin tienda: `None`)."""
    cs = CorridaSucursal
    resultado = await db.execute(
        select(Corrida.codigo, Sucursal.nombre, cs.estado_pedido)
        .select_from(CorridaCarga)
        .join(Corrida, Corrida.id == CorridaCarga.corrida_id)
        .outerjoin(cs, and_(
            cs.corrida_id == Corrida.id,
            cs.estado_pedido.in_(_BLOQUEANTES)))
        .outerjoin(Sucursal, Sucursal.id == cs.sucursal_id)
        .where(CorridaCarga.carga_id == carga_id,
               or_(Corrida.estado == estados.CERRADA,
                   cs.corrida_id.is_not(None)))
        .order_by(Corrida.codigo, Sucursal.nombre)
        .limit(1))
    return resultado.first()


async def aplicar_guard_anulacion(db, carga) -> List[str]:
    """Aplica la guarda; devuelve los códigos de las corridas invalidadas."""
    await db.execute(
        select(CargaArchivo.id)
        .where(CargaArchivo.id == carga.id)
        .with_for_update())
    bloqueo = await _pedido_bloqueante(db, carga.id)
    if bloqueo is not None:
        corrida, tienda, estado = bloqueo
        raise ErrorCorrida(
            codigos.E_CARGA_ANULACION_BLOQUEADA,
            codigos.mensaje_carga_bloqueada(corrida, tienda, estado),
            {"corrida": corrida, "tienda": tienda, "estado_pedido": estado})
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


def _tiendas_en_mensaje(filas: list) -> str:
    """"Nombre (ESTADO), ..." de las primeras tiendas y cuántas más hay."""
    nombradas = [
        f"{nombre} ({estado})"
        for nombre, estado in filas[:_TIENDAS_EN_MENSAJE]]
    resto = len(filas) - len(nombradas)
    texto = ", ".join(nombradas)
    return f"{texto} y {resto} más" if resto > 0 else texto


async def exigir_sin_pedidos_cerrados(db, corrida_id) -> None:
    """E-CORRIDA-051: la corrida no se anula mientras alguna de sus tiendas
    esté CERRADO o ENVIADO. El llamador ya tiene la corrida `FOR UPDATE`, así
    que ninguna operación por tienda (todas la toman `FOR SHARE`) corre a la
    vez y el estado leído es el definitivo."""
    cs = CorridaSucursal
    filas = (await db.execute(
        select(Sucursal.nombre, cs.estado_pedido)
        .join(Sucursal, Sucursal.id == cs.sucursal_id)
        .where(cs.corrida_id == corrida_id,
               cs.estado_pedido.in_(_BLOQUEANTES))
        .order_by(Sucursal.nombre))).all()
    if filas:
        raise ErrorCorrida(
            codigos.E_CORRIDA_ANULAR_CON_PEDIDOS,
            codigos.mensaje(
                codigos.E_CORRIDA_ANULAR_CON_PEDIDOS,
                tiendas=_tiendas_en_mensaje(filas)),
            {"tiendas": [
                {"tienda": nombre, "estado_pedido": estado}
                for nombre, estado in filas]})
