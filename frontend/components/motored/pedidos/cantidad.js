/**
 * Pure rules of the inline edit of "Cantidad a pedir": what the screen accepts
 * before calling the server, and the optimistic value of an edited line.
 * The server stays the judge (E-CORRIDA-053); these only save a round trip.
 */
export const MAX_CANTIDAD = 9999999;

const SOLO_DIGITOS = /^\d+$/;

/** `{ valor }` for a whole number from 0 to 9.999.999, otherwise `{ error }` in Spanish. */
export function validarCantidad(texto) {
  const limpio = String(texto ?? '').trim();
  if (limpio === '') return { error: 'Escriba la cantidad a pedir.' };
  if (!SOLO_DIGITOS.test(limpio)) return { error: 'Escriba solo números enteros, sin decimales ni signos.' };
  const valor = Number(limpio);
  if (valor > MAX_CANTIDAD) return { error: 'El máximo es 9.999.999 unidades.' };
  return { valor };
}

/** `"48.00"` as `"48"`, the text that goes inside the input; empty when missing. */
export function cantidadEntera(valor) {
  if (valor == null || String(valor).trim() === '') return '';
  return String(Math.trunc(Number(valor)));
}

/** A line as it will look once `cantidad` is saved: quantity, value and pack warning (the edit marks wait for the server). */
export function lineaConCantidad(linea, cantidad) {
  const precio = Number(linea.precio || 0);
  return {
    ...linea,
    pedido_final: `${cantidad}.00`,
    valor_pedido: (Math.round(cantidad * precio * 100) / 100).toFixed(2),
    fuera_de_empaque: cantidad > 0 && cantidad % Number(linea.unidad_empaque) !== 0,
  };
}
