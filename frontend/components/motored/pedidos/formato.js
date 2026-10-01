/** Display helpers of the Pedidos screens (the backend sends decimals as text). */
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

/** `2026-10-02T09:15:00` as `02/10/2026 09:15`, read from the text (no time-zone shift). */
export function fechaHora(iso) {
  const [fecha, hora] = String(iso || '').split('T');
  const [anio, mes, dia] = fecha.split('-');
  if (!anio || !mes || !dia) return '—';
  const dmy = `${dia}/${mes}/${anio}`;
  return hora ? `${dmy} ${hora.slice(0, 5)}` : dmy;
}

/** Spanish wording of the engine stock state; unknown values pass through. */
export function etiquetaQuiebre(estado) {
  if (!estado) return '—';
  return QUIEBRE[estado] || estado;
}

/** "{n} día(s)". */
export const dias = (n) => `${n} ${Number(n) === 1 ? 'día' : 'días'}`;

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
