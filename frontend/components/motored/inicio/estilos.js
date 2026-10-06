/** Inicio: shared inline styles (Motored tokens; the grids wrap on tablet and phone). */
export const tituloSeccion = {
  margin: 0, fontFamily: 'var(--motored-font-kpi)', fontSize: '18px', fontWeight: 800,
  color: 'var(--motored-text, #1a1a18)',
};

export const tarjeta = {
  display: 'flex', flexDirection: 'column', gap: '10px', padding: '20px 22px', boxSizing: 'border-box',
  background: 'var(--motored-surface, #ffffff)', border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: '12px', textDecoration: 'none', color: 'var(--motored-text, #1a1a18)', minWidth: 0,
};

export const textoSuave = { fontSize: '13px', color: 'var(--motored-text-muted, #5a5a5a)' };

export function grilla(minimo) {
  return {
    display: 'grid', gap: '16px',
    gridTemplateColumns: `repeat(auto-fit, minmax(min(${minimo}px, 100%), 1fr))`,
  };
}

export const seccion = { display: 'flex', flexDirection: 'column', gap: '14px' };
