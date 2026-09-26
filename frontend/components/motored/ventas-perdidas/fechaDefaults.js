/**
 * frontend/components/motored/ventas-perdidas/fechaDefaults.js
 *
 * sdd/motored-ventas-perdidas-panel, Phase 7, task 7.1. Owner decision made
 * AFTER the design doc (folded into `tasks.md` as authoritative): the
 * panel's date filter defaults to "last 30 days" on load, FRONTEND-only --
 * `GET /demanda-perdida/bot-lineas` keeps `desde`/`hasta` required with no
 * server-side default (design D2). Pure functions, no side effects, so
 * they're testable without mocking `Date` globally -- `ahora` is always an
 * explicit parameter (defaults to `new Date()` only at the call site inside
 * `useVentasPerdidas.js`).
 */
export function formatFechaISO(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function calcularRangoUltimos30Dias(ahora = new Date()) {
  const hasta = new Date(ahora);
  const desde = new Date(ahora);
  desde.setDate(desde.getDate() - 30);
  return { desde: formatFechaISO(desde), hasta: formatFechaISO(hasta) };
}
