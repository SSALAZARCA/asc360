'use client';
/** Login attempts table (scrolls horizontally inside its container on tablet). */
import MotoredTableScroll from '../MotoredTableScroll';
import InfoTooltip from '../InfoTooltip';
import { MOTIVO_LABELS, RESULTADO_LABELS, browserName, formatFechaHoraCo } from './labels';

const thStyle = { padding: '0 12px 8px 0', textAlign: 'left', whiteSpace: 'nowrap' };
const tdStyle = { padding: '10px 12px 10px 0', verticalAlign: 'top' };
const nowrapStyle = { ...tdStyle, whiteSpace: 'nowrap' };

const badgeBase = {
  display: 'inline-block', padding: '2px 10px', borderRadius: 'var(--motored-radius-pill, 999px)',
  fontSize: '0.7rem', fontWeight: 700, whiteSpace: 'nowrap',
};
const RESULTADO_COLORS = {
  EXITO: { background: 'var(--motored-success-bg, #ecfdf3)', color: 'var(--motored-success, #15803d)' },
  FALLO: { background: 'var(--motored-warning-bg, #fef3e2)', color: 'var(--motored-warning, #d97706)' },
  BLOQUEADO: { background: 'var(--motored-danger, #c0392b)', color: '#fff' },
};

const IP_HELP = 'Dirección desde donde se hizo el intento. Detrás de un proxy puede mostrar la del proxy y no la del equipo.';

function ResultadoBadge({ resultado }) {
  return <span style={{ ...badgeBase, ...RESULTADO_COLORS[resultado] }}>{RESULTADO_LABELS[resultado] || resultado}</span>;
}

function Row({ evento }) {
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
      <td style={nowrapStyle}>{formatFechaHoraCo(evento.fecha)}</td>
      <td style={tdStyle}>
        {evento.usuario_nombre && <div>{evento.usuario_nombre}</div>}
        <div style={{ fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>{evento.email}</div>
      </td>
      <td style={tdStyle}><ResultadoBadge resultado={evento.resultado} /></td>
      <td style={tdStyle}>{evento.motivo ? (MOTIVO_LABELS[evento.motivo] || evento.motivo) : '—'}</td>
      <td style={nowrapStyle} className="motored-mono">{evento.ip || '—'}</td>
      <td style={nowrapStyle} title={evento.user_agent || undefined}>{browserName(evento.user_agent)}</td>
    </tr>
  );
}

export default function IngresosTable({ eventos }) {
  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <th style={thStyle}>Fecha y hora</th>
            <th style={thStyle}>Usuario / Correo</th>
            <th style={thStyle}>Resultado</th>
            <th style={thStyle}>Motivo</th>
            <th style={thStyle}>IP <InfoTooltip text={IP_HELP} /></th>
            <th style={thStyle}>Navegador</th>
          </tr>
        </thead>
        <tbody>{eventos.map((e) => <Row key={e.id} evento={e} />)}</tbody>
      </table>
    </MotoredTableScroll>
  );
}
