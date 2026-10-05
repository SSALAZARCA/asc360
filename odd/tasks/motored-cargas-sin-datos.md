# Motored: declare "no data at this date" for backorder, facturas and ingresos

## Objective
Let ADMIN/COMPRAS unblock the corrida when HMCL truly has no backorder (or no facturas / ingresos) for the period, without weakening the preflight.

## Problem
The corrida preflight (`services/corridas/vigencia.py`) requires an APPLIED carga of BACKORDER, FACTURAS_PEDIDOS and INGRESOS_FACTURAS within their age limits. An uploaded file with zero rows ends CON_ERRORES (`CODIGO_SIN_FILAS_VALIDAS`), so "nothing pending" cannot be expressed and the corrida is blocked.

## Owner decision (2026-10-05, option A)
An explicit declaration "Sin <tipo> a esta fecha": a carga with 0 rows, APLICADO, with date and user, that the preflight accepts like any other. It stays auditable and anulable. The preflight is not relaxed (option B was rejected).

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Backend: endpoint plus service to create the declaration (types BACKORDER, FACTURAS_PEDIDOS, INGRESOS_FACTURAS only; ADMIN/COMPRAS). Verify the preflight accepts it and that the corrida reads zero backorder or tránsito from it. Anular works. Listing shows it distinctly. Frontend: button and confirmation in the Cargas tabs of those types, and a distinct label in the list. | delegated writer |

- [x] T1

## Checks
- Backend: `cd backend && .venv/bin/python -m pytest tests/motored -q`, plus pg_real on a throwaway PG.
- Frontend: `cd frontend && npx jest`.
- Test-first.

## Log
- 2026-10-05: T1 done.
  - `POST /cargas/sin-datos` (`services/ingesta/sin_datos.py`) creates an APLICADO EXCEL carga with 0 rows. It is marked by `log.sin_datos`, the name "Sin datos (declarado)" and the hash/path sentinel "sin-archivo". `origen` stays EXCEL, because the CHECK allows only EXCEL/BOT.
  - The preflight accepts it unchanged.
  - BACKORDER: rejected with a 409 if live backorder rows already exist at that date, or if a declaration is duplicated.
  - Tránsito is untouched.
  - Frontend: a "Declarar sin datos" button and dialog on the three tabs; the list label reads "Sin filas".
  - RED observed first.
  - Results: tests/motored 5690 passed; pg_real 640 passed, 3 skipped; jest 1935 passed.
