/** Display helpers of the Pedidos screens (the backend sends decimals as text). */
import { fechaHoraBogota } from '../../../lib/motored/fechas';

const NUMERO = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 });

const QUIEBRE = {
  SIN_MOVIMIENTO: 'Sin movimiento',
  INVENTARIO_MUERTO: 'Inventario muerto',
  SOBRESTOCK: 'Sobrestock',
  QUIEBRE_TOTAL: 'Quiebre total',
  QUIEBRE_PISO: 'Quiebre piso',
  BAJO_MINIMO: 'Bajo mínimo',
  NORMAL: 'Normal',
};

export const ESTADOS_QUIEBRE = Object.entries(QUIEBRE);

/** `"1010.00"` as `1.010`, `"12.50"` as `12,5`; `—` when missing. */
export function unidades(valor) {
  if (valor == null || String(valor).trim() === '') return '—';
  const numero = Number(valor);
  return Number.isFinite(numero) ? NUMERO.format(numero) : '—';
}

const DECIMAL = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 });
const COP = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });

/** A COP value short enough for a narrow column: `5,4 M`, `450 mil`, `950`; `—` when missing. The exact pesos go in a tooltip. */
export function valorCompacto(valor) {
  if (valor == null || String(valor).trim() === '') return '—';
  const numero = Number(valor);
  if (!Number.isFinite(numero)) return '—';
  const magnitud = Math.abs(numero);
  if (magnitud >= 1e6) return `${DECIMAL.format(numero / 1e6)} M`;
  if (magnitud >= 1e3) return `${DECIMAL.format(numero / 1e3)} mil`;
  return DECIMAL.format(numero);
}

const LARGO_TIENDA = 10;

/** A tienda name for a narrow column header: up to 10 characters, then an ellipsis. */
export function abreviarTienda(nombre) {
  const texto = String(nombre || '');
  return texto.length > LARGO_TIENDA ? `${texto.slice(0, LARGO_TIENDA)}…` : texto;
}

/** An instant as `02/10/2026 09:15` in Colombia time (a date-only value shows just the date). */
export const fechaHora = fechaHoraBogota;

/** Spanish wording of the engine stock state; unknown values pass through. */
export function etiquetaQuiebre(estado) {
  if (!estado) return '—';
  return QUIEBRE[estado] || estado;
}

/** "{n} día(s)". */
export const dias = (n) => `${n} ${Number(n) === 1 ? 'día' : 'días'}`;

const DATASETS = {
  inventario: 'Inventario', backorder: 'Backorder', facturas: 'Facturas de pedidos', ingresos: 'Ingresos de facturas',
};
/** Business name of an input dataset of the engine (unknown values pass through). */
export const etiquetaDataset = (tipo) => DATASETS[tipo] || tipo;

const EVENTOS = {
  CERRADO: 'Cerrado', REABIERTO: 'Reabierto', ENVIADO: 'Enviado', ENVIO_CORREGIDO: 'Número de orden corregido',
};
const MOTIVOS_EDICION = { MANUAL: 'Manual', RECORTE_PRESUPUESTO: 'Recorte por presupuesto' };
const EXCLUSIONES = { SUSTITUIDA: 'Sustituida', INACTIVA_SIN_REEMPLAZO: 'Inactiva sin reemplazo' };

/** Name of a tienda pedido event (unknown values pass through). */
export const etiquetaEvento = (evento) => EVENTOS[evento] || evento;
/** Name of the reason of a line edit. */
export const etiquetaMotivoEdicion = (motivo) => MOTIVOS_EDICION[motivo] || motivo;
/** Name of the reason a line is excluded from the pedido. */
export const etiquetaExclusion = (motivo) => EXCLUSIONES[motivo] || motivo;

/** `uno` when `n` is 1, `varios` otherwise (Spanish wording of counts). */
export const plural = (n, uno, varios) => (Number(n) === 1 ? uno : varios);

// `+ 0` turns a negative zero into 0 (Intl would write "-0").
const numeroDe = (valor) => (valor == null || String(valor).trim() === '' ? NaN : Number(valor) + 0);

/** A difference with its sign: `+12`, `-10` or `0`; `—` when missing. */
export function deltaConSigno(valor) {
  const n = numeroDe(valor);
  if (!Number.isFinite(n)) return '—';
  return n > 0 ? `+${NUMERO.format(n)}` : NUMERO.format(n);
}

/** `sube`, `baja` or `igual`: where the scenario stands against the real corrida. */
export function direccionDelta(valor) {
  const n = numeroDe(valor);
  if (n > 0) return 'sube';
  return n < 0 ? 'baja' : 'igual';
}

/** A peso difference with its sign: `+$ 120.000`, `-$ 90.000`; `—` when missing. */
export function deltaCOP(valor) {
  const n = numeroDe(valor);
  if (!Number.isFinite(n)) return '—';
  return n > 0 ? `+${COP.format(n)}` : COP.format(n);
}
