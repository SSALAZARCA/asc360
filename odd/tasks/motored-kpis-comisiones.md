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
- [ ] **C1 Backend calc + endpoint.**
  - Pure: tier selection, commission per asesor, summary, `cerca de subir` (falta/gana as in the design).
  - Endpoint plus tests, including pg_real live/summary equivalence.
- [ ] **C2 Frontend tab.** The design sections and the wiring; jest tests; webpack compile.

## Acceptance
- The numbers match a hand calculation on fixtures.
- Live and summary paths are equal.
- The UI matches the canvas design.
- The full unit, jest and pg_real suites stay green.

## Progress
(none yet)

## Next step
C1 + C2 by one delegated writer (2+ non-trivial files).
