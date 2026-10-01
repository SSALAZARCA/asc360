/** Shared inline styles for the Pedidos screens (theme variables, no themeCss). */
export const cardStyle = {
  background: 'var(--motored-surface, #ffffff)',
  border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)',
  padding: '1.25rem', minWidth: 0,
  display: 'flex', flexDirection: 'column', gap: '0.75rem',
};

export const errorStyle = { margin: 0, fontSize: '0.8rem', color: 'var(--motored-danger, #c0392b)' };
export const mutedStyle = { fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' };
export const labelStyle = {
  display: 'flex', flexDirection: 'column', fontSize: '0.7rem',
  color: 'var(--motored-text-muted, #5a5a5a)', gap: '2px',
};
// Dark-theme rule: every <option> needs an explicit colour.
export const optionStyle = { color: '#1a1a18' };
export const thStyle = { padding: '0 12px 8px 0', textAlign: 'left', whiteSpace: 'nowrap' };
export const tdStyle = { padding: '8px 12px 8px 0', verticalAlign: 'middle', whiteSpace: 'nowrap' };

// Sticky first column and header row of the long tables (they scroll inside their box).
export const stickyColStyle = { position: 'sticky', left: 0, zIndex: 2, background: 'var(--motored-surface, #ffffff)' };
export const stickyHeadStyle = { position: 'sticky', top: 0, zIndex: 3, background: 'var(--motored-surface, #ffffff)' };
// Last column (row actions) that stays reachable while a wide table scrolls sideways on a tablet.
export const stickyRightStyle = {
  position: 'sticky', right: 0, zIndex: 2, background: 'var(--motored-surface, #ffffff)',
  boxShadow: '-6px 0 8px -6px rgba(0, 0, 0, 0.18)',
};
// The tables sit on the surface colour so the sticky column (opaque) matches the other cells.
export const tablaStyle = { background: 'var(--motored-surface, #ffffff)' };
export const numStyle = { fontVariantNumeric: 'tabular-nums' };
// Denser cells for the 9-column line table (less sideways scrolling on a tablet).
export const tdCompactStyle = { ...tdStyle, padding: '8px 8px 8px 0' };
export const thCompactStyle = { ...thStyle, padding: '0 8px 8px 0' };

// Modal dialogs: dim overlay, centred panel that scrolls when it does not fit the viewport.
export const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.45)', zIndex: 50,
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem',
};
export const panelStyle = {
  background: 'var(--motored-surface, #ffffff)', borderRadius: 'var(--motored-radius-md, 8px)',
  padding: '1.5rem', width: '100%', maxWidth: '480px', maxHeight: '90vh', overflowY: 'auto',
  display: 'flex', flexDirection: 'column', gap: '1rem',
};

// Budget cap banner (warning tone, same family as the Borrador badge) and the lines the proposal would cut.
export const topeBannerStyle = {
  background: 'var(--motored-warning-bg, #fef3e2)', borderLeft: '4px solid var(--motored-warning, #d97706)',
  borderRadius: 'var(--motored-radius-md, 8px)', padding: '1rem 1.25rem', minWidth: 0,
  display: 'flex', flexDirection: 'column', gap: '0.6rem',
};
export const recorteMarcaStyle = {
  display: 'block', fontSize: '0.7rem', fontWeight: 700, whiteSpace: 'normal', maxWidth: '170px',
  color: 'var(--motored-warning, #d97706)',
};
export const recorteFondoStyle = { background: 'var(--motored-warning-bg, #fef3e2)' };

// Summary strip of the consolidated matrix: neutral (it informs, it does not warn).
export const resumenRedStyle = {
  background: 'var(--motored-surface-alt, #f4f4f5)', border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)', padding: '0.75rem 1.25rem', minWidth: 0,
  display: 'flex', flexWrap: 'wrap', gap: '0.5rem 1.5rem', fontSize: '0.85rem', fontWeight: 700,
};
