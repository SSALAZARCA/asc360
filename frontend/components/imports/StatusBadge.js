export default function StatusBadge({ status, type = 'computed_status' }) {
  if (!status) return null;

  if (type === 'docs_status') {
    const DOCS_MAP = {
      PENDING:  { label: 'Pendiente', color: '#f97316', bg: 'rgba(249,115,22,0.12)', border: 'rgba(249,115,22,0.3)', icon: '⏳' },
      UPLOADED: { label: 'Recibido',  color: '#22c55e', bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.3)', icon: '✓' },
      READY:    { label: 'Recibido',  color: '#22c55e', bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.3)', icon: '✓' },
    };
    const cfg = DOCS_MAP[status?.toUpperCase()] || DOCS_MAP.PENDING;
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        fontSize: '10px', fontWeight: 700, letterSpacing: '0.05em',
        padding: '2px 8px', borderRadius: '20px',
        background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
        whiteSpace: 'nowrap',
      }}>
        {cfg.icon} {cfg.label}
      </span>
    );
  }

  const STATUS_MAP = {
    en_preparacion: { label: 'En Preparación', color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)' },
    listo_fabrica:  { label: 'Listo Fábrica',  color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.3)' },
    en_transito:    { label: 'En Tránsito',    color: '#fb923c', bg: 'rgba(251,146,60,0.12)',  border: 'rgba(251,146,60,0.3)' },
    en_destino:     { label: 'En Destino',     color: '#fbbf24', bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.3)' },
    recibido_parcial: { label: 'Parcial',      color: '#34d399', bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.3)' },
    completado:     { label: 'Completado',     color: '#22c55e', bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.3)' },
    backorder:      { label: 'Backorder',      color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
    pending:        { label: 'Pendiente',      color: '#9ca3af', bg: 'rgba(156,163,175,0.12)', border: 'rgba(156,163,175,0.3)' },
  };

  const cfg = STATUS_MAP[status] || { label: status, color: '#9ca3af', bg: 'rgba(156,163,175,0.12)', border: 'rgba(156,163,175,0.3)' };

  return (
    <span style={{
      display: 'inline-block',
      fontSize: '10px', fontWeight: 700, letterSpacing: '0.05em',
      padding: '2px 8px', borderRadius: '20px',
      background: cfg.bg, color: cfg.color,
      border: `1px solid ${cfg.border}`,
      whiteSpace: 'nowrap',
    }}>
      {cfg.label}
    </span>
  );
}
