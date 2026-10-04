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
- [x] T2 (implemented, verified, NOT yet committed)
- [x] T3 (implemented, verified, NOT yet committed)
- [x] T4 (implemented, verified, NOT yet committed; period tolerance wired and shown, see the 2026-10-04 T4 completion entry)
- [x] T5 (implemented, verified, NOT yet committed)
- [x] T6 (implemented, verified, NOT yet committed)
- [x] T7 (implemented, verified, NOT yet committed)
- [x] T8 (the Topes link shipped in T1)

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

- 2026-10-04: T2 + T3 + T4 (Cargas tab) + T5 done by one delegated writer (route: delegated, trigger: 2+ non-trivial files across backend and frontend). TDD: RED observed per behaviour (48 registry failures, 7 reader failures, 13 avisos failures, 12 retention failures, 21 jest failures before code), then GREEN. The pg_real tests (`pg_real/test_configuracion_limpieza_pg.py`) were written after the code and passed on first run. No migration (head stays `c4e8a1f6d903`; `git fetch` showed nothing newer).
  - Backend keys (all `GRUPO_OPERACION`, global, not snapshotted, except `periodo_tolerancia_pct` in `GRUPO_INGESTA`): `aviso_hora_vispera` "16:30", `aviso_hora_dia` "08:30", `aviso_roles_destino` ["COMPRAS"] (ADMIN|COMPRAS, non-empty, no repeats); `retencion_inventario_habilitada` (env `MOTORED_RETENCION_ENABLED`), `retencion_inventario_dias` (env, 30..3650), `retencion_corridas_habilitada` (env), `retencion_corridas_dias` (env, 7..3650), with a Spanish explanation of the minimum; `periodo_tolerancia_pct` (env, 0..100). New builders `hora_hhmm`, `lista_de_opciones`; `_entera(explicacion=)`.
  - Shared reader `parametros.leer_valores` / `leer_con_memoria(db, fecha, respaldos, memoria, deshacer=True)`: stored valid row wins, else the caller's fallback (constant or env read at call time); a failed read keeps the last known value, then the fallback, and never raises.
  - T3: `avisos_antiguedad.ConfigAvisos` + `leer_config`; `procesar_avisos(..., config=None)` (no config = old constants); the early return uses the earliest of the two hours; `destinatarios(db, roles)`; `supervisor_avisos.run_tick` reads once per tick into `_memoria_config`. The reservation table is untouched, so idempotency is unchanged.
  - T5: `retencion.leer_config` / `ConfigRetencion`, `ejecutar_purga_inventario(dias=)`, `retencion_corridas.leer_config`; each purge cycle reads once and the days travel with the call (never re-read mid-purge). Side effect: a disabled purge now costs one config read (it used to cost no query); the old "never queries" tests were updated to expect exactly that one read.
  - T4 BLOCKED sub-part: the consumer of `MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT` is `services/ingesta/ventas.py::evaluar_periodo_declarado` (settings default, outside the allowed surface). Its callers in `orquestador.py` (`_verificar_periodo_ventas`, `ejecutar_aplicar`) pass no tolerance. Wiring the resolver in `orquestador.py` was tried and reverted: it adds one query to flows whose tests queue exact results and broke 7 tests outside the surface (`test_ingesta_orquestador.py` x3, `test_ingesta_ventas_fecha_max.py` x3, `test_ingesta_ventas_taller.py` x1). The key is registered but the Cargas tab does not show it.
  - Frontend: tabs Pedido (5 groups, banner, tooltips, per-tienda `ExcepcionesPorTienda` using `listMaestros('sucursales')` and the T1 per-sucursal save), Avisos (time inputs, role checkboxes), Cargas (4 keys, chips), Limpieza ("Nunca borra pedidos cerrados o enviados."). New controls `hora` and `lista_opciones`; `etiquetas.js` gives readable option names; `CampoConfiguracion` only lists scheduled versions of its own scope.
  - Verification: backend `tests/motored` 4917 passed; UM `tests --ignore=tests/motored` 1296 passed; `-m pg_real` 430 passed, 2 skipped (throwaway PG 18, stopped and deleted); full jest 159 suites / 1643 tests passed (run alone). Browser check 768/1024/1280 (mocked API): no horizontal overflow, every control of the four tabs >= 44 px (only the untouched sidebar nav buttons are smaller). Screenshots `t2-`, `t3-`, `t4-`, `t5-` in `Documents/Motored/capturas-configuracion/`.
  - Open: `inventario.py:374` (`fecha_corte_fuera_de_ventana`) still reads `MOTORED_RETENCION_DIAS` but has no caller today; wire it if E-CARGA-021 ever uses it.

- 2026-10-04: T4 completed by one delegated writer (route: delegated, trigger: ingest edit plus tests across 4 files, backend and frontend). TDD: RED observed (a stored 5 left the verdict RECHAZO for a file with 2.94 % out-of-period lines; the Cargas jest tests failed before the field existed), then GREEN. Replaces the BLOCKED note above.
  - Ingest: `orquestador._leer_tolerancia_periodo` reads `periodo_tolerancia_pct` once per carga through `parametros.leer_con_memoria` (real signature: `(db, fecha, respaldos, memoria, deshacer)`), fallback `settings.MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT` read at call time, `deshacer=False` (the carga has pending work, a rollback would expire it), coerced with `float()` because the form stores numeric text such as "5". Only VENTAS reads it (the only type with the period check): `_verificar_periodo_ventas` (dry run) and `ejecutar_aplicar` -> `aplicar_con_periodo(..., tolerancia_pct)`. `ventas.py` was NOT edited: `evaluar_periodo_declarado` already takes `tolerancia_pct` and stays pure with its settings default.
  - No stored row: byte-identical verdicts (tests with env 0.5 and env 5.0). The queues of the VENTAS dry-run and aplicar tests in `test_ingesta_orquestador.py`, `test_ingesta_ventas_fecha_max.py`, `test_ingesta_ventas_taller.py` got the extra read. A failed read is swallowed by the shared reader, so an unqueued test would pass silently on the fallback; the queues were updated explicitly anyway. Module memory `_memoria_tolerancia` is cleared by an autouse fixture.
  - Frontend: the Cargas tab now shows "Tolerancia del período declarado (%)" with the tooltip "Porcentaje máximo de líneas de otro mes que se acepta al declarar el período de un archivo. ..."; the decimal control sends numeric text ("5").
  - Verification: backend `tests/motored` 5052 passed; UM `--ignore=tests/motored` 1296 passed; `-m pg_real` 457 passed, 2 skipped, 2 failed (`test_the_retention_purges_only_old_annulled_failed_or_draft`, `test_the_retention_keeps_corridas_whose_pedido_is_history`: they also fail on a clean HEAD worktree against the same PG, so they are not caused by this change; the new `pg_real/test_configuracion_ingesta_pg.py` passed; the pg_real run was before the `float()` coercion, the new test was not rerun); full jest 159 suites / 1644 tests passed (run alone). Throwaway PG 18 stopped and deleted.
  - Open: the 2 pg_real retention failures need their own look (T5 area, committed in 96364cc).
