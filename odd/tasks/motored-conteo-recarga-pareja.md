# Motored: the pair screen recovers its counted list after a failed reload

## Problem (owner test, 2026-10-10)

F5 on the desktop pair screen showed "Contado en A1" empty, with 0 units. The readings were safe on the server and the leader panel showed them; a second F5 restored everything.

Root cause (read-only investigation):
- On mount, `useConteo.js:92-105` calls `api.recientes()`. When it fails, it seeds with `sembrar(null, cola.itemsActuales(), local.codigo)`. `pedirJson` treats any 5xx as a network error; the likely trigger was the backend restarting after a deploy.
- Nothing ever seeds again: the 30 s timer and the `online` handler only call `refrescar`/`sincronizar`, and `resembrarLista` runs only after a location change.
- A non-network error seeds nothing at all.
- No jest test makes `/lecturas/recientes` fail on mount and then recover. `sesionGuardada()` never saves a location.

Risk: the pair sees 0, scans everything again, and the count doubles.

## Decisions (owner, 2026-10-10)

1. If the seed failed, the screen retries it automatically on the 30 s timer and on `online`, until it succeeds. It reuses `resembrarLista`, which already pauses the queue so nothing is counted twice.
2. While the seed is pending, the screen shows a notice instead of a silent 0: "No se pudo cargar lo contado. Reintentando… No vuelva a escanear lo que ya contó." The notice clears on success. This applies to both the desktop and mobile screens.
3. A jest test covers it: `/lecturas/recientes` fails on mount with a saved location, the notice shows, then a later retry succeeds, the list is restored and the notice is gone. Another test covers the non-network error path.
4. The saved session (`conteoPublicoApi.guardarSesion`) also stores `esPrueba`, so the PRUEBA badge shows at once after a reload.

## Checklist

- [x] T1 retry + notice + esPrueba persistence + jest tests (route: delegated writer, because there are 3+ non-trivial files)
- [x] T2 commit 1ad1950 (gga PASSED), pushed

## Progress

- 2026-10-10: decisions recorded. The writer starts once the panel-search writer is done (one writer at a time).
- 2026-10-10 T1 done (delegated writer, not committed). `useConteo` keeps a `faltaSembrar` ref, set when the mount seed fails with any non-401 error (it still seeds the queue, then warns). The 30 s refresh and `online` call `reintentarSiembra`: when a location is known and confirmed, it runs `resembrarLista`, which now returns true on success and clears the flag and the notice. `BannerListaSinCargar` (Avisos.js) shows `TEXTOS.listaSinCargar` on desktop and phone. `guardarSesion` stores `esPrueba`.
  - No double count: `useCola.pausar` now also waits for a send already in flight, and the queue's own `online` handler no longer sends while paused, so a reading is either in the server's list or still queued at reseed time.
  - Evidence: new `frontend/__tests__/motored-conteo-publico-recarga.test.jsx` (5 tests: 503 then `online`, 409 then the 30 s refresh, readings scanned during the notice end at 3+2=5 with 2 POSTed, phone notice, PRUEBA from the saved session with `/sesion` hanging). RED 5 failed / 5; GREEN `npx jest conteo`: Tests: 167 passed, 167 total.
