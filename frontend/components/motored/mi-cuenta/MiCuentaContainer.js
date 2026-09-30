'use client';
/**
 * "Mi cuenta": every web user changes their own password. The backend answers
 * with a fresh session (other sessions are cut), which replaces the stored one
 * so this tab stays logged in.
 */
import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import PasswordField from './PasswordField';
import { changeOwnPassword } from '../../../lib/motored/api';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import { PASSWORD_HINT, FORCED_CHANGE_BANNER, newPasswordProblem } from '../../../lib/motored/passwordRules';
import { homePathFor, storeSession } from '../../../lib/motored/session';

const formStyle = { display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%', maxWidth: '420px' };
const msgStyle = { margin: 0, fontSize: '0.8rem', fontWeight: 700 };
const bannerStyle = {
  maxWidth: '420px', margin: '0.75rem 0', padding: '0.75rem 1rem', borderRadius: 'var(--motored-radius-sm, 4px)', fontSize: '0.8rem', fontWeight: 700,
  background: 'var(--motored-danger-bg, #fdecea)', border: '1px solid var(--motored-danger, #c0392b)', color: 'var(--motored-danger, #c0392b)',
};

/** Stored user flagged for a forced change; read once on mount, so the banner survives the change. */
function useForcedChange() {
  return useMemo(() => {
    try {
      return Boolean(JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.must_change_password);
    } catch {
      return false;
    }
  }, []);
}

export default function MiCuentaContainer() {
  const router = useRouter();
  const forced = useForcedChange();
  const [actual, setActual] = useState('');
  const [nueva, setNueva] = useState('');
  const [confirmacion, setConfirmacion] = useState('');
  const [error, setError] = useState('');
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setOk(false);
    const problema = newPasswordProblem(nueva, confirmacion);
    setError(problema);
    if (problema) return;
    setBusy(true);
    try {
      const data = await changeOwnPassword(actual, nueva);
      storeSession(data);
      setActual(''); setNueva(''); setConfirmacion('');
      setOk(true);
      if (forced) router.push(homePathFor(data.user?.role));
    } catch (err) {
      setError(err.message || 'No se pudo cambiar la contraseña.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h1 className="motored-t-interfaz" style={{ fontWeight: 700, fontSize: '1.1rem' }}>Cambiar mi contraseña</h1>
      {forced && <p role="alert" style={bannerStyle}>{FORCED_CHANGE_BANNER}</p>}
      <p style={{ fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Al cambiarla, se cierran tus otras sesiones abiertas. Esta sigue activa.
      </p>
      <form onSubmit={handleSubmit} style={formStyle}>
        <PasswordField label="Contraseña actual" value={actual} onChange={setActual} autoComplete="current-password" />
        <PasswordField
          label="Nueva contraseña" value={nueva} onChange={setNueva} autoComplete="new-password"
          hint={PASSWORD_HINT}
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
