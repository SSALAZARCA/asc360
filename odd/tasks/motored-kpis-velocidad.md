# Motored KPI's — speed fixes (fewer queries per screen)

## Objective
Bring the KPI tabs back to fast in production without changing any figure: Ventas ~10 s and Asesores ~20 s today, on every asesor switch.

## Evidence (2026-10-08 measurement, 944k rows, summary ON, local)
- The summary is in use: the header shows "Datos actualizados".
- Each tab runs 10–37 sequential statements (100–230 ms each locally). Production latency and CPU multiply that into 5–20 s.
- Ventas went from 0.51 s to 1.0 s since 10-07 (`cumplimiento_por_mes` / cost work).
- Asesores: `opciones` (0.95 s) + `detalle` (1.47 s) both rebuild the tablero, including an unused top-5-clients query over `kpi_cliente_mes`. `ultima_fecha_venta` scans `venta_detalle` (no fecha index) on every detail.
- `usar_resumen` / `kpi_resumen_estado` is queried up to 14 times per request.

## Decisions (user, 2026-10-08: "procede")
Speed only: identical outputs, no UI change.

## Tasks
- [x] **S1** Read the summary state once per request: cache `usar_resumen`/`frescura` in a request-scoped context.
- [x] **S2** Asesores: skip the top-5 clients in `calcular_opciones_asesores` and the detail (they don't use it); avoid rebuilding the tablero twice per load/switch; reuse within the request, or let opciones be light.
- [x] **S3** `fecha_datos` without scanning `venta_detalle`: derive it from `max(carga_archivo.periodo_hasta)` of applied/validated VENTAS cargas covering the month and the stores, or add an index on `venta_detalle(fecha)`. Prefer no migration if equivalent.
- [x] **S4** Ventas: find why it doubled and remove duplicate cubes or reads (one cube by asesor, derive sucursal/total; share `cumplimiento_por_mes` work).
- [x] **S5** Before/after per-statement timings, per tab, recorded here.

## Out of scope
The admin send-status page blocking is the pedidos session's fix. Stale-while-rebuilding is still pending a user decision.

## Progress
**Done (2026-10-08).** Pushed to main (tip eaf2b90).

- **Golden test.** Captures the 35 KPI reads × 4 modes; every figure is identical after each commit.
- **S1.** `memo_de_peticion` reads the summary state once per request.
- **S2.** Asesores options are built from the cube + personas only. The detail drops the top-5 clients.
- **S3.** The carga `periodo_hasta` was NOT used, because it isn't equivalent. Instead: index `ix_venta_detalle_fecha` (migration b5d9e3a7c142, built concurrently) plus an ORDER BY … LIMIT 1 query: 16 ms → 0.07 ms.
- **S4.** Ventas reads the asesor cube once and makes one Tecnired count query.

**Before → after, summary ON** (statements, local ms):

| Read | Before | After |
|---|---|---|
| opciones | 17 / 527 | 4 / 259 |
| detalle (año corrido) | 37 / 878 | 19 / 583 |
| ventas | 23 / 714 | 11 / 433 |
| tiendas | 18 / 477 | 10 / 437 |
| reportes | 28 / 612 | 18 / 413 |

In production each statement costs 100–230 ms, so the savings are larger there.

**Native review.** The full range exceeded the lens budget because of the golden JSON. The code range was reviewed separately, approved and acknowledged. Advisories:
- the index retry would stay INVALID if the concurrent build fails;
- equivalence proofs for the detail commissions and the report clients;
- rollup NULL ambiguity.

**Checks.** Unit 6490, green; pg_real 205, green.

## Next step
The user confirms speed in production. Follow-ups:
- the public link page builds the full report per open (f7's suggestion: `to_thread` for the CPU part);
- add `Index(...)` to the `VentaDetalle` model;
- stale-while-rebuilding is still pending a user decision.
