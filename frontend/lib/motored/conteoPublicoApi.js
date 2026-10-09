/**
 * frontend/lib/motored/conteoPublicoApi.js
 *
 * Client of the PUBLIC pair API of the inventory counts
 * (`/api/motored/publico/conteos/{slug}/...`, odd/motored-conteos-inventario
 * WU7-WU9). Counting pairs have no Motored account, so this is a plain
 * `fetch` with the device token as a Bearer header -- never `motoredFetch`,
 * which carries the logged-in Motored session.
 *
 * Errors are thrown as `ConteoApiError`:
 * - `red: true` when the request never got an answer (offline, DNS, CORS)
 *   or the server failed (5xx): the caller keeps its data and retries;
 * - otherwise `status` plus the backend's stable `codigo` and `mensaje`.
 *
 * The device session (token, label, store) is kept in `localStorage` keyed
 * by slug, so a reload or a reopen on the same device resumes counting.
 * Cédulas are only ever sent in the join body: they are never stored.
 */
import { getMotoredApiUrl } from './motoredFetch';

const PREFIJO_SESION = 'motored_conteo_sesion:';

export class ConteoApiError extends Error {
  constructor({ status = 0, codigo = null, mensaje = '', red = false }) {
    super(mensaje || codigo || 'Error de conexión');
    this.name = 'ConteoApiError';
    this.status = status;
    this.codigo = codigo;
    this.red = red;
  }
}

export function esErrorDeRed(error) {
  return Boolean(error && error.red);
}

function urlBase(slug) {
  return `${getMotoredApiUrl()}/publico/conteos/${encodeURIComponent(slug)}`;
}

async function leerJson(res) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function errorDesde(res, cuerpo) {
  const detalle = cuerpo && typeof cuerpo.detail === 'object' ? cuerpo.detail : {};
  return new ConteoApiError({
    status: res.status,
    codigo: detalle.code || null,
    mensaje: detalle.mensaje || '',
    red: res.status >= 500,
  });
}

async function pedir(url, { token, method = 'GET', body, headers = {} } = {}) {
  let res;
  try {
    res = await fetch(url, {
      method,
      cache: 'no-store',
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ConteoApiError({ red: true, mensaje: 'Sin conexión' });
  }
  return res;
}

async function pedirJson(url, opciones) {
  const res = await pedir(url, opciones);
  const cuerpo = res.status === 204 ? null : await leerJson(res);
  if (!res.ok) throw errorDesde(res, cuerpo);
  return cuerpo;
}

/** `{sesion_token, sesion_id, etiqueta, integrantes, sucursal, estado_conteo}`. */
export function unirse(slug, { codigo, integrantes, dispositivo }) {
  return pedirJson(`${urlBase(slug)}/unirse`, {
    method: 'POST',
    body: { codigo, dispositivo, integrantes },
  });
}

/** The calls of a joined device; `token` is the device's Bearer token. */
export function crearConteoApi(slug, token) {
  const base = urlBase(slug);
  const conToken = (opciones = {}) => ({ ...opciones, token });
  return {
    sesion: () => pedirJson(`${base}/sesion`, conToken()),
    salir: () => pedirJson(`${base}/salir`, conToken({ method: 'POST' })),
    /** `{noCambio: true}` on 304, else `{etag, version, referencias}`. */
    async catalogo(etag) {
      const headers = etag ? { 'If-None-Match': etag } : {};
      const res = await pedir(`${base}/catalogo`, conToken({ headers }));
      if (res.status === 304) return { noCambio: true };
      const cuerpo = await leerJson(res);
      if (!res.ok) throw errorDesde(res, cuerpo);
      const nuevaEtag = res.headers && res.headers.get ? res.headers.get('ETag') : null;
      return { etag: nuevaEtag, version: cuerpo.version, referencias: cuerpo.referencias || [] };
    },
    ubicaciones: () => pedirJson(`${base}/ubicaciones`, conToken()),
    fijarUbicacion: (codigo, nombre) =>
      pedirJson(`${base}/ubicacion`, conToken({
        method: 'PUT',
        body: nombre ? { codigo, nombre } : { codigo },
      })),
    enviarLecturas: (lecturas) =>
      pedirJson(`${base}/lecturas`, conToken({ method: 'POST', body: { lecturas } })),
    anular: (id) =>
      pedirJson(`${base}/lecturas/${encodeURIComponent(id)}/anular`, conToken({ method: 'POST' })),
    recientes: (limite = 200) =>
      pedirJson(`${base}/lecturas/recientes?limite=${limite}`, conToken()),
    reconteos: () => pedirJson(`${base}/reconteos`, conToken()),
    terminarReconteo: (id) =>
      pedirJson(`${base}/reconteos/${encodeURIComponent(id)}/terminar`, conToken({ method: 'POST' })),
  };
}

// --- device session persistence ---------------------------------------------

function almacen() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

/**
 * `{token, sesionId, etiqueta, sucursal, ubicacion}` or null. `ubicacion`
 * (`{codigo, nombre}`) is the last known location, used when the device
 * reopens offline.
 */
export function leerSesionGuardada(slug) {
  const ls = almacen();
  if (!ls) return null;
  try {
    const guardada = JSON.parse(ls.getItem(PREFIJO_SESION + slug));
    return guardada && guardada.token ? guardada : null;
  } catch {
    return null;
  }
}

export function guardarSesion(slug, { token, sesionId, etiqueta, sucursal, ubicacion = null }) {
  const ls = almacen();
  if (!ls) return;
  try {
    const datos = { token, sesionId, etiqueta, sucursal, ubicacion };
    ls.setItem(PREFIJO_SESION + slug, JSON.stringify(datos));
  } catch {
    // Storage full or blocked: the session still works until a reload.
  }
}

export function borrarSesion(slug) {
  const ls = almacen();
  if (!ls) return;
  try {
    ls.removeItem(PREFIJO_SESION + slug);
  } catch {
    // Nothing to clean.
  }
}

export function claveSesion(slug) {
  return PREFIJO_SESION + slug;
}
