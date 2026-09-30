'use client';
/** "Registrar acción" form. Closed cases only accept notes and corrections. */
import { useState } from 'react';
import { cardStyle, errorStyle, labelStyle, mutedStyle, optionStyle } from './styles';
import { TIPOS_ACCION, TIPOS_ACCION_CERRADO, TIPO_LABELS } from './labels';

const MIN = 5;
const MAX = 4000;

export default function AccionForm({ estado, error, busy, onSubmit }) {
  const tipos = estado === 'CERRADO' ? TIPOS_ACCION_CERRADO : TIPOS_ACCION;
  const [chosen, setChosen] = useState(tipos[0]);
  const [descripcion, setDescripcion] = useState('');
  const tipo = tipos.includes(chosen) ? chosen : tipos[0];
  const valid = descripcion.trim().length >= MIN;

  const submit = async (e) => {
    e.preventDefault();
    if (await onSubmit({ tipo, descripcion: descripcion.trim() })) setDescripcion('');
  };

  return (
    <form onSubmit={submit} style={cardStyle}>
      <h2 className="motored-h-seccion">Registrar acción</h2>
      <label style={labelStyle}>
        Tipo de acción
        <select value={tipo} onChange={(e) => setChosen(e.target.value)}>
          {tipos.map((t) => <option key={t} value={t} style={optionStyle}>{TIPO_LABELS[t]}</option>)}
        </select>
      </label>
      <label style={labelStyle}>
        Descripción
        <textarea rows={3} maxLength={MAX} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
      </label>
      <span style={{ fontSize: '0.7rem', ...mutedStyle }}>{descripcion.length}/{MAX}</span>
      {!valid && descripcion.length > 0 && (
        <span style={{ fontSize: '0.7rem', ...mutedStyle }}>Escribe al menos {MIN} caracteres.</span>
      )}
      {error && <div role="alert" style={errorStyle}>{error}</div>}
      <button type="submit" className="motored-btn motored-btn-primary" style={{ alignSelf: 'flex-start' }} disabled={!valid || busy}>
        Registrar acción
      </button>
    </form>
  );
}
