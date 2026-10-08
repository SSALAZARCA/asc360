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
- [ ] R1: the create-referencia form (línea + proveedor), plus backend support for both fields on the resolver action.
- [ ] R2: "Volver a validar". The backend reprocesses from the stored file and persists ignores across reprocessing. The frontend gets the button, a Procesando state and a refreshed informe.

## Sequencing
This starts after the ingresos-upload fix lands, because both touch `api/cargas.py` and the ingesta orchestrator.
