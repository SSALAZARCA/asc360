'use client';
import { useState, useEffect, useRef } from 'react';
import {
  Clock, AlertTriangle, CheckCircle2, Activity, Zap, Timer,
  ShieldAlert, TrendingUp, MapPin, BarChart3, Gauge,
  ArrowUpRight, ArrowDownRight, RefreshCw, Filter,
  ClipboardList, CalendarDays, Wrench, Hourglass, CircleHelp, Factory, Handshake
} from 'lucide-react';
import { authFetch } from '../lib/authFetch';

// ─── Utilidades ────────────────────────────────────────────────────────────
const API = () => process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

const STATES = [
  { id: 'received',       name: 'Recibido',        color: '#3b82f6', icon: ClipboardList },
  { id: 'scheduled',      name: 'Agendado',         color: '#8b5cf6', icon: CalendarDays },
  { id: 'in_progress',    name: 'En Proceso',       color: '#f59e0b', icon: Wrench },
  { id: 'on_hold_parts',  name: 'Espera Repuestos', color: '#ef4444', icon: Hourglass },
  { id: 'on_hold_client', name: 'Espera Cliente',   color: '#f97316', icon: CircleHelp },
  { id: 'external_work',  name: 'Trabajo Externo',  color: '#06b6d4', icon: Factory },
  { id: 'rescheduled',    name: 'Reagendado',       color: '#6366f1', icon: RefreshCw },
  { id: 'completed',      name: 'Finalizado',       color: '#10b981', icon: CheckCircle2 },
  { id: 'delivered',      name: 'Entregado',        color: '#22c55e', icon: Handshake },
];

const TYPE_CFG = {
  warranty:  { label: 'Garantía',     color: '#eab308', bg: 'rgba(234,179,8,0.15)'  },
  km_review: { label: 'Rev. KM',      color: '#22c55e', bg: 'rgba(34,197,94,0.15)'  },
  regular:   { label: 'Mecánica',     color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
  pdi:       { label: 'Alistamiento', color: '#f97316', bg: 'rgba(249,115,22,0.15)' },
};

// ─── Contador animado ──────────────────────────────────────────────────────
function AnimatedNumber({ value, decimals = 0, suffix = '' }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(null);

  useEffect(() => {
    if (value == null) return;
    const start = 0;
    const end   = Number(value);
    const duration = 1200;
    const startTime = performance.now();

    const tick = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setDisplay(start + (end - start) * ease);
      if (progress < 1) ref.current = requestAnimationFrame(tick);
    };
    ref.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(ref.current);
  }, [value]);

  return <span>{display.toFixed(decimals)}{suffix}</span>;
}

// ─── Donut SVG semáforo ────────────────────────────────────────────────────
function DonutChart({ green, yellow, red }) {
  const realTotal = (green || 0) + (yellow || 0) + (red || 0);
  const total  = realTotal || 1; // Para evitar división por cero en las barras de progreso/segmentos
  const r = 54;
  const circ  = 2 * Math.PI * r;
  const gPct  = (green  || 0) / total;
  const yPct  = (yellow || 0) / total;
  const rPct  = (red    || 0) / total;

  const gLen = circ * gPct;
  const yLen = circ * yPct;
  const rLen = circ * rPct;
  const gap  = 4;

  const segments = [
    { len: gLen, color: '#10b981', offset: 0,              label: 'Óptimo',  val: green  || 0 },
    { len: yLen, color: '#fbbf24', offset: gLen + gap,     label: 'Alerta',  val: yellow || 0 },
    { len: rLen, color: '#ef4444', offset: gLen + yLen + gap * 2, label: 'Crítico', val: red    || 0 },
  ];

  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 140 140" width="140" height="140">
        {/* Track */}
        <circle cx="70" cy="70" r={r} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="18" />
        {/* Segments */}
        {segments.map((s, i) => (
          <circle
            key={i}
            cx="70" cy="70" r={r}
            fill="none"
            stroke={s.color}
            strokeWidth="18"
            strokeDasharray={`${Math.max(s.len - gap, 0)} ${circ}`}
            strokeDashoffset={-(s.offset)}
            transform="rotate(-90 70 70)"
            style={{ filter: `drop-shadow(0 0 6px ${s.color}60)`, transition: 'all 0.8s ease' }}
          />
        ))}
        {/* Center */}
        <text x="70" y="65" textAnchor="middle" fill="white" fontSize="22" fontWeight="900">{realTotal}</text>
        <text x="70" y="81" textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="8" fontWeight="700">MOTOS</text>
      </svg>
      {/* Leyenda */}
      <div className="donut-legend">
        {segments.map((s, i) => (
          <div key={i} className="donut-legend-item">
            <span className="donut-dot" style={{ background: s.color, boxShadow: `0 0 6px ${s.color}` }} />
            <span className="donut-lbl">{s.label}</span>
            <span className="donut-val" style={{ color: s.color }}>{s.val}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Barra de progreso animada ─────────────────────────────────────────────
function AnimBar({ value, max, color, label, count }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="animbar">
      <div className="animbar-head">
        <span className="animbar-label">{label}</span>
        <span className="animbar-count" style={{ color }}>{count}</span>
      </div>
      <div className="animbar-track">
        <div
          className="animbar-fill"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}90, ${color})`,
            boxShadow: `0 0 10px ${color}40`,
          }}
        />
      </div>
    </div>
  );
}

// ─── Tarjeta KPI hero ──────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon: Icon, color, decimals = 0, suffix = '', alert = false }) {
  return (
    <div className="kpi-card" style={{ borderLeft: `3px solid ${color}`, background: alert ? `${color}08` : undefined }}>
      <div className="kpi-card-top">
        <p className="kpi-label" style={{ color: alert ? color : undefined }}>{label}</p>
        <div className="kpi-icon" style={{ color, background: `${color}15` }}>
          <Icon size={14} />
        </div>
      </div>
      <h2 className="kpi-value" style={{ color: alert ? color : 'white' }}>
        <AnimatedNumber value={value} decimals={decimals} suffix={suffix} />
      </h2>
      {sub && <p className="kpi-sub">{sub}</p>}
    </div>
  );
}

// ─── Tabla maestra de servicios ────────────────────────────────────────────
function ServicesTable({ services, loading }) {
  const [filter, setFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortCol, setSortCol] = useState('tiempo_taller_dias');
  const [sortDir, setSortDir] = useState('desc');

  const stateMap = Object.fromEntries(STATES.map(s => [s.id, s]));

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  const filtered = (services || [])
    .filter(s => {
      const q = filter.toLowerCase();
      return (
        s.placa?.toLowerCase().includes(q) ||
        s.centro_actual?.toLowerCase().includes(q) ||
        s.ciudad?.toLowerCase().includes(q)
      );
    })
    .filter(s => typeFilter === 'all' || s.tipo_trabajo === typeFilter)
    .sort((a, b) => {
      const va = a[sortCol] ?? 0;
      const vb = b[sortCol] ?? 0;
      const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return sortDir === 'asc' ? cmp : -cmp;
    });

  const SortIcon = ({ col }) => sortCol === col
    ? (sortDir === 'asc' ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />)
    : null;

  const dayColor = d => d > 5 ? '#ef4444' : d > 2 ? '#fbbf24' : '#10b981';

  return (
    <div className="table-wrap">
      {/* Controles */}
      <div className="table-controls">
        <div className="table-search">
          <Filter size={11} style={{ color: 'rgba(255,255,255,0.3)' }} />
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Buscar placa, centro, ciudad..."
            className="table-input"
          />
        </div>
        <div className="type-filters">
          {[['all', 'Todos'], ...Object.entries(TYPE_CFG).map(([k, v]) => [k, v.label])].map(([k, lbl]) => (
            <button
              key={k}
              onClick={() => setTypeFilter(k)}
              className="type-btn"
              style={{
                background:   typeFilter === k ? (TYPE_CFG[k]?.bg ?? 'rgba(255,255,255,0.1)') : 'transparent',
                color:        typeFilter === k ? (TYPE_CFG[k]?.color ?? 'white') : 'rgba(255,255,255,0.35)',
                borderColor:  typeFilter === k ? (TYPE_CFG[k]?.color ?? 'rgba(255,255,255,0.15)') : 'rgba(255,255,255,0.06)',
              }}
            >{lbl}</button>
          ))}
        </div>
        <span className="table-count">{filtered.length} registros</span>
      </div>

      {/* Tabla */}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {[
                ['placa',             'Placa'],
                ['tipo_trabajo',      'Tipo'],
                ['estado',            'Estado'],
                ['tiempo_taller_dias','Días'],
                ['kilometraje',       'KM'],
                ['centro_actual',     'Centro'],
                ['ciudad',            'Ciudad'],
                ['v_totales',         'Visitas'],
                ['g_totales',         'Garantías'],
              ].map(([col, lbl]) => (
                <th key={col} onClick={() => toggleSort(col)} className="th-sortable">
                  {lbl} <SortIcon col={col} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} style={{ textAlign:'center', padding:'2rem', color:'rgba(255,255,255,0.2)', fontSize:'0.7rem' }}>Cargando...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={9} style={{ textAlign:'center', padding:'2rem', color:'rgba(255,255,255,0.2)', fontSize:'0.7rem' }}>Sin resultados</td></tr>
            ) : filtered.map((s, i) => {
              const st  = stateMap[s.estado];
              const tc  = TYPE_CFG[s.tipo_trabajo] || TYPE_CFG.regular;
              const dc  = dayColor(s.tiempo_taller_dias ?? 0);
              return (
                <tr key={s.order_id} className="tr-row" style={{ animationDelay: `${i * 0.02}s` }}>
                  <td className="td-plate">{s.placa}</td>
                  <td><span className="td-type" style={{ color: tc.color, background: tc.bg }}>{tc.label}</span></td>
                  <td>
                    <span className="td-state" style={{ color: st?.color ?? 'white', background: `${st?.color ?? '#777'}18` }}>
                      {st?.emoji} {st?.name ?? s.estado}
                    </span>
                  </td>
                  <td>
                    <span style={{ color: dc, fontWeight: 900, fontSize: '0.78rem' }}>
                      {s.tiempo_taller_dias ?? 0}d
                    </span>
                  </td>
                  <td className="td-dim">{(s.kilometraje || 0).toLocaleString()} km</td>
                  <td className="td-dim">{s.centro_actual}</td>
                  <td className="td-dim">{s.ciudad || '—'}</td>
                  <td className="td-dim">{s.v_totales ?? '—'}</td>
                  <td className="td-dim">{s.g_totales ?? '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Componente principal ──────────────────────────────────────────────────
export default function KPISummary() {
  const [kpis,     setKpis]     = useState(null);
  const [services, setServices] = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [loadSvc,  setLoadSvc]  = useState(true);
  const [lastSync, setLastSync] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = async () => {
    setRefreshing(true);
    try {
      const [kRes, sRes] = await Promise.all([
        authFetch('/orders/analytics/kpis'),
        authFetch('/orders/analytics/services'),
      ]);
      if (kRes.ok) setKpis(await kRes.json());
      if (sRes.ok) setServices(await sRes.json());
      setLastSync(new Date());
    } catch (e) {
      console.error('Error cargando KPIs:', e);
    } finally {
      setLoading(false);
      setLoadSvc(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  // Auto-refresh cada 60s
  useEffect(() => {
    const t = setInterval(fetchAll, 60000);
    return () => clearInterval(t);
  }, []);

  if (loading) return (
    <div className="kpi-loading">
      <div className="kpi-spinner" />
      <p>Sincronizando inteligencia operativa...</p>
    </div>
  );

  if (!kpis) return (
    <div className="kpi-error">
      <ShieldAlert size={36} />
      <p>No se pudo conectar con el servidor</p>
    </div>
  );

  const totalActive = Object.values(kpis.count_by_status || {}).reduce((a, b) => a + b, 0);
  const cycleDays   = kpis.avg_total_time_minutes
    ? (kpis.avg_total_time_minutes / 60 / 24).toFixed(1)
    : 0;
  const criticalPct = totalActive > 0
    ? Math.round(((kpis.semaphore?.red || 0) / totalActive) * 100)
    : 0;

  // Máximo para barras proporcionales
  const maxCount = Math.max(...STATES.map(s => kpis.count_by_status?.[s.id] || 0), 1);

  // Calcular ranking de centros por volumen de motos
  const centerRanking = Object.entries(
    (services || []).reduce((acc, s) => {
      const c = s.centro_actual || 'Desconocido';
      acc[c] = (acc[c] || 0) + 1;
      return acc;
    }, {})
  )
    .sort((a, b) => b[1] - a[1]) // Mayor a menor
    .map(([name, count]) => ({ name, count }));

  const maxCenterCount = centerRanking.length > 0 ? centerRanking[0].count : 1;

  return (
    <div className="kpi-root">

      {/* ── Sync bar ── */}
      <div className="sync-bar">
        <span className="sync-dot" />
        <span className="sync-txt">
          {lastSync ? `Última sync: ${lastSync.toLocaleTimeString('es-CO')}` : 'Conectando...'}
        </span>
        <button className="sync-btn" onClick={fetchAll} disabled={refreshing}>
          <RefreshCw size={11} style={{ animation: refreshing ? 'spin 0.8s linear infinite' : 'none' }} />
          Actualizar
        </button>
      </div>

      {/* ── Fila 1: KPIs Hero ── */}
      <div className="kpi-grid">
        <KpiCard
          label="Motos Activas en Red"
          value={totalActive}
          sub="en todos los centros"
          icon={Activity}
          color="#3b82f6"
        />
        <KpiCard
          label="Ciclo Promedio"
          value={cycleDays}
          decimals={1}
          suffix=" días"
          sub="ingreso → entrega"
          icon={Timer}
          color="#8b5cf6"
        />
        <KpiCard
          label="Permanencia Crítica"
          value={kpis.semaphore?.red || 0}
          sub={`${criticalPct}% del total — más de 5 días`}
          icon={AlertTriangle}
          color="#ef4444"
          alert={(kpis.semaphore?.red || 0) > 0}
        />
        <KpiCard
          label="Estado Óptimo"
          value={kpis.semaphore?.green || 0}
          sub="dentro del rango (≤ 2 días)"
          icon={CheckCircle2}
          color="#10b981"
        />
      </div>

      {/* ── Fila 2: Semáforo + Distribución + Tiempos por Estado ── */}
      <div className="section-grid-3">

        {/* Semáforo donut */}
        <div className="glass-panel">
          <div className="panel-header">
            <Gauge size={14} className="panel-icon" />
            <h3>Semáforo de Permanencia</h3>
          </div>
          <div className="semaphore-body">
            <DonutChart
              green={kpis.semaphore?.green}
              yellow={kpis.semaphore?.yellow}
              red={kpis.semaphore?.red}
            />
            <div className="semaphore-rules">
              {[
                { color: '#10b981', label: 'Óptimo',  rule: '≤ 2 días en taller',   val: kpis.semaphore?.green  || 0 },
                { color: '#fbbf24', label: 'Alerta',  rule: '3 a 5 días en taller',  val: kpis.semaphore?.yellow || 0 },
                { color: '#ef4444', label: 'Crítico', rule: 'Más de 5 días — actuar', val: kpis.semaphore?.red    || 0 },
              ].map((s, i) => (
                <div key={i} className="sem-rule">
                  <div className="sem-rule-head">
                    <span className="sem-rule-dot" style={{ background: s.color }} />
                    <span className="sem-rule-label">{s.label}</span>
                    <span className="sem-rule-val" style={{ color: s.color }}>{s.val}</span>
                  </div>
                  <p className="sem-rule-desc">{s.rule}</p>
                  <div className="sem-rule-bar">
                    <div style={{
                      width: `${totalActive > 0 ? (s.val / totalActive) * 100 : 0}%`,
                      height: '100%',
                      background: s.color,
                      borderRadius: 4,
                      boxShadow: `0 0 8px ${s.color}50`,
                      transition: 'width 1s ease',
                    }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Distribución por estado */}
        <div className="glass-panel">
          <div className="panel-header">
            <BarChart3 size={14} className="panel-icon" />
            <h3>Distribución por Estado</h3>
            <span className="panel-badge">{totalActive} motos</span>
          </div>
          <div className="states-list">
            {STATES.map(st => {
              const cnt = kpis.count_by_status?.[st.id] || 0;
              const IconComp = st.icon;
              return (
                <AnimBar
                  key={st.id}
                  label={
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <IconComp size={12} style={{ color: st.color }} />
                      <span>{st.name}</span>
                    </div>
                  }
                  value={cnt}
                  max={maxCount}
                  color={st.color}
                  count={cnt}
                />
              );
            })}
          </div>
        </div>

        {/* Tiempo promedio por estado */}
        <div className="glass-panel">
          <div className="panel-header">
            <Clock size={14} className="panel-icon" />
            <h3>Tiempo Promedio por Estado</h3>
          </div>
          <div className="times-list">
            {STATES.map(st => {
              const mins = kpis.avg_time_by_status?.[st.id];
              const IconComp = st.icon;
              if (mins === undefined || mins === null) {
                return (
                  <div key={st.id} className="time-row">
                    <span className="time-emoji"><IconComp size={14} style={{ opacity: 0.5 }} /></span>
                    <span className="time-name">{st.name}</span>
                    <div className="time-val-wrap">
                      <span className="time-val" style={{ color: 'rgba(255,255,255,0.15)', fontSize: '0.7rem' }}>Sin datos</span>
                    </div>
                  </div>
                );
              }
              const hours = (mins / 60).toFixed(1);
              const days  = (mins / 60 / 24).toFixed(1);
              return (
                <div key={st.id} className="time-row">
                  <span className="time-emoji"><IconComp size={14} style={{ color: st.color }} /></span>
                  <span className="time-name">{st.name}</span>
                  <div className="time-val-wrap">
                    <span className="time-val" style={{ color: st.color }}>
                      {mins < 60 ? `${Math.round(mins)}min` : mins < 1440 ? `${hours}h` : `${days}d`}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Fila 3: Ranking por Volumen + Garantías por centro ── */}
      <div className="section-grid-2">

        {/* Ranking por Volumen */}
        <div className="glass-panel">
          <div className="panel-header">
            <TrendingUp size={14} className="panel-icon" />
            <h3>Ranking por Volumen</h3>
            <span className="panel-badge">{centerRanking.length} centros</span>
          </div>
          <div className="ranking-list">
            {centerRanking.slice(0, 8).map((c, i) => (
              <div key={i} className="ranking-row">
                <span className="ranking-pos">#{i + 1}</span>
                <div className="ranking-info">
                  <span className="ranking-name">{c.name}</span>
                  <div className="animbar-track">
                    <div
                      className="animbar-fill"
                      style={{
                        width: `${(c.count / maxCenterCount) * 100}%`,
                        background: 'linear-gradient(90deg, rgba(59,130,246,0.3), #3b82f6)',
                        boxShadow: '0 0 10px rgba(59,130,246,0.4)',
                        height: '100%',
                      }}
                    />
                  </div>
                </div>
                <span className="ranking-val">{c.count}</span>
              </div>
            ))}
            {centerRanking.length === 0 && (
              <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', textAlign: 'center', padding: '1rem' }}>
                Sin actividad
              </p>
            )}
          </div>
        </div>

        {/* Top centros por garantías */}
        <div className="glass-panel">
          <div className="panel-header">
            <ShieldAlert size={14} className="panel-icon" style={{ color: '#eab308' }} />
            <h3>Top Centros — Tiempo en Garantía</h3>
          </div>
          <div className="warranty-list">
            {(kpis.warranty_management || []).length === 0 ? (
              <p style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', textAlign: 'center', padding: '1rem' }}>
                Sin garantías activas registradas
              </p>
            ) : kpis.warranty_management.slice(0, 6).map((w, i) => {
              const days = (w.avg_minutes / 60 / 24).toFixed(1);
              const isHigh = w.avg_minutes > 60 * 24 * 5;
              return (
                <div key={i} className="warranty-row">
                  <span className="warranty-rank" style={{ color: i === 0 ? '#eab308' : 'rgba(255,255,255,0.25)' }}>
                    #{i + 1}
                  </span>
                  <div className="warranty-info">
                    <span className="warranty-name">{w.tenant_name}</span>
                    <div className="warranty-bar-track">
                      <div className="warranty-bar-fill" style={{
                        width: `${Math.min((w.avg_minutes / (kpis.warranty_management[0]?.avg_minutes || 1)) * 100, 100)}%`,
                        background: isHigh ? 'linear-gradient(90deg, #eab308, #ef4444)' : 'linear-gradient(90deg, #eab308, #f97316)',
                      }} />
                    </div>
                  </div>
                  <span className="warranty-days" style={{ color: isHigh ? '#ef4444' : '#eab308' }}>
                    {days}d
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Fila 4: Tabla maestra de órdenes activas ── */}
      <div className="glass-panel">
        <div className="panel-header">
          <TrendingUp size={14} className="panel-icon" />
          <h3>Maestro de Órdenes Activas</h3>
          <span className="panel-badge">{(services || []).length} registros</span>
        </div>
        <ServicesTable services={services} loading={loadSvc} />
      </div>

      <style jsx global>{`
        /* ── Root ── */
        .kpi-root { display:flex; flex-direction:column; gap:1.25rem; padding-bottom:2rem; }

        /* ── Sync bar ── */
        .sync-bar { display:flex; align-items:center; gap:0.6rem; }
        .sync-dot { width:6px; height:6px; border-radius:50%; background:#10b981; box-shadow:0 0 8px #10b981; animation:pulse 2s ease infinite; flex-shrink:0; }
        @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.4;} }
        .sync-txt { font-size:0.6rem; font-weight:700; color:rgba(255,255,255,0.3); text-transform:uppercase; letter-spacing:0.08em; flex:1; }
        .sync-btn { display:flex; align-items:center; gap:0.3rem; font-size:0.6rem; font-weight:800; color:rgba(255,255,255,0.35); background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:4px 10px; cursor:pointer; text-transform:uppercase; letter-spacing:0.06em; transition:all 0.15s; }
        .sync-btn:hover { color:white; border-color:rgba(255,255,255,0.12); }

        /* ── KPI grid ── */
        .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:0.85rem; }
        @media(max-width:1200px){ .kpi-grid{ grid-template-columns:repeat(2,1fr);} }
        @media(max-width:640px){  .kpi-grid{ grid-template-columns:1fr;} }

        .kpi-card { padding:1.25rem 1.4rem; border-radius:14px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); transition:transform 0.15s, box-shadow 0.15s; }
        .kpi-card:hover { transform:translateY(-3px); box-shadow:0 12px 32px rgba(0,0,0,0.3); }
        .kpi-card-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:0.6rem; }
        .kpi-label { font-size:0.6rem; font-weight:800; text-transform:uppercase; letter-spacing:0.1em; color:rgba(255,255,255,0.4); }
        .kpi-icon  { width:28px; height:28px; border-radius:8px; display:flex; align-items:center; justify-content:center; }
        .kpi-value { font-size:2.4rem; font-weight:900; color:white; line-height:1; margin:0.25rem 0; }
        .kpi-sub   { font-size:0.58rem; color:rgba(255,255,255,0.25); font-weight:600; }

        /* ── Sección 2 columnas ── */
        .section-grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:0.85rem; }
        @media(max-width:1000px){ .section-grid-2{ grid-template-columns:1fr;} }

        /* ── Sección 3 columnas (Ranking Fila 2) ── */
        .section-grid-3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.85rem; }
        @media(max-width:1200px){ .section-grid-3{ grid-template-columns:1fr 1fr;} }
        @media(max-width:800px){  .section-grid-3{ grid-template-columns:1fr;} }

        /* ── Ranking ── */
        .ranking-list { display:flex; flex-direction:column; gap:0.6rem; }
        .ranking-row { display:flex; align-items:center; gap:0.5rem; }
        .ranking-pos { font-size:0.65rem; font-weight:900; width:18px; text-align:center; color:rgba(255,255,255,0.25); }
        .ranking-info { flex:1; display:flex; flex-direction:column; gap:4px; min-width:0; }
        .ranking-name { font-size:0.62rem; font-weight:700; color:rgba(255,255,255,0.6); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .ranking-val { font-size:0.85rem; font-weight:900; color:white; width:28px; text-align:right; }

        /* ── Panel glass ── */
        .glass-panel { background:rgba(255,255,255,0.025); border:1px solid rgba(255,255,255,0.06); border-radius:16px; padding:1.25rem; }
        .panel-header { display:flex; align-items:center; gap:0.5rem; margin-bottom:1rem; border-bottom:1px solid rgba(255,255,255,0.04); padding-bottom:0.75rem; }
        .panel-header h3 { font-size:0.65rem; font-weight:900; text-transform:uppercase; letter-spacing:0.1em; color:rgba(255,255,255,0.6); flex:1; }
        .panel-icon { color:rgba(255,255,255,0.3); flex-shrink:0; }
        .panel-badge { font-size:0.58rem; font-weight:800; color:rgba(255,255,255,0.3); background:rgba(255,255,255,0.05); border-radius:6px; padding:2px 8px; }

        /* ── Donut ── */
        .donut-wrap { display:flex; align-items:center; gap:1.5rem; }
        .donut-legend { display:flex; flex-direction:column; gap:0.7rem; flex:1; }
        .donut-legend-item { display:flex; align-items:center; gap:0.5rem; }
        .donut-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
        .donut-lbl { font-size:0.65rem; font-weight:700; color:rgba(255,255,255,0.5); flex:1; text-transform:uppercase; letter-spacing:0.07em; }
        .donut-val { font-size:0.9rem; font-weight:900; }

        /* ── Semáforo ── */
        .semaphore-body { display:flex; align-items:center; gap:1.5rem; }
        .semaphore-rules { display:flex; flex-direction:column; gap:0.75rem; flex:1; }
        .sem-rule { display:flex; flex-direction:column; gap:4px; }
        .sem-rule-head { display:flex; align-items:center; gap:0.4rem; }
        .sem-rule-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
        .sem-rule-label { font-size:0.65rem; font-weight:800; text-transform:uppercase; letter-spacing:0.07em; color:rgba(255,255,255,0.5); flex:1; }
        .sem-rule-val { font-size:0.9rem; font-weight:900; }
        .sem-rule-desc { font-size:0.58rem; color:rgba(255,255,255,0.25); padding-left:1.2rem; }
        .sem-rule-bar { height:4px; background:rgba(255,255,255,0.05); border-radius:4px; overflow:hidden; margin-left:1.2rem; }

        /* ── AnimBar ── */
        .animbar { display:flex; flex-direction:column; gap:4px; }
        .animbar-head { display:flex; align-items:center; justify-content:space-between; }
        .animbar-label { font-size:0.6rem; font-weight:700; color:rgba(255,255,255,0.45); }
        .animbar-count { font-size:0.65rem; font-weight:900; }
        .animbar-track { height:5px; background:rgba(255,255,255,0.05); border-radius:3px; overflow:hidden; }
        .animbar-fill { height:100%; border-radius:3px; transition:width 1s ease; }
        .states-list { display:flex; flex-direction:column; gap:0.55rem; }

        /* ── Tiempos ── */
        .times-list { display:flex; flex-direction:column; gap:0.5rem; }
        .time-row { display:flex; align-items:center; gap:0.5rem; padding:0.45rem 0.6rem; border-radius:8px; background:rgba(255,255,255,0.02); }
        .time-emoji { font-size:0.85rem; }
        .time-name { font-size:0.65rem; font-weight:700; color:rgba(255,255,255,0.5); flex:1; text-transform:uppercase; letter-spacing:0.07em; }
        .time-val { font-size:0.82rem; font-weight:900; }

        /* ── Garantías por centro ── */
        .warranty-list { display:flex; flex-direction:column; gap:0.6rem; }
        .warranty-row { display:flex; align-items:center; gap:0.6rem; }
        .warranty-rank { font-size:0.7rem; font-weight:900; width:20px; text-align:center; }
        .warranty-info { flex:1; display:flex; flex-direction:column; gap:3px; }
        .warranty-name { font-size:0.65rem; font-weight:700; color:rgba(255,255,255,0.6); }
        .warranty-bar-track { height:3px; background:rgba(255,255,255,0.05); border-radius:2px; overflow:hidden; }
        .warranty-bar-fill { height:100%; border-radius:2px; transition:width 1s ease; }
        .warranty-days { font-size:0.78rem; font-weight:900; width:32px; text-align:right; }

        /* ── Tabla ── */
        .table-wrap { display:flex; flex-direction:column; gap:0.75rem; }
        .table-controls { display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap; }
        .table-search { display:flex; align-items:center; gap:0.4rem; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:6px 10px; flex:1; min-width:180px; }
        .table-input { background:transparent; border:none; outline:none; font-size:0.68rem; color:rgba(255,255,255,0.8); width:100%; font-family:inherit; }
        .table-input::placeholder { color:rgba(255,255,255,0.2); }
        .type-filters { display:flex; gap:0.3rem; flex-wrap:wrap; }
        .type-btn { font-size:0.58rem; font-weight:800; padding:4px 10px; border-radius:7px; border:1px solid; cursor:pointer; text-transform:uppercase; letter-spacing:0.05em; transition:all 0.15s; }
        .table-count { font-size:0.58rem; font-weight:700; color:rgba(255,255,255,0.25); text-transform:uppercase; letter-spacing:0.08em; white-space:nowrap; }

        .table-scroll { overflow-x:auto; border-radius:10px; border:1px solid rgba(255,255,255,0.06); }
        .data-table { width:100%; border-collapse:collapse; }
        .th-sortable { padding:0.55rem 0.75rem; text-align:left; font-size:0.56rem; font-weight:900; text-transform:uppercase; letter-spacing:0.1em; color:rgba(255,255,255,0.3); background:rgba(255,255,255,0.025); cursor:pointer; white-space:nowrap; border-bottom:1px solid rgba(255,255,255,0.06); user-select:none; }
        .th-sortable:hover { color:rgba(255,255,255,0.6); }
        .tr-row { border-bottom:1px solid rgba(255,255,255,0.03); transition:background 0.12s; animation:rowIn 0.3s ease both; }
        .tr-row:hover { background:rgba(255,255,255,0.025); }
        @keyframes rowIn { from{opacity:0;transform:translateX(-6px);} to{opacity:1;transform:none;} }
        .tr-row td { padding:0.55rem 0.75rem; }
        .td-plate { font-size:0.8rem; font-weight:900; color:#ff8c5a; letter-spacing:0.04em; white-space:nowrap; }
        .td-type { font-size:0.56rem; font-weight:800; padding:2px 6px; border-radius:5px; white-space:nowrap; text-transform:uppercase; }
        .td-state { font-size:0.6rem; font-weight:700; padding:2px 7px; border-radius:6px; white-space:nowrap; }
        .td-dim { font-size:0.65rem; color:rgba(255,255,255,0.45); white-space:nowrap; }

        /* ── Spinner ── */
        .kpi-loading { display:flex; flex-direction:column; align-items:center; justify-content:center; padding:5rem; gap:1rem; color:rgba(255,255,255,0.35); font-size:0.7rem; text-transform:uppercase; letter-spacing:0.1em; }
        .kpi-spinner { width:32px; height:32px; border:3px solid rgba(255,95,51,0.15); border-top-color:#ff5f33; border-radius:50%; animation:spin 0.8s linear infinite; }
        @keyframes spin { to{transform:rotate(360deg);} }
        .kpi-error { display:flex; flex-direction:column; align-items:center; justify-content:center; padding:5rem; gap:1rem; color:#ef4444; font-size:0.7rem; text-transform:uppercase; }
      `}</style>
    </div>
  );
}
