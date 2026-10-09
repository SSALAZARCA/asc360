/**
 * frontend/lib/motored/conteoCola.js
 *
 * The device's offline queue of inventory count operations
 * (odd/motored-conteos-inventario WU13, design ADR-5). Readings are shown
 * at once and queued here with a client UUID; a flusher sends them in
 * batches of at most 100. The server is idempotent by id, so a resend
 * after a lost answer comes back as `duplicadas` and never counts twice.
 *
 * Storage: `localStorage`, keyed by slug. Chosen over IndexedDB because it
 * is synchronous (the queue is written before the beep, so a crash right
 * after a scan loses nothing), it is what ADR-5 specifies, and the volume
 * fits easily: a queued reading is ~250 bytes, so even 5 000 unsent
 * readings use ~1.2 MB of the ~5 MB quota. IndexedDB would add async
 * writes and a dependency (fake-indexeddb) just for the tests.
 *
 * Queue items:
 * - `{op: 'lectura', id, codigo_leido, cantidad, leida_en, metodo,
 *    forzar_desconocido, reconteo_id, ubicacion, descripcion}`;
 * - `{op: 'anular', id, codigo, cantidad, ubicacion}`: voids a reading the
 *   server already has (edits are void + new reading; the API refuses
 *   quantities <= 0).
 * `ubicacion` and `descripcion` are local only and never sent.
 */

export const LOTE_MAXIMO = 100;
const PREFIJO = 'motored_conteo_cola:';
const RETRASO_MAXIMO_MS = 30000;

export function claveCola(slug) {
  return PREFIJO + slug;
}

function almacenPorDefecto() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** `{sesionId, items}`; an empty queue when nothing (valid) is stored. */
export function leerCola(slug, almacen = almacenPorDefecto()) {
  const vacia = { sesionId: null, items: [] };
  if (!almacen) return vacia;
  try {
    const guardada = JSON.parse(almacen.getItem(claveCola(slug)));
    if (!guardada || !Array.isArray(guardada.items)) return vacia;
    return { sesionId: guardada.sesionId || null, items: guardada.items };
  } catch {
    return vacia;
  }
}

/** Returns false when the browser refused the write (quota, private mode). */
export function guardarCola(slug, cola, almacen = almacenPorDefecto()) {
  if (!almacen) return false;
  try {
    if (!cola.items.length) {
      almacen.removeItem(claveCola(slug));
    } else {
      almacen.setItem(claveCola(slug), JSON.stringify(cola));
    }
    return true;
  } catch {
    return false;
  }
}

/** The next request to make: up to 100 consecutive readings, or one void. */
export function siguienteEnvio(items, tamanoLote = LOTE_MAXIMO) {
  if (!items.length) return null;
  if (items[0].op === 'anular') return { tipo: 'anular', items: [items[0]] };
  const lote = [];
  for (const item of items) {
    if (item.op !== 'lectura' || lote.length >= tamanoLote) break;
    lote.push(item);
  }
  return { tipo: 'lecturas', items: lote };
}

/** The body the API accepts for one queued reading. */
export function aPayload(item) {
  const payload = {
    id: item.id,
    codigo_leido: item.codigo_leido,
    cantidad: item.cantidad,
    leida_en: item.leida_en,
    metodo: item.metodo,
  };
  if (item.forzar_desconocido) payload.forzar_desconocido = true;
  if (item.reconteo_id) payload.reconteo_id = item.reconteo_id;
  return payload;
}

/**
 * Sorts a batch's answer. Accepted and duplicated ids are done; unknown and
 * rejected ones are dropped from the queue and reported. Ids the answer does
 * not mention stay queued (a later resend is harmless).
 */
export function aplicarRespuesta(items, enviados, respuesta) {
  const hechos = new Set([...(respuesta.aceptadas || []), ...(respuesta.duplicadas || [])]);
  const desconocidos = new Map((respuesta.desconocidos || []).map((d) => [d.id, d.codigo]));
  const rechazos = new Map((respuesta.rechazadas || []).map((r) => [r.id, r.motivo]));
  const resultado = { items: [], hechos: [], desconocidos: [], rechazadas: [] };
  const enviadosIds = new Set(enviados.map((i) => i.id));
  for (const item of items) {
    const enLote = enviadosIds.has(item.id) && item.op === 'lectura';
    if (enLote && hechos.has(item.id)) resultado.hechos.push(item);
    else if (enLote && desconocidos.has(item.id)) resultado.desconocidos.push(item);
    else if (enLote && rechazos.has(item.id)) {
      resultado.rechazadas.push({ item, motivo: rechazos.get(item.id) });
    } else resultado.items.push(item);
  }
  return resultado;
}

export function quitarItem(items, id, op = 'lectura') {
  return items.filter((i) => !(i.id === id && i.op === op));
}

/** Backoff after `fallos` consecutive failures: base, 2x, 4x... capped. */
export function retrasoReintento(fallos, base = 1500) {
  if (fallos <= 0) return base;
  return Math.min(base * 2 ** fallos, RETRASO_MAXIMO_MS);
}

export function lecturasPendientes(items) {
  return items.filter((i) => i.op === 'lectura').length;
}

/** A RFC 4122 v4 id; `crypto.randomUUID` is missing on old mobile browsers. */
export function nuevoId() {
  const c = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === 'function') c.getRandomValues(bytes);
  else for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
