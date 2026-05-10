'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';

export default function TgTenant() {
  const router = useRouter();
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [search,  setSearch]  = useState('');
  const [user,    setUser]    = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    const u = JSON.parse(stored);
    setUser(u);
    if (u.role !== 'superadmin') { router.replace('/tg/home'); return; }
    loadTenants();
  }, []);

  const loadTenants = async () => {
    setLoading(true);
    try {
      const res = await authFetch('/tenants/');
      if (res.status === 401) { router.replace('/tg'); return; }
      if (!res.ok) { setError('No se pudieron cargar los centros de servicio'); return; }
      setTenants(await res.json());
    } catch (e) {
      setError(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const selectTenant = (tenant) => {
    sessionStorage.setItem('um_active_tenant_id',   String(tenant.id));
    sessionStorage.setItem('um_active_tenant_name', tenant.name);
    router.replace('/tg/home');
  };

  const filtered = tenants.filter(t =>
    !search ||
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    (t.ciudad && t.ciudad.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', paddingBottom: '2rem' }}>

      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <img src="/logo.png" alt="UM" style={{ height: 28, width: 'auto', objectFit: 'contain', flexShrink: 0, opacity: 0.9 }} />
        <div>
          <p style={{ margin: 0, fontWeight: 900, fontSize: '0.9rem', color: '#fff' }}>Centro de Servicio</p>
          <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075' }}>¿Desde qué centro trabajás hoy?</p>
        </div>
      </div>

      <div style={{ padding: '1rem' }}>

        {/* Buscador */}
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Buscar por nombre o ciudad…"
          style={{ width: '100%', background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.65rem 0.9rem', color: '#fff', fontSize: '0.85rem', outline: 'none', boxSizing: 'border-box', marginBottom: '0.75rem' }}
        />

        {error && (
          <div style={{ padding: '0.65rem 0.9rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.75rem' }}>
            <p style={{ margin: 0, fontSize: '0.7rem', color: '#ef4444', fontWeight: 700 }}>{error}</p>
          </div>
        )}

        {loading ? (
          <p style={{ color: '#606075', fontSize: '0.75rem', textAlign: 'center', padding: '2rem 0' }}>Cargando centros…</p>
        ) : filtered.length === 0 ? (
          <p style={{ color: '#606075', fontSize: '0.75rem', textAlign: 'center', padding: '2rem 0' }}>Sin resultados</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {filtered.map(t => (
              <div
                key={t.id}
                onClick={() => selectTenant(t)}
                style={{ background: '#13131a', borderRadius: 12, padding: '0.85rem 1rem', border: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                <div>
                  <p style={{ margin: 0, fontWeight: 800, fontSize: '0.82rem', color: '#e2e2f0' }}>{t.name}</p>
                  {(t.ciudad || t.departamento) && (
                    <p style={{ margin: '2px 0 0', fontSize: '0.62rem', color: '#606075' }}>
                      {[t.ciudad, t.departamento].filter(Boolean).join(', ')}
                    </p>
                  )}
                </div>
                <span style={{ fontSize: '0.7rem', color: '#ff5f33', fontWeight: 700 }}>→</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
