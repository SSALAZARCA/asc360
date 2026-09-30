'use client';
/** One case row; the whole row opens the detail. */
import { ConsentBadge, EstadoBadge } from './badges';
import { formatFecha, formatFechaHora } from './labels';

const tdStyle = { padding: '10px 12px 10px 0', verticalAlign: 'top' };

export default function DetractoresRow({ caso, onOpen }) {
  const { cliente } = caso;
  const open = () => onOpen(caso.id);
  return (
    <tr
      tabIndex={0} onClick={open} onKeyDown={(e) => { if (e.key === 'Enter') open(); }}
      style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', cursor: 'pointer' }}
    >
      <td style={tdStyle} className="motored-mono">{caso.numero}</td>
      <td style={tdStyle}>{formatFecha(caso.created_at)}</td>
      <td style={tdStyle}>
        {cliente.nombre}
        <div style={{ fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>{cliente.cedula}</div>
      </td>
      <td style={tdStyle} className="motored-mono">{cliente.placa}</td>
      <td style={tdStyle}>{cliente.centro_servicio || '—'}</td>
      <td style={tdStyle}>{caso.satisfaccion_general}/5</td>
      <td style={tdStyle}><ConsentBadge autoriza={caso.autoriza_datos} /></td>
      <td style={tdStyle}><EstadoBadge estado={caso.estado} /></td>
      <td style={tdStyle}>{caso.asignado_a?.nombre || '—'}</td>
      <td style={tdStyle}>{formatFechaHora(caso.ultima_accion_at)}</td>
    </tr>
  );
}
