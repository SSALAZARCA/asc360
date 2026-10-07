# Motored — raw ERP VENTAS load (backend)

## Objective
Load the raw ERP VENTAS file untouched. Discard non-parts rows by ERP tipo code, take each row's line from the referencia master, let users fix missing lines before apply, and optionally replace a whole month for the network.

The frontend belongs to the pedidos session (71); its plan is in `odd/tasks/` (raw ERP sales upload screens). The contract is agreed with 71 and 5d (Engram topic `motored/ventas-linea-desde-maestro`).

## Decisions (user, 2026-10-06; GO confirmed directly to this session)
- **Denylist.** Key `ventas_tipos_excluidos` = `[{codigo, modo: "prefijo"|"exacto"}]`, GRUPO_OPERACION, section "cargas", trimmed and upper-cased. Defaults: IM19 as prefijo; VS12, VS13, ST001–ST008, G01, OBS2 and RPGOGORO as exacto. Matching rows are counted in the log (`filas_tipo_excluido`) and are never a carga_error.
- **Line from the master.** The line comes from `referencia.linea_comercial` (trim, upper, no accents) and is checked against `tipos_inventario_incluidos`. It is evaluated against the CURRENT master when building the report AND at apply.
  - A line outside the list (e.g. MOTOS) is counted as `filas_fuera_de_linea` and is not listed for action.
  - **Rule revised 2026-10-06** (the user: "se hace durante el proceso de cargue"; agreed by 84, 71 and 5d). There is NO legacy fallback. A row with an empty master line goes to `sin_linea`, and apply is BLOCKED (409 "Hay N referencias sin línea: asígnelas antes de aplicar.") while that list is non-empty. Nothing is silently dropped from `venta_mensual`, which protects pedido demand and the pedido universe.
  - The scoped PUT accepts `lineas_comerciales` ∪ {"NO COMERCIAL"}. The selector option "No es de repuestos (descartar)" writes that sentinel, so the ref becomes `fuera_de_linea` from then on.
- **Unknown referencia.** A ref not in the master gives REFERENCIA_NO_ENCONTRADA (existing behavior), aggregated per code in `no_encontradas`.
- **Endpoints:**
  - `GET /api/motored/cargas/{id}/referencias-sin-linea` → `{sin_linea: [{referencia_id, codigo, nombre, filas, unidades, valor}], fuera_de_linea: [{linea, filas}], no_encontradas: [{codigo, filas}]}`, computed live.
  - `PUT /api/motored/cargas/{carga_id}/referencias-sin-linea/{referencia_id}` with body `{linea_comercial}`:
    - roles ADMIN and COMPRAS;
    - guards: the carga is VENTAS, not applied, not annulled; the ref is in the live `sin_linea` list, otherwise 409; the line is in `lineas_comerciales`, otherwise 422;
    - writes through `maestros.update_referencia` (KPI dirty hook) plus a carga log audit entry `{referencia_id, codigo, linea, usuario_id, en}`;
    - returns 200 with the full payload above.
  - The general `PATCH /maestros/referencias/{id}` stays ADMIN-only.
- **Full-month replace.** `POST /cargas` (VENTAS) takes the form field `reemplaza_mes_completo: bool`, persisted on the carga. Apply reads it from the carga.
  - `GET /cargas/{id}/vaciado-previsto` → `[{sucursal_id, nombre, mes, filas_actuales}]`: stores with existing sales in the file's months that are absent from the file. Empty when the flag is false.
  - With the flag, apply purges `venta_detalle` + `venta_mensual` for ALL stores of those months and refreshes the KPI summary for every purged (store, month).
  - Annulling the carga later does NOT restore the purged rows; the UI warns about this.
- **venta_mensual purge.** Before the upsert, delete the file's (sucursal, año, mes) keys, mirroring `venta_detalle`, in the same transaction. Check that `anular_carga` stays consistent.
- **Unchanged:** MODULO and C.O.; `refrescar_si_construido` in `aplicar_detalle`; the cost-from-sales feature is postponed.

## Production safety
Coolify auto-deploys main. Each piece ships only when it works on its own, and the existing load must never break. Tests must be green and checked on Python 3.11 before each push.

## Tasks
- [ ] **V1** `ventas_tipos_excluidos` key + validator + defaults (no behavior change yet).
- [ ] **V2** Ingest core: the denylist, the master line with the legacy fallback, the counters, `no_encontradas` aggregation, plus `GET referencias-sin-linea` and the scoped `PUT`.
- [ ] **V3** The venta_mensual purge for the file's keys, and `anular_carga` consistency.
- [ ] **V4** `reemplaza_mes_completo` + `GET vaciado-previsto` + the full-month purge + the KPI refresh for the purged keys.

## Next step
V1–V4 by one delegated writer, one commit each, pushed one by one after review. Ping 71 as each contract lands.
