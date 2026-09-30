'use client';
/** Presentational upload panel: template, file picker, validate, save. */
import MotoredTableScroll from '../MotoredTableScroll';
import ColumnasPlantilla from './ColumnasPlantilla';
import { cardStyle, errorStyle } from './styles';

const thStyle = { padding: '0 12px 8px 0', textAlign: 'left' };
const tdStyle = { padding: '8px 12px 8px 0' };
const noteStyle = { margin: 0, fontSize: '0.8rem' };

function Errores({ errores }) {
  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr><th style={thStyle}>Fila</th><th style={thStyle}>Motivo</th></tr>
        </thead>
        <tbody>
          {errores.map((e, i) => (
            <tr key={`${e.fila}-${i}`} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
              <td style={tdStyle}>{e.fila}</td>
              <td style={tdStyle}>{e.motivo}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}

function Resultado({ resultado }) {
  const errores = resultado.errores || [];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <p style={noteStyle}>
        {resultado.total_filas} filas leídas.{' '}
        {errores.length ? `${errores.length} con errores.` : 'Sin errores.'}
      </p>
      {errores.length > 0 && <Errores errores={errores} />}
      {(resultado.advertencias || []).map((a) => (
        <p key={a} style={{ ...noteStyle, color: 'var(--motored-warning, #8a5a00)' }}>{String(a)}</p>
      ))}
    </div>
  );
}

export default function CargaBase({ state, actions }) {
  const { file, resultado, guardado, busy, error, canSave } = state;
  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Cargar base de clientes</h2>
      <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Sube el Excel con los clientes antes de que Escala envíe los mensajes.
      </p>
      <ColumnasPlantilla />
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <button type="button" className="motored-btn motored-btn-secondary" onClick={actions.downloadTemplate}>
          Descargar plantilla
        </button>
        <input
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          aria-label="Archivo Excel de clientes"
          onChange={(e) => actions.pickFile(e.target.files?.[0] || null)}
          style={{ maxWidth: '100%' }}
        />
        <button type="button" className="motored-btn motored-btn-secondary" disabled={!file || busy} onClick={actions.validate}>
          Validar
        </button>
        <button type="button" className="motored-btn motored-btn-primary" disabled={!canSave} onClick={actions.save}>
          Guardar carga
        </button>
      </div>
      {error && <div role="alert" style={errorStyle}>{error}</div>}
      {resultado && <Resultado resultado={resultado} />}
      {guardado && (
        <p role="status" style={{ ...noteStyle, fontWeight: 700 }}>
          Carga guardada: {guardado.insertados} registros guardados.
        </p>
      )}
    </section>
  );
}
