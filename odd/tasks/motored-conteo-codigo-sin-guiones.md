# Motored: count readings match codes ignoring hyphens

## Objective

A scanned code finds its master reference even when the label omits the hyphens, spaces or dots that the master code has.

## Problem

In the owner's test count (2026-10-10), the label `9410912000S` gave "Código no encontrado". The master code is `94109-12000S`. Today both the pair device catalog and the backend match only on `upper(btrim(codigo))`.

## Decisions (owner, 2026-10-10)

1. The match key is the code in upper case with every character outside `A-Z0-9` removed. Example: `94109-12000S`, `9410912000S` and `94109 12000S` all give the key `9410912000S`.
2. A key that matches exactly ONE master code resolves to that code.
   - The reading is stored and counted under the master code (`94109-12000S`), so it lines up with the snapshot, differences, reconteos and the Excel.
   - The raw scanned text is kept as read (`codigo_leido`), if the model already keeps it.
3. A key that matches TWO OR MORE master codes is ambiguous.
   - The device shows "Código ambiguo: coincide con X y Y. Escríbalo exactamente como en el maestro." and adds nothing.
   - The backend does not guess either: it treats the code as not found, unless it exactly equals one master code under `upper(btrim)`. That covers a person typing the exact code.
4. Location scans (`UBI-` prefix) keep working as today. Check the prefix before normalizing.
5. The device and the backend use the same rule. Both have unit tests over the same examples.

## Scope

- Frontend:
  - the pair catalog lookup in `frontend/components/motored/conteo-publico/` and its helpers;
  - the warning text.
- Backend:
  - wherever a reading's code is resolved to a referencia (lecturas, and reconteos if separate);
  - a functional index on the normalized key if the resolution queries the referencia table by it.
- Out of scope: changing master codes, and the Excel layout.

## Checklist

- [x] T1 backend resolution + tests (route: delegated writer, because there are 2+ non-trivial files across layers)
  - `lecturas.clave_codigo` (key helper), `elegir_referencias` (pure pick), `resolver` (exact stored code, then ONE query for the misses by key through the new functional index; `upper(btrim)` only for `UBI-`/key-less codes), `confirmar_ronda_dos` (a round-2 key match must resolve to the reconteo's own master code). A resolved reading stores `codigo_leido` = normalized master code. `reconteos.crear_manual` gets the key match through `resolver` with no change.
  - Migration `b7d3e9a1c540` (down `f4b8d2a6c917`): `ix_referencia_codigo_clave` on `regexp_replace(upper(codigo), '[^A-Z0-9]', '', 'g')`, `SET LOCAL lock_timeout`, downgrade drops it. EXPLAIN confirmed an Index Scan.
  - Evidence: `pytest tests -q -k conteo` 521 passed; pg_real conteo (PG18, migrated to head, downgrade -1 and up again OK) 128 passed.
- [x] T2 device lookup + ambiguity warning + jest tests (same writer)
  - `registro.claveCodigo`, `useCatalogo.indiceDesde`/`buscarEn` (key index built on the device from the codes it already gets: no payload change); `useLecturas` sends the master code, also for reconteo tasks; `textos.textoAmbiguo`.
  - Evidence: `npx jest conteo` Tests: 152 passed, 152 total.
- [x] T3 commits a78c9bd 209fb64 (gga PASSED), pushed

## Progress

- 2026-10-10: decisions recorded, writer launched.
- 2026-10-10: T1 and T2 done (not committed). The model has no separate raw-scan column: `codigo_leido` now holds the master code for resolved readings; the scanned text is not kept. Next: T3.
