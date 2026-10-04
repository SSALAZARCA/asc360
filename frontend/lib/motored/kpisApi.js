/** Clients of the KPI's endpoints (`/tablero-asesores/kpis/*`; ADMIN, COMPRAS and GERENCIA). */
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
