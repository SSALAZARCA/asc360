'use client';
/**
 * frontend/app/motored/login/page.js
 *
 * Motored login page (sdd/motored-pedidos-cimientos, Phase 6, task 6.2).
 * Posts to the REAL `/api/motored/auth/login` (see
 * `backend/app/motored/api/auth.py`) and stores the returned token under
 * the Motored-only session keys (`motored_token`/`motored_user`) -- never
 * `um_token`/`um_user`. Mirrors `app/login/page.js`'s shape (plain fetch,
 * no wrapper needed pre-auth) but with Motored's own distinct visual
 * identity (cyan accent instead of asc360's orange).
 */
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ShieldCheck, Mail, Lock } from 'lucide-react';
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
          <div className="motored-brand-logo">
            <ShieldCheck size={28} color="#0a1420" strokeWidth={2.5} />
          </div>
          <h1>MOTORED</h1>
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
            {loading ? 'Verificando...' : <><ShieldCheck size={16} /> INICIAR SESIÓN</>}
          </button>
        </form>
      </div>

      <style jsx>{`
        .motored-login-wrapper { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: #0a1420; background-image: radial-gradient(circle at 50% 0%, rgba(34, 211, 238, 0.15), transparent 40%); }
        .motored-login-box { width: 100%; max-width: 380px; background: #101d2e; border: 1px solid rgba(148,197,255,0.12); border-radius: 12px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.8); overflow: hidden; }

        .motored-brand-header { padding: 2.5rem 2rem 1.5rem; text-align: center; border-bottom: 1px solid rgba(148,197,255,0.12); background: linear-gradient(180deg, rgba(34, 211, 238, 0.08) 0%, transparent 100%); }
        .motored-brand-logo { width: 64px; height: 64px; background: #22d3ee; border-radius: 12px; margin: 0 auto 1.5rem; display: flex; align-items: center; justify-content: center; box-shadow: 0 10px 30px rgba(34, 211, 238, 0.3); }
        .motored-brand-header h1 { margin: 0; font-size: 1.25rem; font-weight: 800; letter-spacing: 0.1em; color: #e6f4ff; }
        .motored-brand-header p { margin: 0.25rem 0 0; font-size: 0.75rem; color: #22d3ee; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; }

        .motored-login-form { padding: 2rem; display: flex; flex-direction: column; gap: 1.25rem; }

        .motored-input-group label { display: block; font-size: 0.65rem; font-weight: 700; color: #7fa3c4; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
        .motored-input-icon { position: relative; display: flex; align-items: center; }
        .motored-input-icon :global(svg) { position: absolute; left: 1rem; color: rgba(230,244,255,0.3); }
        .motored-input-icon input { width: 100%; background: #0a1420; border: 1px solid rgba(148,197,255,0.12); padding: 0.85rem 1rem 0.85rem 2.8rem; border-radius: 8px; color: #e6f4ff; font-size: 0.85rem; outline: none; transition: all 0.2s; }
        .motored-input-icon input:focus { border-color: #22d3ee; box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.1); }

        .motored-login-btn { display: flex; align-items: center; justify-content: center; gap: 0.5rem; width: 100%; background: #22d3ee; color: #0a1420; border: none; padding: 1rem; border-radius: 8px; font-weight: 800; font-size: 0.85rem; letter-spacing: 0.05em; cursor: pointer; transition: all 0.2s; margin-top: 1rem; }
        .motored-login-btn:hover:not(:disabled) { background: #0891b2; color: #fff; }
        .motored-login-btn:disabled { opacity: 0.7; cursor: not-allowed; }

        .motored-error-box { background: rgba(248, 113, 113, 0.1); border: 1px solid rgba(248, 113, 113, 0.3); color: #f87171; padding: 0.75rem; border-radius: 8px; font-size: 0.75rem; font-weight: 700; text-align: center; }
      `}</style>
    </div>
  );
}
