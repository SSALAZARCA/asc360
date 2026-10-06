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

## Owner correction (2026-10-06): sales are the KPI total, asesores are the ones with sales
The sales figures were only the Repuestos line. They must equal the KPI Ventas tab's headline: "Venta 1 mes" (Sep 2026, $1.872 M) and "Venta 9 meses" (Jan–Sep 2026, $15.092 M), the total of all the commercial lines. Asesores means the asesores with sales in the last complete month.

| ID | Task | Route |
|---|---|---|
| T3 | `ventas_mes` / `ventas_anio` = `calcular_kpis_ventas(...)["total"]["venta"]["total"]` for the last complete month and the KPI "Año corrido". `asesores` = KPIs › Asesores "con venta" for the last complete month (`{cantidad, mes}`). Titles drop "— Repuestos"; tooltips name the lines and the KPI equality; the Asesores subtitle shows the month. | delegated writer (2+ non-trivial files) |

- [x] T3

### T3 log
- Sales: `inicio._acumulados` replays the KPI read (`cargar_filtro` with HMCL incluir and all stores, `fecha_corte_costos`, `cubo` by store, `filtrar_cubo_por_hmcl`, `acumular_cubo`). `venta_kpi` returns `round(acum[TOTAL].venta, 2)`, which is `_bloque_venta`'s `"total"`, shown by the KPI front as "Venta N meses" (`kpis/ventas/datos.js` `miniKpis`).
- "Año corrido" in the KPI runs from January to `ultimo_mes`, the last month with sales (`tablero_kpis.calcular_opciones`, `periodo.js` `presetMeses('ytd')`). It is not "last complete month". Inicio uses the same rule, so `ventas_anio` is `{valor, desde: "AAAA-01", hasta: ultimo_mes}`. Once the current month has loaded sales, it includes that month, exactly like the KPI. With no sales at all it returns `{valor: 0, desde: null, hasta: null}`.
- Asesores: the KPI front counts `filas` with `tipo == "PERSONA"` and `venta.total > 0` (`kpis/asesores/datos.js` `miniKpisAsesores`). A PERSONA is an active vendedor whose cargo maps to a person in `grupo_por_cargo`, identified by cedula (`_expr_clave`). Inicio counts the same keys (`es_clave_persona`) in the asesor cube of the last complete month. The old count (`vendedor.activo` in the master) is gone.
- RED observed: unit tests 8 failed; pg_real `ventas_mes` failed against the HEAD service; jest 10 failed. All GREEN after the change.
- Results:
  - tests/motored: 5839 passed.
  - pg_real (full, PG 18 throwaway): 654 passed, 3 skipped.
  - jest: 2092 passed.
