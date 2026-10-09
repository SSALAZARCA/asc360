/**
 * Shared inline styles of the pair counting screens (colors from the
 * approved prototypes "IngresoPareja", "ConteoPortatil", "ConteoCelular").
 * Inputs set `height: 'auto'` because the Motored theme fixes inputs at
 * 36 px.
 */
export const C = {
  tinta: '#1a1a18',
  medio: '#5a5a5a',
  borde: '#e4e4e7',
  bordeCampo: '#d4d4d8',
  fondo: '#f7f7f8',
  blanco: '#ffffff',
  marca: '#e20714',
  marcaOscura: '#b00510',
  vino: '#7a030b',
  rosa: '#fde8ea',
  rosaBorde: '#f5b9be',
  critico: '#9f2a1e',
  criticoFondo: '#fdecea',
  criticoBorde: '#f5c2bd',
  ok: '#15803d',
  okFondo: '#f0fdf4',
  alerta: '#92400e',
  alertaFondo: '#fef3e2',
};

export const MONO = "var(--motored-font-mono), 'IBM Plex Mono', monospace";
export const FUENTE = "var(--motored-font-body), 'Mulish', system-ui, sans-serif";

export const pantalla = {
  fontFamily: FUENTE,
  color: C.tinta,
  background: C.fondo,
  minHeight: '100vh',
  boxSizing: 'border-box',
  display: 'flex',
  flexDirection: 'column',
};

export const campo = {
  fontFamily: 'inherit',
  fontSize: 16,
  height: 'auto',
  padding: '11px 12px',
  borderRadius: 10,
  border: `1px solid ${C.bordeCampo}`,
  background: C.blanco,
  color: C.tinta,
  boxSizing: 'border-box',
  width: '100%',
};

export const botonPrimario = {
  fontFamily: 'inherit',
  fontSize: 17,
  fontWeight: 800,
  padding: 16,
  borderRadius: 12,
  border: 'none',
  background: C.marca,
  color: C.blanco,
  cursor: 'pointer',
  width: '100%',
};

export const botonContorno = {
  fontFamily: 'inherit',
  fontSize: 14,
  fontWeight: 800,
  padding: '10px 14px',
  borderRadius: 10,
  border: `2px solid ${C.marcaOscura}`,
  background: C.blanco,
  color: C.marcaOscura,
  minHeight: 44,
  cursor: 'pointer',
};

export const botonNeutro = {
  fontFamily: 'inherit',
  fontSize: 15,
  fontWeight: 800,
  padding: '14px 10px',
  borderRadius: 12,
  border: `1px solid ${C.bordeCampo}`,
  background: C.blanco,
  color: C.tinta,
  minHeight: 52,
  cursor: 'pointer',
};

export const tarjeta = {
  background: C.blanco,
  border: `1px solid ${C.borde}`,
  borderRadius: 12,
};
