/** Badge for the calculation state of a corrida (the pedido state is per tienda). */
const base = {
  display: 'inline-block', padding: '2px 10px', borderRadius: 'var(--motored-radius-pill, 999px)',
  fontSize: '0.7rem', fontWeight: 700, whiteSpace: 'nowrap',
};

const ESTADOS = {
  PENDIENTE: { label: 'Pendiente', background: 'var(--motored-surface-alt, #f4f4f5)', color: 'var(--motored-text, #1a1a18)' },
  CALCULANDO: { label: 'Calculando', background: 'var(--motored-warning-bg, #fef3e2)', color: 'var(--motored-warning, #d97706)' },
  FALLIDA: { label: 'Fallida', background: 'var(--motored-danger-bg, #fdecea)', color: 'var(--motored-danger, #c0392b)' },
  BORRADOR: { label: 'Calculada', background: 'var(--motored-success-bg, #ecfdf3)', color: 'var(--motored-success, #15803d)' },
  // Legacy F3 corridas closed at corrida level count as calculated.
  CERRADA: { label: 'Calculada', background: 'var(--motored-success-bg, #ecfdf3)', color: 'var(--motored-success, #15803d)' },
  ANULADA: { label: 'Anulada', background: 'var(--motored-surface-alt, #f4f4f5)', color: 'var(--motored-text-muted, #5a5a5a)' },
};

export default function EstadoCalculoBadge({ estado }) {
  const { label = estado, ...colores } = ESTADOS[estado] || {};
  return <span style={{ ...base, ...colores }}>{label}</span>;
}
