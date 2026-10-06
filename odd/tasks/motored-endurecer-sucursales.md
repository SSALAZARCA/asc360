# Motored: harden the Sucursales data after the C.O. migration

## Objective
Close the gaps found while loading the owner's Sucursales file and in the independent audit, so bad data cannot slip in silently.

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Make `sucursal.codigo_co` NOT NULL. The migration fails with a clear message if any row is still NULL. The `sucursal_sin_codigo_co` health check goes away or becomes unreachable. Test fixtures that create sucursales without a C.O. get updated (the KPI session's too, coordinated). | delegated writer |
| T2 | The upload and CRUD IntegrityError handlers report the real constraint as a readable Spanish message. Keep "Otra carga modificó…" only for real natural-key races (23505 on a natural key). Log every IntegrityError with its constraint name. Switch the Sucursales pg_real fixtures to `autoflush=False`, as in production. | delegated writer (same) |
| T3 | Reject (upload and form) a store's principal bodega that already belongs to another store as its principal or secondary, unless the same file or save releases it. Spanish message naming the other store. Also ignore or validate a raw `principal_id` sent in JSON upload rows. | delegated writer (same) |

- [x] T1
- [ ] T2
- [ ] T3

## Out of scope
- `start.sh` keeps starting the app when a migration fails. That is a deploy-behavior decision for the owner.

## Checks
- `tests/motored`, full pg_real on a throwaway PG, full jest.
- Test-first.
