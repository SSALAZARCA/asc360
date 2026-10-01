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
