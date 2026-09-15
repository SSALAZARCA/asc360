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

          <button type="submit" className="motored-login-btn" disabled={loading}>
            {loading ? 'Verificando...' : <>Iniciar sesión <ArrowRight size={16} /></>}
          </button>
        </form>
      </div>

      <style jsx>{`
        .motored-login-wrapper { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: #f7f7f8; }
        .motored-login-box { width: 100%; max-width: 380px; background: #ffffff; border: 1px solid #e4e4e7; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow: hidden; }

        .motored-brand-header { padding: 2.5rem 2rem 1.5rem; text-align: center; border-bottom: 1px solid #e4e4e7; display: flex; flex-direction: column; align-items: center; }
        .motored-brand-header p { margin: 0.75rem 0 0; font-size: 0.75rem; color: #5a5a5a; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }

        .motored-login-form { padding: 2rem; display: flex; flex-direction: column; gap: 1.25rem; }

        .motored-input-group label { display: block; font-size: 0.65rem; font-weight: 700; color: #5a5a5a; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
        .motored-input-icon { position: relative; display: flex; align-items: center; }
        .motored-input-icon :global(svg:first-child) { position: absolute; left: 1rem; color: #8a8a8a; }
        .motored-input-icon input { width: 100%; background: #ffffff; border: 1px solid #e4e4e7; padding: 0.85rem 1rem 0.85rem 2.8rem; border-radius: 6px; color: #1a1a18; font-size: 0.85rem; outline: none; transition: all 0.2s; }
        .motored-input-icon input:focus { border-color: #e20714; box-shadow: 0 0 0 3px #fde8ea; }

        .motored-login-btn { display: flex; align-items: center; justify-content: center; gap: 0.5rem; width: 100%; background: #e20714; color: #ffffff; border: none; padding: 1rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem; letter-spacing: 0.02em; cursor: pointer; transition: all 0.2s; margin-top: 1rem; }
        .motored-login-btn:hover:not(:disabled) { background: #b00510; }
        .motored-login-btn:disabled { opacity: 0.7; cursor: not-allowed; }

        .motored-error-box { background: #fdf3f4; border: 1px solid #fcd4d8; color: #7a1f16; padding: 0.75rem; border-radius: 6px; font-size: 0.75rem; font-weight: 700; text-align: center; }
      `}</style>
    </div>
  );
}
