# Motored: per-line sales detail (venta_detalle) from the VENTAS upload

## Objective
The VENTAS upload in Maestros should also keep every sale line, with its salesperson, gross value, discount, invoice customer and invoice number. This feeds the future advisor dashboard (TABLERO ASESORES).

Pedidos are unchanged: the monthly aggregate `venta_mensual` keeps being built exactly as today.

## Decisions (user, 2026-09-30)
- **Five new REQUIRED columns** in the VENTAS file:

  | Column | Meaning |
  |---|---|
  | "Nombre vendedor" | Salesperson |
  | "Valor bruto" | Value before discount and before IVA |
  | "Valor descuentos" | Discount amount |
  | "Cliente factura" | Invoice customer |
  | "Nro documento" | Invoice number |

  - "Nro documento" was added after analysing the Excel dashboard. About 13 indicators need it: facturas, ticket, items per invoice, % of invoices per line, multi-line invoices.
  - A file missing any of these columns is rejected with a clear message listing what is missing.
- **One upload feeds two tables.**
  - `venta_mensual`: same aggregate, same REPLACE upsert, read by the motor.
  - `venta_detalle` (new): one row per file line. The motor never reads it.
- **Volume is acceptable.** The cap is 50k rows per upload, the table gets indexes, and a retention policy can come later.
- **No indicators in this feature.** This work only stores the data.
- **Dashboard sales definition.** The dashboard computes VENTA as bruto − descuentos, counting only the 7 lines. We store both raw values so either can be derived.

## Constraints from the F3/F4 agent's impact check
- These stay byte-for-byte unchanged:
  - `venta_mensual` (read by `corridas/cargador.py:210`, which filters `carga_archivo.estado != 'ANULADO'`).
  - `carga_archivo.periodo_desde` / `periodo_hasta`.
  - `log["fecha_max_detectada"]` (`orquestador.py:413-419`).
- **Detection.** `deteccion.verificar_tipo` only verifies the DECLARED tipo and accepts when the ratio is ≥ 0.6.
  - An old 8-column file now scores 8/13 ≈ 0.615. It is still accepted as VENTAS, then rejected by the required-column check. Test that verdict explicitly.
  - A 7/13 header (0.54) fails as "tipo no coincide" but still lists `columnas_faltantes`. Test that its message stays clear.
- **Anulación.** Never delete `venta_detalle` rows. Keep `carga_id` on every row, and every reader filters cargas with estado ANULADO.
- **Re-upload.** Replace the detail rows for the same (sucursal, anio, mes) set present in the new carga. Do it consistently, as a delete-on-replace.
- **Salesperson name.** Store the raw text plus a normalized key (`vendedor_norm`), because Excel names drift.
- **Indexes.** (sucursal_id, fecha) and (vendedor_norm, fecha).
- **Migration.** One new alembic_motored revision chained on the current single head (`a3f7c1d9e642` on 2026-09-30). Tell the F3/F4 agent the new head after pushing.
- **Do not touch.** `supervisor_corridas.ensure_started()` in deps, the F4 files (`services/corridas/*`, `api/corridas*.py`, `schemas/pedido.py`), and the "- copia" worktree.
- **Personal data.** "Cliente factura" is personal data under Ley 1581. Store it as text. It is visible only to the roles that already see sales data (no new exposure, no new endpoint).

## TDD
- Mode: strict. Source: project rules and user memory. RED, then GREEN, then REFACTOR.
- Backend runner: `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/motored`. `backend/.venv` is Python 3.11.16, the same as production.
- pg_real and regresion suites: `-m pg_real` and `-m regresion`, on a throwaway PG 18 (TCP 127.0.0.1, `unix_socket_directories=''`, deleted afterwards).
- Frontend: `cd frontend && npx jest`, only if the Maestros template or UI hint changes.

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Parser and template: the 5 required columns with aliases, money parsing (Colombian formats), staging payload, a clear missing-columns message, and the server-generated VENTAS template. Update every VENTAS fixture in the repo, including the F3 regression ones (`tests/motored/fixtures/regresion/entradas_app.py`, `almacen.py`). | delegated writer |
| T2 | `venta_detalle` model (with `nro_documento`) and migration. Write it on Aplicar in the same transaction as `venta_mensual`, with the replace-by-(sucursal, anio, mes) rule, the anulación rule and indexes. pg_real tests. | delegated writer (same as T1) |

Route evidence: T1 and T2 together touch 2+ non-trivial files (parser, ingestion, model, migration, fixtures), so the writer trigger fired.

- [x] T1 (commit 2583b6c)
- [x] T2 (commit 2583b6c)

## Follow-ups (separate features, user-approved direction, not in this scope)
- **Inventory cost.** An OPTIONAL "Costo" column in INVENTARIO, stored as a nullable column on `inventario_snapshot`, kept out of `COLUMNAS_ESPERADAS`. Open decision: the inventory key has no bodega, so how does a per-bodega cost aggregate (median, as the Excel did)?
- **CLIENTES TECNIRED.** A new Maestros upload type (NIT + razón social). The engine never sees it. Do not add it to the `vigencia.py` freshness list, and check the "6 keys" assumptions.
- **Salesperson to advisor mapping.** An explicit vendedor → Usuario (ASESOR_MOSTRADOR) table, with a "sin asignar" bucket and no fuzzy auto-matching.
- **Referencias.** The user will reload `linea_comercial` with the 7 dashboard lines. The engine only carries this field, so the reload is safe.
- **Dashboard.** Build the TABLERO ASESORES indicators. Analysis is in Engram `motored/tablero-asesores-analysis`.

## Log
- 2026-09-30: impact check with the F3 agent done (no blocker; two traps noted above). The user confirmed the columns. The F3 agent was told the columns are REQUIRED.
- 2026-09-30: the previous session (a7) was suspended mid-task, and session d0 resumed it. Its partial work was preserved: the model draft, 21 RED tests and the `models/__init__` export.
- 2026-09-30: the user's Excel dashboard was analysed. "Nro documento" was added as the 5th required column. The F3 agent confirmed none of the follow-ups touch the engine. Worktree fast-forwarded to main f6b6c88.
- 2026-09-30: T1 and T2 done in ONE commit (the apply path, model and tests are coupled: `aplicar_detalle` lives in `ventas.py` and needs the model). New alembic head: `b8e2d4a1c735` (chained on `a3f7c1d9e642`). Evidence:
  - RED: with the old `ventas.py` restored, `test_ingesta_ventas_detalle.py` gave 45 failed / 3 passed. GREEN: 48 passed after the implementation.
  - Existing VENTAS fixtures updated (`test_ingesta_ventas.py`, `_fecha_max`, `_orquestador`, `_hojas`, `_deteccion`, `_perf`). The F3 regression fixtures (`entradas_app.py`, `almacen.py`) build no VENTAS file (they insert `venta_mensual` rows directly), so nothing to change there.
  - pg_real: 4 new tests in `pg_real/test_venta_detalle_pg.py` (apply writes detail, replace by (sucursal, anio, mes), anulacion keeps rows, period rejection writes nothing). Their first run was already GREEN because the implementation came first; the only failure was a test-isolation bug (`anular_carga` commits), fixed by degrading `commit` to `flush`.
  - Side effect: "Nro documento" normalizes the same as INGRESOS_FACTURAS "Nrodocumento", so a VENTAS file declared as INGRESOS_FACTURAS now scores 3/5 = 0.6 in `verificar_tipo` and passes detection; the dry-run still rejects it for missing columns. The deteccion mismatch pair was changed to (INGRESOS_FACTURAS, FACTURAS_PEDIDOS).
  - No header aliases were added: the column matcher only compares normalized canonical names (case, accents, spaces, dots, dashes already tolerated).
