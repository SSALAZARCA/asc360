/**
 * frontend/lib/motored/pedidosApi.js
 *
 * Pedido screens client (`/api/motored/corridas`, Motored Fase 4). Every
 * function rejects with an `Error` that carries `status` and, for a coded
 * rule, `code` and `detalle` (see `httpErrors.codedError`). The backend pages
 * with `limite` / `offset`; `paginacion.js` adapts the UI paging.
 */
import { motoredFetchJson } from './motoredFetch';

const BASE = '/corridas';

function consulta(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([clave, valor]) => {
    if (valor !== '' && valor !== null && valor !== undefined) query.set(clave, String(valor));
  });
  const texto = query.toString();
  return texto ? `?${texto}` : '';
}

const post = (path, cuerpo) => motoredFetchJson(path, { method: 'POST', body: JSON.stringify(cuerpo) });
const patch = (path, cuerpo) => motoredFetchJson(path, { method: 'PATCH', body: JSON.stringify(cuerpo) });

// --- Corridas --------------------------------------------------------------

export const listarCorridas = (filtros) => motoredFetchJson(`${BASE}${consulta(filtros)}`);
export const crearCorrida = (cuerpo) => post(BASE, cuerpo);
export const getCorrida = (id) => motoredFetchJson(`${BASE}/${id}`);
export const getProgreso = (id) => motoredFetchJson(`${BASE}/${id}/progreso`);
export const anularCorrida = (id, motivo) => post(`${BASE}/${id}/anular`, { motivo });

// --- Lines and tienda pedido (reads) ----------------------------------------

export const listarLineas = (id, filtros) => motoredFetchJson(`${BASE}/${id}/lineas${consulta(filtros)}`);
export const getPedidoTienda = (id, sucursalId) => motoredFetchJson(`${BASE}/${id}/sucursales/${sucursalId}`);
export const getEventosTienda = (id, sucursalId) => motoredFetchJson(`${BASE}/${id}/sucursales/${sucursalId}/eventos`);
export const getHistorialLinea = (id, lineaId) => motoredFetchJson(`${BASE}/${id}/lineas/${lineaId}/historial`);

// --- Line edit ---------------------------------------------------------------

/** Sets "Cantidad a pedir" of a line; `esperado` is the quantity the screen saw (stale guard, E-CORRIDA-066). */
export const editarLinea = (id, lineaId, { pedido_final, esperado }) => (
  patch(`${BASE}/${id}/lineas/${lineaId}`, { pedido_final, esperado })
);
