# Motored KPI's — margin with the real cost from the sales file

## Objective
Use the ERP cost at the moment of sale ("Costo promedio total", the line total) for the KPI margin and the días de inventario, instead of re-costing past sales at today's inventory cost.

## Decisions (user, 2026-10-07; GO given directly; plan verified by 84, 71 and 5d)
- **Storage.** `venta_detalle.costo` is a new nullable NUMERIC column holding the line total. It is filled from the OPTIONAL VENTAS column "Costo promedio total", which is added to the optional columns so it appears in the plantilla.
  - Absent column, blank cell or unparsable cell → NULL. The value is stored as-is.
  - Old hand-built files carry no cost column (5d checked Jan–Sep), so they load unchanged.
  - "Costo prom. uni." is a different header and is ignored.
- **Per-row cost used by the KPIs:**
  - `cantidad ≠ 0` and `costo` not NULL and ≠ 0 → `sign(cantidad) × |costo|`. This is the defensive sign rule.
  - `cantidad ≠ 0` and `costo` NULL or 0 → `cantidad × unit fallback`. The fallback is today's `kpi_costo_referencia` rule (median inventory cost, else precio_normal), so it is negative for returns.
  - `cantidad = 0` → `costo` as-is if present, else 0.

  Everything is summed as-is: NNC/DVT subtract, and ±pairs net out. There is no special treatment of negatives.
- **No new UI.** The real-vs-estimated flag was removed by the user. The existing margin tooltip keeps its meaning: the share of sales that used the fallback.
- **Readers to change:** every KPI margin/cost reader, i.e. the live asesores and tablero queries, `consultar_costo_venta` (días de inventario), and the summary builder/reader. The summary likely needs a migration; the switch must give identical results live and from the summary.
- **Unaffected:** pedidos (it values with precio_normal), commissions and bonuses (no cost).
- **History.** Jan–Sep stay on the fallback unless they are reloaded with the raw file.
- **Rollout.** The summary schema change marks the estado dirty, so the loop rebuilds it (about 20 s at 1M rows). Afterwards, verify `/kpis/estado`.

## Tasks
- [ ] **C1** Migration (column on top of the current alembic head; update the head-pin tests) + ingest parse/store + optional column/plantilla + tests (present, absent, blank, 0, negative, decimal formats; old file has a byte-identical log; pg apply stores the cost). No KPI behavior change.
- [ ] **C2** The KPI per-row cost rule in all readers + the summary column/migration + tests: pure tests for every branch (sign mismatch, negative qty fallback, zero qty, ±pairs); pg_real live = summary for a mixed month; an old month unchanged; días de inventario; a perf re-check with the 1M-row perf test.

## Next step
C1 and C2 by one delegated writer. Push after review; report hashes to 5d.
