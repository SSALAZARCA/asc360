'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, Key, Mail, Lock } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const API = () => (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await fetch(`${API()}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Error de autenticación');
      }

      // Guardar token y datos del usuario
      sessionStorage.setItem('um_token', data.access_token);
      sessionStorage.setItem('um_user', JSON.stringify(data.user));
      
      // Actualizar el contexto en la app
      window.dispatchEvent(new Event('storage'));

      // Redirigir según rol
      if (data.user.role === 'superadmin' || data.user.role === 'administrativo') {
        router.push('/');
      } else if (data.user.role === 'proveedor') {
        router.push('/imports');
      } else {
        router.push('/kanban');
      }
    } catch (e) {
      setError(e.message || 'Credenciales inválidas o servidor inalcanzable.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-box">
        <div className="brand-header">
          <div className="brand-logo">UM</div>
          <h1>MASTER-DATA</h1>
          <p>Red de Servicio Técnico</p>
        </div>

        <form onSubmit={handleLogin} className="login-form">
          {error && <div className="error-box">{error}</div>}
          
          <div className="input-group">
            <label>Correo Electrónico</label>
            <div className="input-icon">
              <Mail size={16} />
              <input 
                type="email" 
                placeholder="usuario@umcolombia.co"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="input-group">
            <label>Contraseña / Pin de Acceso</label>
            <div className="input-icon">
              <Lock size={16} />
              <input 
                type="password" 
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
              />
            </div>
          </div>

          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? 'Verificando biometría...' : <><Shield size={16}/> INICIAR SESIÓN</>}
          </button>
        </form>
      </div>

      <style jsx>{`
        .login-wrapper { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: #0c0c0e; background-image: radial-gradient(circle at 50% 0%, rgba(255, 95, 51, 0.15), transparent 40%); }
        .login-box { width: 100%; max-width: 380px; background: #111114; border: 1px solid rgba(255,255,255,0.05); border-radius: 20px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.8), 0 0 30px rgba(255, 95, 51, 0.05); overflow: hidden; }
        
        .brand-header { padding: 2.5rem 2rem 1.5rem; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.05); background: linear-gradient(180deg, rgba(255, 95, 51, 0.05) 0%, transparent 100%); }
        .brand-logo { width: 64px; height: 64px; background: #ff5f33; border-radius: 16px; margin: 0 auto 1.5rem; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; font-weight: 900; font-style: italic; color: white; transform: skewX(-10deg); box-shadow: 0 10px 30px rgba(255, 95, 51, 0.3); }
        .brand-header h1 { margin: 0; font-size: 1.25rem; font-weight: 900; letter-spacing: 0.1em; color: white; }
        .brand-header p { margin: 0.25rem 0 0; font-size: 0.75rem; color: #ff5f33; text-transform: uppercase; font-weight: 800; letter-spacing: 0.05em; }

        .login-form { padding: 2rem; display: flex; flex-direction: column; gap: 1.25rem; }
        
        .input-group label { display: block; font-size: 0.65rem; font-weight: 800; color: rgba(255,255,255,0.5); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
        .input-icon { position: relative; display: flex; align-items: center; }
        .input-icon :global(svg) { position: absolute; left: 1rem; color: rgba(255,255,255,0.3); }
        .input-icon input { width: 100%; background: #0c0c0e; border: 1px solid rgba(255,255,255,0.1); padding: 0.85rem 1rem 0.85rem 2.8rem; border-radius: 12px; color: white; font-size: 0.85rem; outline: none; transition: all 0.2s; }
        .input-icon input:focus { border-color: #ff5f33; box-shadow: 0 0 0 3px rgba(255, 95, 51, 0.1); }
        
        .login-btn { display: flex; align-items: center; justify-content: center; gap: 0.5rem; width: 100%; background: #ff5f33; color: white; border: none; padding: 1rem; border-radius: 12px; font-weight: 900; font-size: 0.85rem; letter-spacing: 0.05em; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 15px rgba(255, 95, 51, 0.3); margin-top: 1rem; }
        .login-btn:hover:not(:disabled) { background: #e04a22; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(255, 95, 51, 0.4); }
        .login-btn:disabled { opacity: 0.7; cursor: not-allowed; animation: pulse 2s infinite; }

        .error-box { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; padding: 0.75rem; border-radius: 8px; font-size: 0.75rem; font-weight: 700; text-align: center; }

        @keyframes pulse { 0% { opacity: 0.7; } 50% { opacity: 0.4; } 100% { opacity: 0.7; } }
      `}</style>
    </div>
  );
}
