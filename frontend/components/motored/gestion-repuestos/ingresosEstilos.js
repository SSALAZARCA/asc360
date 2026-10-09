// Shared look of the "Ingresos facturas" panel (amber = needs action now).
export const AMBAR = '#8A3F06';

export const tarjeta = {
  background: 'var(--motored-surface, #ffffff)',
  border: '1px solid var(--motored-border, #e4e4e1)',
  borderRadius: '14px', padding: '20px', minWidth: 0, boxSizing: 'border-box',
};
export const tituloSeccion = { margin: 0, fontSize: '15px', fontWeight: 700 };
export const subtitulo = { margin: '4px 0 0', fontSize: '12.5px', color: 'var(--motored-text-muted, #595954)' };
export const tabla = { width: '100%', borderCollapse: 'collapse', fontSize: '13px' };
export const th = (izq) => ({
  fontSize: '11px', fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase',
  color: 'var(--motored-text-muted, #595954)', textAlign: izq ? 'left' : 'right',
  padding: '8px 10px', borderBottom: '1px solid var(--motored-border, #e4e4e1)', whiteSpace: 'nowrap',
  position: 'sticky', top: 0, background: 'var(--motored-surface, #ffffff)',
});
export const td = (izq) => ({
  padding: '10px', textAlign: izq ? 'left' : 'right', whiteSpace: 'nowrap',
  borderBottom: '1px solid var(--motored-border, #f2f2f0)', fontVariantNumeric: 'tabular-nums',
});
// Dark-theme rule: every <option> needs an explicit colour and background.
export const opcion = { color: '#1a1a18', background: '#ffffff' };
export const select = {
  fontFamily: 'inherit', fontSize: '13.5px', height: '40px', minWidth: '180px', padding: '0 10px',
  borderRadius: '10px', border: '1px solid #c9c9c6', background: '#ffffff', color: '#1a1a18',
};
export const segmento = (activo) => ({
  fontFamily: 'inherit', fontSize: '13px', fontWeight: activo ? 700 : 500, height: '40px', padding: '0 12px',
  borderRadius: '10px', cursor: 'pointer', border: `1px solid ${activo ? '#1a1a18' : '#c9c9c6'}`,
  background: activo ? '#1a1a18' : '#ffffff', color: activo ? '#ffffff' : '#1a1a18',
});
export const botonLink = {
  appearance: 'none', border: 0, background: 'transparent', fontFamily: 'inherit', fontSize: '13px',
  fontWeight: 700, color: '#1d4e89', cursor: 'pointer', padding: '0 4px', minHeight: '36px',
  textDecoration: 'underline',
};

export const ESTADOS = {
  LLEGO: { texto: 'Ya llegó sin ingresar', estilo: { background: '#fdf1e3', color: '#8a3f06', border: '1px solid #b45309' }, punto: '#0f766e' },
  SIN_CONFIRMAR: { texto: 'Sin confirmar', estilo: { background: '#f2f2f0', color: '#3d3d3a', border: '1px solid #c9c9c6' }, punto: '#6e6e68' },
  NO_HA_LLEGADO: { texto: 'Aún no llega', estilo: { background: '#f3eafb', color: '#5a1f8c', border: '1px solid #c9b2e6' }, punto: '#b45309' },
};
