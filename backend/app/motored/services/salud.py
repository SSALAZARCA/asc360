"""
Motored Pedidos — tablero de salud de maestros (sdd/motored-pedidos-
cimientos, Fase 3, task 3.5, §7.12). Clasificación:

- `sucursal` sin `sic` -> el ÚNICO hallazgo BLOQUEANTE.
- Referencia activa sin `precio_normal`, `unidad_empaque` corregido (fila
  con `unidad_empaque_advertencia = true`), bodega sin `sucursal_id` ->
  siempre ADVERTENCIA, nunca bloqueante (spec "Masters health board").

Nota de alcance (Fase 1): no existe todavía ningún dato de demanda
(`venta_mensual` es de Fase 2), así que "referencia con demanda pero sin
precio" se aproxima con "referencia ACTIVA sin `precio_normal`" -- toda
referencia activa es, por definición en Fase 1, potencialmente ordenable, y
es el proxy más cercano disponible sin la tabla de demanda real. Documentado
como desviación en el apply-progress.
"""
from typing import Callable, List

from sqlalchemy import Select, select

from app.motored.models.bodega import Bodega
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.salud import Hallazgo, SaludMaestros


async def _hallazgos_de(
    db, stmt: Select, tipo: str, entidad: str, mensaje_fn: Callable[[object], str], bloqueante: bool
) -> List[Hallazgo]:
    """Ejecuta `stmt` y arma un `Hallazgo` por fila encontrada -- las 4
    reglas del tablero de salud comparten esta misma forma (query -> por
    cada fila, un hallazgo con el mismo `tipo`/`bloqueante`), solo cambia
    la condición del query y el mensaje."""
    filas = (await db.execute(stmt)).scalars().all()
    return [
        Hallazgo(tipo=tipo, entidad=entidad, entidad_id=fila.id, mensaje=mensaje_fn(fila), bloqueante=bloqueante)
        for fila in filas
    ]


async def evaluar_salud(db) -> SaludMaestros:
    hallazgos: List[Hallazgo] = []

    hallazgos += await _hallazgos_de(
        db,
        select(Sucursal).where(Sucursal.activa == True, Sucursal.sic.is_(None)),  # noqa: E712
        tipo="sucursal_sin_sic",
        entidad="sucursal",
        mensaje_fn=lambda s: f"Sucursal '{s.nombre}' no tiene SIC asignado",
        bloqueante=True,
    )
    hallazgos += await _hallazgos_de(
        db,
        select(Referencia).where(Referencia.activa == True, Referencia.precio_normal.is_(None)),  # noqa: E712
        tipo="referencia_sin_precio",
        entidad="referencia",
        mensaje_fn=lambda r: f"Referencia '{r.codigo}' no tiene precio_normal",
        bloqueante=False,
    )
    hallazgos += await _hallazgos_de(
        db,
        select(Referencia).where(Referencia.unidad_empaque_advertencia == True),  # noqa: E712
        tipo="unidad_empaque_corregida",
        entidad="referencia",
        mensaje_fn=lambda r: f"Referencia '{r.codigo}' tenía unidad_empaque 0/nulo -- corregida a 1",
        bloqueante=False,
    )
    hallazgos += await _hallazgos_de(
        db,
        select(Bodega).where(Bodega.activa == True, Bodega.sucursal_id.is_(None)),  # noqa: E712
        tipo="bodega_sin_sucursal",
        entidad="bodega",
        mensaje_fn=lambda b: f"Bodega '{b.codigo}' no está asociada a ninguna sucursal",
        bloqueante=False,
    )

    if any(h.bloqueante for h in hallazgos):
        estado = "bloqueado"
    elif hallazgos:
        estado = "advertencia"
    else:
        estado = "verde"

    return SaludMaestros(estado=estado, hallazgos=hallazgos)
