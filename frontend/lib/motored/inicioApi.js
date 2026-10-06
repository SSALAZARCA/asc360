/**
 * The welcome page's data (`GET /api/motored/inicio`): the same four
 * figures for every role (`ventas_mes`, `ventas_anio`, `puntos_venta`,
 * `asesores`), each `{ disponible, ...numbers }`. Errors carry their HTTP
 * status (`motoredFetchJson`).
 */
import { motoredFetchJson } from './motoredFetch';

export function getInicio() {
  return motoredFetchJson('/inicio');
}
