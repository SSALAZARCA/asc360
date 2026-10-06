# Motored KPI's — Comisiones tab

## Objective
Add the **Comisiones** tab to KPI's (after Asesores), implementing the approved design in the "Motored KPIs" canvas (`project/Main.dc.html`, tab id `presupuesto`, lines ~777-913 and helpers ~1515-1539).

## Why
Gerencia needs to see what each asesor earns under the configurable commission rules, and how close each one is to the next tier. The rules are already in Configuración (`comision_*` keys, still unread) and the budgets per asesor exist.

## Decisions (user, 2026-10-05)
- **One month only.** The tab always settles ONE month: the LAST month of the period filter. The period does not otherwise change the figures; the store filter applies.
- **Design.** Keep the approved design as-is. Its sections:
  - KPI card;
  - "Cómo se calcula";
  - "Dónde cae cada asesor";
  - "Comisión por asesor", with a Comisión | Cumplimiento toggle;
  - "Cerca de subir de tramo".
- **Trend chart dropped (2026-10-05).** The user first asked for a dual-axis chart (sales vs commissions). After seeing it in the canvas, as bars then as lines, they rejected it: "no me dice nada". It is removed from the canvas and from scope.
- **Rules and defaults** (taken from the docs and the config; the user did not object):
  - The rate is flat on the whole base: comisión = venta (`comision_base_pago`, default sin HMCL) × tier rate.
  - Cumplimiento = venta (`cumplimiento_base`, default con HMCL) ÷ the asesor's budget for that month.
  - A tier applies from `desde_pct` inclusive (ELITE from exactly 105%), compared without division, like `semaforo_de`.
  - Only cargos in `comision_cargos_asesor` earn commission.
  - Asesores without a budget don't earn commission (counted in `advertencias`).
  - Rules are read with vigencia at the settled month (`parametros.leer_valores`).
  - The HMCL display selector does not change the bases.

## Scope
- **Backend:**
  - `GET /api/motored/tablero-asesores/kpis/comisiones` (same `_filtro` and roles).
  - `calcular_kpis_comisiones` in `services/tablero_kpis.py`, with pure calc helpers.
  - The comisión rules reader.
  - Live and summary paths identical through `lectura.cubo`.
- **Frontend:** the `kpis/comisiones/*` tab, wiring in `KpiTabs`/`KpisContent`/`useKpis`/`kpisApi`,.

## Constraints
- Brand manual: red only for the brand; tier colors ELITE #0F766E, PRO #1D4E89, BASE #A3A39E.
- Tooltips on non-obvious fields; tablet responsive; explicit `<option>` styles.
- Python 3.11; strict TDD; no `git stash`.

## Tasks
- [x] **C1 Backend calc + endpoint.**
  - Pure: tier selection, commission per asesor, summary, `cerca de subir` (falta/gana as in the design).
  - Endpoint plus tests, including pg_real live/summary equivalence.
- [x] **C2 Frontend tab.** The design sections and the wiring; jest tests; webpack compile.

## Acceptance
- The numbers match a hand calculation on fixtures.
- Live and summary paths are equal.
- The UI matches the canvas design.
- The full unit, jest and pg_real suites stay green.

## Progress
**C1 + C2 done (2026-10-05).** Route: one delegated writer (2+ non-trivial files). Commits d585d40 and b55a68e.
- **Backend:**
  - `services/tablero_comisiones.py` is the pure calc: tier inclusive without division, flat rate, cerca de subir.
  - `calcular_kpis_comisiones` settles the last month only, with rules by vigencia.
  - `GET /kpis/comisiones`.
  - `GET /kpis/comisiones/excel` (`services/tablero_comisiones_excel.py`):
    - the cédula is text;
    - columns: Cédula, Asesor, Tienda, Cargo, Presupuesto, Venta con HMCL, Cumplimiento %, Tramo, % comisión, Venta sin HMCL, Comisión, with totals;
    - a "Sin presupuesto" sheet;
    - header rows with the mes, filtros and tramos;
    - file name `comisiones_<AAAA-MM>.xlsx`.
- **Frontend:** `kpis/comisiones/*` per the canvas design, with the "Mes liquidado" chip, the empty state, tooltips and the "Descargar Excel" button in the "Comisión por asesor" header (user request).
- **Writer's assumptions:**
  - A person is commissioned if any of their cargos is in `comision_cargos_asesor`.
  - A person with no known cargo is excluded (`advertencias.cargo_desconocido`).
  - "Cerca de subir" means a gap of 15 points or less with venta above 0.
- **Checks:**
  - unit 5761 green;
  - pg_real 110 green (switch ON/OFF identical; the HMCL selector doesn't change the figures);
  - jest 1972 green;
  - webpack compile 200.
- **Native review:** medium, 1677 lines. Consent granted; R3 approved and acknowledged.
- **Advisories (informational):**
  - `tablero_kpis.py:595-596`;
  - `comisiones/datos.js:30` and `:68-75`. The strip loop can't underflow, because the config validator forces the first tier `desde_pct` to 0.

## Status
Delivered to main; awaiting the user's check in production with real budgets.

## Next step
The user checks the Comisiones tab with real data (September budgets loaded).
