# Motored: welcome page ("Inicio")

## Objective
Every user with screens lands on "Inicio" after login: a greeting with their name and role, today's pending items with real numbers, quick links to their screens, and, for ADMIN and COMPRAS, the data status that the pedido depends on.

## Owner decisions (2026-10-05)
- The design is approved as shown in https://claude.ai/artifact/3UZntvzVbxRJxJ6JgM6yqV (source: scratchpad `inicio/project/Main.dc.html`).
- Roles:
  - **ADMIN:** pedidos en borrador, datos por vencer, detractores sin gestionar, plus data status.
  - **COMPRAS:** pedidos en borrador, datos por vencer, último pedido enviado, plus data status.
  - **GERENCIA:** venta del mes against budget, tiendas en verde, tiendas en rojo.
  - **SERVICIO_CLIENTE:** detractores sin gestionar, encuestas cargadas este mes.
- SUCURSAL and CONSULTA stay blocked (28f7ff5): no Inicio, they keep landing on mi-cuenta. ASESOR_MOSTRADOR has no web access.

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Backend `GET /api/motored/inicio` that composes existing services into role-aware sections; each section fails soft. Frontend page `/motored/inicio` following the design, an "Inicio" sidebar item at the top, and `homePathFor` sending roles with screens to Inicio. | delegated writer |

- [x] T1

## Checks
- Backend: `tests/motored` plus pg_real.
- Frontend: full jest.
- Test-first.

## Log
- 2026-10-05: T1 done.
  - `GET /api/motored/inicio` (`services/inicio.py`) builds role-aware sections. Each section runs in its own savepoint and fails soft.
  - Reused: `resumen_pedidos`, `vigencia.cargar_hechos` / `elegir_carga_vigente`, `avisos_antiguedad`, `caso_detractor.listar`, and `tablero_kpis.calcular_kpis_ventas` (semáforo thresholds come from config; "rojo" maps to violeta).
  - Page `/motored/inicio`, with an "Inicio" sidebar item first. `homePathFor` sends roles with screens to Inicio.
  - Also fixed: the pg forced-password test used CONSULTA, which has been blocked since df709fc.
  - Results: tests/motored 5850 passed; pg_real 654 passed plus the fixed test; jest 2088 passed.
