/**
 * Survey customer-base uploads (`/api/motored/encuesta/cargas`).
 * Invalid files answer HTTP 200 with `{ ok: false, errores }`, so callers
 * read the `ok` field instead of catching.
 */
import { motoredFetch, motoredFetchJson } from './motoredFetch';

const BASE = '/encuesta/cargas';

function fileBody(file) {
  const formData = new FormData();
  formData.append('file', file);
  return { method: 'POST', body: formData };
}

export async function descargarPlantillaEncuesta() {
  const res = await motoredFetch(`${BASE}/plantilla`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'plantilla_encuesta.xlsx';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function validarCargaEncuesta(file) {
  return motoredFetchJson(`${BASE}/validar`, fileBody(file));
}

export function guardarCargaEncuesta(file) {
  return motoredFetchJson(BASE, fileBody(file));
}

export function listCargasEncuesta() {
  return motoredFetchJson(BASE);
}
