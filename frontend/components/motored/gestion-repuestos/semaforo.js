/**
 * Urgency traffic light of a pending invoice (pure, no React). Thresholds come from the measured lag between the
 * invoice date and its ingreso (median 7 days, p90 17): up to 7 days is normal, 8-15 needs attention, over 15 is critical.
 * Colors are the Motored KPI data tokens (teal / amber / violet); brand red is never used for data.
 */
import { COLOR } from '../kpis/tokens';

export const NORMAL = 'normal';
export const ATENCION = 'atencion';
export const CRITICO = 'critico';

export const DIAS_NORMAL = 7;
export const DIAS_ATENCION = 15;

export const TEXTO_UMBRALES = 'Los límites de 7 y 15 días salen del tiempo habitual entre la factura y su ingreso: la mitad se ingresa en 7 días y casi todas antes de 17.';

export const PALETA = {
  [NORMAL]: { color: COLOR.good, soft: COLOR.goodSoft, ink: COLOR.goodInk, texto: 'Normal' },
  [ATENCION]: { color: COLOR.mid, soft: COLOR.midSoft, ink: COLOR.midInk, texto: 'Atención' },
  [CRITICO]: { color: COLOR.bad, soft: COLOR.badSoft, ink: COLOR.badInk, texto: 'Crítico' },
};

/** Level by days since the invoice; null when there is no usable number. */
export function nivelPorDias(dias) {
  const n = dias == null || dias === '' ? NaN : Number(dias);
  if (!Number.isFinite(n)) return null;
  if (n <= DIAS_NORMAL) return NORMAL;
  return n <= DIAS_ATENCION ? ATENCION : CRITICO;
}

/** Level of the state chip: LLEGO is always critical, NO_HA_LLEGADO follows the age, SIN_CONFIRMAR is neutral (null). */
export function nivelEstado(estado, dias) {
  if (estado === 'LLEGO') return CRITICO;
  if (estado === 'NO_HA_LLEGADO') return nivelPorDias(dias);
  return null;
}

/** Worst state of a store: any LLEGO or an invoice over 15 days is critical. */
export function nivelTienda(tienda) {
  if ((tienda?.llegaron_sin_ingresar ?? 0) > 0) return CRITICO;
  return nivelPorDias(tienda?.mas_antigua) || NORMAL;
}
