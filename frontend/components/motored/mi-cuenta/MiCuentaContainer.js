'use client';
/**
 * "Mi cuenta": every web user changes their own password. The backend answers
 * with a fresh session (other sessions are cut), which replaces the stored one
 * so this tab stays logged in.
 */
import { useState } from 'react';
import PasswordField from './PasswordField';
import { changeOwnPassword } from '../../../lib/motored/api';
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import { PASSWORD_MIN_LENGTH } from '../CambiarPasswordForm';

const formStyle = { display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%', maxWidth: '420px' };
const msgStyle = { margin: 0, fontSize: '0.8rem', fontWeight: 700 };

function validar(nueva, confirmacion) {
  if (nueva.length < PASSWORD_MIN_LENGTH) return `La contraseña debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres`;
  if (nueva !== confirmacion) return 'Las contraseñas no coinciden';
  return '';
}

function storeSession(data) {
  sessionStorage.setItem(MOTORED_TOKEN_KEY, data.access_token);
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify(data.user));
}

export default function MiCuentaContainer() {
  const [actual, setActual] = useState('');
  const [nueva, setNueva] = useState('');
  const [confirmacion, setConfirmacion] = useState('');
  const [error, setError] = useState('');
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setOk(false);
    const problema = validar(nueva, confirmacion);
    setError(problema);
    if (problema) return;
    setBusy(true);
    try {
      storeSession(await changeOwnPassword(actual, nueva));
      setActual(''); setNueva(''); setConfirmacion('');
      setOk(true);
    } catch (err) {
      setError(err.message || 'No se pudo cambiar la contraseña.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h1 className="motored-t-interfaz" style={{ fontWeight: 700, fontSize: '1.1rem' }}>Cambiar mi contraseña</h1>
      <p style={{ fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Al cambiarla, se cierran tus otras sesiones abiertas. Esta sigue activa.
      </p>
      <form onSubmit={handleSubmit} style={formStyle}>
        <PasswordField label="Contraseña actual" value={actual} onChange={setActual} autoComplete="current-password" />
        <PasswordField
          label="Nueva contraseña" value={nueva} onChange={setNueva} autoComplete="new-password"
          hint={`Mínimo ${PASSWORD_MIN_LENGTH} caracteres (máximo 72).`}
        />
        <PasswordField label="Confirmar nueva contraseña" value={confirmacion} onChange={setConfirmacion} autoComplete="new-password" />
        {error && <p role="alert" style={{ ...msgStyle, color: 'var(--motored-danger, #c0392b)' }}>{error}</p>}
        {ok && <p role="status" style={{ ...msgStyle, color: 'var(--motored-success, #1e7e34)' }}>Contraseña actualizada.</p>}
        <button type="submit" className="motored-btn motored-btn-primary" disabled={busy} style={{ minHeight: '44px' }}>
          {busy ? 'Guardando...' : 'Guardar contraseña'}
        </button>
      </form>
    </section>
  );
}
