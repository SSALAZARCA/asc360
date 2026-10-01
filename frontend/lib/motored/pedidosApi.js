/**
 * frontend/lib/motored/pedidosApi.js
 *
 * Pedido screens client (`/api/motored/corridas`, Motored Fase 4). Every
 * function rejects with an `Error` that carries `status` and, for a coded
 * rule, `code` and `detalle` (see `httpErrors.codedError`). The backend pages
 * with `limite` / `offset`; `paginacion.js` adapts the UI paging.
 */
import { motoredFetchJson } from './motoredFetch';
import { descargarArchivo } from './descargas';

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

// --- Pedido lifecycle (per tienda) -------------------------------------------

const tienda = (id, sucursalId) => `${BASE}/${id}/sucursales/${sucursalId}`;

export const cerrarTienda = (id, sucursalId) => post(`${tienda(id, sucursalId)}/cerrar`);
/** Closes the named tiendas (all or nothing) or, without a list, every tienda still in draft. */
export const cerrarLote = (id, sucursalIds) => (
  post(`${BASE}/${id}/cerrar`, sucursalIds ? { sucursal_ids: sucursalIds } : undefined)
);
export const reabrirTienda = (id, sucursalId, motivo) => post(`${tienda(id, sucursalId)}/reabrir`, { motivo });
/** `{ numero_pedido_proveedor, fecha_envio }` of ONE tienda. */
export const enviarTienda = (id, sucursalId, cuerpo) => post(`${tienda(id, sucursalId)}/enviar`, cuerpo);
/** `[{ sucursal_id, numero_pedido_proveedor, fecha_envio }]`, all or nothing. */
export const enviarLote = (id, envios) => post(`${BASE}/${id}/enviar`, { envios });
export const corregirEnvio = (id, sucursalId, numero) => (
  patch(`${tienda(id, sucursalId)}/envio`, { numero_pedido_proveedor: numero })
);

// --- Export to HMCL -----------------------------------------------------------

/** Downloads the xlsx of one tienda; resolves `{ nombre, omitidas }`. */
export const exportarTienda = (id, sucursalId) => descargarArchivo(`${tienda(id, sucursalId)}/exportar`, 'pedido.xlsx');
/** Downloads the zip of the closed and sent tiendas (or of `sucursalIds`); `omitidas` lists the skipped ones. */
export function exportarZip(id, sucursalIds) {
  const tiendas = (sucursalIds || []).map((s) => `sucursal_id=${encodeURIComponent(s)}`).join('&');
  return descargarArchivo(`${BASE}/${id}/exportar${tiendas ? `?${tiendas}` : ''}`, 'pedidos.zip');
}
