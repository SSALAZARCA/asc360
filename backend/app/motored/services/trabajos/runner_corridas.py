"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6b, ADR-5): puerto
`CorridaRunner`, el equivalente para corridas del `JobRunner` de F2 (sin
compartir su registro de handlers).

Es el único punto de contacto entre la API (S7) y CÓMO se ejecuta una corrida
ya persistida como PENDIENTE. Dos adaptadores:

- `SupervisorCorridaRunner` (producción): no ejecuta nada; sólo garantiza
  que el loop de corridas esté corriendo. Es el propio loop quien reclama y
  ejecuta la fila con su UPDATE atómico.
- `InlineCorridaRunner` (tests y scripts): reclama esa corrida y la ejecuta
  hasta el final en el contexto async del llamador, sin loop de fondo.
"""
import abc
from uuid import UUID

from app.motored.services.corridas import ejecucion
from app.motored.services.trabajos import supervisor_corridas


class CorridaRunner(abc.ABC):
    """Puerto: abstrae cómo se ejecuta una corrida PENDIENTE. El llamador no
    debe asumir que terminó al volver, salvo con `InlineCorridaRunner`."""

    @abc.abstractmethod
    async def enqueue(self, corrida_id: UUID) -> None:
        """Garantiza que `corrida_id` (PENDIENTE) termine ejecutándose."""
        raise NotImplementedError


class InlineCorridaRunner(CorridaRunner):
    """Reclama y ejecuta la corrida en línea, sin loop ni ejecutor."""

    async def enqueue(self, corrida_id: UUID) -> None:
        await ejecucion.reclamar_y_ejecutar(corrida_id)


class SupervisorCorridaRunner(CorridaRunner):
    """Adaptador de producción: sólo asegura el loop en marcha."""

    async def enqueue(self, corrida_id: UUID) -> None:
        supervisor_corridas.ensure_started()
