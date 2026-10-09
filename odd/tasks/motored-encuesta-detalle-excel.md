# Motored Encuesta satisfacción — per-carga detail and Excel export

## Objective
In Encuesta satisfacción → Cargue de encuestas, let the user see how each survey of a carga was answered, and download results to Excel.

## Decisions (user, 2026-10-08)
- **Expandable detail.** Tapping a row in "Cargas realizadas" expands, below it, the carga's surveys:
  - columns: cliente, teléfono, tienda, estado (enviada / respondida / sin responder), nota 0–10, categoría (promotor / pasivo / detractor, semáforo colors), comentario, fecha de respuesta;
  - quick filter: Todas · Respondidas · Sin responder · Detractores;
  - inner scroll for long lists.
- **Excel per carga.** An "Excel" button on each carga row downloads all of its surveys.
- **Excel general.** A "Descargar resultados" button above the table, with a date range (desde – hasta) that filters by **send/carga date (option A)**: a result belongs to the month the survey was sent (the service month), not the response month. The response date is a column. Columns: the detail columns plus the carga file name and the send date.
- The detractor follow-up keeps using the response date (unchanged).

## Tasks
- [ ] **E1 Backend:** a per-carga detail endpoint, an Excel per carga, and an Excel by send-date range (openpyxl, following the existing Motored Excel export patterns; dates in Bogotá; cédula/phone as text). Tests.
- [ ] **E2 Frontend:** the expandable detail, filters and both download buttons in `encuesta-admin` (`CargasRealizadas`). Jest.

## Next step
E1 + E2 by one delegated writer.
