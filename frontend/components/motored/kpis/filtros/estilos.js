/** Inline styles of the header filters, copied from the design (chips, trigger button, popover). */
import { COLOR } from '../tokens';

export const chip = (activo, deshabilitado = false) => ({
  fontFamily: 'inherit', fontSize: 12.5, fontWeight: 700, minHeight: 36, padding: '6px 10px', borderRadius: 8,
  cursor: deshabilitado ? 'not-allowed' : 'pointer',
  border: `1px solid ${activo ? COLOR.ink : COLOR.track}`,
  background: activo ? COLOR.ink : deshabilitado ? COLOR.wash : COLOR.surface,
  color: activo ? '#FFFFFF' : deshabilitado ? COLOR.gray400 : COLOR.ink,
});

export const BOTON_FILTRO = {
  fontFamily: 'inherit', fontSize: 13.5, height: 40, border: `1px solid ${COLOR.line}`, borderRadius: 10, padding: '0 10px',
  whiteSpace: 'nowrap', background: COLOR.surface, color: COLOR.ink, display: 'inline-flex', alignItems: 'center',
  justifyContent: 'space-between', gap: 10, cursor: 'pointer',
};

export const ROTULO_FILTRO = {
  display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, fontWeight: 500, color: COLOR.muted, position: 'relative',
};

export const POPOVER = {
  position: 'absolute', top: 66, zIndex: 20, background: COLOR.surface, border: `1px solid ${COLOR.track}`, borderRadius: 14,
  boxShadow: '0 12px 32px rgba(26,26,24,.14)', padding: 14, display: 'flex', flexDirection: 'column',
};

export const TITULO_POPOVER = { fontSize: 11, fontWeight: 700, color: COLOR.soft, textTransform: 'uppercase', letterSpacing: '.04em' };

export const BOTON_LISTO = {
  fontFamily: 'inherit', fontSize: 12.5, fontWeight: 700, border: 0, borderRadius: 8, padding: '8px 14px',
  background: COLOR.ink, color: '#FFFFFF', cursor: 'pointer',
};
