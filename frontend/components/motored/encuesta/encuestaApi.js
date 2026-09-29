import { getMotoredApiUrl } from '../../../lib/motored/motoredFetch';

// Public endpoints: plain fetch, no auth header, never motoredFetch.
async function post(path, payload) {
  let res;
  try {
    res = await fetch(`${getMotoredApiUrl()}/encuesta/publico/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    return { kind: 'network' };
  }
  const data = await res.json().catch(() => ({}));
  if (res.ok) return { kind: 'ok', data };
  if (res.status === 429) return { kind: 'rate' };
  if (res.status === 409) return { kind: 'conflict' };
  if (res.status === 404) return { kind: 'notfound' };
  return { kind: 'error' };
}

export const identificar = (cedula) => post('identificar', { cedula });
export const enviarRespuesta = (payload) => post('respuestas', payload);
