"""
Motored Pedidos — tablero de salud de maestros (sdd/motored-pedidos-
cimientos, Fase 3, task 3.5, §7.12). Clasificación:

- `sucursal` sin `sic` -> el ÚNICO hallazgo BLOQUEANTE. Solo tiendas
  principales: una tienda asociada nunca tiene pedido propio.
- Tienda activa sin Código C.O. (centro de operación del ERP) ->
  ADVERTENCIA.
- Tienda asociada con su principal inactiva, o tienda asociada activa (no
  tendrá pedido propio) -> ADVERTENCIA.
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
from typing import Callable, List, Optional, Sequence

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


def _sucursales_sin_sic(sucursales: Sequence[Sucursal]) -> List[Hallazgo]:
    """Active PRINCIPAL stores without SIC. An associated store never gets
    its own pedido, so it does not need a SIC."""
    return [
        Hallazgo(
            tipo="sucursal_sin_sic", entidad="sucursal", entidad_id=s.id,
            mensaje=f"Sucursal '{s.nombre}' no tiene SIC asignado",
            bloqueante=True,
        )
        for s in sucursales
        if s.activa and s.sic is None and s.principal_id is None
    ]


def _sucursales_sin_codigo_co(
    sucursales: Sequence[Sucursal],
) -> List[Hallazgo]:
    """Active stores without their ERP code (C.O.). A warning: the code
    tells stores apart, but nothing is computed from it yet."""
    return [
        Hallazgo(
            tipo="sucursal_sin_codigo_co", entidad="sucursal",
            entidad_id=s.id, bloqueante=False,
            mensaje=f"Sucursal '{s.nombre}' no tiene Código C.O. asignado",
        )
        for s in sucursales
        if s.activa and s.codigo_co is None
    ]


def _aviso_de_asociada(
    asociada: Sucursal, principal: Sucursal
) -> Optional[Hallazgo]:
    if not principal.activa:
        return Hallazgo(
            tipo="asociada_principal_inactiva", entidad="sucursal",
            entidad_id=asociada.id, bloqueante=False,
            mensaje=(
                f"La sucursal '{asociada.nombre}' está asociada a "
                f"'{principal.nombre}', que está inactiva: su pedido y sus "
                "indicadores se suman a una tienda cerrada."
            ),
        )
    if asociada.activa:
        return Hallazgo(
            tipo="asociada_activa", entidad="sucursal",
            entidad_id=asociada.id, bloqueante=False,
            mensaje=(
                f"La sucursal '{asociada.nombre}' está activa pero asociada "
                f"a '{principal.nombre}': no tiene pedido propio, se suma "
                "al de su tienda principal."
            ),
        )
    return None


def _hallazgos_de_asociadas(sucursales: Sequence[Sucursal]) -> List[Hallazgo]:
    """Associated stores whose principal is inactive, and active associated
    stores (they never get their own pedido). Warnings, never blocking."""
    por_id = {s.id: s for s in sucursales}
    avisos = (
        _aviso_de_asociada(s, por_id[s.principal_id])
        for s in sucursales if s.principal_id in por_id
    )
    return [aviso for aviso in avisos if aviso is not None]


async def evaluar_salud(db) -> SaludMaestros:
    hallazgos: List[Hallazgo] = []

    sucursales = (await db.execute(select(Sucursal))).scalars().all()
    hallazgos += _sucursales_sin_sic(sucursales)
    hallazgos += _sucursales_sin_codigo_co(sucursales)
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
        # Se muestra en la pestaña Sucursales: la pestaña Bodegas ya no existe,
        # las bodegas se administran desde "Bodegas secundarias" de cada tienda.
        entidad="sucursal",
        mensaje_fn=lambda b: (
            f"La bodega '{b.codigo}' no está asociada a ninguna sucursal; "
            "agréguela en 'Bodegas secundarias' de su sucursal."
        ),
        bloqueante=False,
    )

    hallazgos += _hallazgos_de_asociadas(sucursales)

    if any(h.bloqueante for h in hallazgos):
        estado = "bloqueado"
    elif hallazgos:
        estado = "advertencia"
    else:
        estado = "verde"

    return SaludMaestros(estado=estado, hallazgos=hallazgos)
