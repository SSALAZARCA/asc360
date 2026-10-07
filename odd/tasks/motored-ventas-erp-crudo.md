# Motored: load the raw ERP VENTAS file (frontend part)

Status: **plan agreed between the 3 sessions; waiting for the owner's go. No code yet.**

## Split
- **KPI session (84):** backend. Covers the denylist key, the ingest core, the purge, the full-month option and the KPI hooks.
- **This session:** frontend.
  - **F1:** the denylist editor in Configuración > Cargas.
  - **F2:** the dry-run panel, with the line selector for refs that have no line.
  - **F3:** the "reemplaza el mes completo" checkbox and its warning.

## Contract (agreed with 84)
- **A.** Key `ventas_tipos_excluidos` (GRUPO_OPERACION, section "cargas"): `[{codigo, modo: "prefijo"|"exacto"}]`.
  - Defaults: IM19 as a prefijo; VS12, VS13, ST001..ST008, G01, OBS2 and RPGOGORO as exacto.
- **B.** The line is evaluated against the current `referencia.linea_comercial`, both in the report and at apply. There is no revalidar step.
- **C.** `GET /cargas/{id}/referencias-sin-linea` returns `{sin_linea: [{referencia_id, codigo, nombre, filas, unidades, valor}], fuera_de_linea: [{linea, filas}], no_encontradas: [{codigo, filas}]}`, computed live.
  - A line is saved through `PATCH /maestros/referencias/{id}` with `{linea_comercial}`.
  - Whether COMPRAS may do this is a pending owner decision.
- **D.**
  - `POST /cargas` (VENTAS) takes the form field `reemplaza_mes_completo: bool`, persisted on the carga.
  - `GET /cargas/{id}/vaciado-previsto` returns `[{sucursal_id, nombre, mes, filas_actuales}]`.
  - Warning text: "Anular esta carga después NO recupera las ventas borradas de otras tiendas."
- **E.** Log counters: `filas_tipo_excluido`, `filas_fuera_de_linea`, `filas_sin_linea`, `filas_co_vacio`.

## Tasks
- [ ] F1 (after A lands)
- [ ] F2 (after C lands)
- [ ] F3 (after D lands)

## Owner decisions (relayed by 5d)
- COMPRAS may set `linea_comercial`, but ONLY for refs in a VENTAS carga's "sin línea" list. This does not grant general master editing.
  - Proposed scoped endpoint for 84: `PUT /cargas/{carga_id}/referencias-sin-linea/{referencia_id}` with body `{linea_comercial}`, for ADMIN and COMPRAS.
- Everything outside the parts lines is discarded. The scope is repuestos sold through mostrador and taller.
