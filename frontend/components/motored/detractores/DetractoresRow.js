'use client';
/** One case row. The action button is the only way in: take an open case, view the rest. */
import { ConsentBadge, EstadoBadge } from './badges';
import { formatFecha, formatFechaHora } from './labels';
import { errorStyle } from './styles';

const tdStyle = { padding: '10px 12px 10px 0', verticalAlign: 'top' };
const nowrapStyle = { ...tdStyle, whiteSpace: 'nowrap' };

function RowAction({ caso, onOpen, onTomar, busy, error }) {
  const abierto = caso.estado === 'ABIERTO';
  return (
    <td style={{ ...tdStyle, minWidth: '140px' }}>
      <button
        type="button" disabled={busy} style={{ whiteSpace: 'nowrap' }}
        className={`motored-btn ${abierto ? 'motored-btn-primary' : 'motored-btn-secondary'}`}
        onClick={() => (abierto ? onTomar(caso.id) : onOpen(caso.id))}
      >
        {abierto ? 'Tomar caso' : 'Ver caso'}
      </button>
      {error && <div role="alert" style={{ ...errorStyle, fontSize: '0.7rem', marginTop: '4px' }}>{error}</div>}
    </td>
  );
}

export default function DetractoresRow({ caso, onOpen, onTomar, busy, error }) {
  const { cliente } = caso;
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
      <RowAction caso={caso} onOpen={onOpen} onTomar={onTomar} busy={busy} error={error} />
      <td style={nowrapStyle} className="motored-mono">{caso.codigo}</td>
      <td style={nowrapStyle}>{formatFecha(caso.created_at)}</td>
      <td style={tdStyle}>
        {cliente.nombre}
        <div style={{ fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>{cliente.cedula}</div>
      </td>
      <td style={nowrapStyle} className="motored-mono">{cliente.placa}</td>
      <td style={tdStyle}>{cliente.centro_servicio || '—'}</td>
      <td style={tdStyle}>{caso.satisfaccion_general}/5</td>
      <td style={tdStyle}><ConsentBadge autoriza={caso.autoriza_datos} /></td>
      <td style={tdStyle}><EstadoBadge estado={caso.estado} /></td>
      <td style={tdStyle}>{caso.asignado_a?.nombre || '—'}</td>
      <td style={nowrapStyle}>{formatFechaHora(caso.ultima_accion_at)}</td>
    </tr>
  );
}
