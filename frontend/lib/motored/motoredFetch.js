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
import { codedError } from './httpErrors';

export const MOTORED_TOKEN_KEY = 'motored_token';
export const MOTORED_USER_KEY = 'motored_user';
/** Set when the session ended on its own (401), so the login page can explain it. */
export const MOTORED_EXPIRED_KEY = 'motored_session_expired';

export const getMotoredApiUrl = () => {
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
  const httpsBase = base.replace(/^http:\/\/(?!localhost)/, 'https://');
  return httpsBase.replace(/\/api\/v1\/?$/, '/api/motored');
};

/**
 * `role` del usuario Motored logueado, o `null` si no hay sesión o el JSON
 * guardado es inválido (sdd/motored-pedidos-ingesta, Phase 10). Vivía
 * copiado 3 veces (`cargas/page.js`, `ErroresTab.js`, `ResumenTab.js`,
 * gga-driven fix) -- una sola fuente acá, mismo criterio "esta es la
 * garantía real de sesión Motored" que ya justifica que `MOTORED_USER_KEY`
 * viva en este módulo y no en `./api.js`.
 */
export function getRolActual() {
  if (typeof window === 'undefined') return null;
  try {
    const stored = sessionStorage.getItem(MOTORED_USER_KEY);
    return stored ? JSON.parse(stored).role : null;
  } catch {
    return null;
  }
}

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
      // A failed login attempt is not a lost session: only flag real expiries.
      if (token && !path.endsWith('/auth/login')) sessionStorage.setItem(MOTORED_EXPIRED_KEY, '1');
      sessionStorage.removeItem(MOTORED_TOKEN_KEY);
      sessionStorage.removeItem(MOTORED_USER_KEY);
      window.dispatchEvent(new Event('storage'));
    }
  }

  if (response.status === 403) await flagPasswordChangeRequired(response);

  return response;
}

/** A 403 PASSWORD_CHANGE_REQUIRED means the stored session must go to mi-cuenta: flag it and wake the layout. */
async function flagPasswordChangeRequired(response) {
  if (typeof window === 'undefined') return;
  try {
    const body = await response.clone().json();
    if (body?.detail?.code !== 'PASSWORD_CHANGE_REQUIRED') return;
    const user = JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY));
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ ...user, must_change_password: true }));
    window.dispatchEvent(new Event('storage'));
  } catch {
    /* not JSON or no stored user: leave the 403 to the caller */
  }
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
    throw codedError(res.status, body, `HTTP ${res.status}`);
  }
  return body;
}
