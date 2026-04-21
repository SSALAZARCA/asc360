'use client';
import { useState, useEffect, useCallback, useRef } from 'react';
import { authFetch } from '../../lib/authFetch';
import { RefreshCw, TrendingUp, Package, FileText, Ship, Loader } from 'lucide-react';

function API() {
  return (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');
}

function daysUntil(isoDate) {
  if (!isoDate) return null;
  const diff = new Date(isoDate).getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

// ---------------------------------------------------------------------------
// KPI Card
// ---------------------------------------------------------------------------
function KPICard({ label, value, sub, color = '#9ca3af', accent = false }) {
  return (
    <div style={{
      padding: '16px 18px', borderRadius: '12px',
      background: accent ? `linear-gradient(135deg, ${color}18, ${color}08)` : 'rgba(255,255,255,0.03)',
      border: `1px solid ${accent ? color + '30' : 'rgba(255,255,255,0.06)'}`,
    }}>
      <p style={{ margin: 0, fontSize: '22px', fontWeight: 800, color, lineHeight: 1 }}>{value}</p>
      <p style={{ margin: '5px 0 0', fontSize: '10px', fontWeight: 700, color: '#606075', letterSpacing: '0.06em', textTransform: 'uppercase' }}>{label}</p>
      {sub && <p style={{ margin: '3px 0 0', fontSize: '10px', color: '#404050' }}>{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Orders Popover — lista compacta de pedidos al hacer hover
// ---------------------------------------------------------------------------
function OrdersPopover({ orders, loading, title, color }) {
  if (!loading && (!orders || orders.length === 0)) return null;
  const MAX = 12;
  const visible = orders ? orders.slice(0, MAX) : [];
  const extra = orders ? orders.length - MAX : 0;

  return (
    <div style={{
      position: 'absolute', right: 0, top: '50%', transform: 'translate(calc(100% + 12px), -50%)',
      zIndex: 100, width: 240,
      background: '#14141c', border: `1px solid ${color}40`,
      borderRadius: 10, boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      padding: '10px 0', pointerEvents: 'none',
    }}>
      {/* Flecha */}
      <div style={{
        position: 'absolute', left: -5, top: '50%', transform: 'translateY(-50%)',
        width: 8, height: 8, background: '#14141c',
        border: `1px solid ${color}40`, borderRight: 'none', borderTop: 'none',
        transform: 'translateY(-50%) rotate(45deg)',
      }} />

      <p style={{ margin: '0 10px 8px', fontSize: '9px', fontWeight: 800, color, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
        {title}
      </p>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '12px 0', gap: 6, color: '#606075', fontSize: 11 }}>
          <Loader size={11} style={{ animation: 'spin 1s linear infinite' }} /> Cargando...
        </div>
      ) : (
        <>
          {visible.map((o, i) => (
            <div key={o.id || i} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '5px 10px',
              borderTop: i > 0 ? '1px solid rgba(255,255,255,0.04)' : 'none',
            }}>
              <span style={{ fontSize: 10, fontWeight: 800, color: '#fff', fontFamily: 'monospace', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {o.pi_number}
              </span>
              {o.is_spare_part && (
                <span style={{ fontSize: 8, fontWeight: 800, padding: '1px 4px', borderRadius: 3, background: 'rgba(251,146,60,0.15)', color: '#fb923c', flexShrink: 0 }}>SP</span>
              )}
              {o.cycle && (
                <span style={{ fontSize: 9, color: '#606075', flexShrink: 0, marginLeft: 'auto' }}>C{o.cycle}</span>
              )}
              {o.qty_motos != null && (
                <span style={{ fontSize: 9, color: '#9ca3af', flexShrink: 0, marginLeft: 'auto' }}>{o.qty_motos} u.</span>
              )}
            </div>
          ))}
          {extra > 0 && (
            <p style={{ margin: '6px 10px 0', fontSize: 9, color: '#606075', fontStyle: 'italic' }}>y {extra} más...</p>
          )}
        </>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hook: lazy fetch con cache por clave
// ---------------------------------------------------------------------------
function useOrdersCache() {
  const cache = useRef({});

  const fetch = useCallback(async (key, params) => {
    if (cache.current[key]) return cache.current[key];
    const qs = new URLSearchParams({ ...params, limit: 50 }).toString();
    const res = await authFetch(`${API()}/imports/shipment-orders?${qs}`);
    const json = await res.json();
    const orders = Array.isArray(json) ? json : (json.items || []);
    cache.current[key] = orders;
    return orders;
  }, []);

  const clear = useCallback(() => { cache.current = {}; }, []);

  return { fetch, clear };
}

// ---------------------------------------------------------------------------
// Status Pipeline — barra horizontal de estados con hover popover
// ---------------------------------------------------------------------------
const STATUS_PIPELINE = [
  { key: 'en_preparacion', label: 'En Preparación', color: '#60a5fa', noPopover: true },
  { key: 'listo_fabrica',  label: 'Listo Fábrica',  color: '#a78bfa' },
  { key: 'en_transito',    label: 'En Tránsito',    color: '#fb923c' },
  { key: 'en_destino',     label: 'En Destino',     color: '#fbbf24' },
  { key: 'completado',     label: 'Completado',     color: '#22c55e' },
  { key: 'backorder',      label: 'Backorder',      color: '#f87171' },
];

function StatusPipeline({ data, ordersCache }) {
  const [hovered, setHovered] = useState(null);
  const [orders, setOrders] = useState({});
  const [loading, setLoading] = useState({});
  const hideTimer = useRef(null);

  const total = STATUS_PIPELINE.reduce((s, st) => s + (data[st.key] || 0), 0) || 1;

  const handleEnter = async (st) => {
    if (st.noPopover) return;
    clearTimeout(hideTimer.current);
    setHovered(st.key);
    if (!orders[st.key]) {
      setLoading(l => ({ ...l, [st.key]: true }));
      try {
        const result = await ordersCache.fetch(`status_${st.key}`, { computed_status: st.key });
        setOrders(o => ({ ...o, [st.key]: result }));
      } finally {
        setLoading(l => ({ ...l, [st.key]: false }));
      }
    }
  };

  const handleLeave = () => {
    hideTimer.current = setTimeout(() => setHovered(null), 200);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {STATUS_PIPELINE.map(st => {
        const count = data[st.key] || 0;
        const pct = Math.round((count / total) * 100);
        const isHovered = hovered === st.key;
        return (
          <div
            key={st.key}
            style={{ display: 'flex', alignItems: 'center', gap: '10px', position: 'relative', cursor: st.noPopover || count === 0 ? 'default' : 'pointer' }}
            onMouseEnter={() => handleEnter(st)}
            onMouseLeave={handleLeave}
          >
            <span style={{ fontSize: '10px', color: isHovered ? st.color : '#9ca3af', width: 110, flexShrink: 0, textAlign: 'right', transition: 'color 0.15s' }}>{st.label}</span>
            <div style={{ flex: 1, height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${pct}%`, background: st.color, borderRadius: 4, transition: 'width 0.6s ease', minWidth: count > 0 ? 4 : 0, opacity: isHovered ? 1 : 0.75 }} />
            </div>
            <span style={{ fontSize: '11px', fontWeight: 700, color: st.color, width: 28, textAlign: 'right', flexShrink: 0 }}>{count}</span>

            {isHovered && !st.noPopover && count > 0 && (
              <OrdersPopover
                orders={orders[st.key]}
                loading={loading[st.key]}
                title={st.label}
                color={st.color}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ciclos bar chart con hover popover
// ---------------------------------------------------------------------------
function CycleChart({ cycles, ordersCache }) {
  const [hovered, setHovered] = useState(null);
  const [orders, setOrders] = useState({});
  const [loading, setLoading] = useState({});
  const hideTimer = useRef(null);

  if (!cycles || cycles.length === 0) {
    return <p style={{ color: '#606075', fontSize: '11px', textAlign: 'center', margin: '20px 0' }}>Sin datos de ciclos</p>;
  }
  const max = Math.max(...cycles.map(c => c.count)) || 1;

  const handleEnter = async (cycle) => {
    clearTimeout(hideTimer.current);
    setHovered(cycle);
    if (!orders[cycle]) {
      setLoading(l => ({ ...l, [cycle]: true }));
      try {
        const result = await ordersCache.fetch(`cycle_${cycle}`, { cycle });
        setOrders(o => ({ ...o, [cycle]: result }));
      } finally {
        setLoading(l => ({ ...l, [cycle]: false }));
      }
    }
  };

  const handleLeave = () => {
    hideTimer.current = setTimeout(() => setHovered(null), 200);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {cycles.map(({ cycle, count }) => {
        const isHovered = hovered === cycle;
        return (
          <div
            key={cycle}
            style={{ display: 'flex', alignItems: 'center', gap: '10px', position: 'relative', cursor: 'pointer' }}
            onMouseEnter={() => handleEnter(cycle)}
            onMouseLeave={handleLeave}
          >
            <span style={{ fontSize: '10px', color: isHovered ? '#ff5f33' : '#9ca3af', width: 56, flexShrink: 0, textAlign: 'right', fontFamily: 'monospace', transition: 'color 0.15s' }}>Ciclo {cycle}</span>
            <div style={{ flex: 1, height: 10, borderRadius: 5, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${(count / max) * 100}%`, background: 'linear-gradient(90deg, #ff5f33, #ff8a65)', borderRadius: 5, transition: 'width 0.6s ease', opacity: isHovered ? 1 : 0.75 }} />
            </div>
            <span style={{ fontSize: '11px', fontWeight: 700, color: '#d1d5db', width: 24, textAlign: 'right', flexShrink: 0 }}>{count}</span>

            {isHovered && (
              <OrdersPopover
                orders={orders[cycle]}
                loading={loading[cycle]}
                title={`Ciclo ${cycle}`}
                color="#ff5f33"
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Upcoming ETAs list
// ---------------------------------------------------------------------------
function UpcomingEtas({ etas }) {
  if (!etas || etas.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '24px 0', color: '#606075' }}>
        <Ship size={28} style={{ margin: '0 auto 8px', display: 'block', opacity: 0.3 }} />
        <p style={{ margin: 0, fontSize: '11px' }}>No hay pedidos con ETA en los próximos 60 días</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {etas.map(o => {
        const days = daysUntil(o.eta);
        const urgency = days <= 7 ? '#f87171' : days <= 14 ? '#fb923c' : days <= 30 ? '#fbbf24' : '#22c55e';

        return (
          <div key={o.id} style={{
            display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 12px',
            borderRadius: '8px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)',
          }}>
            <div style={{ textAlign: 'center', minWidth: 44, flexShrink: 0 }}>
              <p style={{ margin: 0, fontSize: '15px', fontWeight: 800, color: urgency, lineHeight: 1 }}>{days}</p>
              <p style={{ margin: 0, fontSize: '8px', color: urgency, fontWeight: 700 }}>días</p>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: o.is_spare_part ? '#60a5fa' : '#fff', fontFamily: 'monospace' }}>{o.pi_number}</span>
                {o.is_spare_part && (
                  <span style={{ fontSize: '8px', fontWeight: 800, padding: '1px 5px', borderRadius: '4px', background: 'rgba(251,146,60,0.15)', color: '#fb923c' }}>SP</span>
                )}
                {o.cycle && <span style={{ fontSize: '9px', color: '#606075' }}>· Ciclo {o.cycle}</span>}
              </div>
              <p style={{ margin: '1px 0 0', fontSize: '10px', color: '#9ca3af', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.model}</p>
            </div>
            <div style={{ flexShrink: 0, textAlign: 'right' }}>
              <p style={{ margin: 0, fontSize: '11px', fontWeight: 700, color: '#d1d5db' }}>{o.qty || '—'}</p>
              <p style={{ margin: 0, fontSize: '9px', color: '#606075' }}>{o.eta_raw || o.eta?.split('T')[0]}</p>
            </div>
            <div style={{ width: 4, height: 36, borderRadius: 2, background: urgency, flexShrink: 0 }} />
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main DashboardTab
// ---------------------------------------------------------------------------
export default function DashboardTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const ordersCache = useOrdersCache();

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    ordersCache.clear();
    try {
      const res = await authFetch(`${API()}/imports/dashboard`);
      const json = await res.json();
      setData(json);
      setLastUpdated(new Date().toLocaleTimeString('es-CO'));
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [ordersCache]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  if (loading) {
    return <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '60px 0' }}>Cargando dashboard...</p>;
  }

  if (!data) {
    return <p style={{ color: '#f87171', fontSize: '12px', textAlign: 'center', margin: '60px 0' }}>Error cargando datos del dashboard</p>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* Header refresh */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '10px' }}>
        {lastUpdated && <span style={{ fontSize: '10px', color: '#606075' }}>Actualizado: {lastUpdated}</span>}
        <button onClick={fetchDashboard} style={{ padding: '6px 8px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer', color: '#9ca3af' }}>
          <RefreshCw size={12} />
        </button>
      </div>

      {/* Row 1: KPIs principales */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr) repeat(2, 1fr)', gap: '10px' }}>
        <KPICard label="Pedidos activos" value={data.total_active} color="#ff5f33" accent />
        <KPICard label="Motos / Repuestos" value={`${data.moto_orders} / ${data.sp_orders}`} color="#9ca3af" />
        <KPICard label="Backorders activos" value={data.active_backorders} sub={`${data.total_backorder_units} uds. pendientes`} color={data.active_backorders > 0 ? '#f87171' : '#22c55e'} accent={data.active_backorders > 0} />
        <KPICard
          label="Valor declarado total"
          value={data.total_declared_value_usd > 0 ? `$${data.total_declared_value_usd.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` : '—'}
          sub="USD — lotes de repuestos"
          color="#a78bfa"
        />
      </div>

      {/* Row 2: Pipeline + Ciclos — con overflow visible para los popovers */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>

        <div style={{ padding: '18px', borderRadius: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', overflow: 'visible' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <TrendingUp size={14} color="#ff5f33" />
            <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 700, color: '#fff', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Pipeline de pedidos</h3>
            <span style={{ marginLeft: 'auto', fontSize: '9px', color: '#404050' }}>hover para ver detalle</span>
          </div>
          <StatusPipeline data={data} ordersCache={ordersCache} />
        </div>

        <div style={{ padding: '18px', borderRadius: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', overflow: 'visible' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <Package size={14} color="#ff5f33" />
            <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 700, color: '#fff', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Pedidos por ciclo</h3>
            <span style={{ marginLeft: 'auto', fontSize: '9px', color: '#404050' }}>hover para ver detalle</span>
          </div>
          <CycleChart cycles={data.by_cycle} ordersCache={ordersCache} />
        </div>
      </div>

      {/* Row 3: Documentación pendiente */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
        <div style={{ padding: '14px 16px', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <FileText size={20} color="#60a5fa" style={{ flexShrink: 0 }} />
          <div>
            <p style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: data.pending_docs_digital > 0 ? '#60a5fa' : '#22c55e' }}>{data.pending_docs_digital}</p>
            <p style={{ margin: '2px 0 0', fontSize: '10px', color: '#606075', fontWeight: 600 }}>Docs digitales pendientes</p>
          </div>
        </div>
        <div style={{ padding: '14px 16px', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <FileText size={20} color="#a78bfa" style={{ flexShrink: 0 }} />
          <div>
            <p style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: data.pending_docs_original > 0 ? '#a78bfa' : '#22c55e' }}>{data.pending_docs_original}</p>
            <p style={{ margin: '2px 0 0', fontSize: '10px', color: '#606075', fontWeight: 600 }}>Docs originales pendientes</p>
          </div>
        </div>
      </div>

      {/* Row 4: Próximas ETAs */}
      <div style={{ padding: '18px', borderRadius: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
          <Ship size={14} color="#ff5f33" />
          <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 700, color: '#fff', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Próximas llegadas — 60 días</h3>
          <span style={{ marginLeft: 'auto', fontSize: '10px', color: '#606075' }}>
            {data.upcoming_etas?.length || 0} pedido{data.upcoming_etas?.length !== 1 ? 's' : ''}
          </span>
        </div>
        <UpcomingEtas etas={data.upcoming_etas} />
      </div>

    </div>
  );
}
