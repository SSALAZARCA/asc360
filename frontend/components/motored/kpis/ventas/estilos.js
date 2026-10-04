/** Shared inline styles of the Ventas cards, copied from the design (card padding 20, gaps 16-18). */
import { COLOR } from '../tokens';

export const TARJETA = { background: COLOR.surface, border: `1px solid ${COLOR.track}`, borderRadius: 14, padding: 20, boxSizing: 'border-box', minWidth: 0 };
export const CABECERA = { display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 10, alignItems: 'center' };
export const TITULO = { fontSize: 15, fontWeight: 700, color: COLOR.ink, margin: 0 };
export const ROTULO = { fontSize: 12, fontWeight: 500, letterSpacing: '.04em', textTransform: 'uppercase', color: COLOR.muted, margin: 0 };
export const NUM = { fontVariantNumeric: 'tabular-nums' };
export const LEYENDA = { display: 'flex', gap: 16, fontSize: 12.5, color: COLOR.muted, flexWrap: 'wrap', alignItems: 'center' };
