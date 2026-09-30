'use client';
/** Presentational table of past customer-base uploads. */
import MotoredTableScroll from '../MotoredTableScroll';
import { cardStyle, errorStyle } from './styles';

const thStyle = { padding: '0 12px 8px 0', textAlign: 'left' };
const tdStyle = { padding: '10px 12px 10px 0' };

function respondidas(carga) {
  const pct = carga.total_registros ? Math.round((carga.respondidos / carga.total_registros) * 100) : 0;
  return `${carga.respondidos} (${pct}%)`;
}

export default function CargasRealizadas({ cargas, loading, error }) {
  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Cargas realizadas</h2>
      {error && <div role="alert" style={errorStyle}>{error}</div>}
      {!error && loading && <p style={{ margin: 0, fontSize: '0.8rem' }}>Cargando...</p>}
      {!error && !loading && cargas.length === 0 && (
        <p style={{ margin: 0, fontSize: '0.8rem' }}>Todavía no hay cargas de clientes.</p>
      )}
      {!error && cargas.length > 0 && (
        <MotoredTableScroll>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
                <th style={thStyle}>Archivo</th>
                <th style={thStyle}>Fecha</th>
                <th style={thStyle}>Cargado por</th>
                <th style={thStyle}>Registros</th>
                <th style={thStyle}>Respondidas</th>
              </tr>
            </thead>
            <tbody>
              {cargas.map((c) => (
                <tr key={c.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
                  <td style={tdStyle}>{c.nombre_archivo}</td>
                  <td style={tdStyle}>{c.created_at ? new Date(c.created_at).toLocaleString('es-CO') : '—'}</td>
                  <td style={tdStyle}>{c.usuario || '—'}</td>
                  <td style={tdStyle}>{c.total_registros}</td>
                  <td style={tdStyle}>{respondidas(c)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </MotoredTableScroll>
      )}
    </section>
  );
}
