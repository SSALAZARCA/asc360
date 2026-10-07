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
- [x] **C1** Migration (column on top of the current alembic head; update the head-pin tests) + ingest parse/store + optional column/plantilla + tests (present, absent, blank, 0, negative, decimal formats; old file has a byte-identical log; pg apply stores the cost). No KPI behavior change.
- [x] **C2** The KPI per-row cost rule in all readers + the summary column/migration + tests: pure tests for every branch (sign mismatch, negative qty fallback, zero qty, ±pairs); pg_real live = summary for a mixed month; an old month unchanged; días de inventario; a perf re-check with the 1M-row perf test.

## Progress
**Done (2026-10-07).** One delegated writer. Commits: C1 4eabf64 (migration d2b7a94e5c61), C2 251305b (data migration e5c9b3d8f024, which marks the summary dirty). Pushed.

- **Cost rule.** One shared helper, `_expr_costo_fila` in `tablero_asesores_consultas.py`, used by the live cube, `consultar_costo_venta` and the summary builder. The summary needed no new column: the builder applies the cost at build time.
- **`costo_estimado`.** It stays as the cost priced from precio_normal on rows without a real cost, so all-NULL (old) months are exactly unchanged. `con_costo` = real cost OR fallback.
- **Ingest.** The optional column is registered in `deteccion.COLUMNAS_OPCIONALES_POR_TIPO` (plantilla); invalid cells are counted as `filas_costo_invalido`, never as a carga_error.

**Checks**
- unit 6145, green;
- pg_real 228 + 1 skipped (perf), green.

**Perf** (1M rows):
- summary reads are unchanged (0.58–0.94 s);
- the rebuild is unchanged (18.7 s);
- live queries are 5–13% slower (CASE expression).

**Native review.** Medium risk, 794 lines. Consent was granted; R3 approved and was acknowledged, with 2 suggestions.

## Next step
- Verify `/kpis/estado` rebuilt after deploy.
- The user reloads a month with the raw file to see real-cost margins.
- Then the Comisiones UI decisions (bonus bar B + grey note, Bonos por línea A/B) once the user confirms them.
