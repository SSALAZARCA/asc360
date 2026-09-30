/** Survey answer: overall score, matrix rows (verbatim) and comments. */
import { cardStyle, mutedStyle } from './styles';
import { MATRIX_ROWS, SATISFACCION_LABELS, formatFechaHora } from './labels';

export default function RespuestaCard({ respuesta }) {
  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Respuesta de la encuesta</h2>
      <p style={{ margin: 0, fontSize: '0.85rem' }}>
        Satisfacción general: <strong>{respuesta.satisfaccion_general}/5</strong>{' '}
        <span style={mutedStyle}>{SATISFACCION_LABELS[respuesta.satisfaccion_general]}</span>
      </p>
      <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {MATRIX_ROWS.map(([key, text]) => (
          <li key={key} style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', fontSize: '0.8rem' }}>
            <span>{text}</span>
            <strong style={{ whiteSpace: 'nowrap' }}>
              {respuesta[key] ?? <span style={mutedStyle}>NS/NR</span>}
            </strong>
          </li>
        ))}
      </ul>
      <p style={{ margin: 0, fontSize: '0.85rem' }}>{respuesta.observaciones || 'Sin observaciones'}</p>
      <p style={{ margin: 0, fontSize: '0.7rem', ...mutedStyle }}>Respondida el {formatFechaHora(respuesta.created_at)}</p>
    </section>
  );
}
