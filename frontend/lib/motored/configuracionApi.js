/**
 * frontend/lib/motored/configuracionApi.js
 *
 * Client of the ADMIN-only Configuración page (`/api/motored/parametros`).
 * Every function rejects with an `Error` that carries `status` and, for a
 * coded rule (E-PARAM-nnn), `code` (see `httpErrors.codedError`).
 */
import { motoredFetchJson } from './motoredFetch';

/** `{ secciones: [{ seccion, grupos: [{ grupo, claves: [...] }] }] }`. */
export const getConfiguracion = () => motoredFetchJson('/parametros/configuracion');

/** The versions of one key, newest first, with the author's name. */
export const getHistorialParametro = (clave) => (
  motoredFetchJson(`/parametros/${encodeURIComponent(clave)}/historial`)
);

/** A new version: `{ clave, valor, vigente_desde (YYYY-MM-DD), sucursal_id }`. */
export const guardarParametro = (payload) => (
  motoredFetchJson('/parametros', { method: 'POST', body: JSON.stringify(payload) })
);
