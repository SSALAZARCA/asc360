/**
 * frontend/lib/motored/descargas.js
 *
 * Authenticated file downloads for the pedido exports (xlsx per tienda, zip
 * per corrida). Unlike the private blob helper in `api.js` it:
 *   - names the file from `Content-Disposition` (`filename*` wins over the
 *     ASCII fallback) and only then from the default name;
 *   - turns a JSON error body into a coded error, so the 055/056/057
 *     messages reach the user;
 *   - returns the tiendas the server skipped (`X-Tiendas-Omitidas`).
 */
import { motoredFetch } from './motoredFetch';
import { codedError } from './httpErrors';

const FILENAME_STAR = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i;
const FILENAME_PLAIN = /filename\s*=\s*"?([^";]+)"?/i;

function decodificar(texto) {
  try {
    return decodeURIComponent(texto);
  } catch {
    return texto;
  }
}

/** The file name a `Content-Disposition` value asks for, or `null`. */
export function nombreDeContentDisposition(valor) {
  if (!valor) return null;
  const star = FILENAME_STAR.exec(valor);
  if (star) return decodificar(star[2].trim());
  const plain = FILENAME_PLAIN.exec(valor);
  return plain ? plain[1].trim() : null;
}

/** The skipped tiendas from the percent-encoded JSON header (`[]` if unreadable). */
export function leerOmitidas(valor) {
  if (!valor) return [];
  try {
    const lista = JSON.parse(decodeURIComponent(valor));
    return Array.isArray(lista) ? lista : [];
  } catch {
    return [];
  }
}

function guardar(blob, nombre) {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = nombre;
  enlace.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Downloads `path`; resolves `{ nombre, omitidas }`, rejects with a coded error. */
export async function descargarArchivo(path, nombrePorDefecto) {
  const res = await motoredFetch(path);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw codedError(res.status, body, `HTTP ${res.status}`);
  }
  const nombre = nombreDeContentDisposition(res.headers.get('content-disposition')) || nombrePorDefecto;
  guardar(await res.blob(), nombre);
  return { nombre, omitidas: leerOmitidas(res.headers.get('x-tiendas-omitidas')) };
}
