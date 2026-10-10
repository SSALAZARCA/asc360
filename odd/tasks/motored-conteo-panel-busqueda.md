# Motored: "Contadas" filter and reference search on the leader panel

## Objective

The count leader can see the references as they get counted, and can look up any reference to audit it with a pair. This is for the leader panel only; pairs see no change (owner decision: pairs with a doubt ask the leader, who audits at the shelf).

## Decisions (owner, 2026-10-10)

1. A new filter chip, "Contadas (N)", sits next to Todas / Críticas / En reconteo.
   - It shows only references with contado > 0, the most recently counted first (by the latest non-voided reading).
   - N is the number of counted references.
2. A search box sits above the differences table.
   - It matches by code (ignoring hyphens/spaces/dots, using the same key rule as the counting: `clave_codigo` / `regexp_replace(upper(codigo), '[^A-Z0-9]', '', 'g')`) or by part of the name (case-insensitive).
   - It searches ALL references of the count, not just the 200 rendered rows: a server-side query, debounced.
   - It combines with the active filter chip.
3. For each reference, the leader can see the counted quantity per location, which pair counted it and when (last reading time).
   - Use an expandable row, or extend the existing "Ubicaciones" cell.
   - The leader is not blind; quantities are shown.
4. The pair device gets no change.
5. Visibility and roles stay as today for the panel. GERENCIA is read-only and may see it too.
6. The 15 s polling must stay cheap: the search runs on demand, and the "Contadas" ordering reuses existing aggregates where possible.

## Checklist

- [x] T1 backend: filter + search + per-location/pair detail + tests (route: delegated writer, because there are 2+ non-trivial files across layers)
  - `GET /api/motored/conteos/{id}/diferencias?filtro=contadas&q=...` (new `services/conteos/busqueda.py`); `GET /api/motored/conteos/{id}/diferencias/detalle?codigo=...`; `diferencias_resumen.contadas` on `/panel`; `ultima_lectura_en` per row (aggregate `GREATEST(max round-1, max assignee round-2 recibida_en)`). No migration.
  - Evidence 2026-10-10: `pytest tests -q -k conteo` 561 passed; pg_real `-k conteo` 143 passed (11 new in `test_conteos_busqueda_pg.py`) on a throwaway PG18 migrated to head.
- [x] T2 frontend: chip, search box, detail + jest tests (same writer)
  - "Contadas (N)" chip (N from the panel summary), debounced (350 ms) search box, "Ver detalle" expandable row (`DetalleReferencia.js`, `useBusquedaDiferencias.js`). The pair device is untouched.
  - Evidence 2026-10-10: `npx jest conteo` Tests: 162 passed, 162 total (RED first: missing module).
- [x] T3 commits b0f3446 2e60f66 (gga PASSED), pushed
- [ ] T4 after T3, ask the manuals session to update the existing counts manual. The owner's 2026-10-10 rule: a pair with a doubt about whether something was counted asks the leader, and the leader audits it at the shelf with the panel search. Also cover today's changes:
  - test counts;
  - Tab or Enter scanners;
  - hyphen-less codes and the "Código ambiguo" warning;
  - the units card and the pairs shown by units;
  - the "Contadas" filter, the search and the detail.

## Progress

- 2026-10-10: decisions recorded, writer launched.
- 2026-10-10: T1 and T2 implemented and verified (not committed). Interpretation: with a search under "Todas" every reference of the count matches (also those with no difference), so the leader can audit any reference; without a search "Todas" stays the differences list. Search matching is done in Python over the full aggregate (partial code key or name), not with the functional index.
