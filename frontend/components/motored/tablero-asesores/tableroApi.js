/** Client of `GET /api/motored/tablero-asesores` (ADMIN and COMPRAS). Rejects with an `Error` carrying `status`. */
import { motoredFetchJson } from '../../../lib/motored/motoredFetch';

export function obtenerTablero({ desde, hasta, hmcl }) {
  const query = new URLSearchParams({ desde, hasta, hmcl });
  return motoredFetchJson(`/tablero-asesores?${query.toString()}`);
}
