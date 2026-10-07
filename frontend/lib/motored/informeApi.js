/**
 * Public asesor report link: the asesor opens `/motored/informe/<token>` and proves who they are with
 * their cédula. No session exists here, so this is a plain fetch with NO auth headers (never the
 * authenticated Motored wrapper); only the API base URL helper is shared.
 */
import { getMotoredApiUrl } from './motoredFetch';

export const INFORME_INVALIDO = 'Enlace o cédula no válidos.';
export const INFORME_DEMASIADOS_INTENTOS = 'Demasiados intentos. Intenta de nuevo en unos minutos.';
export const INFORME_ERROR = 'No pudimos cargar tu informe. Intenta de nuevo.';

/** The asesor detail for this link, or an Error whose message is ready to show. */
export async function verInforme(token, cedula) {
  let res;
  try {
    res = await fetch(`${getMotoredApiUrl()}/publico/informe/${encodeURIComponent(token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cedula }),
    });
  } catch {
    throw new Error(INFORME_ERROR);
  }
  if (res.status === 401) throw new Error(INFORME_INVALIDO);
  if (res.status === 429) throw new Error(INFORME_DEMASIADOS_INTENTOS);
  if (!res.ok) throw new Error(INFORME_ERROR);
  try {
    const body = await res.json();
    // Accept the detail either bare or wrapped as `{ detalle }`.
    return body && body.detalle ? body.detalle : body;
  } catch {
    throw new Error(INFORME_ERROR);
  }
}
