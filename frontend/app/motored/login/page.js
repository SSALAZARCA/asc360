'use client';
/**
 * frontend/app/motored/login/page.js
 *
 * Motored login page (sdd/motored-pedidos-cimientos, Phase 6, task 6.2).
 * Posts to the REAL `/api/motored/auth/login` (see
 * `backend/app/motored/api/auth.py`) and stores the returned token under
 * the Motored-only session keys (`motored_token`/`motored_user`) -- never
 * `um_token`/`um_user`. Mirrors `app/login/page.js`'s shape (plain fetch,
 * no wrapper needed pre-auth) but with Motored's own real brand identity:
 * the actual "Motored — Es Hero en Colombia" logo (`public/motored-logo.png`,
 * copied from the brand assets the user provided), rojo Motored (#E20714)
 * as the single accent, on a light surface (per the app's own design-
 * system reference, not the dark theme this page originally shipped with).
 */
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { Mail, Lock, ArrowRight } from 'lucide-react';
import { login } from '../../../lib/motored/api';
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';

export default function MotoredLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const data = await login(email, password);

      sessionStorage.setItem(MOTORED_TOKEN_KEY, data.access_token);
      sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify(data.user));
      window.dispatchEvent(new Event('storage'));

      router.push('/motored/maestros');
    } catch (err) {
      setError(err.message || 'Credenciales inválidas o servidor inalcanzable.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="motored-login-wrapper">
      <div className="motored-login-box">
        <div className="motored-brand-header">
          <Image src="/motored-logo.png" alt="Motored" width={180} height={58} priority />
          <p>Pedidos &amp; Reposición</p>
        </div>

        <form onSubmit={handleLogin} className="motored-login-form">
          {error && <div className="motored-error-box">{error}</div>}

          <div className="motored-input-group">
            <label>Correo Electrónico</label>
            <div className="motored-input-icon">
              <Mail size={16} />
              <input
                type="email"
                placeholder="usuario@motoredcolombia.com.co"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="motored-input-group">
            <label>Contraseña</label>
            <div className="motored-input-icon">
              <Lock size={16} />
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </div>

          <button type="submit" className="motored-btn motored-btn-primary" style={{ width: '100%', height: '44px', marginTop: '0.5rem' }} disabled={loading}>
            {loading ? 'Verificando...' : <>Iniciar sesión <ArrowRight size={16} /></>}
          </button>
        </form>
      </div>

      <style jsx>{`
        .motored-login-wrapper { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: var(--motored-bg, #f7f7f8); }
        .motored-login-box { width: 100%; max-width: 380px; background: var(--motored-surface, #ffffff); border: 1px solid var(--motored-border, #e4e4e7); border-radius: var(--motored-radius-md, 8px); box-shadow: var(--motored-shadow, 0 1px 3px rgba(0,0,0,0.08)); overflow: hidden; }

        .motored-brand-header { padding: 2.5rem 2rem 1.5rem; text-align: center; border-bottom: 1px solid var(--motored-border, #e4e4e7); display: flex; flex-direction: column; align-items: center; }
        .motored-brand-header p { margin: 0.75rem 0 0; font-size: 0.75rem; color: var(--motored-text-muted, #5a5a5a); text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }

        .motored-login-form { padding: 2rem; display: flex; flex-direction: column; gap: 1.25rem; }

        .motored-input-group label { display: block; font-size: 0.65rem; font-weight: 700; color: var(--motored-text-muted, #5a5a5a); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
        .motored-input-icon { position: relative; display: flex; align-items: center; }
        .motored-input-icon :global(svg:first-child) { position: absolute; left: 1rem; color: var(--motored-text-soft, #8a8a8a); }
        .motored-input-icon :global(input) { width: 100%; padding-left: 2.8rem; }

        .motored-error-box { background: var(--motored-danger-bg, #fdecea); border: 1px solid var(--motored-danger, #c0392b); color: var(--motored-danger, #c0392b); padding: 0.75rem; border-radius: var(--motored-radius-sm, 4px); font-size: 0.75rem; font-weight: 700; text-align: center; }
      `}</style>
    </div>
  );
}
