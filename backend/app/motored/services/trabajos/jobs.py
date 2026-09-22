"""
Motored Pedidos — Fase 2 "Ingesta", registro de handlers por `tipo`
(sdd/motored-pedidos-ingesta, ADR-1; ver `runner.py` y `supervisor.py`).

Alcance de esta fase: SOLO el mecanismo de registro. Ningún handler real
se registra acá todavía -- los transforms de movimiento (`VENTAS`,
`INVENTARIO`, etc., Fase 3+) llamarán `register_job(tipo, handler)` desde
su propio módulo (`services/ingesta/*.py`), sin necesitar tocar este
archivo, `runner.py` ni `supervisor.py`.
"""
from __future__ import annotations

import uuid
from typing import Awaitable, Callable, Dict

# Un handler recibe el `carga_id` ya reclamado (estado `PROCESANDO`) y hace
# todo su trabajo -- parseo, staging, commits por lote -- de forma async.
JobHandler = Callable[[uuid.UUID], Awaitable[None]]

JOB_HANDLERS: Dict[str, JobHandler] = {}


def register_job(tipo: str, handler: JobHandler) -> None:
    """Registra `handler` para `tipo`. Un registro posterior para el mismo
    `tipo` pisa al anterior -- intencional, para que un test pueda
    reemplazar un handler sin necesitar un seam de
    `app.dependency_overrides`."""
    JOB_HANDLERS[tipo] = handler
