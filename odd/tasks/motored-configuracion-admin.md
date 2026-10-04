# Motored: admin "Configuración" page

## Objective
ADMIN edits, from the app, every business-operation and calculation setting of Motored, with history and an "applies from <month>" date. Technical settings (connections, secrets, worker tuning, upload limits) stay in Coolify.

## Why
Many tunable values have no screen today. They are either env vars changed in Coolify, `parametro_metodologia` keys with no UI, or constants hardcoded in the tablero. The owner wants to manage the business from the app (decisions of 2026-10-01 and 2026-10-04).

## Sources
- Backlog: `odd/backlog/motored-configuracion-admin.md` (the parameter inventory; its `tipos_inventario_incluidos` default is stale, it is now the 7 commercial lines).
- Agreed plan and parameter shapes: Engram `motored/configuracion-admin-plan` (F3/F4 session + KPI session, 2026-10-04).

## Owner decisions
- The page is ADMIN only.
- Business settings live in the app; technical settings stay in Coolify.
- `hmcl_nits` is configurable.
- Commission and KPI settings are created NOW. The UI labels them "Se aplican cuando estén activos los indicadores de comisiones" until the KPI session consumes them.
- Every change is versioned (`vigente_desde`, who, when) and applies from a chosen month.

## Constraints
- Storage reuses `parametro_metodologia` (typed registry, validation, scopes, insert-only versions). No second settings table.
- New non-snapshotted group `GRUPO_OPERACION` for operation keys. Existing `GRUPO_MOTOR` keys stay snapshotted per corrida, so a change affects new corridas only.
- Point-in-time read: `vigente_en(clave, fecha)` returns the row with the max `vigente_desde` <= the first day of that month.
- Retention keys fall back to env when no row exists.
- Background jobs read settings once per cycle (cached), and a change applies from the next run.
- Ownership: this session registers the tablero/KPI keys, defaults, validation, resolver and UI. The KPI session swaps the constants in `services/tablero_asesores.py` and `tablero_asesores_consultas.py` for resolver reads. This feature does NOT edit those two files.
- Python 3.11 (prod), pinned deps, gga style, tablet layout 768–1024 px verified in a real browser, `<option>` style, no backticks in `themeCss` comments.
- Every Motored migration chains on main's current head (`b5d91e3a7c42` unless it moved).

## Test-first
- Applicable: deterministic backend and frontend tests exist.
- Backend runner: `cd backend && .venv/bin/python -m pytest tests/motored -q`, plus `-m pg_real` on a throwaway PG 18.
- Frontend runner: `cd frontend && npx jest`.

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Framework: `GRUPO_OPERACION`, `vigente_en`, list/history and per-sucursal read API, ADMIN-only write of any registered key with validation and `vigente_desde`; an ADMIN-only page `/motored/configuracion` with tabs, typed controls, tooltips, history drawer and "rige desde" month; sidebar entry for ADMIN. | delegated writer |
| T2 | Section Pedido: engine keys and staleness limits, `dias_entre_pedidos` per sucursal. | delegated writer |
| T3 | Section Avisos: Lore hours (16:30 / 08:30) and recipient roles as keys read by `supervisor_avisos`. | delegated writer |
| T4 | Section Cargas: `tipos_inventario_incluidos`, `estados_backorder_vigentes`, ingresos window and tolerance, period tolerance (env to app). | delegated writer |
| T5 | Section Limpieza: retention inventario and corridas on/off and days (env to app, env as fallback). | delegated writer |
| T6 | Section Indicadores y tablero: `hmcl_nits`, `grupo_por_cargo`, `lineas_comerciales`, `kpi_semaforo_cortes` (keys only; the KPI session swaps the reads). | delegated writer |
| T7 | Section Comisiones: `comision_tramos`, `comision_base_pago`, `cumplimiento_base`, `comision_cargos_asesor` (keys only, "not yet in use" label). | delegated writer |
| T8 | Link to "Topes por tienda". | inline or with T1 |

- [x] T1 (implemented, verified, NOT yet committed; commit pending)
- [ ] T2
- [ ] T3
- [ ] T4
- [ ] T5
- [x] T6 (implemented, verified, NOT yet committed)
- [x] T7 (implemented, verified, NOT yet committed)
- [ ] T8

## Delivery
- One or more work-unit commits per task. Project rule: commit and push to main after every change (Coolify auto-deploys).
- Running count of authored lines against the ~400 budget. Owner strategy so far: ask-on-risk.

## Log
- 2026-10-04: feature document created (gentle-ai 4.0 ODD route; SDD no longer used).
- 2026-10-04: T1 done by a delegated writer (route: delegated, trigger: 2+ non-trivial files across backend and frontend). TDD: pytest `tests/motored` + jest; RED observed per behaviour (collection errors and failing tests before code); pg_real tests for `vigente_en`/history written after the code (they exercise the real SQL, passed first run).
  - Backend: `GRUPO_OPERACION` (empty), `SECCIONES`, EspecClave fields (minimo/maximo/campos/seccion), builders `lista_de_texto`, `lista_de_digitos`, `mapa_a_opcion`, `objeto_numerico`, `tramos_ordenados` (no T6/T7 key registered), `ficha`, `es_snapshotted`, `normalizar_vigencia`; `vigente_en(db, clave, fecha, sucursal_id=None)`, `listar_historial`, `leer_configuracion`; `GET /parametros/configuracion`, `GET /parametros/{clave}/historial` (ADMIN only); `POST /parametros` normalizes `vigente_desde` to day 1 and rejects past months for MOTOR keys (E-PARAM-002 with the rule). No migration (head stays `b5d91e3a7c42`).
  - Frontend: `/motored/configuracion` (ADMIN gate, 7 tabs, Topes links to `/motored/pedidos/topes`), `CampoConfiguracion` (typed controls, tooltip, Rige desde, history drawer), `configuracionApi.js`, sidebar "Configuración" (ADMIN, appended last).
  - Tablet check 768/1024/1280 done (no horizontal overflow); screenshots in `Documents/Motored/capturas-configuracion/`.
  - Open: a dedicated error code for the vigencia rule needs `corridas/codigos.py` (out of T1 surface); E-PARAM-002 reused.

- 2026-10-04: T6 + T7 done by one delegated writer (route: delegated, trigger: 2+ non-trivial files across backend and frontend). TDD: pytest and jest written first; RED observed (68 backend failures and 12 frontend failures before code), then GREEN.
  - Backend: 8 keys in `GRUPO_OPERACION` (global, not snapshotted, versioned): `hmcl_nits` (unique digit strings), `grupo_por_cargo` (cargo names uppercase/trimmed -> PERSONA|COMERCIALES|OTROS), `lineas_comerciales`, `kpi_semaforo_cortes` (0..200, ambar < verde) in section indicadores; `comision_tramos` (first desde 0, strictly increasing, tasa >= 0, unique non-empty names), `comision_base_pago` (sin_hmcl), `cumplimiento_base` (con_hmcl), `comision_cargos_asesor` in section comisiones. Defaults copied from `tablero_asesores` (a test guards drift; the tablero files were NOT edited). Builders extended: `unicos` (digit list), `normalizado` (map), `maximo` (numeric object), unique names (tramos).
  - `lineas_comerciales` is NOT cross-checked against `tipos_inventario_incluidos`: a registry validator sees one key and no DB, and that list can change after the lines are saved. The tooltip tells the admin to keep them consistent.
  - New code `E-PARAM-005` (`E_PARAM_VIGENCIA_PASADA`, same message) for the "past month on a snapshotted key" rule; T1 tests updated to it.
  - Frontend: tabs Indicadores and Comisiones (`SeccionIndicadores`, `SeccionComisiones`, `CamposDeSeccion`), dedicated editors chosen by key (`editores.js`): chips list, cargo map ("Agregar cargo"), semaforo with live 3-band preview, tramos table (add/remove/reorder). Live Spanish validation (`validaciones.js`) also blocks Guardar. `SeccionPanel`/`ConfiguracionContainer` now pass `data` and `recargar`. Option labels "Sin HMCL"/"Con HMCL" for the two base enums.
  - Verification: backend `tests/motored` 4836 passed; UM `tests --ignore=tests/motored` 1296 passed; `-m pg_real` 423 passed, 2 skipped (throwaway PG 18, new `pg_real/test_configuracion_operacion_pg.py`); full jest 157 suites / 1607 tests passed (run alone). Browser check at 768/1024/1280 (mocked API): no horizontal overflow; every control of the two tabs is >= 44 px (only the sidebar nav buttons, 35 px, are smaller, untouched). Screenshots `t6-*`, `t7-*` in `Documents/Motored/capturas-configuracion/`.
  - Open: "Valor por defecto" still shows raw codes (`sin_hmcl`, `verde_desde: 90`) because `formatearValor` is generic (T1).
