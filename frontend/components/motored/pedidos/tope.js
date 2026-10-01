/** Pure rules of the budget cap screens (Topes por tienda, cap banner, recorte preview). */
import { unidades } from './formato';

const MAX_DIGITOS = 15;
const MENSAJE_FORMATO = 'Escriba el tope en pesos, solo números enteros (sin puntos ni comas).';

/**
 * Reads what the user typed in the cap field: `{ valor: null }` for an empty
 * text (sin tope), `{ valor: <whole pesos> }` for a positive whole number, or
 * `{ error }` in Spanish. The server checks again.
 */
export function parsearTope(texto) {
  const limpio = String(texto ?? '').trim();
  if (limpio === '') return { valor: null };
  if (!/^\d+$/.test(limpio)) return { error: MENSAJE_FORMATO };
  if (limpio.length > MAX_DIGITOS) return { error: `El tope admite hasta ${MAX_DIGITOS} dígitos, en pesos.` };
  const valor = Number(limpio);
  if (valor <= 0) return { error: 'El tope debe ser mayor que cero.' };
  return { valor };
}

/** The stored cap (`"80000000.00"`) as the text of the input: `80000000`; empty when there is none. */
export function topeComoTexto(valor) {
  if (valor == null || String(valor).trim() === '') return '';
  const numero = Number(valor);
  return Number.isFinite(numero) ? String(numero) : '';
}

/** `{ [linea_id]: recorte }` of an active proposal (empty without one). */
export function mapaRecortes(propuesta) {
  if (!propuesta || !propuesta.activo) return {};
  return Object.fromEntries(propuesta.recortes.map((r) => [r.linea_id, r]));
}

/** How many lines the proposal cuts and the value (COP) it frees. */
export function resumenRecorte(propuesta) {
  const recortes = propuesta && propuesta.activo ? propuesta.recortes : [];
  return { lineas: recortes.length, liberado: recortes.reduce((suma, r) => suma + Number(r.valor_recortado), 0) };
}

/** True when the proposal is active and the pedido is above its cap. */
export function hayExceso(propuesta) {
  return Boolean(propuesta && propuesta.activo && Number(propuesta.exceso) > 0);
}

/** How many tiendas of the summary are above their cap. */
export function contarSobreTope(tiendas) {
  return (tiendas || []).filter((t) => Number(t.exceso) > 0).length;
}

/** The code of a recorte rejected because the proposal changed after the user saw it. */
export const PROPUESTA_DESACTUALIZADA = 'E-CORRIDA-060';

/** The fresh proposal that a 060 error carries in `detalle`, or `null` when it carries none. */
export function propuestaFresca(fallo) {
  const propuesta = fallo && fallo.code === PROPUESTA_DESACTUALIZADA && fallo.detalle && fallo.detalle.propuesta;
  return propuesta && typeof propuesta === 'object' && Array.isArray(propuesta.recortes) ? propuesta : null;
}

/** True when the proposal is active and has at least one line to cut. */
export const tieneRecortes = (propuesta) => Boolean(propuesta && propuesta.activo && propuesta.recortes.length > 0);

/** "Recorte propuesto: 50 (−10)": the quantity a recorte would leave on a line and how much it cuts. */
export function textoRecorte(recorte) {
  const quita = Number(recorte.pedido_actual) - Number(recorte.pedido_propuesto);
  return `Recorte propuesto: ${unidades(recorte.pedido_propuesto)} (−${unidades(quita)})`;
}

/**
 * What the user changed in the cap fields: `{ cambios: [{ sucursal_id, valor }], errores: { [sucursal_id]: texto } }`.
 * A field that was not touched, or went back to the stored cap, is not a change; an invalid one is an error, not a change.
 */
export function cambiosDeTopes(topes, textos) {
  const cambios = [];
  const errores = {};
  topes.forEach((t) => {
    if (!(t.sucursal_id in textos)) return;
    const texto = String(textos[t.sucursal_id]).trim();
    if (texto === topeComoTexto(t.valor)) return;
    const { valor, error } = parsearTope(texto);
    if (error) errores[t.sucursal_id] = error;
    else cambios.push({ sucursal_id: t.sucursal_id, valor });
  });
  return { cambios, errores };
}

const sinTildes = (texto) => String(texto).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** The tiendas whose name contains `texto`, ignoring case and accents (all of them for an empty search). */
export function filtrarTiendas(tiendas, texto) {
  const buscado = sinTildes(String(texto ?? '').trim());
  if (buscado === '') return tiendas;
  return tiendas.filter((t) => sinTildes(t.nombre).includes(buscado));
}
