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
- [ ] **S1** Read the summary state once per request: cache `usar_resumen`/`frescura` in a request-scoped context.
- [ ] **S2** Asesores: skip the top-5 clients in `calcular_opciones_asesores` and the detail (they don't use it); avoid rebuilding the tablero twice per load/switch; reuse within the request, or let opciones be light.
- [ ] **S3** `fecha_datos` without scanning `venta_detalle`: derive it from `max(carga_archivo.periodo_hasta)` of applied/validated VENTAS cargas covering the month and the stores, or add an index on `venta_detalle(fecha)`. Prefer no migration if equivalent.
- [ ] **S4** Ventas: find why it doubled and remove duplicate cubes or reads (one cube by asesor, derive sucursal/total; share `cumplimiento_por_mes` work).
- [ ] **S5** Before/after per-statement timings, per tab, recorded here.

## Out of scope
The admin send-status page blocking is the pedidos session's fix. Stale-while-rebuilding is still pending a user decision.

## Next step
S1–S5 by one delegated writer, one commit each where sensible.
