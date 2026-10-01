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

// --- Budget cap and recorte (F4) ----------------------------------------------

/** Cap, value and excess of every tienda of the corrida (`activo: false` when the mode is off or it is a scenario). */
export const getTopesCorrida = (id) => motoredFetchJson(`${BASE}/${id}/topes`);
/** The proposal of ONE draft tienda; it carries the `token` that `aplicarRecorte` must send back. */
export const getRecorte = (id, sucursalId) => motoredFetchJson(`${tienda(id, sucursalId)}/recorte`);
/** Applies the proposal the user saw; a changed proposal answers 409 E-CORRIDA-060 with the fresh one in `detalle`. */
export const aplicarRecorte = (id, sucursalId, token) => post(`${tienda(id, sucursalId)}/recorte`, { token });
/** The switch and the cap of every active tienda (ADMIN and COMPRAS read). */
export const getTopesPresupuesto = () => motoredFetchJson('/parametros/topes-presupuesto');
/** `[{ sucursal_id, valor }]`; `valor: null` removes the cap (ADMIN only). */
export const guardarTopes = (topes) => post('/parametros/topes-presupuesto', { topes });
/** Turns the cap mode on or off from `vigenteDesde` (`YYYY-MM-DD`); ADMIN only. */
export const setModoTope = (activo, vigenteDesde) => (
  post('/parametros', { clave: 'modo_tope_presupuesto', valor: activo, vigente_desde: vigenteDesde })
);

// --- Consolidated network view (F5a) -------------------------------------------

/** One page of the references x tiendas matrix; `filtros` are `q`, `limite` (<= 100) and `offset`. */
export const getConsolidado = (id, filtros) => motoredFetchJson(`${BASE}/${id}/consolidado${consulta(filtros)}`);

// --- Scenarios and comparison (F5b) ---------------------------------------------

/** The engine keys a scenario can override: `{ clave, tipo, dominio, default, opciones? }` (defaults, not current values). */
export const listarClavesMotor = () => motoredFetchJson('/parametros/claves?grupo=MOTOR');
/** The value in force today for one key (404 when it has no version: the default applies). */
export const getParametroVigente = (clave) => motoredFetchJson(`/parametros/${encodeURIComponent(clave)}/vigente`);
/** A scenario next to a real corrida (`con`): `con`, `sucursal_id`, `solo_diferencias`, `limite` (<= 100), `offset`. */
export const compararCorridas = (id, filtros) => motoredFetchJson(`${BASE}/${id}/comparar${consulta(filtros)}`);

// --- Export to HMCL -----------------------------------------------------------

/** Downloads the xlsx of one tienda; resolves `{ nombre, omitidas }`. */
export const exportarTienda = (id, sucursalId) => descargarArchivo(`${tienda(id, sucursalId)}/exportar`, 'pedido.xlsx');
/** Downloads the zip of the closed and sent tiendas (or of `sucursalIds`); `omitidas` lists the skipped ones. */
export function exportarZip(id, sucursalIds) {
  const tiendas = (sucursalIds || []).map((s) => `sucursal_id=${encodeURIComponent(s)}`).join('&');
  return descargarArchivo(`${BASE}/${id}/exportar${tiendas ? `?${tiendas}` : ''}`, 'pedidos.zip');
}
