'use client';
/**
 * One list of "Pendientes por sanear" (WU15): a short table that scrolls
 * inside its box. A row marked "Verificado en el ERP" is greyed out with who
 * and when; the leader can mark or undo it (this conteo only).
 */
import { fechaHoraBogota } from '../../../lib/motored/fechas';
import { mutedStyle, tdStyle, thStyle, touchStyle } from './estilos';

const cajaStyle = {
  maxHeight: '240px', overflow: 'auto', border: '1px solid var(--motored-border, #e2e2e2)',
  borderRadius: '8px', padding: '8px 0 0 10px',
};
const tablaStyle = { width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' };
const h3Style = { margin: 0, fontSize: '0.95rem', fontWeight: 700 };
const botonStyle = { ...touchStyle, fontSize: '0.8rem', whiteSpace: 'nowrap' };

function Accion({ fila, tipo, ocupado, onCambiar }) {
  const marcada = Boolean(fila.verificado);
  return (
    <button
      type="button" className="motored-btn" style={botonStyle} disabled={ocupado === fila.clave}
      aria-label={marcada
        ? `Deshacer verificación de ${fila.id}`
        : `Marcar ${fila.id} como verificado en el ERP`}
      onClick={() => onCambiar(tipo, fila)}
    >
      {marcada ? 'Deshacer' : 'Verificado en el ERP'}
    </button>
  );
}

function Fila({ fila, columnas, tipo, puedeMarcar, ocupado, onCambiar }) {
  const v = fila.verificado;
  return (
    <tr style={{ opacity: v ? 0.55 : 1 }}>
      <td style={tdStyle}>
        <strong>{fila.id}</strong>
        {v && (
          <div style={{ ...mutedStyle, fontSize: '0.75rem' }}>
            Verificado en el ERP por {v.por || '—'} · {fechaHoraBogota(v.en)}
          </div>
        )}
      </td>
      {columnas.map((c) => <td key={c.titulo} style={tdStyle}>{c.valor(fila)}</td>)}
      {puedeMarcar && (
        <td style={tdStyle}><Accion fila={fila} tipo={tipo} ocupado={ocupado} onCambiar={onCambiar} /></td>
      )}
    </tr>
  );
}

export default function PendientesTabla({
  titulo, tipo, primera, filas, columnas, puedeMarcar, ocupado, onCambiar,
}) {
  const sinVerificar = filas.filter((f) => !f.verificado).length;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', minWidth: 0 }}>
      <h3 style={h3Style}>{`${titulo} · ${sinVerificar}`}</h3>
      {filas.length === 0 ? (
        <div style={mutedStyle}>Ninguno.</div>
      ) : (
        <div style={cajaStyle}>
          <table style={tablaStyle}>
            <thead>
              <tr>
                <th scope="col" style={thStyle}>{primera}</th>
                {columnas.map((c) => <th key={c.titulo} scope="col" style={thStyle}>{c.titulo}</th>)}
                {puedeMarcar && <th scope="col" style={thStyle} aria-label="Acción" />}
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <Fila
                  key={f.clave} fila={f} columnas={columnas} tipo={tipo}
                  puedeMarcar={puedeMarcar} ocupado={ocupado} onCambiar={onCambiar}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
