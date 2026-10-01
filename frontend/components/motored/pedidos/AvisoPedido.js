'use client';
/** Notice left on the screen after an action: a success (status) or a failure (alert), with the skipped tiendas of a zip. */
import { cardStyle, errorStyle, mutedStyle } from './styles';

export default function AvisoPedido({ aviso, onDescartar, onVerCorrida }) {
  if (!aviso) return null;
  const esError = aviso.tipo === 'error';
  return (
    <div role={esError ? 'alert' : 'status'} style={{ ...cardStyle, flexDirection: 'row', alignItems: 'flex-start', gap: '1rem' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        <span style={esError ? errorStyle : { fontSize: '0.85rem', fontWeight: 600 }}>{aviso.texto}</span>
        {aviso.omitidas && (
          <>
            <span style={mutedStyle}>{aviso.omitidas.cabecera}</span>
            <ul style={{ ...mutedStyle, margin: 0, paddingLeft: '1.2rem' }}>
              {aviso.omitidas.filas.map((fila) => <li key={fila}>{fila}</li>)}
            </ul>
          </>
        )}
        {aviso.corridaId && (
          <div>
            <button type="button" className="motored-btn motored-btn-secondary" onClick={() => onVerCorrida(aviso.corridaId)}>
              Ver corrida
            </button>
          </div>
        )}
      </div>
      <button type="button" className="motored-row-action" style={{ minHeight: '44px' }} onClick={onDescartar}>
        Descartar aviso
      </button>
    </div>
  );
}
