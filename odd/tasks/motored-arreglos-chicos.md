# Motored: small fixes batch (2026-10-04)

## Objective
Three small owner-approved fixes from the pending list.

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Non-store bodegas (99999 "BODEGA MOTORED", PYM01 "SOACHA MT ELEC PRODUCTO TERMINADO"): an explicit, ADMIN-editable list `bodegas_excluidas` (GRUPO_OPERACION, default ["99999","PYM01"]) shown in Configuración > Cargas. VENTAS and INVENTARIO rows whose bodega code is in the list are skipped silently (no carga_error), counted in the carga log (`filas_bodega_excluida`). Unmapped codes NOT in the list keep erroring (explicit marker, never an implicit skip). | delegated writer |
| T2 | Configuración shows readable labels instead of raw codes in "valor actual" / "valor por defecto" (e.g. `sin_hmcl` → "Sin HMCL", objects like `verde_desde: 90` → "Verde desde 90%"). | delegated writer (same) |
| T3 | Lore replies with the linked user's real role when a web user links Telegram (e.g. "Vinculado como Compras"), instead of always "administrador"; `/yo` shows the role too. | delegated writer (same) |

- [x] T1
- [x] T2
- [x] T3

## Constraints
- Decision basis: Engram `motored/bodegas-secundarias-consignacion` (explicit `no_tienda` marker, never implicit skip) and `motored/configuracion-admin-shipped`.
- Engine output must be unchanged except that rows from excluded bodegas no longer produce errors. They never fed any sucursal anyway.
- Python 3.11, gga style, tablet layout, `<option>` style, no backticks in `themeCss` comments.
- Coordinate with the KPI session: ingesta files are shared.

## Test-first
- Applicable. Backend: `cd backend && .venv/bin/python -m pytest tests/motored -q` plus pg_real. Frontend: `cd frontend && npx jest`. lore-bot: `cd lore-bot && .venv/bin/python -m pytest -q`.

## Log
- 2026-10-04: feature document created.
- 2026-10-04: T2 and T3 done (uncommitted). T2: formatearValor renders readable Spanish (labels, semaforo, tramos, maps, decimal comma); group labels moved to etiquetas.js. T3: backend /admin/vincular already returns role; Lore uses new etiqueta_rol (ADMIN, COMPRAS, ASESOR_MOSTRADOR, fallback usuario) in /vincular and /yo. RED observed first. Full jest 1711 passed; lore-bot pytest 418 passed.
- 2026-10-04: T1 done (uncommitted). Key `bodegas_excluidas` (GRUPO_OPERACION, tab Cargas, default ["99999","PYM01"], non-empty, upper-case/trimmed, unique) read once per carga in `_construir_procesador_fila` via `leer_con_memoria(deshacer=False)` for VENTAS and INVENTARIO only. Processors take `bodegas_excluidas` and return the identity sentinel `resolucion.FILA_BODEGA_EXCLUIDA` before sucursal resolution (VENTAS: after the Aprobada check, before the solo-detalle branch; INVENTARIO: after the blank-Referencia filler check); the orquestador counts them in `log["filas_bodega_excluida"]` (only when > 0). No staging, no carga_error, nothing in venta_detalle/inventario_detalle (rows with an unresolved sucursal never reached the detail tables anyway). Non-excluded unresolved codes keep SUCURSAL_NO_ENCONTRADA. UI: chips editor + tooltip in SeccionCargas. RED observed first (module attribute missing / 4 jest failures). Backend tests/motored 5115 passed; UM 1296 passed; pg_real 462 passed, 2 skipped (throwaway PG 18, stopped and deleted); full jest 1714 passed. Test queues updated for the extra read (ventas: tipos, bodegas, tolerancia; inventario: bodegas).
