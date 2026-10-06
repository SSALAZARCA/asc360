# Motored KPI's — Asesor filter (Todos / Un asesor)

## Objective
Add an "Asesor" filter to the KPI's **Asesores** tab:
- **Todos los asesores** shows the general view.
- **One asesor selected** shows that person's detail view.

Both follow the approved canvas proposals in "Motored KPIs": `project/AsesoresTodos.dc.html` and `project/AsesoresUno.dc.html`.

## Why
The user wants to inspect one asesor's results. The current indicators were designed for the whole group and lose meaning for one person.

## Decisions (user, 2026-10-06)
- **The proposal replaces the current tab.** The user's instruction was to use the first "Un asesor" proposal ("cambiemos la de asesores por la propuesta un asesor"). A block-by-block variant was built by mistake and discarded; the first proposal was restored on the canvas (version 44).
- **Filter.** A searchable dropdown with "Todos los asesores" plus "Nombre · Tienda". It respects the Punto de venta filter and sits in the same header row as Período, Punto de venta and HMCL.
- **Todos view.** The current Asesores tab, plus the hint chip "Elegí un asesor para ver su detalle". Names in the rankings and Tecnired lists are clickable and select that asesor.
- **Un asesor view, per the canvas:**
  - ficha: nombre, cargo, tienda, cédula, tramo chip, and positions in cumplimiento, venta and Tecnired;
  - cumplimiento gauge vs her meta, with the 90/105 cuts;
  - comisión estimada, with "le faltan $X para <siguiente>" (reuses the Comisiones calc, last month of the period);
  - 6 tiles vs the red (venta vs promedio asesores, ticket, facturas, clientes únicos, margen, % Tecnired);
  - tendencia de cumplimiento per month, with tier bands and the red average;
  - venta por línea vs red;
  - dónde está frente a sus compañeros: the strip with the others grey and her highlighted;
  - comparación con su tienda (her / prom. tienda / prom. red);
  - clientes Tecnired atendidos (total and top 5).
- **No invented data.** A field with no data source (fecha de ingreso, antigüedad) is omitted, not shown as a placeholder.

## Scope
- **Backend:** an `asesor` (cédula) query param on `/kpis/asesores`, or a new `/kpis/asesores/detalle`, returning the single-asesor payload. Live and summary paths must give identical results.
- **Frontend:** the filter, the Todos additions and the Un asesor view, in `components/motored/kpis/asesores/*`.

## Constraints
- Brand manual: red only for the brand; tier colors ELITE #0F766E, PRO #1D4E89, BASE #A3A39E.
- Tooltips on non-obvious fields; tablet responsive; explicit `<option>` styles; dates through `lib/motored/fechas.js`.
- Strict TDD; Python 3.11; no `git stash`.

## Tasks
- [ ] **A1 Backend detail payload** + tests (pure, API, pg_real live/summary equivalence).
- [ ] **A2 Frontend filter + Todos additions + Un asesor view** + jest + webpack compile.

## Next step
A1 + A2 by one delegated writer.
