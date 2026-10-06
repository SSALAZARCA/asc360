/** Pure rules of the corridas list: which states are in flight, who can be anulada. */
import { fechaBogota } from '../../../lib/motored/fechas';
import { dias, etiquetaDataset } from './formato';

export const EN_CURSO = ['PENDIENTE', 'CALCULANDO'];
const ANULABLES = ['PENDIENTE', 'CALCULANDO', 'FALLIDA', 'BORRADOR'];

export const estaCalculando = (estado) => EN_CURSO.includes(estado);

/** A corrida can be annulled only while no tienda pedido is closed or sent (E-CORRIDA-051). */
export function puedeAnular(corrida) {
  if (!ANULABLES.includes(corrida.estado)) return false;
  const { cerrados = 0, enviados = 0 } = corrida.pedidos || {};
  return cerrados + enviados === 0;
}

/** `2026-10-01` as `01/10/2026` (no shift); an instant as its Colombia calendar date. */
export const fechaCorta = fechaBogota;

/** The stale-data warning of a list row (UX-06), or null when the data is within its limit or unknown. */
export function avisoAntiguedad(corrida) {
  const peor = corrida.antiguedad_peor;
  if (!peor || !peor.supera_limite) return null;
  return {
    texto: 'Datos desactualizados',
    ayuda: `Los datos de ${etiquetaDataset(peor.dataset)} tenían ${dias(peor.antiguedad_dias)} de antigüedad al calcular; el máximo permitido es ${peor.limite_dias}.`,
  };
}
