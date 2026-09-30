/** Small presentational badges for case state and data consent. */
import { ESTADO_LABELS } from './labels';

const base = {
  display: 'inline-block', padding: '2px 10px', borderRadius: 'var(--motored-radius-pill, 999px)',
  fontSize: '0.7rem', fontWeight: 700, whiteSpace: 'nowrap',
};

const ESTADO_COLORS = {
  ABIERTO: { background: 'var(--motored-warning-bg, #fef3e2)', color: 'var(--motored-warning, #d97706)' },
  EN_GESTION: { background: 'var(--motored-surface-alt, #f4f4f5)', color: 'var(--motored-text, #1a1a18)' },
  CERRADO: { background: 'var(--motored-success-bg, #ecfdf3)', color: 'var(--motored-success, #15803d)' },
};

export function EstadoBadge({ estado }) {
  return <span style={{ ...base, ...ESTADO_COLORS[estado] }}>{ESTADO_LABELS[estado] || estado}</span>;
}

export function ConsentBadge({ autoriza }) {
  if (autoriza) return <span style={{ fontSize: '0.8rem' }}>Sí</span>;
  return (
    <span style={{
      ...base, background: 'var(--motored-danger, #c0392b)', color: '#fff', textTransform: 'uppercase',
    }}
    >
      NO autorizó
    </span>
  );
}
