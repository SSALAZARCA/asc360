# Motored KPI's — asesor commission card and calculation (didactic)

## Objective
In KPI › Asesores (single-asesor view), make the commission readable for the asesor. Approved design: canvas "Motored KPIs", board `project/AsesoresUno.dc.html`, version 55 or later.

## Decisions (user, 2026-10-07)
- **Card "Comisión estimada · <mes>"** (next to the gauge):
  - big total;
  - "Comisión $X + bonos $Y";
  - tier chip;
  - earned bonuses only, as thin ámbar rows;
  - **"Para ganar más bonos"**: if the 95% gate passed, one row per active unmet line with "te faltan $X" (`falta_venta`, budget-minimum based) and its bonus "+$Y", sorted ascending. If the gate is not passed, show "te faltan $X de venta para activar los bonos" (umbral × presupuesto − venta on `cumplimiento_base`) instead;
  - **"Para llegar al 100%"**: at or above 100% it says "¡Ya superaste tu presupuesto! (N%)". Otherwise "te faltan $X · quedan N días hábiles (lun–sáb, sin festivos) · necesitas $Y por día". The days count from the day after the latest loaded sale to month end, Monday to Saturday, EXCLUDING Colombian public holidays (default; the user accepted it);
  - "Datos al <fecha de la última venta cargada>";
  - a tooltip explaining the minimum.
- **Gauge.** Bigger, filling the card height.
- **New last section "Así se calcula tu comisión"** (approved as shown):
  - an info hint "Pasa el mouse o toca un dato para ver cómo se calculó.";
  - an equation of tiles `[Venta que cuenta] × [Tramo %] = [Comisión] + [Bonos]`, then `= [Total]`, where each operator is attached to the next tile;
  - short captions;
  - `title` tooltips with the full math (venta total − HMCL; cumplimiento = con HMCL ÷ presupuesto ≥ desde → tier; base × %; gate + earned lines);
  - an info icon on each tile;
  - the tier ladder BASE/PRO/ELITE with "Estás aquí · N%" and one note.
- Brand rules apply, and tablet 768–1024 must work.

## Tasks
- [ ] **D1 Backend:** in the detail payload, add `fecha_datos` (last loaded sale date in scope), `dias_habiles_restantes` (Mon–Sat minus Colombian holidays, computed by a pure helper covering fixed dates, Emiliani Monday moves and Easter-based dates), `falta_100`, `venta_diaria_necesaria` and `falta_compuerta`. Tests, including holiday dates for 2026 and 2027.
- [ ] **D2 Frontend:** the card, the bigger gauge and the new section, per the canvas; jest; webpack compile.

## Next step
D1 and D2 by one delegated writer; review, push, send hashes to 5d.
