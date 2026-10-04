/**
 * Number formats of the KPI's section (es-CO): thousands with a dot, decimals with a comma,
 * `$1.554 M` for millions. Built by hand because `Intl` in es-CO does not group four-digit
 * numbers, which would make `1554` and `15540` look inconsistent. A missing value is always
 * the dash, never 0. Pesos/percent helpers shared with the old tablero are re-exported.
 */
import { entero, fechaCorta, pesos } from '../tablero-asesores/formato';

export { entero, fechaCorta, pesos };

export const VACIO = '—';
const MENOS = '−';

const esNumero = (valor) => valor !== null && valor !== undefined && valor !== '' && Number.isFinite(Number(valor));
const agrupar = (texto) => texto.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

/** `1554.2` -> `1.554`. */
export function miles(valor) {
  return esNumero(valor) ? agrupar(String(Math.round(Number(valor)))) : VACIO;
}

/** `1554.25, 1` -> `1.554,3`. */
export function decimales(valor, cantidad = 1) {
  if (!esNumero(valor)) return VACIO;
  const [entera, resto] = Math.abs(Number(valor)).toFixed(cantidad).split('.');
  const signo = Number(valor) < 0 && Number(Math.abs(Number(valor)).toFixed(cantidad)) !== 0 ? '-' : '';
  return signo + agrupar(entera) + (resto ? `,${resto}` : '');
}

/** `85615` -> `$85.615`. */
export const moneda = (valor) => (esNumero(valor) ? `$${miles(valor)}` : VACIO);

/** Pesos in the millions style: `1554000000` -> `$1.554 M`. */
export function millones(valor, cantidad = 0) {
  return esNumero(valor) ? `$${decimales(Number(valor) / 1e6, cantidad)} M` : VACIO;
}

/** A fraction as a percentage: `0.0769` -> `7,7%`. */
export const pct = (fraccion, cantidad = 1) => (esNumero(fraccion) ? `${decimales(Number(fraccion) * 100, cantidad)}%` : VACIO);

/** A fraction with an explicit sign: `0.077` -> `+7,7%`, `-0.032` -> `−3,2%`. */
export function pctSigned(fraccion, cantidad = 1) {
  if (!esNumero(fraccion)) return VACIO;
  const texto = pct(Math.abs(Number(fraccion)), cantidad);
  if (Number(fraccion) === 0) return texto;
  return (Number(fraccion) > 0 ? '+' : MENOS) + texto;
}
