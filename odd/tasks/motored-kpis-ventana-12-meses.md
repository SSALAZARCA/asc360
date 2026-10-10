# Motored KPI's: monthly charts over a fixed 12-month window

## Objective
Four monthly charts stop following the Período filter and always show the LAST 12 MONTHS ending at the last month with sales.

## Decision (user, 2026-10-09)
- The window ends at `ultimo_mes` (the last month with sales) and never starts before the first month with data (no empty padding), so with today's history (Jan-Oct 2026) it is just the months available.
- The store filter (`sucursales`) and the HMCL mode keep applying; the rules (Configuración) are the period filter's.
- Blocks, all other blocks of those tabs keep following the period:
  1. Ventas: "Venta mensual por línea" (stacked area and its line tiles).
  2. Ventas: "Clientes Tecnired" card (donut, bars, line split, header chip, title with the window months). The top 5 stays the period's.
  3. Tiendas: "Venta mensual por tienda · vs su promedio" heatmap.
  4. Asesor detail ("Tendencia de cumplimiento"), shared by the Asesores tab and the public daily-report link.
- UI: a muted note under each title: "Últimos 12 meses · no cambia con el período".

## Design
- `tablero_asesores.meses_de_ventana(disponibles)` (pure) and `filtro_con_meses(filtro, meses)` (same stores / HMCL / rules over other months).
- `tablero_kpis._filtro_de_ventana_12m` reads `lectura.meses` (summary or live) and builds the window filter.
- Ventas: `ventana_meses` + `ventana {total, tecnired}`; Tiendas: `ventana_meses` + `ventana {tiendas}`; Asesor detail: `ventana_meses` and `tendencia` now over the window. Field names inside the blocks are the existing ones.
- When the window equals the period nothing is recomputed. Otherwise the blocks are built with the existing builders on a second `Filtro`, reading the summaries when they answer.
- The window total carries no `costo` (its cube is read without the inventory cut-off; the live query then has no cost while the summary always has it).
- The public link needs no endpoint change: `informe_publico.detalle_del_anio` calls `calcular_kpis_asesor_detalle`, and the page renders the shared `AsesorDetalle`.

## Tasks
- [x] **V1 Backend** pure window helpers + Ventas / Tiendas / Asesor detail blocks + tests (unit, pg_real live and summary, golden).
- [x] **V2 Frontend** blocks render from the window, titles use `ventana_meses`, the note under four titles + jest.

## Evidence
- RED observed before each change (unit helpers: 4 failed; pg_real: 7 failed with KeyError 'ventana_meses'; jest: 6 failed).
- Route: delegated writer, inline (the change crosses backend and frontend files that were read to prepare the write).
- Golden: regenerated; besides the new `ventana*` keys it carries a pre-existing drift (the default `comision_cargos_asesor` already includes `CAJERO POSVENTA`; the stored golden failed on HEAD before this change).
