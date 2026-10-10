# Motored: units on the live count panel

## Objective

The live panel of a count shows progress in UNITS, not only references, and compares pairs by units counted.

## Decisions (owner, 2026-10-10)

1. A new KPI card, "Unidades contadas", sits next to "Avance".
   - **Total contado**: the units counted.
   - **Dentro de lo esperado**: the sum over references of `min(contado, max(sistema, 0))`.
   - **Sobrantes**: the sum over references of `max(0, contado - max(sistema, 0))`. It includes every unit of a reference that the store's system does not have (sistema = 0), and of unknown/forced codes.
     - Sobrantes only grow while counting. They drop only when a pair corrects or voids a reading.
   - **Avance en unidades**: a bar showing `dentro de lo esperado` / total system units, where total system units is the sum of `max(sistema, 0)` over the snapshot.
   - Invariant: Total = Dentro + Sobrantes.
   - "contado" per reference must be EXACTLY the same quantity the differences table shows in its "Contado" column, so the card and the table never disagree.
2. Each pair in the "Parejas" card shows only:
   - the pair name and its total units counted (the sum of the quantities of its non-voided readings), e.g. "39 unidades";
   - pairs sorted by units, descending, each with a small bar relative to the leading pair;
   - the location and the "N lecturas" text are removed;
   - kept: the yellow idle warning (over 2 minutes without readings), the Desconectar button and the reconteo-task line.
3. The panel polls every 15 s, so the new aggregates must stay cheap: one grouped query, no N+1. Reuse what `panel.py` already computes where possible.
4. Help tooltips (InfoTooltip, like the other cards) explain "Dentro de lo esperado" and "Sobrantes" in plain Spanish.

## Checklist

- [x] T1 backend panel aggregates + tests (route: delegated writer, because there are 2+ non-trivial files across layers)
  - `panel.unidades(crudas)` runs over the differences aggregate that `armar` already loads (no new query); per-pair units are a `sum(cantidad)` added to the existing grouped `_SQL_POR_SESION` (non-voided readings, all rounds). No migration.
  - Parity: new `diferencias.contado_de(fila)` is the single definition of "Contado"; `calcular` (the table) and `panel.unidades` (the card) both call it. Unit test `test_units_use_the_differences_table_contado` and pg_real `test_units_match_the_differences_table` (rebuilds dentro/sobrantes from `GET /diferencias`) compare the two.
  - Evidence: RED 12 failed before implementation; `pytest tests -q -k conteo` 533 passed; pg_real `-m pg_real tests/motored/pg_real -k conteo` 132 passed (PG18 throwaway).
- [x] T2 frontend card + pairs card + jest tests (same writer)
  - "Unidades contadas" card next to "Avance" (total, dentro de lo esperado, sobrantes with InfoTooltips, "Avance en unidades" bar); "Parejas" shows name + units + relative bar, sorted by units desc; location and "N lecturas" removed; idle warning, Desconectar and reconteo line kept; disconnected pairs keep a "Desconectada" line.
  - Evidence: RED 4 failed; `npx jest conteo` Tests: 155 passed, 155 total.
- [x] T3 commits ab30005 6772451 (gga PASSED), pushed

## Progress

- 2026-10-10: decisions recorded, writer launched.
- 2026-10-10: T1 and T2 done (uncommitted). Next: T3 commits through gga, push.
