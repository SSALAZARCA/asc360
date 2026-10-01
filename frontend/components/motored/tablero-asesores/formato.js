/** Display formats of the "Tablero de asesores". A missing value (`null`) is always "—", never 0. */
import { formatCOP } from '../../../lib/motored/formatCOP';

const VACIO = '—';
const PORCENTAJE = new Intl.NumberFormat('es-CO', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
const ENTERO = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });
const DECIMAL = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const esNumero = (valor) => valor !== null && valor !== undefined && Number.isFinite(Number(valor));

export const pesos = (valor) => (esNumero(valor) ? formatCOP(valor) : VACIO);
export const porcentaje = (fraccion) => (esNumero(fraccion) ? PORCENTAJE.format(Number(fraccion)) : VACIO);
export const entero = (valor) => (esNumero(valor) ? ENTERO.format(Number(valor)) : VACIO);
export const decimal = (valor) => (esNumero(valor) ? DECIMAL.format(Number(valor)) : VACIO);

/** `0.0769` -> `7,7%` (compact, for sentences). */
export const porcentajeTexto = (fraccion) => `${(Number(fraccion) * 100).toFixed(1).replace('.', ',')}%`;

/** `2026-09-03` -> `03/09/2026`. */
export function fechaCorta(iso) {
  const partes = String(iso || '').split('-');
  return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : VACIO;
}
