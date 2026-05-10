'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';

const STATES = {
  received: 'Recibido', scheduled: 'Agendado', in_progress: 'En Proceso',
  on_hold_parts: 'Espera Repuestos', on_hold_client: 'Espera Cliente',
  external_work: 'Trabajo Externo', rescheduled: 'Reagendado',
  completed: 'Finalizado', delivered: 'Entregado', pending_signature: 'Firma Pendiente',
};

export default function TgVehicle() {
  const router = useRouter();
  const [user, setUser]       = useState(null);
  const [plate, setPlate]     = useState('');
  const [vehicle, setVehicle] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    setUser(JSON.parse(stored));
  }, []);

  const search = async () => {
    if (!plate.trim()) return;
    setLoading(true);
    setError(null);
    setVehicle(null);
    setHistory([]);
    try {
      const res = await authFetch(`/vehicles/${plate.trim().toUpperCase()}`);
      if (res.status === 401) { router.replace('/tg'); return; }
      if (res.status === 404) { setError('Vehículo no encontrado'); return; }
      if (!res.ok) { setError('Error al consultar'); return; }
      const data = await res.json();
      setVehicle(data);
      if (data.id) {
        const hr = await authFetch(`/vehicles/${data.id}/lifecycle`);
        if (hr.ok) setHistory(await hr.json());
      }
    } catch (e) {
      setError(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', paddingBottom: '5.5rem' }}>
      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem' }}>
        <p style={{ margin: 0, fontWeight: 900, fontSize: '0.9rem', color: '#fff' }}>Hoja de Vida</p>
        <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075' }}>Historial de la moto</p>
      </div>

      {/* Buscador */}
      <div style={{ padding: '1rem 1rem 0.5rem', display: 'flex', gap: '0.5rem' }}>
        <input
          value={plate}
          onChange={e => setPlate(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && search()}
          placeholder="Ej: ABC123"
          maxLength={6}
          style={{ flex: 1, background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.7rem 1rem', color: '#fff', fontSize: '1rem', fontWeight: 800, letterSpacing: '0.08em', outline: 'none' }}
        />
        <button
          onClick={search}
          disabled={loading || !plate.trim()}
          style={{ padding: '0.7rem 1.1rem', background: '#ff5f33', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 800, fontSize: '0.85rem', cursor: 'pointer', opacity: loading || !plate.trim() ? 0.5 : 1 }}
        >
          {loading ? '...' : 'Buscar'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{ margin: '0 1rem 0.5rem', padding: '0.7rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10 }}>
          <p style={{ margin: 0, fontSize: '0.72rem', color: '#ef4444', fontWeight: 700 }}>{error}</p>
        </div>
      )}

      {/* Datos del vehículo */}
      {vehicle && (
        <div style={{ padding: '0 1rem' }}>
          {/* Info básica */}
          <div style={{ background: '#13131a', borderRadius: 14, padding: '1rem', marginBottom: '0.75rem', border: '1px solid rgba(255,255,255,0.06)' }}>
            <p style={{ margin: '0 0 0.6rem', fontWeight: 900, fontSize: '1.4rem', color: '#ff8c5a', letterSpacing: '0.06em' }}>{vehicle.plate}</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
              {[
                ['Modelo', vehicle.model || '—'],
                ['Marca', vehicle.brand || '—'],
                ['Año', vehicle.year || '—'],
                ['Color', vehicle.color || '—'],
                ['VIN', vehicle.vin || '—'],
                ['KM', vehicle.latest_mileage ? (vehicle.latest_mileage).toLocaleString() + ' km' : '—'],
              ].map(([l, v]) => (
                <div key={l} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '0.5rem 0.7rem' }}>
                  <p style={{ margin: 0, fontSize: '0.5rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>{l}</p>
                  <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: '#e2e2f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Orden activa */}
          {vehicle.active_order && (
            <div style={{ background: 'rgba(255,95,51,0.08)', border: '1px solid rgba(255,95,51,0.25)', borderRadius: 12, padding: '0.85rem 1rem', marginBottom: '0.75rem' }}>
              <p style={{ margin: '0 0 0.4rem', fontSize: '0.55rem', color: '#ff5f33', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>Orden Activa</p>
              <p style={{ margin: 0, fontSize: '0.78rem', color: '#fff', fontWeight: 700 }}>{STATES[vehicle.active_order.status] || vehicle.active_order.status}</p>
              {vehicle.active_order.centro && (
                <p style={{ margin: '2px 0 0', fontSize: '0.62rem', color: '#606075' }}>{vehicle.active_order.centro}</p>
              )}
            </div>
          )}

          {/* Historial */}
          {history.length > 0 && (
            <>
              <p style={{ margin: '0 0 0.5rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>Historial</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                {history.map(ev => (
                  <div key={ev.id} style={{ background: '#13131a', borderRadius: 10, padding: '0.65rem 0.9rem', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <p style={{ margin: 0, fontSize: '0.7rem', fontWeight: 700, color: '#e2e2f0' }}>{ev.summary}</p>
                      <span style={{ fontSize: '0.52rem', color: '#606075', whiteSpace: 'nowrap', marginLeft: '0.5rem' }}>
                        {ev.event_date ? new Date(ev.event_date).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: '2-digit' }) : ''}
                      </span>
                    </div>
                    {ev.km_at_event && (
                      <p style={{ margin: '2px 0 0', fontSize: '0.58rem', color: '#606075' }}>{Number(ev.km_at_event).toLocaleString()} km</p>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <TgNav userRole={user?.role} />
    </div>
  );
}
