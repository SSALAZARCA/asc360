'use client';
/** Confirmation dialog to annul a corrida; the motivo is required (1..500). */
import { errorStyle, labelStyle, mutedStyle, overlayStyle, panelStyle } from './styles';

export default function AnularCorridaDialog({ anular }) {
  const { corrida, motivo, setMotivo, busy, error, cerrar, confirmar } = anular;
  if (!corrida) return null;
  return (
    <div style={overlayStyle}>
      <div role="dialog" aria-modal="true" aria-labelledby="anular-titulo" style={panelStyle}>
        <h2 id="anular-titulo" className="motored-h-seccion">{`Anular ${corrida.codigo}`}</h2>
        <p style={{ ...mutedStyle, margin: 0 }}>
          Se descarta el cálculo de esta corrida. Las tiendas cerradas o enviadas quedan protegidas:
          si alguna lo está, el sistema no permite anular y hay que reabrir su pedido antes.
        </p>
        <label style={labelStyle}>
          Motivo
          <textarea
            rows={3} maxLength={500} value={motivo} onChange={(e) => setMotivo(e.target.value)}
            placeholder="Explique por qué se anula"
          />
        </label>
        {error && <p role="alert" style={errorStyle}>{error}</p>}
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button type="button" className="motored-btn motored-btn-secondary" onClick={cerrar} disabled={busy}>Cancelar</button>
          <button
            type="button" className="motored-btn motored-btn-primary"
            onClick={confirmar} disabled={busy || motivo.trim() === ''}
          >
            Anular corrida
          </button>
        </div>
      </div>
    </div>
  );
}
