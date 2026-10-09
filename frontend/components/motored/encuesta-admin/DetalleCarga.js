'use client';
/** Expanded detail of one carga: quick filter pills and the surveys table. */
import { TONO } from '../kpis/tokens';
import { fechaHoraBogota } from '../../../lib/motored/fechas';
import { errorStyle } from './styles';
import useDetalleCarga from './useDetalleCarga';

const FILTROS = [
  ['todas', 'Todas'],
  ['respondidas', 'Respondidas'],
  ['sin_responder', 'Sin responder'],
  ['detractores', 'Detractores'],
];
const ESTADO = { RESPONDIDA: 'Respondida', SIN_RESPONDER: 'Sin responder' };
const CATEGORIA = {
  DETRACTOR: { texto: 'Detractor', tono: 'bad' },
  SATISFECHO: { texto: 'Satisfecho', tono: 'good' },
};
const COLUMNAS = ['Cliente', 'Teléfono', 'Tienda', 'Estado', 'Nota', 'Categoría', 'Comentario', 'Fecha de respuesta'];

const cellStyle = { padding: '8px 12px 8px 0', verticalAlign: 'top' };

const pillStyle = (activa) => ({
  padding: '4px 12px', borderRadius: '999px', fontSize: '12px', cursor: 'pointer',
  border: '1px solid var(--motored-border, #e4e4e7)',
  background: activa ? TONO.none.ink : 'var(--motored-surface, #ffffff)',
  color: activa ? '#ffffff' : 'inherit',
});

function CategoriaChip({ categoria }) {
  const def = CATEGORIA[categoria];
  if (!def) return '—';
  const tono = TONO[def.tono];
  return (
    <span
      data-testid="categoria-chip"
      data-tono={def.tono}
      style={{
        background: tono.soft, color: tono.ink, border: `1px solid ${tono.ring}`,
        borderRadius: '999px', padding: '2px 10px', fontSize: '12px', whiteSpace: 'nowrap',
      }}
    >
      {def.texto}
    </span>
  );
}

export default function DetalleCarga({ carga }) {
  const { filtro, setFiltro, filas, loading, error } = useDetalleCarga(carga.id);
  return (
    <section aria-label={`Detalle de ${carga.nombre_archivo}`} style={{ padding: '8px 0 12px' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
        {FILTROS.map(([valor, texto]) => (
          <button key={valor} type="button" aria-pressed={filtro === valor} style={pillStyle(filtro === valor)} onClick={() => setFiltro(valor)}>
            {texto}
          </button>
        ))}
      </div>
      {error && <div role="alert" style={errorStyle}>{error}</div>}
      {!error && loading && <p style={{ margin: 0, fontSize: '0.8rem' }}>Cargando detalle...</p>}
      {!error && !loading && filas.length === 0 && (
        <p style={{ margin: 0, fontSize: '0.8rem' }}>No hay encuestas para este filtro.</p>
      )}
      {!error && !loading && filas.length > 0 && (
        <div data-testid="detalle-scroll" style={{ maxHeight: '360px', overflowY: 'auto', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', minWidth: '720px' }}>
            <thead>
              <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)', textAlign: 'left' }}>
                {COLUMNAS.map((c) => <th key={c} style={{ ...cellStyle, position: 'sticky', top: 0, background: 'var(--motored-surface, #ffffff)' }}>{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.cedula + f.cliente} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
                  <td style={cellStyle}>{f.cliente}</td>
                  <td style={cellStyle}>{f.telefono || '—'}</td>
                  <td style={cellStyle}>{f.tienda || '—'}</td>
                  <td style={cellStyle}>{ESTADO[f.estado]}</td>
                  <td style={cellStyle}>{f.nota ?? '—'}</td>
                  <td style={cellStyle}><CategoriaChip categoria={f.categoria} /></td>
                  <td style={cellStyle}>{f.comentario || '—'}</td>
                  <td style={cellStyle}>{f.fecha_respuesta ? fechaHoraBogota(f.fecha_respuesta) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
