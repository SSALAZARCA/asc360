/** Inline styles of the inventory counts screens (theme variables only; no themeCss). */
export {
  cardStyle, errorStyle, labelStyle, mutedStyle, numStyle, optionStyle, tdStyle, thStyle, touchStyle,
} from '../pedidos/styles';

export const paginaStyle = { display: 'flex', flexDirection: 'column', gap: '1.25rem', minWidth: 0 };
export const filaFlexStyle = { display: 'flex', flexWrap: 'wrap', gap: '1.25rem', alignItems: 'flex-start' };
export const rotuloStyle = {
  fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
  color: 'var(--motored-text-muted, #5a5a5a)',
};
export const tituloStyle = { margin: 0, fontSize: '1.6rem', fontWeight: 800 };
export const h2Style = { margin: 0, fontSize: '1.1rem', fontWeight: 800 };
export const monoStyle = { fontFamily: 'var(--motored-font-mono, ui-monospace, monospace)' };
export const kpiValorStyle = { ...monoStyle, fontSize: '1.5rem', fontWeight: 600 };
export const avisoStyle = (tono) => ({
  display: 'flex', gap: '0.75rem', alignItems: 'flex-start', padding: '0.85rem', borderRadius: '10px',
  background: `var(--motored-${tono}-bg)`, color: `var(--motored-${tono})`,
  border: `1px solid var(--motored-${tono})`, fontSize: '0.875rem',
});
export const pildoraStyle = (fondo, texto) => ({
  display: 'inline-block', fontSize: '0.75rem', fontWeight: 700, padding: '4px 10px',
  borderRadius: 'var(--motored-radius-pill, 999px)', background: fondo, color: texto, whiteSpace: 'nowrap',
});
export const selectStyle = { minHeight: '44px', boxSizing: 'border-box', fontSize: '0.9rem' };
