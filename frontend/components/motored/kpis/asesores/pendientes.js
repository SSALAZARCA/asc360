/** View-models of the "Pedidos por ingresar" card (pure, no React). */
import { decimales, miles } from '../format';
import { fechaBogota, horaBogota } from '../../../../lib/motored/fechas';
import { COORDINADOR_REPUESTOS } from '../../../../lib/motored/session';

export const LLEGO = 'LLEGO';
export const NO_HA_LLEGADO = 'NO_HA_LLEGADO';

/** Roles that may confirm in the app (the backend enforces it); COMPRAS and GERENCIA only read. */
export const puedeConfirmarRol = (role) => role === 'ADMIN' || role === COORDINADOR_REPUESTOS;
const DIA_MS = 24 * 3600 * 1000;

/** `1200000` -> `$1,2 M`, `642000` -> `$642 mil`. */
export function valorCorto(valor) {
  const n = valor == null || valor === '' ? NaN : Number(valor);
  if (!Number.isFinite(n)) return '—';
  return Math.abs(n) >= 1e6 ? `$${decimales(n / 1e6, 1)} M` : `$${miles(n / 1000)} mil`;
}

/** The line split around its days segment, so the card can color it: `RH 482915 · 28/09 · ` + `12 días` + ` · $1,2 M`. */
export function partesDe(item) {
  return {
    antes: `${item.factura} · ${fechaBogota(item.fecha).slice(0, 5)} · `,
    dias: `${item.dias} ${item.dias === 1 ? 'día' : 'días'}`,
    despues: ` · ${valorCorto(item.valor)}`,
  };
}

/** `RH 482915 · 28/09 · 12 días · $1,2 M`. */
export function lineaDe(item) {
  const { antes, dias, despues } = partesDe(item);
  return `${antes}${dias}${despues}`;
}

/** `hoy 9:15`, `ayer 17:40`, otherwise `30/09 09:15`. */
export function cuandoDe(instante, ahora = new Date()) {
  const dia = fechaBogota(instante);
  const hora = horaBogota(instante);
  if (dia === '—' || hora === '—') return null;
  if (dia === fechaBogota(ahora)) return `hoy ${hora}`;
  if (dia === fechaBogota(new Date(ahora.getTime() - DIA_MS))) return `ayer ${hora}`;
  return `${dia.slice(0, 5)} ${hora}`;
}

/** `Ana Gómez · hoy 9:15`, or null when nobody answered yet. */
export function quienDe(item, ahora) {
  if (!item.confirmado_por) return null;
  const cuando = cuandoDe(item.confirmado_en, ahora);
  return cuando ? `${item.confirmado_por} · ${cuando}` : item.confirmado_por;
}

export const llegaron = (items) => items.filter((i) => i.estado === LLEGO).length;
