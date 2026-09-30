/**
 * Detractor cases (`/api/motored/detractores`). Errors carry the HTTP status
 * so callers can tell a 409 (someone else changed the case) from the rest.
 */
import { motoredFetch } from './motoredFetch';

const BASE = '/detractores';

export class DetractoresApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function messageOf(body, status) {
  const { detail } = body || {};
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((d) => d.msg).join('. ');
  return `Error ${status}`;
}

async function request(path, options) {
  const res = await motoredFetch(path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new DetractoresApiError(messageOf(body, res.status), res.status);
  return body;
}

const post = (path, payload) => request(path, { method: 'POST', body: JSON.stringify(payload) });

export function listDetractores(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) query.set(key, String(value));
  });
  return request(`${BASE}?${query.toString()}`);
}

export const getDetractor = (id) => request(`${BASE}/${id}`);
export const agregarAccion = (id, payload) => post(`${BASE}/${id}/acciones`, payload);
export const cambiarEstadoDetractor = (id, payload) => post(`${BASE}/${id}/estado`, payload);
