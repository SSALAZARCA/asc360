'use client';

// ---------------------------------------------------------------------------
// Shared display labels/badge for the Remisiones module — lives in its own
// module (not inside RemisionesTab.js) so RemisionDetailModal.js can import
// it without creating a circular dependency between the two.
// ---------------------------------------------------------------------------

export const STATUS_CONFIG = {
  BORRADOR:   { label: 'Borrador',   color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  border: 'rgba(251,191,36,0.3)'  },
  DESPACHADO: { label: 'Despachado', color: '#22c55e', bg: 'rgba(34,197,94,0.12)',   border: 'rgba(34,197,94,0.3)'   },
  ANULADO:    { label: 'Anulado',    color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
};

export const TYPE_LABELS = {
  PEDIDO:         'Pedido',
  GARANTIA:       'Garantía',
  CORTESIA:       'Cortesía',
  VEHICULO_PROPIO: 'Consumo Interno',
};

export function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, color: '#9ca3af', bg: 'rgba(156,163,175,0.1)', border: 'rgba(156,163,175,0.3)' };
  return (
    <span style={{
      fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '20px',
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
      textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap',
    }}>
      {cfg.label}
    </span>
  );
}
