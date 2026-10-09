/**
 * Public asesor report link: the asesor opens `/motored/informe/<token>` and proves who they are with
 * their cédula. No session exists here, so this is a plain fetch with NO auth headers (never the
 * authenticated Motored wrapper); only the API base URL helper is shared.
 */
import { getMotoredApiUrl } from './motoredFetch';

export const INFORME_INVALIDO = 'Enlace o cédula no válidos.';
export const INFORME_DEMASIADOS_INTENTOS = 'Demasiados intentos. Intenta de nuevo en unos minutos.';
export const INFORME_ERROR = 'No pudimos cargar tu informe. Intenta de nuevo.';
export const PENDIENTE_YA_NO = 'Esta factura ya no está pendiente.';
export const PENDIENTE_ERROR = 'No pudimos guardar tu respuesta. Intenta de nuevo.';

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

/**
 * The asesor answers "LLEGO" / "NO_HA_LLEGADO" for a pending invoice of her store (same link + cédula as the
 * report; nothing is stored). Resolves the updated invoice, or an Error whose message is ready to show.
 */
export async function confirmarPendiente(token, cedula, factura, estado) {
  let res;
  try {
    res = await fetch(`${getMotoredApiUrl()}/publico/informe/${encodeURIComponent(token)}/pendientes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cedula, factura, estado }),
    });
  } catch {
    throw new Error(PENDIENTE_ERROR);
  }
  if (res.status === 401) throw new Error(INFORME_INVALIDO);
  if (res.status === 429) throw new Error(INFORME_DEMASIADOS_INTENTOS);
  if (res.status === 409) throw new Error(PENDIENTE_YA_NO);
  if (!res.ok) throw new Error(PENDIENTE_ERROR);
  try {
    return await res.json();
  } catch {
    throw new Error(PENDIENTE_ERROR);
  }
}
