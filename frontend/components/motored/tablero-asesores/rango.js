/**
 * Month range helpers of the "Tablero de asesores" (months are `AAAA-MM`
 * strings, the value of an `<input type="month">`). Mirrors the backend rule:
 * `desde` <= `hasta` and at most 12 months.
 */
export const MAX_MESES = 12;
const PATRON = /^\d{4}-(0[1-9]|1[0-2])$/;
const NOMBRES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

const aIndice = (mes) => {
  const [anio, numero] = mes.split('-').map(Number);
  return anio * 12 + (numero - 1);
};

function aTexto(indice) {
  const anio = Math.floor(indice / 12);
  return `${anio}-${String((indice % 12) + 1).padStart(2, '0')}`;
}

/** The 6 months ending in the month of `hoy`. */
export function rangoPorDefecto(hoy = new Date()) {
  const fin = hoy.getFullYear() * 12 + hoy.getMonth();
  return { desde: aTexto(fin - 5), hasta: aTexto(fin) };
}

/** A Spanish message when the range is not valid, `null` when it is. */
export function validarRango(desde, hasta) {
  if (!PATRON.test(desde || '') || !PATRON.test(hasta || '')) return 'Elija el mes inicial y el mes final.';
  if (aIndice(desde) > aIndice(hasta)) return 'El mes inicial no puede ser posterior al mes final.';
  if (aIndice(hasta) - aIndice(desde) + 1 > MAX_MESES) return `El rango no puede pasar de ${MAX_MESES} meses.`;
  return null;
}

/** `2026-09` -> `sep 2026`. */
export function etiquetaMes(mes) {
  if (!PATRON.test(mes || '')) return '—';
  const [anio, numero] = mes.split('-');
  return `${NOMBRES[Number(numero) - 1]} ${anio}`;
}
