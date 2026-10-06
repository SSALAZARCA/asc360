# Motored Comisiones — per-line bonuses

## Objective
Add fixed per-line bonuses to KPI commissions, configurable in Configuración. Also show each asesor's minimum line sale in the Presupuestos month detail.

## Decisions (owner, relayed by the pedidos session, 2026-10-06; confirmed shape)
- **Gate.** Line bonuses activate only when the asesor's TOTAL cumplimiento (venta on `cumplimiento_base` ÷ month budget) is ≥ `comision_bono_umbral_pct`. Default 95, inclusive: `venta*100 >= umbral*presupuesto`.
- **Line rule.** Once the gate passes, line L pays its `bono` when the asesor's line venta (con HMCL, same base) ≥ `pct_meta`% of the asesor's TOTAL venta in the month. Compared without division: `linea*100 >= pct*total`.
- **Lines and defaults:**

  | Line | Target | Bonus |
  |---|---|---|
  | LUBRICANTES | 21% | $35.000 |
  | CASCOS | 6% | $30.000 |
  | ACCESORIOS ("Otros accesorios") | 3% | $25.000 |
  | LLANTAS | 1% | $25.000 |
  | BATERIAS | 1% | $25.000 |
  | TECNIRED | 6% | $25.000 |

  TECNIRED is venta to Tecnired customers (`es_tecnired`) across all lines; overlap is accepted. REPUESTOS and GPS have no target.
- **Eligibility.** The asesor needs a budget (otherwise listed in `sin_presupuesto`) and a cargo in `comision_cargos_asesor`.
- **Payout.** Total = commission + Σ bonuses of ACTIVE lines met. Inactive lines are not paid but still shown (who would have earned it).
- **Config keys** (GRUPO_OPERACION, section comisiones, vigencia by month):
  - `comision_lineas = [{linea, pct_meta, bono, activo}]`. `linea` is a normalized `lineas_comerciales` key or "TECNIRED", unique. `pct_meta` is a decimal string with 0 < x ≤ 100. `bono` is a decimal string ≥ 0 in whole pesos. `activo` is a bool. Numbers are accepted and normalized to strings; an empty list is allowed.
  - `comision_bono_umbral_pct`: decimal string, default "95", range 0–200.
- **Presupuestos month detail.** It adds:
  - `lineas_bono [{linea, etiqueta, pct_meta, bono}]`, the active lines in config order;
  - `umbral_bono_pct`;
  - per line `minimos {LINEA: int}`, where minimum = round_half_up(presupuesto × umbral/100 × pct_meta/100);
  - `totales_minimos`.

  All values come from the vigencia of that month.
- **Split.** The pedidos session builds the Configuración editor (`EditorBonosLinea`) and the Presupuestos flat-table frontend. This session builds everything backend, plus the Comisiones UI and the Excel.

## Tasks
- [ ] **B1 Backend:**
  - registry keys and validators;
  - pure bonus calc in `tablero_comisiones`;
  - payload (per asesor `bonos [{linea, etiqueta, pct_real, pct_meta, cumple, activo, bono_pagado}]`, `bono_total`, `total_a_pagar`, `gate {umbral, cumple}`; resumen totals);
  - Excel columns;
  - presupuestos `minimos`;
  - tests (pure, API, pg_real live/summary).
- [ ] **B2 Frontend:**
  - Comisiones UI: total a pagar; bonos per asesor (chips per line, with the inactive ones greyed); summary of bonuses; a "Cómo se calcula" step for bonuses;
  - jest.
  - Also fix the review advisory: the KPI asesor options failure leaves a skeleton forever.

## Next step
B1 + B2 by one delegated writer.
