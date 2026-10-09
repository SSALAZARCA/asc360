/**
 * What this device counted, kept on the client so the screen answers at
 * once, even offline.
 *
 * - `base`: the server's per-code summary of the current location (round 1)
 *   at the last seed (load or location change).
 * - `registro`: readings known to this screen. `origen: 'servidor'` ones
 *   came from `recientes` and are already inside `base`; `origen: 'local'`
 *   ones were made here since the seed and are not.
 *
 * Shown quantity = base + live local readings - voided server readings.
 * Nothing here is an expected quantity: the count stays blind.
 */

/** As the server matches and stores a code (trim + upper case). */
export function normalizar(texto) {
  return (texto || '').trim().toUpperCase();
}

export const PREFIJO_UBICACION = 'UBI-';

export function esEtiquetaUbicacion(codigo) {
  return normalizar(codigo).replace(/\s+/g, '').startsWith(PREFIJO_UBICACION);
}

/** `{codigo: {codigo, descripcion, cantidad}}` from `resumen_ubicacion`. */
export function baseDesde(resumen) {
  const base = {};
  for (const fila of resumen || []) {
    base[fila.codigo] = {
      codigo: fila.codigo,
      descripcion: fila.descripcion || '',
      cantidad: Number(fila.cantidad) || 0,
    };
  }
  return base;
}

/** Server readings of the current location still alive, newest first. */
export function registroDesde(lecturas, ubicacionCodigo) {
  return (lecturas || [])
    .filter((l) => !l.anulada_en && l.ubicacion && l.ubicacion.codigo === ubicacionCodigo)
    .map((l) => ({
      id: l.id,
      codigo: l.codigo,
      descripcion: l.descripcion || '',
      cantidad: Number(l.cantidad) || 0,
      ubicacion: ubicacionCodigo,
      reconteoId: null,
      origen: 'servidor',
      anulada: false,
    }));
}

/** Adds the stored queue on top of a fresh seed (after a reload). */
export function sumarCola(registro, items, ubicacionCodigo) {
  let resultado = [...registro];
  for (const item of items) {
    if (item.op === 'lectura') {
      resultado.push({
        id: item.id,
        codigo: item.codigo_leido,
        descripcion: item.descripcion || '',
        cantidad: Number(item.cantidad) || 0,
        ubicacion: item.ubicacion,
        reconteoId: item.reconteo_id || null,
        origen: 'local',
        anulada: false,
      });
    } else if (item.ubicacion === ubicacionCodigo) {
      const existe = resultado.some((r) => r.id === item.id);
      resultado = existe
        ? resultado.map((r) => (r.id === item.id ? { ...r, anulada: true } : r))
        : [...resultado, {
          id: item.id, codigo: item.codigo, descripcion: '', cantidad: Number(item.cantidad) || 0,
          ubicacion: item.ubicacion, reconteoId: null, origen: 'servidor', anulada: true,
        }];
    }
  }
  return resultado;
}

function aporte(r) {
  if (r.origen === 'local') return r.anulada ? 0 : r.cantidad;
  return r.anulada ? -r.cantidad : 0;
}

/** Rows of "Contado en <ubicación>": `[{codigo, descripcion, cantidad}]`. */
export function resumenUbicacion(base, registro, ubicacionCodigo) {
  const filas = {};
  for (const fila of Object.values(base)) filas[fila.codigo] = { ...fila };
  for (const r of registro) {
    if (r.reconteoId || r.ubicacion !== ubicacionCodigo) continue;
    const fila = filas[r.codigo] || { codigo: r.codigo, descripcion: r.descripcion, cantidad: 0 };
    fila.cantidad += aporte(r);
    if (!fila.descripcion && r.descripcion) fila.descripcion = r.descripcion;
    filas[r.codigo] = fila;
  }
  return Object.values(filas).filter((f) => f.cantidad > 0);
}

/** What this device counted of a code here (or in a reconteo task). */
export function totalDe(base, registro, ubicacionCodigo, codigo, reconteoId) {
  if (reconteoId) {
    return registro
      .filter((r) => r.reconteoId === reconteoId && r.codigo === codigo && !r.anulada)
      .reduce((s, r) => s + r.cantidad, 0);
  }
  const fila = resumenUbicacion(base, registro, ubicacionCodigo).find((f) => f.codigo === codigo);
  return fila ? fila.cantidad : 0;
}

/** Live readings that can be voided to lower a total, newest first. */
export function candidatosAnular(registro, ubicacionCodigo, codigo, reconteoId) {
  const vivos = registro.filter((r) => !r.anulada && r.codigo === codigo
    && r.ubicacion === ubicacionCodigo && (r.reconteoId || null) === (reconteoId || null));
  const locales = vivos.filter((r) => r.origen === 'local').reverse();
  const servidor = vivos.filter((r) => r.origen === 'servidor');
  return [...locales, ...servidor];
}

/** Which readings to void to subtract `cantidad`, and what to re-add. */
export function planReduccion(candidatos, cantidad) {
  const anular = [];
  let resta = cantidad;
  let reponer = 0;
  for (const c of candidatos) {
    if (resta <= 0) break;
    anular.push(c);
    if (c.cantidad > resta) {
      reponer = c.cantidad - resta;
      resta = 0;
    } else {
      resta -= c.cantidad;
    }
  }
  return { anular, reponer };
}
