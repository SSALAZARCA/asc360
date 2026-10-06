/**
 * The welcome page's data (`GET /api/motored/inicio`): the sections of the
 * caller's role, each `{ disponible, ...numbers }`. Errors carry their HTTP
 * status (`motoredFetchJson`).
 */
import { motoredFetchJson } from './motoredFetch';

export function getInicio() {
  return motoredFetchJson('/inicio');
}
