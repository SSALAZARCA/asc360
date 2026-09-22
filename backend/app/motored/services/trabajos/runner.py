"""
Motored Pedidos — Fase 2 "Ingesta", puerto `JobRunner`
(sdd/motored-pedidos-ingesta, ADR-1).

Este puerto es el único punto de contacto entre la capa API/servicio (Fase
9, todavía no existe) y CÓMO se ejecuta un `carga_archivo` que ya está
persistido como `PENDIENTE`. Dos adaptadores:

- `SupervisorRunner` (producción): NO ejecuta el job él mismo -- solo
  garantiza que el supervisor en proceso esté corriendo
  (`supervisor.ensure_started()`, idempotente y O(1) después de la primera
  llamada). El propio poll loop del supervisor es quien reclama y despacha
  la fila `PENDIENTE` vía el UPDATE atómico.
- `InlineRunner` (toda la suite de tests, y cualquier script que quiera
  ejecución determinística e inmediata): busca el handler registrado para
  `tipo` en `jobs.JOB_HANDLERS` y lo llama directamente, en el mismo
  contexto async del caller -- ningún test funcional necesita un loop de
  fondo, un thread ni el supervisor.

Ningún handler real existe todavía (Fase 3+ los registra en `jobs.py` sin
tocar este archivo).
"""
from __future__ import annotations

import abc
import uuid

from app.motored.services.trabajos import jobs


class JobRunner(abc.ABC):
    """Puerto: abstrae *cómo* se ejecuta un `carga_archivo` ya persistido
    como `PENDIENTE`. El caller nunca debe asumir finalización síncrona
    salvo que use explícitamente `InlineRunner`."""

    @abc.abstractmethod
    async def enqueue(self, carga_id: uuid.UUID, tipo: str) -> None:
        """Garantiza que `carga_id` (ya persistido como `PENDIENTE`)
        termine siendo procesado. Cada implementación decide CUÁNDO y
        DÓNDE -- el caller no debe asumir que ya terminó al volver."""
        raise NotImplementedError


class InlineRunner(JobRunner):
    """Adaptador síncrono: busca el handler registrado para `tipo` en
    `jobs.JOB_HANDLERS` y lo llama directamente. Si nada está registrado
    para `tipo` (cierto para los 8 tipos hasta que la Fase 3+ registre sus
    transforms), es un no-op documentado -- nunca un error. Deliberadamente
    NUNCA importa `supervisor` -- así ningún test funcional necesita un
    poll loop, un thread ni Redis."""

    async def enqueue(self, carga_id: uuid.UUID, tipo: str) -> None:
        handler = jobs.JOB_HANDLERS.get(tipo)
        if handler is None:
            return
        await handler(carga_id)


class SupervisorRunner(JobRunner):
    """Adaptador de producción (ADR-1/1b). Import perezoso de `supervisor`
    (evita cualquier ciclo de import con `jobs`/`runner` y deja clara la
    frontera: solo este adaptador conoce al supervisor)."""

    async def enqueue(self, carga_id: uuid.UUID, tipo: str) -> None:
        from app.motored.services.trabajos import supervisor

        supervisor.ensure_started()
