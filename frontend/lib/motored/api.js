/**
 * frontend/lib/motored/api.js
 *
 * Typed helper functions for every Motored endpoint (sdd/motored-pedidos-
 * cimientos, Phase 6, task 6.1), built on top of `motoredFetch`/
 * `motoredFetchJson`. Mirrors the real backend contract 1:1 -- read
 * `backend/app/motored/api/{auth,maestros,carga,salud,usuarios,
 * parametros}.py` for the source of truth used here.
 *
 * `getMotoredApiUrl` is re-exported from `./motoredFetch` for convenience
 * (e.g. the login page needs the base URL for a pre-auth request, before any
 * token exists).
 */
import { motoredFetch, motoredFetchJson, getMotoredApiUrl } from './motoredFetch';

export { getMotoredApiUrl };

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/** POST /auth/login -- credenciales planas, sin token todavía. */
export async function login(email, password) {
  const res = await motoredFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || 'Credenciales incorrectas');
  }
  return body; // { access_token, token_type, user }
}

// ---------------------------------------------------------------------------
// Maestros -- CRUD genérico. `entidad` es PLURAL acá
// (sucursales|bodegas|referencias|proveedores), igual que
// `backend/app/motored/api/maestros.py`'s `_CONFIGS` keys.
// ---------------------------------------------------------------------------

export async function listMaestros(entidadPlural) {
  return motoredFetchJson(`/maestros/${entidadPlural}`);
}

export async function getMaestro(entidadPlural, id) {
  return motoredFetchJson(`/maestros/${entidadPlural}/${id}`);
}

export async function createMaestro(entidadPlural, payload) {
  return motoredFetchJson(`/maestros/${entidadPlural}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateMaestro(entidadPlural, id, payload) {
  return motoredFetchJson(`/maestros/${entidadPlural}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function deactivateMaestro(entidadPlural, id) {
  return motoredFetchJson(`/maestros/${entidadPlural}/${id}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Carga masiva -- `entidad` es SINGULAR acá (sucursal|bodega|proveedor|
// referencia), igual que `backend/app/motored/api/carga.py`. Recibe filas
// YA ESTRUCTURADAS (list[dict]) -- Fase 1 no parsea `.xlsx` en el browser
// (design doc / owner scope), el frontend arma el JSON de filas y el
// backend valida/escribe.
// ---------------------------------------------------------------------------

export async function validarCarga(entidadSingular, filas) {
  return motoredFetchJson(`/maestros/${entidadSingular}/carga/validar`, {
    method: 'POST',
    body: JSON.stringify({ filas }),
  });
}

export async function subirCarga(entidadSingular, filas) {
  return motoredFetchJson(`/maestros/${entidadSingular}/carga`, {
    method: 'POST',
    body: JSON.stringify({ filas }),
  });
}

// ---------------------------------------------------------------------------
// Salud de maestros
// ---------------------------------------------------------------------------

export async function getSalud() {
  return motoredFetchJson('/maestros/salud');
}

// ---------------------------------------------------------------------------
// Usuarios (ADMIN únicamente)
// ---------------------------------------------------------------------------

export async function listUsuarios() {
  return motoredFetchJson('/usuarios');
}

export async function createUsuario(payload) {
  return motoredFetchJson('/usuarios', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deactivateUsuario(id) {
  return motoredFetchJson(`/usuarios/${id}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Parámetros de metodología (estructura únicamente en Fase 1)
// ---------------------------------------------------------------------------

export async function crearParametro(payload) {
  return motoredFetchJson('/parametros', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getParametroVigente(clave) {
  return motoredFetchJson(`/parametros/${clave}/vigente`);
}
