'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';

const ROLE_LABELS = {
  superadmin: 'Super Admin', jefe_taller: 'Jefe Taller',
  technician: 'Técnico', advisor: 'Asesor', client: 'Cliente',
};

export default function TgAdmin() {
  const router  = useRouter();
  const [user, setUser]       = useState(null);
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing]   = useState(null);
  const [error, setError]     = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    const u = JSON.parse(stored);
    setUser(u);
    if (u.role !== 'superadmin') { router.replace('/tg/home'); return; }
    loadPending();
  }, []);

  const loadPending = async () => {
    setLoading(true);
    try {
      const res = await authFetch('/users/pending');
      if (res.status === 401) { router.replace('/tg'); return; }
      if (res.ok) setPending(await res.json());
    } finally {
      setLoading(false);
    }
  };

  const action = async (userId, newStatus) => {
    setActing(userId);
    setError(null);
    try {
      const res = await authFetch(`/users/${userId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        setPending(prev => prev.filter(u => u.id !== userId));
      } else {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || 'Error al procesar');
      }
    } catch (e) {
      setError(`Error: ${e.message}`);
    } finally {
      setActing(null);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', paddingBottom: '5.5rem' }}>
      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <img src="/logo.png" alt="UM" style={{ height: 28, width: 'auto', objectFit: 'contain', flexShrink: 0, opacity: 0.9 }} />
        <div>
          <p style={{ margin: 0, fontWeight: 900, fontSize: '0.9rem', color: '#fff' }}>Panel Admin</p>
          <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075' }}>Solicitudes de acceso pendientes</p>
        </div>
      </div>

      <div style={{ padding: '1rem' }}>
        {/* Error */}
        {error && (
          <div style={{ padding: '0.65rem 0.9rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.75rem' }}>
            <p style={{ margin: 0, fontSize: '0.7rem', color: '#ef4444', fontWeight: 700 }}>{error}</p>
          </div>
        )}

        {loading ? (
          <p style={{ color: '#606075', fontSize: '0.75rem', textAlign: 'center', padding: '2rem 0' }}>Cargando...</p>
        ) : pending.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
            <p style={{ color: '#10b981', fontSize: '0.85rem', fontWeight: 700, margin: '0 0 0.25rem' }}>Sin solicitudes pendientes</p>
            <p style={{ color: '#606075', fontSize: '0.65rem', margin: 0 }}>Todos los accesos están resueltos</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {pending.map(u => (
              <div key={u.id} style={{ background: '#13131a', borderRadius: 14, padding: '1rem', border: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                  <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(255,95,51,0.12)', border: '1px solid rgba(255,95,51,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: '0.8rem', color: '#ff5f33', flexShrink: 0 }}>
                    {u.name?.substring(0, 2).toUpperCase() || '??'}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <p style={{ margin: 0, fontWeight: 800, fontSize: '0.85rem', color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.name}</p>
                    <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075' }}>{ROLE_LABELS[u.role] || u.role} {u.phone ? `· ${u.phone}` : ''}</p>
                  </div>
                </div>

                {u.email && <p style={{ margin: '0 0 0.75rem', fontSize: '0.62rem', color: '#606075' }}>{u.email}</p>}

                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => action(u.id, 'active')}
                    disabled={acting === u.id}
                    style={{ flex: 1, padding: '0.65rem', background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: 10, color: '#10b981', fontWeight: 800, fontSize: '0.78rem', cursor: 'pointer', opacity: acting === u.id ? 0.5 : 1 }}
                  >
                    Aprobar
                  </button>
                  <button
                    onClick={() => action(u.id, 'rejected')}
                    disabled={acting === u.id}
                    style={{ flex: 1, padding: '0.65rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, color: '#ef4444', fontWeight: 800, fontSize: '0.78rem', cursor: 'pointer', opacity: acting === u.id ? 0.5 : 1 }}
                  >
                    Rechazar
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <TgNav userRole={user?.role} />
    </div>
  );
}
