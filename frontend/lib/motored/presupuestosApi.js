/**
 * frontend/lib/motored/presupuestosApi.js
 *
 * Client of the monthly sales budgets (`/api/motored/presupuestos`, ADMIN and
 * GERENCIA). Every function rejects with an `Error` that carries `status`; a
 * rejected apply (422) also carries `errores` (`[{ fila, columna, mensaje }]`).
 */
import { motoredFetch, motoredFetchJson } from './motoredFetch';
import { codedError } from './httpErrors';
import { descargarArchivo } from './descargas';

const ENCABEZADO_MES = (mes) => `/presupuestos/meses/${encodeURIComponent(mes)}`;

/** Months with a budget, newest first: `[{ mes, version, origen, created_at, asesores, total }]`. */
export const listarMesesPresupuesto = () => motoredFetchJson('/presupuestos/meses');

/** Active stores for the manual edit: `[{ id, nombre }]`. */
export const listarTiendasPresupuesto = () => motoredFetchJson('/presupuestos/tiendas');

/** Latest version of a month (`YYYY-MM`) with its lines and per-store totals. */
export const getMesPresupuesto = (mes) => motoredFetchJson(ENCABEZADO_MES(mes));

/** Every version of a month, newest first. */
export const getVersionesPresupuesto = (mes) => motoredFetchJson(`${ENCABEZADO_MES(mes)}/versiones`);

/** One stored version (read-only) with its lines. */
export const getVersionPresupuesto = (id) => motoredFetchJson(`/presupuestos/versiones/${encodeURIComponent(id)}`);

/** Downloads the Excel template. */
export const descargarPlantillaPresupuestos = () => (
  descargarArchivo('/presupuestos/plantilla.xlsx', 'plantilla_presupuestos.xlsx')
);

function enviarArchivo(ruta, file) {
  const formData = new FormData();
  formData.append('file', file);
  return motoredFetch(ruta, { method: 'POST', body: formData, timeout: 120000 });
}

async function leerRespuesta(res) {
  const body = await res.json().catch(() => ({}));
  if (res.ok) return body;
  const detalle = body && body.detail;
  const conErrores = detalle && typeof detalle === 'object' && !Array.isArray(detalle) && detalle.mensaje;
  const error = codedError(res.status, conErrores ? { detail: detalle.mensaje } : body, `HTTP ${res.status}`);
  if (conErrores) error.errores = detalle.errores || [];
  throw error;
}

/** Dry-run: `{ valido, filas, meses, errores, warnings }`. Writes nothing. */
export const validarPresupuestos = async (file) => leerRespuesta(await enviarArchivo('/presupuestos/validar', file));

/** Applies the file: one new version per month. `{ meses: [{ mes, version, asesores, total }] }`. */
export const aplicarPresupuestos = async (file) => leerRespuesta(await enviarArchivo('/presupuestos/aplicar', file));

/** Adds or changes one asesor (a new MANUAL version): `{ sucursal_id, monto, nota? }`. */
export const guardarAsesorPresupuesto = (mes, cedula, payload) => (
  motoredFetchJson(`${ENCABEZADO_MES(mes)}/asesores/${encodeURIComponent(cedula)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
);

/** Removes one asesor from the month (a new MANUAL version). */
export const quitarAsesorPresupuesto = (mes, cedula, nota) => (
  motoredFetchJson(
    `${ENCABEZADO_MES(mes)}/asesores/${encodeURIComponent(cedula)}${nota ? `?nota=${encodeURIComponent(nota)}` : ''}`,
    { method: 'DELETE' },
  )
);
