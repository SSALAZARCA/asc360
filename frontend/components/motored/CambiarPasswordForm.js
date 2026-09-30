'use client';
/**
 * frontend/components/motored/CambiarPasswordForm.js
 *
 * Small form the ADMIN uses on the Usuarios screen to set a new password for
 * one user (feature odd/motored-salir-y-cambio-password, T3). It checks the
 * password rules (length, letter, digit) and that both inputs match BEFORE calling `onSubmit`, never
 * pre-fills the inputs and never renders the typed password anywhere.
 */
import { useState } from 'react';
import { PASSWORD_HINT, ADMIN_FORCED_CHANGE_NOTE, PASSWORD_MAX_LENGTH, newPasswordProblem } from '../../lib/motored/passwordRules';

const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };
const noteStyle = { margin: 0, fontSize: '0.7rem', color: 'var(--motored-text-soft, #8a8a8a)' };
const errorStyle = { color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem', margin: 0 };

export default function CambiarPasswordForm({ usuario, onSubmit, onCancel, serverError }) {
  const [nueva, setNueva] = useState('');
  const [confirmacion, setConfirmacion] = useState('');
  const [errorLocal, setErrorLocal] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    const problema = newPasswordProblem(nueva, confirmacion);
    setErrorLocal(problema);
    if (!problema) onSubmit(nueva);
  };

  const error = errorLocal || serverError;

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <strong style={{ fontSize: '0.8rem', width: '100%' }}>Cambiar contraseña de {usuario.nombre}</strong>
      <label style={labelStyle} title={PASSWORD_HINT}>
        Nueva contraseña
        <input type="password" autoComplete="new-password" maxLength={PASSWORD_MAX_LENGTH} value={nueva} onChange={(e) => setNueva(e.target.value)} />
      </label>
      <label style={labelStyle} title="Repita la contraseña para evitar errores de digitación">
        Confirmar contraseña
        <input type="password" autoComplete="new-password" value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} />
      </label>
      <button type="submit" className="motored-btn motored-btn-primary">Guardar contraseña</button>
      <button type="button" className="motored-row-action" onClick={onCancel}>Cancelar</button>
      <p style={{ ...noteStyle, width: '100%' }}>{PASSWORD_HINT}</p>
      <p style={{ ...noteStyle, width: '100%' }}>{ADMIN_FORCED_CHANGE_NOTE}</p>
      {error && <p style={{ ...errorStyle, width: '100%' }}>{error}</p>}
    </form>
  );
}
