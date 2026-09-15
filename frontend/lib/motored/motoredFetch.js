/**
 * frontend/lib/motored/motoredFetch.js
 *
 * Motored's own fetch wrapper (sdd/motored-pedidos-cimientos, Phase 6,
 * design ADR-7). Mirrors `lib/authFetch.js`'s SHAPE exactly (same
 * Content-Type/FormData handling, same AbortController timeout, same
 * "clear session + dispatch storage on 401" behavior) but is otherwise
 * COMPLETELY ISOLATED from it:
 *   - reads/writes `motored_token` / `motored_user` sessionStorage keys,
 *     NEVER `um_token` / `um_user` (asc360's keys) -- total session
 *     isolation, per spec "Independent user store" / proposal hard
 *     isolation constraint.
 *   - targets `/api/motored` (via `getMotoredApiUrl`), never `/api/v1`.
 *
 * `getMotoredApiUrl` lives here (not in `./api.js`) so this module has zero
 * import-time dependency on `./api.js` -- `./api.js` imports FROM this file
 * (and re-exports `getMotoredApiUrl` for convenience), never the reverse.
 * One-directional dependency, no circular-import risk.
 */
export const MOTORED_TOKEN_KEY = 'motored_token';
export const MOTORED_USER_KEY = 'motored_user';

export const getMotoredApiUrl = () => {
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
  const httpsBase = base.replace(/^http:\/\/(?!localhost)/, 'https://');
  return httpsBase.replace(/\/api\/v1\/?$/, '/api/motored');
};

export async function motoredFetch(path, options = {}) {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem(MOTORED_TOKEN_KEY) : null;

  // Igual que authFetch.js: si el body es FormData, dejamos que el browser
  // setee el Content-Type con el boundary correcto.
  const isFormData = options.body instanceof FormData;

  const headers = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const url = path.startsWith('http') ? path : `${getMotoredApiUrl()}${path}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), options.timeout ?? 30000);

  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }

  // 401 -> token Motored vencido/inválido: limpiar SOLO las claves de
  // Motored. Nunca tocar `um_token`/`um_user` -- esta es la garantía de
  // aislamiento de sesión que el diseño exige.
  if (response.status === 401) {
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem(MOTORED_TOKEN_KEY);
      sessionStorage.removeItem(MOTORED_USER_KEY);
      window.dispatchEvent(new Event('storage'));
    }
  }

  return response;
}

/**
 * motoredFetchJson - igual que motoredFetch pero ya parsea el JSON.
 *
 * Nota: los endpoints de carga masiva (`validar`/`carga`) responden 200 con
 * `{ ok: false, errores: [...] }` para un archivo inválido (ver
 * `backend/app/motored/services/carga.py::procesar_carga`) -- ESE caso NO
 * es un error HTTP, así que no lanza acá; el caller (BulkUploadModal) es
 * quien interpreta el campo `ok` del body.
 */
export async function motoredFetchJson(path, options = {}) {
  const res = await motoredFetch(path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return body;
}
