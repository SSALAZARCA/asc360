'use client';
/** State transitions: Tomar caso / Cerrar caso (closed cases have no controls). */
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
  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
      {estado === 'ABIERTO' && (
        <button type="button" className="motored-btn motored-btn-primary" onClick={() => onPick('EN_GESTION')}>Tomar caso</button>
      )}
      <button type="button" className="motored-btn motored-btn-secondary" onClick={() => onPick('CERRADO')}>Cerrar caso</button>
    </div>
  );
}

export default function EstadoControls({ estado, error, busy, onSubmit }) {
  const [mode, setMode] = useState(null);
  if (estado === 'CERRADO' && !error) return null;
  const confirm = async (payload) => { if (await onSubmit(payload)) setMode(null); };
  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Cambiar estado</h2>
      {error && <div role="alert" style={errorStyle}>{error}</div>}
      {estado !== 'CERRADO' && !mode && <StartButtons estado={estado} onPick={setMode} />}
      {estado !== 'CERRADO' && mode && (
        <ConfirmPanel key={mode} mode={mode} busy={busy} onCancel={() => setMode(null)} onConfirm={confirm} />
      )}
    </section>
  );
}
