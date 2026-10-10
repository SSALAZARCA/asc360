/**
 * What this device counted, kept on the client so the screen answers at
 * once, even offline.
 *
 * - `base`: the server's per-code summary of ONE location (round 1) at its
 *   last seed; the screen keeps one per location it saw (`bases`).
 * - `registro`: readings known to this screen, each with the location it
 *   was stamped with. `origen: 'servidor'` ones came from `recientes` and
 *   are already inside that location's base; `origen: 'local'` ones were
 *   made here since that location's seed and are not.
 *
 * Shown quantity = base + live local readings - voided server readings, all
 * of the same location.
 * Nothing here is an expected quantity: the count stays blind.
 */

/** As the server matches and stores a code (trim + upper case). */
export function normalizar(texto) {
  return (texto || '').trim().toUpperCase();
}

/**
 * The match key of a code: upper case, only A-Z and digits kept, so
 * `94109-12000S`, `9410912000S` and `94109 12000s` share one key. Mirrors
 * `clave_codigo` in backend/app/motored/services/conteos/lecturas.py.
 */
export function claveCodigo(texto) {
  return (texto || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

export const PREFIJO_UBICACION = 'UBI-';

export function esEtiquetaUbicacion(codigo) {
  return normalizar(codigo).replace(/\s+/g, '').startsWith(PREFIJO_UBICACION);
}

const LARGO_UBICACION = 30;

/**
 * A location as the server stores it (`ubicaciones.codigo_ubicacion`):
 * without the `UBI-` prefix, upper case, inner spaces collapsed. '' when
 * it ends up empty or longer than 30.
 */
export function codigoUbicacion(texto) {
  let codigo = (texto || '').split(/\s+/).filter(Boolean).join(' ').toUpperCase();
  if (codigo.startsWith(PREFIJO_UBICACION)) codigo = codigo.slice(PREFIJO_UBICACION.length).trim();
  return codigo.length > LARGO_UBICACION ? '' : codigo;
}

/**
 * A new seed of one location: its server readings plus what is still
 * queued, keeping what the screen knows of the other locations.
 */
export function resembrar(registro, recientes, items, ubicacionCodigo) {
  const encolados = new Set(items.filter((i) => i.op === 'lectura').map((i) => i.id));
  const otras = registro.filter((r) => r.ubicacion !== ubicacionCodigo && !encolados.has(r.id));
  const desdeServidor = recientes ? registroDesde(recientes.lecturas, ubicacionCodigo) : [];
  return sumarCola([...otras, ...desdeServidor], items, ubicacionCodigo);
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
