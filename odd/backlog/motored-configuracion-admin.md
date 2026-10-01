# Backlog: Motored admin "Configuración" screen

Status: **pending**. Build it after the advisor-dashboard feature (`odd/tasks/motored-tablero-asesores.md`).
Compiled 2026-10-01 jointly by the ventas/dashboard session and the F3/F4 session, at the user's request.

## Why
Many admin-tunable parameters exist today with no screen. They are either env vars (changed in Coolify) or DB keys with no UI. The user decided that the inventory retention purge must be switched on and off, and have its days set, from the APP: an auto-purge with an in-app toggle (option B).

**User decisions (2026-10-01)**
- The screen is visible to **ADMIN only**. Motored has no superadmin.
- **Clarified rule.** Everything that concerns the business OPERATION and its CALCULATIONS is set from the app. That covers engine parameters, ingesta business rules, data retention and the budget cap.
- **Server and technical concerns stay in the server config (Coolify).** That covers connections, secrets, worker polls, timeouts, retries, batch sizes and upload size limits.
- An earlier reading ("everything from the app, including technical settings") was corrected by the user the same day.

## Storage decision
- Do NOT create a new key/value table. Reuse `parametro_metodologia`, which already provides:
  - a typed registry with validation (E-PARAM-001/002/003),
  - global and per-sucursal scope,
  - ADMIN-only writes,
  - insert-only versioning with `vigente_desde`, `created_by` and `created_at`, which serves as the audit.
- Add a new registry group (proposed `GRUPO_OPERACION`) that is NOT snapshotted into corridas, like the F2 ingesta group.
- Each consumer reads the effective value through the existing resolver and falls back to the env var when no row exists.
- Proposed retention keys. Tell the F3/F4 session the final names:
  - `retencion_inventario_habilitada`
  - `retencion_inventario_dias`
  - `retencion_corridas_habilitada`
  - `retencion_corridas_dias`

## Gaps to build with the screen
- A list/history GET. Today only `GET /parametros/{clave}/vigente` exists, and it is global only.
- A per-sucursal read.
- The UI itself. `frontend/lib/motored/api.js:267-276` has client stubs that nothing calls.

## Parameter inventory
Paths are relative to `backend/app/motored/` unless noted.

### 1. Operation settings that are env today (`app/config.py`) and move to the app
| Setting | Default | Note |
|---|---|---|
| `MOTORED_RETENCION_ENABLED` | False | Inventory purge (snapshot + `inventario_detalle`). User decision: option B, an auto-purge toggle in the app. |
| `MOTORED_RETENCION_DIAS` | 90 | Window anchored to `max(fecha_corte)`, not to now. |
| `MOTORED_CORRIDA_RETENCION_ENABLED` | False | Corridas purge. |
| `MOTORED_CORRIDA_RETENCION_DIAS` | 45 | |
| `MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT` | 0.5 | Business tolerance for a declared period. |

### 2. Stays in the server config (technical, not operation)
- **Connections and secrets:** `MOTORED_ENABLED`, `MOTORED_DATABASE_URL`, `MOTORED_SECRET_KEY`, `MOTORED_MINIO_BUCKET`.
- **Worker tuning:** `MOTORED_CORRIDAS_LOOP_ENABLED` (emergency kill switch), `MOTORED_CORRIDA_POLL_SEGUNDOS`, `_TIMEOUT_MIN`, `_MAX_INTENTOS`, `MOTORED_INGESTA_POLL_SEGUNDOS`, `_TIMEOUT_MIN`, `_PAUSA_MS`, `MOTORED_INGESTA_LOTE`.
- **Server protection limits:** `MOTORED_MAX_UPLOAD_MB`, `MOTORED_MAX_UPLOAD_ROWS`, `MOTORED_MAX_MOVIMIENTO_UPLOAD_MB`, `MOTORED_MAX_MOVIMIENTO_ROWS`.

### 3. Engine keys in `parametro_metodologia`, group `GRUPO_MOTOR` (no UI today)
- The registry is `services/parametros_claves.py`, with defaults around lines 150-170.
- These keys are snapshotted per corrida (`parametros_corrida.py:146-156`), so a change affects NEW corridas only.

**These change pedido quantities:**
- `incluir_demanda_perdida_en_ponderada` (false), `factor_demanda_perdida` (1), `consolidar_sustituidas` (false).
- `dias_entre_pedidos` (30). Global AND per-sucursal, range 1..60.
- `modo_mes_en_curso` (EXCLUIDO, or PONDERADO), `tope_proyeccion_mes_actual` (3.0), `min_dias_mes_actual` (5).
- `excluir_transito_vencido` (false), `modo_redondeo_empaque` (CERCANO, or ARRIBA).
- `corte_abc_a` (0.80), `corte_abc_b` (0.95), `umbral_f` (2), `umbral_m` (1), `k_fms` (F=3, M=1.5, S=1).

**These change flags only:**
- `tolerancia_sobrestock` (0.25), `meses_inventario_muerto` (6).

**These change the preflight staleness gate only** (`vigencia.py:214`), each 7 days by default, range 1..365:
- `max_dias_antiguedad_inventario`
- `max_dias_antiguedad_backorder`
- `max_dias_antiguedad_facturas`
- `max_dias_antiguedad_ingresos`

### 4. Ingesta keys in `parametro_metodologia` (global, not snapshotted, no UI)
- `tipos_inventario_incluidos` (["0002 - REPUESTOS"])
- `crear_referencias_desconocidas` (false)
- `estados_backorder_vigentes` (["BACKORDER"])
- `dias_ventana_ingresos` (45)
- `tolerancia_ingreso_pct` (2.0)

### 5. Master-data columns
- **Already have UI (Maestros > Sucursales):** `sucursal.dias_seguridad` (2.5), `dias_empaque`, `dias_transito`, `sic`, `fecha_apertura`, `activa`, and `bodega_principal` (via Bodegas).
- **No UI, hidden on purpose by the owner:** `proveedor.dias_empaque_default`, `dias_transito_default`, `dias_seguridad_default` (2.5).
- **Flag:** the 2.5 dias_seguridad default lives in three places: the sucursal column, the proveedor column and `cargador.py:68` (`DIAS_SEGURIDAD_POR_DEFECTO`).

### 6. Budget cap (F4 slice B5a, planned)
- `modo_tope_presupuesto` (global, OFF by default, ADMIN) and `presupuesto_maximo_pedido` (per sucursal).
- Both go in a new registry group, never snapshotted.
- F4 ships its own ADMIN "Topes por tienda" screen. Configuración should LINK to it, not duplicate it.

### 7. Keep in code (sanity limits and owner decisions)
- **Sanity limits:**
  - max edit quantity 9,999,999 (`services/corridas/valores.py:24`)
  - order number 1..50 characters (`envio.py:50`)
  - motivo up to 500 characters (`pedido_tienda.py:48`, `schemas/corrida.py:19-22`)
  - envío batch of 200 (`schemas/pedido.py:121`)
  - page sizes (`api/corridas.py:62-63`)
- **Not configurable:** the weekly one-envío-per-tienda rule. It is an owner decision and a DB unique constraint.
- **Owner decisions:** the window divisor 21 and weights 1..6 (`motor/ventana.py:15-16`), and the 6-month window.
- **Code invariants:** rounding and Fraction math, `MAX_CADENA`, states and codes.

### 8. Future candidates (F5): hardcoded engine constants
- `PESO_M0_BASE = 7` (`motor/mes_en_curso.py:39`)
- `MESES_PARA_TOPE = 3` (`mes_en_curso.py:40`)
- `DIAS_BASE_COBERTURA = 30` (`motor/cobertura.py:16`)

## Constraints for settings read by background jobs (F3/F4 session)
Worker tuning stays in env per the clarified rule, so the timeout-vs-heartbeat constraint is moot. These two still apply to the retention keys that move to the app:
1. **Read cadence.** Jobs read app settings at the start of each cycle through a cheap cached read. If the DB read fails, use the last known value, then env. Never crash the loop.
2. **Mid-run changes.** A change applies to the next run. It is never re-evaluated inside a purge that is already running.

## Open decisions for when this is built
- The safe min/max range for each operational value.
- How the screen warns that engine keys affect only NEW corridas.
- Tooltips for every non-obvious field (project convention for Motored).
