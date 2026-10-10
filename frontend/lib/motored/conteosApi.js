/**
 * frontend/lib/motored/conteosApi.js
 *
 * Client of the inventory counts leader API (odd/motored-conteos-inventario,
 * WU11/WU12/WU12b), `backend/app/motored/api/conteos.py`, prefix
 * `/api/motored/conteos`. Kept apart from `./api.js` so that file does not
 * keep growing. Failures throw `codedError`s: the backend `mensaje`, its
 * `code` and the extra facts of the 409s in `error.datos`.
 */
import { motoredFetch, motoredFetchJson } from './motoredFetch';
import { codedError } from './httpErrors';

const BASE = '/conteos';

function enviar(path, body, method = 'POST') {
  return motoredFetchJson(path, { method, body: JSON.stringify(body ?? {}) });
}

function consulta(params) {
  const limpio = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== '');
  return limpio.length ? `?${new URLSearchParams(limpio).toString()}` : '';
}

// --- list and schedule ------------------------------------------------------

export const listarConteos = (filtros = {}) => motoredFetchJson(`${BASE}${consulta(filtros)}`);
export const listarSucursalesConteo = () => motoredFetchJson(`${BASE}/sucursales`);
export const listarLideres = () => motoredFetchJson(`${BASE}/lideres`);
export const programarConteo = (payload) => enviar(BASE, payload);
export const reprogramarConteo = (id, payload) => enviar(`${BASE}/${id}`, payload, 'PATCH');
export const anularConteo = (id, motivo) => enviar(`${BASE}/${id}/anular`, { motivo });
// ADMIN hard-deletes a TEST conteo (odd/tasks/motored-conteo-prueba.md); a real one is a 409 NO_ES_PRUEBA.
export const borrarConteoPrueba = (id) => motoredFetchJson(`${BASE}/${id}`, { method: 'DELETE' });
export const obtenerConteo = (id) => motoredFetchJson(`${BASE}/${id}`);

// --- start and access -------------------------------------------------------

/** Each 409 warning (INVENTARIO_ANTIGUO, PENDIENTES_POR_SANEAR) has its own confirmation flag. */
export const iniciarConteo = (id, { confirmarAntiguedad = false, confirmarPendientes = false } = {}) =>
  enviar(`${BASE}/${id}/iniciar`, {
    confirmar_antiguedad: confirmarAntiguedad, confirmar_pendientes: confirmarPendientes,
  });

// --- pendientes por sanear (WU15) -------------------------------------------

/** The store's invoices pending ingreso and transfers pending reception, with the load dates. */
export const obtenerPendientesConteo = (id) => motoredFetchJson(`${BASE}/${id}/pendientes`);
/** "Verificado en el ERP" on this conteo only; both answer the refreshed list. */
export const verificarPendiente = (id, tipo, clave) => enviar(`${BASE}/${id}/pendientes/verificar`, { tipo, clave });
export const desverificarPendiente = (id, tipo, clave) =>
  enviar(`${BASE}/${id}/pendientes/desverificar`, { tipo, clave });
export const rotarCodigo = (id) => enviar(`${BASE}/${id}/codigo/rotar`);

/** The QR PNG fetched with the token, as an object URL for an `<img>`. */
export async function obtenerQrObjectUrl(id) {
  const res = await motoredFetch(`${BASE}/${id}/qr.png`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw codedError(res.status, body, 'No se pudo cargar el QR.');
  }
  return URL.createObjectURL(await res.blob());
}

// --- pairs and locations ----------------------------------------------------

export const listarSesiones = (id) => motoredFetchJson(`${BASE}/${id}/sesiones`);
export const desconectarSesion = (id, sesionId) => enviar(`${BASE}/${id}/sesiones/${sesionId}/desconectar`);
export const listarUbicaciones = (id) => motoredFetchJson(`${BASE}/${id}/ubicaciones`);
export const crearUbicacion = (id, payload) => enviar(`${BASE}/${id}/ubicaciones`, payload);
export const editarUbicacion = (id, ubicacionId, payload) =>
  enviar(`${BASE}/${id}/ubicaciones/${ubicacionId}`, payload, 'PATCH');

// --- reconteo ---------------------------------------------------------------

export const terminarRonda = (id) => enviar(`${BASE}/${id}/terminar-ronda`);
/** The live panel (WU12b). With the last `version` still current the answer is `{ version, sin_cambios: true }`. */
export const obtenerPanel = (id, version) => motoredFetchJson(`${BASE}/${id}/panel${consulta({ version })}`);
export const obtenerDiferencias = (id, filtro = 'todas') =>
  motoredFetchJson(`${BASE}/${id}/diferencias${consulta({ filtro })}`);
export const pedirReconteo = (id, codigo) => enviar(`${BASE}/${id}/reconteos`, { codigo });
export const asignarReconteo = (id, reconteoId, body) =>
  enviar(`${BASE}/${id}/reconteos/${reconteoId}/asignar`, body);
export const repartirReconteos = (id) => enviar(`${BASE}/${id}/reconteos/auto-asignar`);
export const cancelarReconteo = (id, reconteoId) => enviar(`${BASE}/${id}/reconteos/${reconteoId}/cancelar`);

// --- close and downloads ----------------------------------------------------

export const cerrarConteo = (id, body) => enviar(`${BASE}/${id}/cerrar`, body);
export const obtenerResultado = (id) => motoredFetchJson(`${BASE}/${id}/resultado`);

function nombreDeDescarga(res, respaldo) {
  const cabecera = res.headers && res.headers.get ? res.headers.get('Content-Disposition') : null;
  const encontrado = cabecera && /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cabecera);
  return encontrado ? decodeURIComponent(encontrado[1]) : respaldo;
}

/** Same mechanism as `api.js`'s private `_descargarBlob`, with the backend mensaje on failure. */
async function descargar(path, respaldo) {
  const res = await motoredFetch(path);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw codedError(res.status, body, 'No se pudo descargar el archivo.');
  }
  const url = URL.createObjectURL(await res.blob());
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = nombreDeDescarga(res, respaldo);
  enlace.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export const descargarAjustes = (id) => descargar(`${BASE}/${id}/ajustes.xlsx`, `ajustes_conteo_${id}.xlsx`);
export const descargarAvance = (id) => descargar(`${BASE}/${id}/avance.xlsx`, `avance_conteo_${id}.xlsx`);
