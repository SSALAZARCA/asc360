/** Badge for the pedido state of ONE tienda (Borrador, Cerrado, Enviado). */
const base = {
  display: 'inline-block', padding: '2px 10px', borderRadius: 'var(--motored-radius-pill, 999px)',
  fontSize: '0.7rem', fontWeight: 700, whiteSpace: 'nowrap',
};

const ESTADOS = {
  BORRADOR: { label: 'Borrador', background: 'var(--motored-warning-bg, #fef3e2)', color: 'var(--motored-warning, #d97706)' },
  CERRADO: { label: 'Cerrado', background: 'var(--motored-surface-alt, #f4f4f5)', color: 'var(--motored-text, #1a1a18)' },
  ENVIADO: { label: 'Enviado', background: 'var(--motored-success-bg, #ecfdf3)', color: 'var(--motored-success, #15803d)' },
};

export const ESTADO_PEDIDO_TEXTO = 'Estado del pedido: Borrador se puede ajustar; Cerrado queda listo para exportar y enviar; Enviado ya se mandó a HMCL y no cambia.';

export default function EstadoPedidoBadge({ estado }) {
  const { label, ...colores } = ESTADOS[estado] || {};
  if (!label) return <span style={{ fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>Sin pedido</span>;
  return <span style={{ ...base, ...colores }}>{label}</span>;
}
