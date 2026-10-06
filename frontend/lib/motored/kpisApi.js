/** Clients of the KPI's endpoints (`/tablero-asesores/kpis/*`; ADMIN, COMPRAS and GERENCIA). */
import { descargarArchivo } from './descargas';
import { motoredFetchJson } from './motoredFetch';

const BASE = '/tablero-asesores/kpis';

/** Path of one tab for the given filters: `meses` and `sucursales` as CSV, `hmcl` as the mode. */
export function rutaKpis(tab, { meses, sucursales = [], hmcl = 'incluir' }) {
  const query = new URLSearchParams({ meses: [...meses].sort().join(',') });
  if (sucursales.length) query.set('sucursales', [...sucursales].sort().join(','));
  query.set('hmcl', hmcl);
  return `${BASE}/${tab}?${query.toString()}`;
}

export const getOpciones = () => motoredFetchJson(`${BASE}/opciones`);
export const getVentas = (filtros) => motoredFetchJson(rutaKpis('ventas', filtros));
export const getTiendas = (filtros) => motoredFetchJson(rutaKpis('tiendas', filtros));
export const getAsesores = (filtros) => motoredFetchJson(rutaKpis('asesores', filtros));
export const getComisiones = (filtros) => motoredFetchJson(rutaKpis('comisiones', filtros));
/** Downloads the xlsx of the settled month `mes` (AAAA-MM) with the same filters as the tab. */
export const descargarComisionesExcel = (filtros, mes) => descargarArchivo(rutaKpis('comisiones/excel', filtros), `comisiones_${mes}.xlsx`);

export const getEstado = () => motoredFetchJson(`${BASE}/estado`);
/** ADMIN only: asks for a full rebuild of the summaries. A 409 carries the "busy" message. */
export const recalcular = () => motoredFetchJson(`${BASE}/recalcular`, { method: 'POST' });
