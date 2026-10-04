/**
 * Display helpers shared by the budget components (Maestros > Presupuestos).
 */

/** Each `<option>` needs its own color: the dark theme hides the text of an unstyled one. */
export const optionStyle = { color: '#1a1a18' };

export const labelStyle = {
  display: 'flex', flexDirection: 'column', gap: '0.2rem', fontSize: '0.7rem',
  color: 'var(--motored-text-muted, #5a5a5a)', minWidth: 0,
};

export const panelStyle = {
  display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '0.85rem 1rem',
  background: 'var(--motored-surface-alt, #f4f4f5)', border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)', minWidth: 0,
};

export const mutedStyle = { margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' };
export const thStyle = { padding: '0 12px 8px 0' };
export const tdStyle = { padding: '8px 12px 8px 0' };
export const tablaStyle = { width: '100%', borderCollapse: 'collapse', fontSize: '13px' };
export const filaStyle = { borderTop: '1px solid var(--motored-border, #e4e4e7)' };
export const errorStyle = { margin: 0, fontSize: '0.8rem', color: 'var(--motored-danger, #c0392b)' };

const ORIGENES = { EXCEL: 'Excel', MANUAL: 'Manual' };

export const origenLegible = (origen) => ORIGENES[origen] || origen;

/** `2026-10` -> `Octubre 2026`. */
export function mesLegible(mes) {
  const [anio, numero] = String(mes).split('-').map(Number);
  if (!anio || !numero) return String(mes);
  const texto = new Date(Date.UTC(anio, numero - 1, 1))
    .toLocaleDateString('es-CO', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** ISO timestamp -> `3/10/2026`; unreadable values come back unchanged. */
export function fechaLegible(iso) {
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? String(iso || '—') : fecha.toLocaleDateString('es-CO');
}
