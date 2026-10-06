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

## Owner change (2026-10-06): one page, four figures
Inicio now looks the same for every role that reaches it (ADMIN, COMPRAS, GERENCIA, SERVICIO_CLIENTE). It shows the greeting and 4 stat boxes, with no links. "Para hoy", "Ir a", "Estado de los datos" and the per-role logic were removed; git history keeps them.

| ID | Task | Route |
|---|---|---|
| T2 | `GET /api/motored/inicio` returns `{hoy, ventas_mes, ventas_anio, puntos_venta, asesores}`. Each figure is computed on its own savepoint and fails soft. The page shows the greeting plus 4 KPI-style boxes with tooltips. | delegated writer (2+ non-trivial files) |

- [x] T2

### T2 log
- Repuestos sales reuse the KPI Ventas tab's own path: `cargar_filtro` (HMCL incluir, all stores), then `kpi_resumen_lectura.cubo` by store, then `acumular_cubo`, then `venta_por_linea["REPUESTOS"]`.
  - A sale is `valor_bruto - valor_descuentos`, and annulled loads are excluded.
  - The line is `referencia.linea_comercial`, normalized, among the configured `lineas_comerciales`.
- A cube by the total dimension is keyed TOTAL, and `acumular_cubo` would count it twice. So the store dimension is used, as the tab does.
- `puntos_venta` uses `tablero_kpis_consultas.consultar_tiendas_activas` (active principals). `asesores` counts `vendedor.activo`.
- The pg_real test asserts that both sales figures equal `calcular_kpis_ventas(...)["total"]["venta"]["por_linea"]["REPUESTOS"]`.
- Results:
  - tests/motored: 5837 passed.
  - pg_real (full, PG 18 throwaway): 654 passed, 3 skipped.
  - jest: 2089 passed.
