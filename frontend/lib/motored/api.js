/**
 * frontend/lib/motored/api.js
 *
 * Typed helper functions for every Motored endpoint (sdd/motored-pedidos-
 * cimientos, Phase 6, task 6.1), built on top of `motoredFetch`/
 * `motoredFetchJson`. Mirrors the real backend contract 1:1 -- read
 * `backend/app/motored/api/{auth,maestros,carga,salud,usuarios,
 * parametros}.py` for the source of truth used here.
 *
 * `getMotoredApiUrl` is re-exported from `./motoredFetch` for convenience
 * (e.g. the login page needs the base URL for a pre-auth request, before any
 * token exists).
 */
import { motoredFetch, motoredFetchJson, getMotoredApiUrl } from './motoredFetch';

export { getMotoredApiUrl };

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/** POST /auth/login -- credenciales planas, sin token todavía. */
export async function login(email, password) {
  const res = await motoredFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || 'Credenciales incorrectas');
  }
  return body; // { access_token, token_type, user }
}

// ---------------------------------------------------------------------------
// Maestros -- CRUD genérico. `entidad` es PLURAL acá
// (sucursales|bodegas|referencias|proveedores), igual que
// `backend/app/motored/api/maestros.py`'s `_CONFIGS` keys.
// ---------------------------------------------------------------------------

export async function listMaestros(entidadPlural) {
  return motoredFetchJson(`/maestros/${entidadPlural}`);
}

export async function getMaestro(entidadPlural, id) {
  return motoredFetchJson(`/maestros/${entidadPlural}/${id}`);
}

export async function createMaestro(entidadPlural, payload) {
  return motoredFetchJson(`/maestros/${entidadPlural}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateMaestro(entidadPlural, id, payload) {
  return motoredFetchJson(`/maestros/${entidadPlural}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function deactivateMaestro(entidadPlural, id) {
  return motoredFetchJson(`/maestros/${entidadPlural}/${id}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Carga masiva -- `entidad` es SINGULAR acá (sucursal|bodega|proveedor|
// referencia), igual que `backend/app/motored/api/carga.py`. Recibe filas
// YA ESTRUCTURADAS (list[dict]) -- Fase 1 no parsea `.xlsx` en el browser
// (design doc / owner scope), el frontend arma el JSON de filas y el
// backend valida/escribe.
// ---------------------------------------------------------------------------

export async function validarCarga(entidadSingular, filas) {
  return motoredFetchJson(`/maestros/${entidadSingular}/carga/validar`, {
    method: 'POST',
    body: JSON.stringify({ filas }),
  });
}

export async function subirCarga(entidadSingular, filas) {
  return motoredFetchJson(`/maestros/${entidadSingular}/carga`, {
    method: 'POST',
    body: JSON.stringify({ filas }),
  });
}

// ---------------------------------------------------------------------------
// Carga masiva vía archivo `.xlsx` crudo -- batch posterior a la Fase 1
// (owner brief "Excel upload capability"). A diferencia de `validarCarga`/
// `subirCarga` de arriba, acá NO se parsea nada en el browser: el archivo
// entero viaja como `multipart/form-data` y `backend/app/motored/services/
// carga_excel.py` lo parsea server-side con `openpyxl`. Distinto
// content-type/body, por eso son funciones separadas, no una variante de
// las de arriba.
// ---------------------------------------------------------------------------

export async function validarCargaArchivo(entidadSingular, file) {
  const formData = new FormData();
  formData.append('file', file);
  return motoredFetchJson(`/maestros/${entidadSingular}/carga/excel/validar`, {
    method: 'POST',
    body: formData,
  });
}

export async function subirCargaArchivo(entidadSingular, file) {
  const formData = new FormData();
  formData.append('file', file);
  return motoredFetchJson(`/maestros/${entidadSingular}/carga/excel`, {
    method: 'POST',
    body: formData,
  });
}

// ---------------------------------------------------------------------------
// Salud de maestros
// ---------------------------------------------------------------------------

export async function getSalud() {
  return motoredFetchJson('/maestros/salud');
}

// ---------------------------------------------------------------------------
// Usuarios (ADMIN únicamente)
// ---------------------------------------------------------------------------

export async function listUsuarios() {
  return motoredFetchJson('/usuarios');
}

export async function createUsuario(payload) {
  return motoredFetchJson('/usuarios', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deactivateUsuario(id) {
  return motoredFetchJson(`/usuarios/${id}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Parámetros de metodología (estructura únicamente en Fase 1)
// ---------------------------------------------------------------------------

export async function crearParametro(payload) {
  return motoredFetchJson('/parametros', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getParametroVigente(clave) {
  return motoredFetchJson(`/parametros/${clave}/vigente`);
}

// ---------------------------------------------------------------------------
// Cargas -- Fase 2 "Ingesta" (sdd/motored-pedidos-ingesta), narrowed by
// Fase 3 "Cargas: Tipo Declarado" (sdd/motored-cargas-tipo-declarado):
// `tipo` es DECLARADO por la pestaña que sube el archivo, nunca inferido --
// UNA sola historia compartida sigue existiendo para los 6 tipos de
// movimiento (más filas históricas de `MAESTRO_*`/`NULL`) -- ver
// `backend/app/motored/api/cargas.py` para el contrato real, NO
// `api/carga.py` (singular, Fase 1's masters endpoint, sin relación).
// ---------------------------------------------------------------------------

export async function listarCargas(filtros = {}) {
  const params = new URLSearchParams();
  ['tipo', 'estado', 'desde', 'hasta'].forEach((clave) => {
    if (filtros[clave]) params.set(clave, filtros[clave]);
  });
  const qs = params.toString();
  return motoredFetchJson(`/cargas${qs ? `?${qs}` : ''}`);
}

/**
 * `POST /cargas` -- multipart. `tipo` es OBLIGATORIO (design D1): la
 * pestaña que llama a esto ya sabe qué está subiendo, nunca se detecta
 * server-side. `periodoDesde`/`periodoHasta` son OPCIONALES (ADR-9), y el
 * caller (`UploadMovimientoModal`) solo los pide cuando `tipoDeclaraPeriodo
 * (tipo)` es `true`. Devuelve `{ carga_id, duplicado_de }` -- `202`, nunca
 * bloquea.
 */
export async function subirCargaMovimiento(file, tipo, { periodoDesde, periodoHasta } = {}) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('tipo', tipo);
  if (periodoDesde) formData.append('periodo_desde', periodoDesde);
  if (periodoHasta) formData.append('periodo_hasta', periodoHasta);
  return motoredFetchJson('/cargas', { method: 'POST', body: formData });
}

/** `GET /cargas/{id}` -- superficie de polling (estado, filas_leidas,
 * lotes_staged, latido_en). */
export async function getCarga(cargaId) {
  return motoredFetchJson(`/cargas/${cargaId}`);
}

export async function getInformeCarga(cargaId) {
  return motoredFetchJson(`/cargas/${cargaId}/informe`);
}

export async function getErroresCarga(cargaId) {
  return motoredFetchJson(`/cargas/${cargaId}/errores`);
}

export async function getPreviewCarga(cargaId, limite = 200) {
  return motoredFetchJson(`/cargas/${cargaId}/preview?limite=${limite}`);
}

export async function resolverErroresCarga(cargaId, acciones) {
  return motoredFetchJson(`/cargas/${cargaId}/resolver`, {
    method: 'POST',
    body: JSON.stringify({ acciones }),
  });
}

export async function aplicarCarga(cargaId) {
  return motoredFetchJson(`/cargas/${cargaId}/aplicar`, { method: 'POST' });
}

export async function anularCarga(cargaId) {
  return motoredFetchJson(`/cargas/${cargaId}/anular`, { method: 'POST' });
}

/**
 * `GET /cargas/{id}/errores.csv` -- NO es JSON, así que no usa
 * `motoredFetchJson` (mismo criterio que `downloadTemplate` en
 * `BulkUploadModal.js`, pero acá el archivo viene del servidor, no se arma
 * en el browser, y necesita el header `Authorization` que `motoredFetch` ya
 * agrega -- un `<a href>` plano no podría mandarlo).
 */
export async function descargarErroresCargaCsv(cargaId) {
  const res = await motoredFetch(`/cargas/${cargaId}/errores.csv`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `errores_${cargaId}.csv`;
  a.click();
  // Revocar en el mismo tick puede cancelar la descarga en algunos
  // navegadores si todavía no terminaron de leer el blob desde el <a>.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
