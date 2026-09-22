"""
Motored Pedidos — Fase 2 "Ingesta", capa de ejecución de trabajos
(sdd/motored-pedidos-ingesta, ADR-1/ADR-1b).

- `runner.py` — el puerto `JobRunner` y sus dos adaptadores
  (`SupervisorRunner`/`InlineRunner`).
- `supervisor.py` — el supervisor asyncio en proceso: arranque perezoso,
  claim atómico, sweep de heartbeat (recuperación de caídas) y el flush de
  mejor esfuerzo ante `SIGTERM`.
- `jobs.py` — el registro `tipo -> handler`, vacío en esta fase. La Fase 3+
  registra los transforms reales sin tocar ninguno de los otros dos
  módulos.
"""
