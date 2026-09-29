'use client';
/**
 * frontend/components/motored/CambiarPasswordForm.js
 *
 * Small form the ADMIN uses on the Usuarios screen to set a new password for
 * one user (feature odd/motored-salir-y-cambio-password, T3). It checks the
 * minimum length and that both inputs match BEFORE calling `onSubmit`, never
 * pre-fills the inputs and never renders the typed password anywhere.
 */
import { useState } from 'react';

export const PASSWORD_MIN_LENGTH = 8;

const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };
const errorStyle = { color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem', margin: 0 };

function validar(nueva, confirmacion) {
  if (nueva.length < PASSWORD_MIN_LENGTH) return `La contraseña debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres`;
  if (nueva !== confirmacion) return 'Las contraseñas no coinciden';
  return '';
}

export default function CambiarPasswordForm({ usuario, onSubmit, onCancel, serverError }) {
  const [nueva, setNueva] = useState('');
  const [confirmacion, setConfirmacion] = useState('');
  const [errorLocal, setErrorLocal] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    const problema = validar(nueva, confirmacion);
    setErrorLocal(problema);
    if (!problema) onSubmit(nueva);
  };

  const error = errorLocal || serverError;

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <strong style={{ fontSize: '0.8rem', width: '100%' }}>Cambiar contraseña de {usuario.nombre}</strong>
      <label style={labelStyle} title={`Mínimo ${PASSWORD_MIN_LENGTH} caracteres`}>
        Nueva contraseña
        <input type="password" autoComplete="new-password" value={nueva} onChange={(e) => setNueva(e.target.value)} />
      </label>
      <label style={labelStyle} title="Repita la contraseña para evitar errores de digitación">
        Confirmar contraseña
        <input type="password" autoComplete="new-password" value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} />
      </label>
      <button type="submit" className="motored-btn motored-btn-primary">Guardar contraseña</button>
      <button type="button" className="motored-row-action" onClick={onCancel}>Cancelar</button>
      {error && <p style={{ ...errorStyle, width: '100%' }}>{error}</p>}
    </form>
  );
}
