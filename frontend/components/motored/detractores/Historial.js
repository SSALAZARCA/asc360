/** Append-only action log, oldest first. */
import { cardStyle, mutedStyle } from './styles';
import { ESTADO_LABELS, TIPO_LABELS, formatFechaHora } from './labels';

function Accion({ accion }) {
  const transicion = accion.estado_anterior && accion.estado_nuevo
    ? `${ESTADO_LABELS[accion.estado_anterior]} → ${ESTADO_LABELS[accion.estado_nuevo]}`
    : null;
  return (
    <li
      data-testid="accion"
      style={{ borderLeft: '3px solid var(--motored-border, #e4e4e7)', paddingLeft: '0.75rem', fontSize: '0.8rem' }}
    >
      <strong>{TIPO_LABELS[accion.tipo] || accion.tipo}</strong>
      {transicion && <span style={{ marginLeft: '0.5rem' }}>{transicion}</span>}
      <div style={{ whiteSpace: 'pre-wrap' }}>{accion.descripcion}</div>
      <div style={{ fontSize: '0.7rem', ...mutedStyle }}>
        {accion.usuario?.nombre || 'Sistema'} · {formatFechaHora(accion.created_at)}
      </div>
    </li>
  );
}

export default function Historial({ acciones }) {
  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Historial</h2>
      <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {acciones.map((a) => <Accion key={a.id} accion={a} />)}
      </ul>
    </section>
  );
}
