'use client';
import { useState } from 'react';

const SOLO_DIGITOS = /^\d+$/;

/** Validation message for the typed cédula, or '' when it can be sent. */
export function validarCedula(valor) {
  const v = valor.trim();
  if (!v) return 'Escribe tu cédula.';
  if (!SOLO_DIGITOS.test(v)) return 'La cédula solo lleva números.';
  return '';
}

export default function CedulaForm({ onSubmit, loading, serverError }) {
  const [cedula, setCedula] = useState('');
  const [localError, setLocalError] = useState('');
  const error = localError || serverError;

  const enviar = (e) => {
    e.preventDefault();
    const msg = validarCedula(cedula);
    setLocalError(msg);
    if (!msg) onSubmit(cedula.trim());
  };

  return (
    <form onSubmit={enviar} noValidate style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 420, margin: '0 auto', width: '100%' }}>
      <label htmlFor="informe-cedula" style={{ fontSize: 16, fontWeight: 700 }}>Tu cédula</label>
      <input
        id="informe-cedula"
        type="text"
        inputMode="numeric"
        autoComplete="off"
        value={cedula}
        onChange={(e) => { setCedula(e.target.value); setLocalError(''); }}
        style={{ height: 48, fontSize: 18 }}
      />
      {error && <p role="alert" style={{ margin: 0, fontSize: 14, color: 'var(--motored-danger)' }}>{error}</p>}
      <button type="submit" className="motored-btn motored-btn-primary" disabled={loading} style={{ height: 48, fontSize: 16 }}>
        {loading ? 'Cargando…' : 'Ver mi informe'}
      </button>
      <p style={{ margin: 0, fontSize: 14, color: 'var(--motored-text-muted)' }}>
        Por seguridad te pediremos tu cédula cada vez que abras este enlace.
      </p>
    </form>
  );
}
