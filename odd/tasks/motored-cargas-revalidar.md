# Motored: fix carga errors and revalidate without re-uploading

## Objective
While a carga is VALIDADO (not applied), the owner fixes errors in the Errores tab and then revalidates the SAME carga from its stored file. There is no re-upload.

## Owner decisions (2026-10-08)
- **"+" on REFERENCIA_NO_ENCONTRADA opens a small form:**
  - Línea comercial: required, from the configured `lineas_comerciales`.
  - Proveedor: defaults to HMCL, editable.
  - The form says how many rows of this carga it resolves.
  - It no longer always creates the referencia under OTROS with no line.
- **"Volver a validar" button (VALIDADO only):**
  - Reprocesses the stored file (MinIO `ruta_objeto`) with the current catalog and mappings.
  - Rows the user marked "ignorar" stay ignored.
  - Staging, errors and the informe are rebuilt for the same carga, which shows "Procesando" meanwhile.
  - Applies to every carga tipo.
  - Not available once APLICADO or ANULADO.
- **Example:** 25 rows of `BTX4L/BTZ5S-BS` in Facturas de pedidos. Create the referencia once, then revalidate, and all 25 enter.

## Tasks
- [x] R1 (4fb32a0, 1b219bd): the create-referencia form (línea + proveedor), plus backend support for both fields on the resolver action.
- [x] R2 (4fb32a0, 1b219bd; backend 6537 passed, pg_real 796 passed, jest 2303 passed): "Volver a validar". The backend reprocesses from the stored file and persists ignores across reprocessing. The frontend gets the button, a Procesando state and a refreshed informe.

## Sequencing
This starts after the ingresos-upload fix lands, because both touch `api/cargas.py` and the ingesta orchestrator.

## Follow-ups (not done)
- Anular does not lock the carga or refuse PENDIENTE/PROCESANDO, so a validation still running can bring an annulled carga back to VALIDADO. This existed before; revalidation makes it slightly more likely.
- "Volver a validar" lives only in Resumen. Showing it in Errores needs `CargaDetalle.js` to pass `onChanged={reload}` to `ErroresTab`.
