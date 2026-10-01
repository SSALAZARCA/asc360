/** Pure rules of the corridas list: which states are in flight, who can be anulada. */
export const EN_CURSO = ['PENDIENTE', 'CALCULANDO'];
const ANULABLES = ['PENDIENTE', 'CALCULANDO', 'FALLIDA', 'BORRADOR'];

export const estaCalculando = (estado) => EN_CURSO.includes(estado);

/** A corrida can be annulled only while no tienda pedido is closed or sent (E-CORRIDA-051). */
export function puedeAnular(corrida) {
  if (!ANULABLES.includes(corrida.estado)) return false;
  const { cerrados = 0, enviados = 0 } = corrida.pedidos || {};
  return cerrados + enviados === 0;
}

/** `2026-10-01` (or an ISO datetime) as `01/10/2026`, without time-zone shifts. */
export function fechaCorta(iso) {
  const [anio, mes, dia] = String(iso || '').slice(0, 10).split('-');
  return anio && mes && dia ? `${dia}/${mes}/${anio}` : '—';
}
