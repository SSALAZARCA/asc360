'use client';
/** State transitions: Cerrar caso; closed cases can be reopened. Taking a case happens from the list. */
import { useState } from 'react';
import { cardStyle, errorStyle, labelStyle, optionStyle } from './styles';
import { RESULTADO_LABELS } from './labels';

const MIN = 5;

function ConfirmPanel({ mode, busy, onCancel, onConfirm }) {
  const [resultado, setResultado] = useState('');
  const [comentario, setComentario] = useState('');
  const closing = mode === 'CERRADO';
  const valid = comentario.trim().length >= MIN && (!closing || resultado !== '');
  const confirm = () => onConfirm({
    estado: mode, ...(closing ? { resultado } : {}), comentario: comentario.trim(),
  });
  return (
    <>
      {closing && (
        <label style={labelStyle}>
          Resultado
          <select value={resultado} onChange={(e) => setResultado(e.target.value)}>
            <option value="" style={optionStyle}>Selecciona...</option>
            {Object.entries(RESULTADO_LABELS).map(([k, v]) => <option key={k} value={k} style={optionStyle}>{v}</option>)}
          </select>
        </label>
      )}
      <label style={labelStyle}>
        Comentario
        <textarea rows={2} value={comentario} onChange={(e) => setComentario(e.target.value)} />
      </label>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button type="button" className="motored-btn motored-btn-primary" disabled={!valid || busy} onClick={confirm}>Confirmar</button>
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancel}>Cancelar</button>
      </div>
    </>
  );
}

function StartButtons({ estado, onPick }) {
  if (estado === 'CERRADO') {
    return (
      <button type="button" className="motored-btn motored-btn-secondary" onClick={() => onPick('EN_GESTION')}>Reabrir caso</button>
    );
  }
  if (estado !== 'EN_GESTION') return null;
  return (
    <button type="button" className="motored-btn motored-btn-secondary" onClick={() => onPick('CERRADO')}>Cerrar caso</button>
  );
}

export default function EstadoControls({ estado, error, busy, onSubmit }) {
  const [mode, setMode] = useState(null);
  const confirm = async (payload) => { if (await onSubmit(payload)) setMode(null); };
  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Cambiar estado</h2>
      {error && <div role="alert" style={errorStyle}>{error}</div>}
      {!mode && <StartButtons estado={estado} onPick={setMode} />}
      {mode && (
        <ConfirmPanel key={mode} mode={mode} busy={busy} onCancel={() => setMode(null)} onConfirm={confirm} />
      )}
    </section>
  );
}
