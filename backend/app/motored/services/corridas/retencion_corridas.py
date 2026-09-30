"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6b, ADR-5b):
retención de corridas.

Se engancha al tick del loop de corridas, igual que la purga de inventario de
F2 (`services/retencion.py`), y reutiliza su ledger: la tabla
`retencion_ejecucion` (con `tabla = 'corrida'`) es a la vez el registro de lo
borrado y el ancla del "¿ya toca?" diario, así que un reinicio no duplica ni
salta un día.

Borra, con cascada a líneas, resumen y sucursales, sólo las corridas
ANULADA, FALLIDA o BORRADOR con más de `MOTORED_CORRIDA_RETENCION_DIAS`
(45) días. NUNCA una CERRADA (es historia del negocio) ni una PENDIENTE o
CALCULANDO (están vivas). Apagada por defecto
(`MOTORED_CORRIDA_RETENCION_ENABLED`); apagada no hace ni una consulta.
"""
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select

from app.config import settings
from app.motored.models.corrida import Corrida
from app.motored.models.retencion_ejecucion import RetencionEjecucion
from app.motored.services import retencion
from app.motored.services.corridas import estados

TABLA_CORRIDA = "corrida"
ESTADOS_PURGABLES = (estados.ANULADA, estados.FALLIDA, estados.BORRADOR)
# Una corrida arrastra ~33.000 líneas: bloques chicos mantienen cortas las
# transacciones.
TAMANO_BLOQUE = 20


async def _borrar_bloque(db, limite: datetime, tamano: int) -> int:
    ids = (await db.execute(
        select(Corrida.id)
        .where(Corrida.estado.in_(ESTADOS_PURGABLES),
               Corrida.created_at < limite)
        .limit(tamano))).scalars().all()
    if not ids:
        return 0
    await db.execute(delete(Corrida).where(Corrida.id.in_(ids)))
    await db.commit()
    return len(ids)


async def ejecutar_si_corresponde(
    db, ahora: datetime, tamano: int = TAMANO_BLOQUE,
) -> Optional[int]:
    """Purga si la retención está encendida y toca (una vez al día).
    Devuelve cuántas corridas borró, o `None` si no corrió."""
    if not settings.MOTORED_CORRIDA_RETENCION_ENABLED:
        return None
    if not await retencion.esta_vencida(db, TABLA_CORRIDA, ahora):
        return None
    inicio = time.monotonic()
    limite = (
        ahora - timedelta(days=settings.MOTORED_CORRIDA_RETENCION_DIAS)
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
