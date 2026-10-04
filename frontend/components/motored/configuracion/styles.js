/** Shared inline styles of the Configuración page (theme variables, no themeCss). */
export const cardStyle = {
  background: 'var(--motored-surface, #ffffff)',
  border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)',
  padding: '1.25rem', minWidth: 0,
  display: 'flex', flexDirection: 'column', gap: '0.75rem',
};

// Tablet touch target: 44 px for every control a finger has to hit.
export const touchStyle = { minHeight: '44px', boxSizing: 'border-box' };
export const controlStyle = { ...touchStyle, maxWidth: '100%' };
export const mutedStyle = { margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' };
export const errorStyle = { margin: 0, fontSize: '0.8rem', color: 'var(--motored-danger, #c0392b)' };
// Dark-theme rule: every <option> needs an explicit colour.
export const optionStyle = { color: '#1a1a18' };
export const filaStyle = { display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' };
export const columnaStyle = { display: 'flex', flexDirection: 'column', gap: '0.5rem' };
