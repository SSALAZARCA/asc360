"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6b, ADR-5b):
retención de corridas.

Se engancha al tick del loop de corridas, igual que la purga de inventario de
F2 (`services/retencion.py`), y reutiliza su ledger: la tabla
`retencion_ejecucion` (con `tabla = 'corrida'`) es a la vez el registro de lo
borrado y el ancla del "¿ya toca?" diario, así que un reinicio no duplica ni
salta un día.

Borra, con cascada a líneas, resumen y sucursales, sólo las corridas
ANULADA, FALLIDA o BORRADOR con más de `retencion_corridas_dias` (por
defecto `MOTORED_CORRIDA_RETENCION_DIAS`, 45) días. NUNCA una CERRADA (es
historia del negocio) ni una PENDIENTE o
CALCULANDO (están vivas). Fase 4 (B3a): tampoco una corrida cuyo pedido de
alguna tienda ya tuvo un evento (cerrado, reabierto, enviado) o está CERRADO
o ENVIADO: el cálculo sigue en BORRADOR pero el pedido es historia (y un
envío tiene `corrida_envio` con ON DELETE RESTRICT). Apagada por defecto
(`retencion_corridas_habilitada`, con `MOTORED_CORRIDA_RETENCION_ENABLED`
de respaldo). Los ajustes se leen UNA vez por ciclo: un cambio rige desde la
próxima corrida de la purga, nunca a mitad de una.
"""
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, exists, select

from app.config import settings
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.models.retencion_ejecucion import RetencionEjecucion
from app.motored.services import parametros, retencion
from app.motored.services.corridas import estados

TABLA_CORRIDA = "corrida"
CLAVE_HABILITADA = "retencion_corridas_habilitada"
CLAVE_DIAS = "retencion_corridas_dias"
# Último valor leído de la Configuración: un fallo de lectura lo conserva.
_memoria_config: dict = {}
ESTADOS_PURGABLES = (estados.ANULADA, estados.FALLIDA, estados.BORRADOR)
# Una corrida arrastra ~33.000 líneas: bloques chicos mantienen cortas las
# transacciones.
TAMANO_BLOQUE = 20


def _sin_pedido_vivo():
    """La corrida no tiene eventos de pedido ni tiendas CERRADO o ENVIADO."""
    con_evento = exists().where(PedidoEvento.corrida_id == Corrida.id)
    con_tienda = exists().where(
        CorridaSucursal.corrida_id == Corrida.id,
        CorridaSucursal.estado_pedido.in_(
            (estados.PEDIDO_CERRADO, estados.PEDIDO_ENVIADO)))
    return ~con_evento, ~con_tienda


async def _borrar_bloque(db, limite: datetime, tamano: int) -> int:
    ids = (await db.execute(
        select(Corrida.id)
        .where(Corrida.estado.in_(ESTADOS_PURGABLES),
               Corrida.created_at < limite, *_sin_pedido_vivo())
        .limit(tamano))).scalars().all()
    if not ids:
        return 0
    await db.execute(delete(Corrida).where(Corrida.id.in_(ids)))
    await db.commit()
    return len(ids)


async def leer_config(db, ahora: datetime) -> retencion.ConfigRetencion:
    """Una lectura por ciclo. Nunca lanza: un fallo conserva el último
    valor conocido y, sin él, las variables de entorno."""
    valores = await parametros.leer_con_memoria(
        db, ahora.date(),
        {CLAVE_HABILITADA: settings.MOTORED_CORRIDA_RETENCION_ENABLED,
         CLAVE_DIAS: settings.MOTORED_CORRIDA_RETENCION_DIAS},
        _memoria_config)
    return retencion.ConfigRetencion(
        valores[CLAVE_HABILITADA], valores[CLAVE_DIAS])


async def ejecutar_si_corresponde(
    db, ahora: datetime, tamano: int = TAMANO_BLOQUE,
) -> Optional[int]:
    """Purga si la retención está encendida y toca (una vez al día).
    Devuelve cuántas corridas borró, o `None` si no corrió."""
    config = await leer_config(db, ahora)
    if not config.habilitada:
        return None
    if not await retencion.esta_vencida(db, TABLA_CORRIDA, ahora):
        return None
    inicio = time.monotonic()
    limite = (
        ahora - timedelta(days=config.dias)
    ).replace(tzinfo=None)
    total = 0
    while True:
        borradas = await _borrar_bloque(db, limite, tamano)
        total += borradas
        if borradas < tamano:
            break
    db.add(RetencionEjecucion(
        tabla=TABLA_CORRIDA,
        ejecutado_en=ahora.replace(tzinfo=None),
        fecha_limite=limite.date(),
        filas_eliminadas=total,
        duracion_ms=int((time.monotonic() - inicio) * 1000)))
    await db.commit()
    return total
