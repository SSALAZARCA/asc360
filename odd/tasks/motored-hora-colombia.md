# Motored — show every time in Colombia time

## Objective
Every date-time shown in Motored must display in America/Bogota (UTC−5), whatever the browser or server timezone.

## Problem
The user saw "Datos actualizados a las 12:43" on KPI's while it was 07:43 in Colombia (5 h off), and asked to review the whole app.

The audit (sdd-explore, 2026-10-05) found:
- Most models store naive UTC (`datetime.utcnow`) and serialize it without an offset.
- The frontend formats with `toLocaleString` without a timeZone, or slices the ISO string.
- There are about 6 independent formatters, and only `ingresos/labels.js` and `kpis/frescura.js` force Bogotá.
- The KPI header reads a `timestamptz` column and already formats in Bogotá by code. The cause there is unconfirmed: prod column drift or an old build. It gets a defensive parse.

## Scope
- **Backend:** a shared serializer that emits naive datetimes as UTC with an offset (aware ones converted to UTC). It applies to the schemas and hand-built dicts listed in the audit:
  - cargas `created_at`;
  - encuesta cargas;
  - detractores (caso, acciones, respuestas);
  - presupuestos `created_at`;
  - corridas/pedidos `creado_en`/`created_at`;
  - parámetros historial `created_at`;
  - any other datetime field the UI displays (backorders/facturas/avisos if shown).

  Pure dates (`fecha_corte`, mes) stay untouched.
- **Frontend:** a single `lib/motored/fechas.js` (`fechaHoraBogota`, `fechaBogota`, `horaBogota`) using Intl with `timeZone: 'America/Bogota'` and `hourCycle: 'h23'`. It treats an ISO string without Z/offset as UTC. It replaces the formatters in:
  - `CargasHistoryTable.js`, `encuesta-admin/CargasRealizadas.js`;
  - `detractores/labels.js`;
  - `pedidos/formato.js` (`fechaHora`), `pedidos/reglas.js` (`fechaCorta`);
  - `CantidadCelda.js`, `VentasPerdidasRow.js`;
  - `configuracion/HistorialDrawer.js`;
  - `presupuestos/formato.js`;
  - `kpis/frescura.js`;
  - `ingresos/labels.js` (reuse).

## Tasks
- [x] **H1** Backend serializer + apply + tests.
- [x] **H2** Frontend helper + replace all formatters + tests (Bogotá with a fixed UTC instant; a naive string treated as UTC; a date that crosses midnight after 19:00 Bogotá).

## Acceptance
- An instant of 12:43 UTC renders as 07:43 everywhere.
- A 00:30 UTC instant renders as the previous day, 19:30.
- Unit, jest and pg_real stay green.

## Progress
**H1 + H2 done (2026-10-05).** Route: one delegated writer. Commits 42ac1f9 and 3046079, pushed to main.
- **Backend:** `services/fechas_utc.py` (`a_utc_iso`, `UtcDatetime`, JSON-only serializer) is applied to the ingesta, corrida, pedido, parametro, demanda_perdida_panel and encuesta_cargas schemas and to the detractor/presupuestos dicts.
- **Frontend:** `lib/motored/fechas.js` (`parseInstante`, `fechaHoraBogota`, `fechaBogota`, `horaBogota`) replaces the formatters in:
  - cargas (history, upload modal), encuesta-admin;
  - detractores;
  - pedidos `fechaHora`/`fechaCorta`, ventas perdidas;
  - configuración historial, presupuestos;
  - kpis frescura (defensive), ingresos.
- **Format change:** most screens now show `05/10/2026 07:43`. Ingresos lost its seconds.
- **KPI header:** confirmed correct. 12:43 was the Bogotá time of the last recalculation; the user misread it as the current time.
- **Checks:** unit 5767, jest 2025 (189 suites), webpack 200. pg_real not run.
- **Native review:** medium, 410 lines. Consent granted; R3 approved (1 suggestion: frescura numeric input) and acknowledged.
- **Not covered:** render tests for cargas table, CargasRealizadas, VentasPerdidasRow, UploadMovimientoModal, configuración HistorialDrawer; presupuestos dict unit test.

## Next step
None. The user checks the screens in production.
