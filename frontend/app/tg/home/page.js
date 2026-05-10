'use client';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';

const STATES = {
  received:          { name: 'Recibido',         color: '#3b82f6' },
  scheduled:         { name: 'Agendado',          color: '#8b5cf6' },
  in_progress:       { name: 'En Proceso',        color: '#f59e0b' },
  on_hold_parts:     { name: 'Espera Repuestos',  color: '#ef4444' },
  on_hold_client:    { name: 'Espera Cliente',    color: '#f97316' },
  external_work:     { name: 'Trabajo Externo',   color: '#06b6d4' },
  rescheduled:       { name: 'Reagendado',        color: '#6366f1' },
  completed:         { name: 'Finalizado',        color: '#10b981' },
  delivered:         { name: 'Entregado',         color: '#22c55e' },
  pending_signature: { name: 'Firma Pendiente',   color: '#f59e0b' },
};

const TYPES = {
  warranty:  { label: 'Garantía',     color: '#eab308' },
  km_review: { label: 'Rev. KM',      color: '#22c55e' },
  regular:   { label: 'Mecánica',     color: '#3b82f6' },
  pdi:       { label: 'Alistamiento', color: '#f97316' },
};

const INACTIVE = ['delivered', 'completed'];

function dayColor(d) { return d > 5 ? '#ef4444' : d > 2 ? '#fbbf24' : '#10b981'; }

export default function TgHome() {
  const router = useRouter();
  const [user, setUser]       = useState(null);
  const [orders, setOrders]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [filter, setFilter]   = useState('active');
  const [refreshing, setRefreshing] = useState(false);
  const [apiError, setApiError] = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    setUser(JSON.parse(stored));
    loadOrders();
  }, []);

  const loadOrders = useCallback(async (silent = false) => {
    if (!silent) setLoading(true); else setRefreshing(true);
    setApiError(null);
    try {
      const res = await authFetch('/orders/analytics/services');
      if (res.status === 401) { router.replace('/tg'); return; }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setApiError(`HTTP ${res.status}: ${err.detail || res.statusText}`);
        return;
      }
      const data = await res.json();
      setOrders(Array.isArray(data) ? data : []);
    } catch (e) {
      setApiError(`Error de conexión: ${e.message}`);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [router]);

  const updateStatus = async (orderId, newStatus) => {
    setUpdating(true);
    try {
      const res = await authFetch(`/orders/${orderId}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        setOrders(prev => prev.map(o => o.order_id === orderId ? { ...o, estado: newStatus } : o));
        setSelected(prev => prev ? { ...prev, estado: newStatus } : null);
      }
    } finally {
      setUpdating(false);
    }
  };

  const displayed = filter === 'active'
    ? orders.filter(o => !INACTIVE.includes(o.estado))
    : orders;

  const semaphore = {
    green:  orders.filter(o => !INACTIVE.includes(o.estado) && (o.tiempo_taller_dias ?? 0) <= 2).length,
    yellow: orders.filter(o => !INACTIVE.includes(o.estado) && (o.tiempo_taller_dias ?? 0) > 2 && (o.tiempo_taller_dias ?? 0) <= 5).length,
    red:    orders.filter(o => !INACTIVE.includes(o.estado) && (o.tiempo_taller_dias ?? 0) > 5).length,
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', paddingBottom: '5.5rem' }}>

      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', position: 'sticky', top: 0, zIndex: 10 }}>
        <div style={{ width: 38, height: 38, borderRadius: '50%', background: 'rgba(255,95,51,0.12)', border: '1px solid rgba(255,95,51,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: '0.85rem', color: '#ff5f33', flexShrink: 0 }}>
          {user?.name?.substring(0, 2).toUpperCase() || '??'}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <p style={{ margin: 0, fontWeight: 800, fontSize: '0.85rem', color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.name}</p>
          <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{user?.role?.replace('_', ' ')}</p>
        </div>
        <button
          onClick={() => loadOrders(true)}
          disabled={refreshing}
          style={{ background: 'transparent', border: 'none', color: refreshing ? '#3f3f55' : '#606075', cursor: 'pointer', fontSize: '1.2rem', padding: '0.4rem', lineHeight: 1, transition: 'color 0.15s' }}
        >↻</button>
      </div>

      {/* Semáforo */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', padding: '1rem 1rem 0.5rem' }}>
        {[
          { label: 'En tiempo',  count: semaphore.green,  color: '#10b981' },
          { label: 'Atención',   count: semaphore.yellow, color: '#fbbf24' },
          { label: 'Urgente',    count: semaphore.red,    color: '#ef4444' },
        ].map(s => (
          <div key={s.label} style={{ background: '#13131a', borderRadius: 12, padding: '0.75rem 0.5rem', border: `1px solid ${s.color}22`, textAlign: 'center' }}>
            <p style={{ margin: 0, fontWeight: 900, fontSize: '1.5rem', color: s.color, lineHeight: 1 }}>{s.count}</p>
            <p style={{ margin: '4px 0 0', fontSize: '0.58rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{s.label}</p>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{ display: 'flex', gap: '0.4rem', padding: '0.75rem 1rem 0.5rem' }}>
        {[['active', `Activas (${orders.filter(o => !INACTIVE.includes(o.estado)).length})`], ['all', `Todas (${orders.length})`]].map(([val, lbl]) => (
          <button key={val} onClick={() => setFilter(val)} style={{ padding: '0.4rem 0.9rem', borderRadius: 20, border: 'none', background: filter === val ? '#ff5f33' : 'rgba(255,255,255,0.06)', color: filter === val ? '#fff' : '#606075', fontWeight: 700, fontSize: '0.68rem', cursor: 'pointer', transition: 'all 0.15s' }}>
            {lbl}
          </button>
        ))}
      </div>

      {/* Error de API */}
      {apiError && (
        <div style={{ margin: '0 0.75rem 0.5rem', padding: '0.75rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10 }}>
          <p style={{ margin: 0, fontSize: '0.65rem', color: '#ef4444', fontWeight: 700, marginBottom: 2 }}>Error al cargar órdenes</p>
          <p style={{ margin: 0, fontSize: '0.6rem', color: '#9ca3af', wordBreak: 'break-all' }}>{apiError}</p>
        </div>
      )}

      {/* Lista de órdenes */}
      <div style={{ padding: '0 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '3rem 0', color: '#3f3f55', fontSize: '0.8rem' }}>Cargando órdenes...</div>
        ) : displayed.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem 0', color: '#3f3f55', fontSize: '0.8rem' }}>Sin órdenes {filter === 'active' ? 'activas' : ''}</div>
        ) : displayed
            .sort((a, b) => (b.tiempo_taller_dias ?? 0) - (a.tiempo_taller_dias ?? 0))
            .map(order => {
          const st = STATES[order.estado] || { name: order.estado, color: '#606075' };
          const tc = TYPES[order.tipo_trabajo] || TYPES.regular;
          const dc = dayColor(order.tiempo_taller_dias ?? 0);
          return (
            <div
              key={order.order_id}
              onClick={() => setSelected(order)}
              style={{ background: '#13131a', borderRadius: 12, border: '1px solid rgba(255,255,255,0.05)', padding: '0.85rem 1rem', cursor: 'pointer', borderLeft: `3px solid ${tc.color}`, transition: 'background 0.15s, transform 0.1s', WebkitTapHighlightColor: 'transparent' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                <span style={{ fontWeight: 900, fontSize: '1rem', color: '#ff8c5a', letterSpacing: '0.05em' }}>{order.placa}</span>
                <span style={{ fontSize: '0.58rem', fontWeight: 800, padding: '2px 8px', borderRadius: 20, background: `${st.color}18`, color: st.color, border: `1px solid ${st.color}28`, whiteSpace: 'nowrap' }}>{st.name}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.68rem', color: '#606075', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>{order.centro_actual}</span>
                <span style={{ fontWeight: 800, fontSize: '0.72rem', color: dc }}>{order.tiempo_taller_dias ?? 0}d</span>
              </div>
            </div>
          );
        })}
      </div>

      <TgNav userRole={user?.role} />

      {/* Bottom sheet — detalle + cambio de estado */}
      {selected && (() => {
        const st = STATES[selected.estado] || { name: selected.estado, color: '#606075' };
        const tc = TYPES[selected.tipo_trabajo] || TYPES.regular;
        const dc = dayColor(selected.tiempo_taller_dias ?? 0);
        return (
          <div
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)', zIndex: 50, display: 'flex', alignItems: 'flex-end' }}
            onClick={() => setSelected(null)}
          >
            <div
              onClick={e => e.stopPropagation()}
              style={{ width: '100%', background: '#13131a', borderRadius: '20px 20px 0 0', padding: '1.25rem 1.25rem 2.5rem', maxHeight: '85vh', overflowY: 'auto' }}
            >
              {/* Handle */}
              <div style={{ width: 36, height: 4, background: 'rgba(255,255,255,0.12)', borderRadius: 2, margin: '0 auto 1.25rem' }} />

              {/* Placa + tipo */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span style={{ fontWeight: 900, fontSize: '1.5rem', color: '#ff8c5a', letterSpacing: '0.06em' }}>{selected.placa}</span>
                <span style={{ fontSize: '0.62rem', fontWeight: 800, padding: '3px 10px', borderRadius: 20, background: `${tc.color}18`, color: tc.color, border: `1px solid ${tc.color}28` }}>{tc.label}</span>
              </div>

              {/* Estado actual */}
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.9rem', borderRadius: 20, background: `${st.color}15`, border: `1px solid ${st.color}30`, marginBottom: '1.25rem' }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: st.color }} />
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: st.color }}>{st.name}</span>
              </div>

              {/* Grid de datos */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '1.5rem' }}>
                {[
                  ['Centro', selected.centro_actual],
                  ['Ciudad', selected.ciudad || '—'],
                  ['KM', (selected.kilometraje || 0).toLocaleString()],
                  ['Días en taller', <span style={{ color: dc, fontWeight: 900 }}>{selected.tiempo_taller_dias ?? 0}d</span>],
                  ['Visitas totales', selected.v_totales ?? '—'],
                  ['Garantías', selected.g_totales ?? '—'],
                ].map(([l, v]) => (
                  <div key={l} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '0.6rem 0.75rem' }}>
                    <p style={{ margin: 0, fontSize: '0.52rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 3 }}>{l}</p>
                    <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 700, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</p>
                  </div>
                ))}
              </div>

              {/* Cambiar estado */}
              <p style={{ margin: '0 0 0.65rem', fontSize: '0.58rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700 }}>Cambiar Estado</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                {Object.entries(STATES)
                  .filter(([k]) => k !== 'pending_signature')
                  .map(([key, s]) => {
                    const isCurrent = selected.estado === key;
                    return (
                      <button
                        key={key}
                        disabled={updating || isCurrent}
                        onClick={() => updateStatus(selected.order_id, key)}
                        style={{ padding: '0.7rem 1rem', borderRadius: 10, border: `1px solid ${isCurrent ? s.color : 'rgba(255,255,255,0.06)'}`, background: isCurrent ? `${s.color}15` : 'transparent', color: isCurrent ? s.color : '#9ca3af', fontWeight: 700, fontSize: '0.78rem', cursor: isCurrent ? 'default' : 'pointer', textAlign: 'left', transition: 'all 0.15s', opacity: updating && !isCurrent ? 0.4 : 1, display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                      >
                        <div style={{ width: 7, height: 7, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
                        {isCurrent ? `✓ ${s.name}` : s.name}
                      </button>
                    );
                  })}
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
