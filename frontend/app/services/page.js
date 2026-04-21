'use client';
import { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import AdminLayout from '../admin-layout';
import {
  Search, Filter, MapPin, Wrench, Clock, X, AlertTriangle,
  CheckCircle2, ArrowUpRight, ArrowDownRight, FolderOpen,
  Calendar, FileDown, Activity, Info, Link as LinkIcon,
  ClipboardList, CalendarDays, Hourglass, CircleHelp, Factory, RefreshCw, Handshake
} from 'lucide-react';
import SoftwayHelperModal from '../../components/SoftwayHelperModal';
import { authFetch } from '../../lib/authFetch';

const API = () => (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');

// ─── Configuraciones visuales ───────────────────────────────────────────────
const STATES = {
  received:       { name: 'Recibido',        color: '#3b82f6', icon: ClipboardList },
  scheduled:      { name: 'Agendado',        color: '#8b5cf6', icon: CalendarDays },
  in_progress:    { name: 'En Proceso',      color: '#f59e0b', icon: Wrench },
  on_hold_parts:  { name: 'Esp. Repuestos',  color: '#ef4444', icon: Hourglass },
  on_hold_client: { name: 'Esp. Cliente',    color: '#f97316', icon: CircleHelp },
  external_work:  { name: 'Trabajo Ext.',    color: '#06b6d4', icon: Factory },
  rescheduled:    { name: 'Reagendado',      color: '#6366f1', icon: RefreshCw },
  completed:      { name: 'Finalizado',      color: '#10b981', icon: CheckCircle2 },
  delivered:      { name: 'Entregado',       color: '#22c55e', icon: Handshake },
};

const TYPE_CFG = {
  warranty:  { label: 'Garantía',      color: '#eab308', bg: 'rgba(234,179,8,0.15)',  letter: 'G' },
  km_review: { label: 'Rev. KM',       color: '#22c55e', bg: 'rgba(34,197,94,0.15)',  letter: 'R' },
  regular:   { label: 'Mec. General',  color: '#3b82f6', bg: 'rgba(59,130,246,0.15)', letter: 'M' },
  quick:     { label: 'Mec. Rápida',   color: '#a855f7', bg: 'rgba(168,85,247,0.15)', letter: 'Q' },
  pdi:       { label: 'Alistamiento',  color: '#f97316', bg: 'rgba(249,115,22,0.15)', letter: 'A' },
};

function dayColor(d) { return d > 5 ? '#ef4444' : d > 2 ? '#fbbf24' : '#10b981'; }
function fmtDate(iso) {
  if (!iso) return '-';
  const utc = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z';
  return new Date(utc).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Bogota' });
}

// ─── Modal Interactivo de Expediente (Heredado de Kanban) ────────────────────
function OrderModal({ order, onClose }) {
  const [detail,  setDetail]  = useState(null);
  const [loading, setLoading] = useState(true);
  const [showSoftwayMode, setShowSoftwayMode] = useState(false);

  const tc  = TYPE_CFG[order.tipo_trabajo] || TYPE_CFG.regular;
  const col = STATES[order.estado];
  const dc  = dayColor(order.tiempo_taller_dias ?? 0);

  useEffect(() => {
    const fn = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', fn);
    return () => window.removeEventListener('keydown', fn);
  }, [onClose]);

  useEffect(() => {
    if (!order?.order_id) return;
    (async () => {
      try {
        const res = await authFetch(`/orders/${order.order_id}/detail`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setDetail(await res.json());
      } catch (e) {
        console.error('Error cargando detalle:', e);
      } finally {
        setLoading(false);
      }
    })();
  }, [order?.order_id]);

  if (!order) return null;

  const content = (
    <div className="mbackdrop" onClick={onClose}>
      <div className="mbox" onClick={e => e.stopPropagation()}>
        <div className="mhead" style={{ borderBottom: `2px solid ${tc.color}` }}>
          <div style={{ display:'flex', alignItems:'center', gap:'0.6rem', flexWrap:'wrap' }}>
            <span className="mplate">{order.placa}</span>
            <span className="mtype" style={{ color: tc.color, background: tc.bg }}>{tc.label}</span>
            {col && (
              <span className="mtype" style={{ color: col.color, background: `${col.color}20`, display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                {col.icon && <col.icon size={12} />} {col.name}
              </span>
            )}
          </div>
          <button className="mclose" onClick={onClose}><X size={15} /></button>
        </div>

        {loading ? (
          <div style={{ padding:'3rem', textAlign:'center', color:'rgba(255,255,255,0.3)', fontSize:'0.7rem' }}>
            Cargando expediente de la base de datos...
          </div>
        ) : showSoftwayMode ? (
          <SoftwayHelperModal detail={detail} order={order} onClose={() => setShowSoftwayMode(false)} />
        ) : (
          <div className="mbody">
            {/* Semáforo */}
            <div className="msemaphore" style={{ borderColor: dc }}>
              <Clock size={14} color={dc} />
              <span style={{ color: dc, fontWeight: 900 }}>
                {detail?.dias_en_taller ?? order.tiempo_taller_dias ?? 0} días en taller
              </span>
              {(detail?.dias_en_taller ?? 0) > 5
                ? <><AlertTriangle size={13} color={dc} /><span style={{ marginLeft:'auto', fontSize:'0.6rem', color: dc }}>Atención requerida</span></>
                : <CheckCircle2 size={13} color={dc} />
              }
            </div>

            {/* Datos generales */}
            <div className="msection">
              <div className="mhead-actions" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.4rem', marginBottom: '0.8rem' }}>
                <h4 className="msection-title" style={{ borderBottom: 'none', margin: 0, paddingBottom: 0 }}><FolderOpen size={10} /> Datos del Expediente</h4>
                {['warranty', 'km_review', 'pdi'].includes(order.tipo_trabajo) && (
                  <button 
                    onClick={() => setShowSoftwayMode(true)}
                    style={{ background: 'rgba(59,130,246,0.15)', color: '#60a5fa', border: '1px solid rgba(59,130,246,0.3)', borderRadius: '6px', padding: '0.4rem 0.8rem', fontSize: '0.65rem', fontWeight: 800, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', transition: 'all 0.2s' }}
                    onMouseOver={e => { e.currentTarget.style.background = 'rgba(59,130,246,0.3)'; e.currentTarget.style.color = '#fff'; }}
                    onMouseOut={e => { e.currentTarget.style.background = 'rgba(59,130,246,0.15)'; e.currentTarget.style.color = '#60a5fa'; }}
                  >
                    <LinkIcon size={12} /> Llenar Softway
                  </button>
                )}
              </div>
              <div className="mgrid">
                {[
                  ['Placa',           detail?.vehiculo?.placa ?? order.placa],
                  ['Marca / Modelo',  `${detail?.vehiculo?.marca ?? ''} ${detail?.vehiculo?.modelo ?? ''}`.trim() || '-'],
                  ['VIN',             detail?.vehiculo?.vin ?? '-'],
                  ['Tipo Servicio',   tc.label],
                  ['Ingreso',         fmtDate(detail?.created_at)],
                  ['Entregado',       fmtDate(detail?.delivered_at)],
                  ['Ciudad',          detail?.centro?.ciudad ?? order.ciudad ?? '-'],
                  ['Centro',          detail?.centro?.nombre ?? order.centro_actual],
                  ['Visitas Tot.',    order.v_totales ?? '-'],
                  ['Garantías Tot.',  order.g_totales ?? '-'],
                  ['KM Ingreso',      detail?.recepcion?.mileage_km ? `${Number(detail.recepcion.mileage_km).toLocaleString()} km` : '-'],
                ].map(([l, v]) => (
                  <div key={l}><span className="mlbl">{l}</span><span className="mval">{v}</span></div>
                ))}
              </div>
            </div>

            {/* Motivo Ingreso */}
            {detail?.recepcion && (
              <div className="msection">
                <h4 className="msection-title"><Activity size={10} /> Motivo de Ingreso</h4>
                {detail.recepcion.customer_notes
                  ? <div className="mtext-block">{detail.recepcion.customer_notes}</div>
                  : <p style={{ fontSize:'0.7rem', color:'rgba(255,255,255,0.3)' }}>Sin notas registradas</p>}
                
                {detail.recepcion.warranty_warnings && (
                  <div className="mwarning">
                    <AlertTriangle size={11} color="#eab308" />
                    <span>{detail.recepcion.warranty_warnings}</span>
                  </div>
                )}
                
                {detail.recepcion.damage_photos_urls?.length > 0 && (
                  <div className="mphotos">
                    {detail.recepcion.damage_photos_urls.map((url, i) => (
                      <a key={i} href={url} target="_blank" rel="noreferrer" className="mphoto-thumb">
                        <img src={url} alt={`Foto ${i + 1}`} onError={e => { e.target.style.display = 'none'; }} />
                      </a>
                    ))}
                  </div>
                )}

                {detail.recepcion.reception_pdf_url && (
                  <a href={`${API()}/orders/${order.order_id}/pdf?token=${typeof window !== 'undefined' ? sessionStorage.getItem('um_token') : ''}`} target="_blank" rel="noreferrer" className="mpdf-btn">
                    <FileDown size={14} /> Ver Acta de Recepción PDF
                  </a>
                )}
              </div>
            )}
            
            {/* Historial */}
            {detail?.historial?.length > 0 && (
              <div className="msection">
                <h4 className="msection-title"><Clock size={10} /> Historial de Estado</h4>
                <div className="mhistory">
                  {detail.historial.map((h, i) => (
                    <div key={i} className="mhistory-item">
                      <div className="mhistory-line">
                        <span style={{ color: STATES[h.from_status]?.color ?? 'rgba(255,255,255,0.3)', fontSize:'0.62rem' }}>
                          {STATES[h.from_status]?.name || h.from_status}
                        </span>
                        <span style={{ color:'rgba(255,255,255,0.25)', fontSize:'0.6rem' }}>→</span>
                        <span style={{ color: STATES[h.to_status]?.color ?? '#10b981', fontSize:'0.62rem', fontWeight:800 }}>
                          {STATES[h.to_status]?.name || h.to_status}
                        </span>
                        {h.duration_minutes && (
                          <span style={{ marginLeft:'auto', fontSize:'0.55rem', color:'rgba(255,255,255,0.25)' }}>
                            {h.duration_minutes < 60 ? `${Math.round(h.duration_minutes)}m` : `${(h.duration_minutes / 60).toFixed(1)}h`}
                          </span>
                        )}
                      </div>
                      <span style={{ fontSize:'0.55rem', color:'rgba(255,255,255,0.2)' }}>{fmtDate(h.changed_at)}</span>
                      {h.comments && <p style={{ fontSize:'0.65rem', color:'rgba(255,255,255,0.6)', marginTop:3, fontStyle:'italic' }}>"{h.comments}"</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
  return typeof window !== 'undefined' ? createPortal(content, document.body) : null;
}

// ─── Componente Principal ───────────────────────────────────────────────────
export default function ServicesPage() {
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Filtros
  const [filterQuery, setFilterQuery] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [filterState, setFilterState] = useState('all');
  const [filterCenter, setFilterCenter] = useState('all');
  
  // Sorting
  const [sortCol, setSortCol] = useState('tiempo_taller_dias');
  const [sortDir, setSortDir] = useState('desc');

  // Modal
  const [selectedOrder, setSelectedOrder] = useState(null);

  useEffect(() => {
    const fetchServices = async () => {
      try {
        const response = await authFetch('/orders/analytics/services');
        const data = await response.json();
        setServices(Array.isArray(data) ? data : []);
      } catch (e) {
        console.error("Error cargando servicios:", e);
      } finally {
        setLoading(false);
      }
    };
    fetchServices();
  }, []);

  // Extraer centros únicos para dropdown
  const uniqueCenters = useMemo(() => {
    return [...new Set(services.map(s => s.centro_actual).filter(Boolean))].sort();
  }, [services]);

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  const filtered = useMemo(() => {
    let result = services;
    
    if (filterQuery) {
      const q = filterQuery.toLowerCase();
      result = result.filter(s => 
        s.placa?.toLowerCase().includes(q) || 
        s.centro_actual?.toLowerCase().includes(q) ||
        s.ciudad?.toLowerCase().includes(q)
      );
    }
    if (filterType !== 'all')   result = result.filter(s => s.tipo_trabajo === filterType);
    if (filterState !== 'all')  result = result.filter(s => s.estado === filterState);
    if (filterCenter !== 'all') result = result.filter(s => s.centro_actual === filterCenter);

    result.sort((a, b) => {
      const va = a[sortCol] ?? 0;
      const vb = b[sortCol] ?? 0;
      const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [services, filterQuery, filterType, filterState, filterCenter, sortCol, sortDir]);

  const SortIcon = ({ col }) => sortCol === col
    ? (sortDir === 'asc' ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />)
    : null;

  return (
    <AdminLayout fullWidth>
      <div className="master-page">

        {/* Header Premium */}
        <header className="page-header">
          <div>
            <h1 className="page-title">Gestión <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Maestra</span></h1>
            <p className="page-subtitle">Repositorio centralizado de expedientes y órdenes en red</p>
          </div>
          <div className="stats-pill">
            <span className="stats-num">{filtered.length}</span>
            <span className="stats-lbl">Órdenes Visibles</span>
          </div>
        </header>

        {/* Toolbar de filtros */}
        <div className="toolbar">
          <div className="search-bar">
            <Search size={14} className="icon-muted" />
            <input 
              className="search-input"
              type="text" 
              placeholder="Buscar placa, ciudad, centro..." 
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
            />
          </div>
          
          <div className="filter-group">
            <Filter size={12} className="icon-muted" />
            <select className="filter-sel" value={filterType} onChange={e => setFilterType(e.target.value)}>
              <option value="all">Tipo: Todos</option>
              {Object.entries(TYPE_CFG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>

          <div className="filter-group">
            <Activity size={12} className="icon-muted" />
            <select className="filter-sel" value={filterState} onChange={e => setFilterState(e.target.value)}>
              <option value="all">Estado: Todos</option>
              {Object.entries(STATES).map(([k, v]) => <option key={k} value={k}>{v.emoji} {v.name}</option>)}
            </select>
          </div>

          <div className="filter-group">
            <MapPin size={12} className="icon-muted" />
            <select className="filter-sel" value={filterCenter} onChange={e => setFilterCenter(e.target.value)}>
              <option value="all">Centro: Todos</option>
              {uniqueCenters.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>

        {/* Tabla Full Surface */}
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                {[['placa', 'Placa'], ['tipo_trabajo', 'Tipo'], ['estado', 'Estado'], 
                  ['tiempo_taller_dias', 'Días'], ['kilometraje', 'KM'], ['centro_actual', 'Centro'], 
                  ['ciudad', 'Ciudad'], ['v_totales', 'Visitas (T)'], ['v_2meses', 'Visitas (2m)'], ['g_totales', 'Garantías']].map(([col, lbl]) => (
                  <th key={col} onClick={() => toggleSort(col)} className="sort-head">
                    {lbl} <SortIcon col={col} />
                  </th>
                ))}
                <th className="sort-head" style={{ cursor: 'default' }}>PDF</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="10" className="td-empty">Sincronizando expedientes...</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan="10" className="td-empty">No se encontraron expedientes activos</td></tr>
              ) : filtered.map((s, i) => {
                const st = STATES[s.estado] || { name: s.estado };
                const tc = TYPE_CFG[s.tipo_trabajo] || TYPE_CFG.regular;
                const dc = dayColor(s.tiempo_taller_dias ?? 0);
                
                return (
                  <tr key={s.order_id} className="row-item" onClick={() => setSelectedOrder(s)} style={{ animationDelay: `${i * 0.02}s` }}>
                    <td className="td-plate">{s.placa}</td>
                    <td><span className="badge-type" style={{ color: tc.color, background: tc.bg }}>{tc.label}</span></td>
                    <td>
                      {st.icon ? (
                        <span className="badge-state" style={{ color: st.color || 'white', background: `${st.color || '#777'}15`, display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                          <st.icon size={13} /> {st.name}
                        </span>
                      ) : (
                        <span className="badge-state" style={{ color: st.color || 'white', background: `${st.color || '#777'}15` }}>
                          {st.name}
                        </span>
                      )}
                    </td>
                    <td><span className="td-days" style={{ color: dc }}>{s.tiempo_taller_dias ?? 0}d</span></td>
                    <td className="td-dim">{(s.kilometraje || 0).toLocaleString()}</td>
                    <td className="td-dim">{s.centro_actual}</td>
                    <td className="td-dim">{s.ciudad || '-'}</td>
                    <td className="td-dim" style={{ textAlign:'center' }}>{s.v_totales ?? '-'}</td>
                    <td className="td-dim" title="Visitas últ. 2 meses" style={{ textAlign:'center', color: (s.v_2meses||0) > 1 ? '#ef4444' : undefined, fontWeight: (s.v_2meses||0) > 1 ? '900' : 'normal' }}>{s.v_2meses ?? '-'}</td>
                    <td className="td-dim" style={{ textAlign:'center', color: (s.g_totales||0) > 1 ? '#eab308' : undefined }}>{s.g_totales ?? '-'}</td>
                    <td onClick={e => e.stopPropagation()}>
                      {s.pdf_url ? (
                        <a href={`${API()}/orders/${s.order_id}/pdf?token=${typeof window !== 'undefined' ? sessionStorage.getItem('um_token') : ''}`} target="_blank" className="btn-pdf">
                          <FileDown size={14} />
                        </a>
                      ) : <span className="td-dim text-[0.6rem]">Sin PDF</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Leyenda Footer */}
        <div className="footer-legend">
          <Info size={11} className="icon-muted" />
          <span>Haz clic en cualquier fila para abrir el expediente completo de la motocicleta.</span>
        </div>
      </div>

      {selectedOrder && <OrderModal order={selectedOrder} onClose={() => setSelectedOrder(null)} />}

      <style jsx global>{`
        /* ── Master Page ── */
        .master-page {
          display: flex;
          flex-direction: column;
          height: calc(100vh - 40px);
          max-width: 100%;
          animation: fadeIn 0.4s ease;
        }

        .title-gradient { font-size:1.6rem; font-weight:900; background:linear-gradient(135deg, #fff 40%, #ff8c5a); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0; text-transform:uppercase; letter-spacing:-0.02em; line-height:1; }
        .stats-pill { display:flex; align-items:center; gap:0.5rem; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:0.4rem 0.8rem; border-radius:10px; }
        .stats-num { font-size:1rem; font-weight:900; color:#3b82f6; }
        .stats-lbl { font-size:0.55rem; font-weight:800; color:rgba(255,255,255,0.4); text-transform:uppercase; letter-spacing:0.1em; }

        /* ── Toolbar / Filters ── */
        .toolbar { display:flex; gap:0.6rem; margin-bottom:1rem; flex-wrap:wrap; flex-shrink:0; }
        .search-bar { display:flex; align-items:center; gap:0.5rem; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:0.45rem 0.8rem; flex:1; min-width:250px; transition:border-color 0.2s; }
        .search-bar:focus-within { border-color:rgba(59,130,246,0.5); }
        .search-input { background:transparent; border:none; outline:none; font-size:0.7rem; color:white; width:100%; font-family:inherit; }
        .search-input::placeholder { color:rgba(255,255,255,0.25); }
        .icon-muted { color:rgba(255,255,255,0.3); }

        .filter-group { display:flex; align-items:center; gap:0.4rem; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:0 0.6rem; cursor:pointer; }
        .filter-sel { background:transparent; border:none; outline:none; font-size:0.65rem; color:rgba(255,255,255,0.7); font-family:inherit; padding:0.45rem 0; cursor:pointer; appearance:none; font-weight:600; text-transform:uppercase; letter-spacing:0.04em; }
        .filter-sel option { background:#111; color:white; }

        /* ── Data Table ── */
        .table-container {
          flex: 1;
          overflow: auto;
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 12px;
          min-height: 0;
        }
        .table-container::-webkit-scrollbar { width:6px; height:6px; }
        .table-container::-webkit-scrollbar-thumb { background:rgba(255,255,255,0.1); border-radius:4px; }

        .data-table { width:100%; border-collapse:collapse; text-align:center; }
        .sort-head { padding:0.7rem 1rem; font-size:0.58rem; font-weight:800; color:rgba(255,255,255,0.4); text-transform:uppercase; letter-spacing:0.1em; border-bottom:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.015); cursor:pointer; white-space:nowrap; position:sticky; top:0; z-index:10; backdrop-filter:blur(10px); }
        .sort-head:hover { color:white; }
        
        .row-item { border-bottom:1px solid rgba(255,255,255,0.03); cursor:pointer; transition:background 0.15s; animation:rowIn 0.3s ease both; }
        .row-item:hover { background:rgba(255,255,255,0.04); }
        @keyframes rowIn { from{opacity:0;transform:translateX(-5px);} to{opacity:1;transform:none;} }

        .row-item td { padding:0.7rem 1rem; font-size:0.68rem; }
        .td-plate { font-size:0.85rem; font-weight:900; color:#ff8c5a; letter-spacing:0.03em; }
        .badge-type { font-size:0.55rem; font-weight:800; padding:3px 7px; border-radius:6px; text-transform:uppercase; }
        .badge-state { font-size:0.6rem; font-weight:700; padding:3px 8px; border-radius:6px; white-space:nowrap; }
        .td-days { font-size:0.8rem; font-weight:900; }
        .td-dim { color:rgba(255,255,255,0.5); }
        .td-empty { text-align:center; padding:4rem; color:rgba(255,255,255,0.3); font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em; }
        .btn-pdf { color:#3b82f6; padding:0.3rem; background:rgba(59,130,246,0.1); border-radius:6px; display:inline-flex; transition:all 0.15s; }
        .btn-pdf:hover { background:rgba(59,130,246,0.25); transform:scale(1.1); }

        .footer-legend { display:flex; align-items:center; gap:0.4rem; padding-top:0.6rem; font-size:0.58rem; color:rgba(255,255,255,0.3); text-transform:uppercase; letter-spacing:0.05em; flex-shrink:0; }

        /* ── Modal Styles (Kanban) ── */
        .mbackdrop { position:fixed; inset:0; background:rgba(0,0,0,0.75); backdrop-filter:blur(8px); z-index:9999; display:flex; align-items:center; justify-content:center; padding:1.5rem; animation:min 0.2s ease; }
        @keyframes min { from{opacity:0;} to{opacity:1;} }
        .mbox { background:#0a0a0b; border:1px solid rgba(255,255,255,0.1); border-radius:14px; width:100%; max-width:640px; max-height:90vh; display:flex; flex-direction:column; box-shadow:0 24px 64px rgba(0,0,0,0.6); overflow:hidden; animation:mup 0.3s cubic-bezier(0.16,1,0.3,1); }
        @keyframes mup { from{opacity:0;transform:translateY(20px) scale(0.97);} to{opacity:1;transform:none;} }
        .mhead { display:flex; align-items:flex-start; justify-content:space-between; padding:1.25rem 1.5rem; background:rgba(255,255,255,0.02); }
        .mplate { font-size:1.6rem; font-weight:900; color:#ff8c5a; letter-spacing:0.05em; line-height:1; }
        .mtype { font-size:0.6rem; font-weight:900; padding:3px 8px; border-radius:6px; text-transform:uppercase; }
        .mclose { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); width:28px; height:28px; border-radius:8px; color:rgba(255,255,255,0.6); display:flex; align-items:center; justify-content:center; cursor:pointer; transition:all 0.15s; }
        .mclose:hover { background:rgba(255,255,255,0.1); color:white; transform:rotate(90deg); }
        .mbody { padding:1.5rem; overflow-y:auto; flex:1; display:flex; flex-direction:column; gap:1.25rem; }
        .mbody::-webkit-scrollbar { width:4px; }
        .mbody::-webkit-scrollbar-thumb { background:rgba(255,255,255,0.15); border-radius:4px; }
        .msemaphore { display:flex; align-items:center; gap:0.5rem; padding:0.75rem 1rem; border-radius:10px; border:1px solid; background:linear-gradient(90deg, rgba(255,255,255,0.03), transparent); font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; }
        .msection { background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); border-radius:12px; padding:1rem; }
        .msection-title { font-size:0.6rem; font-weight:800; text-transform:uppercase; letter-spacing:0.1em; color:rgba(255,255,255,0.4); margin:0 0 0.8rem 0; display:flex; align-items:center; gap:0.4rem; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:0.4rem; }
        .mgrid { display:grid; grid-template-columns:repeat(auto-fill, minmax(130px, 1fr)); gap:0.8rem; }
        .mgrid > div { display:flex; flex-direction:column; gap:2px; }
        .mlbl { font-size:0.55rem; font-weight:700; color:rgba(255,255,255,0.3); text-transform:uppercase; letter-spacing:0.06em; }
        .mval { font-size:0.7rem; font-weight:700; color:rgba(255,255,255,0.85); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .mtext-block { font-size:0.75rem; color:rgba(255,255,255,0.8); line-height:1.5; background:rgba(0,0,0,0.3); padding:0.8rem; border-radius:8px; border-left:3px solid #3b82f6; }
        .mwarning { display:flex; gap:0.5rem; background:rgba(234,179,8,0.1); border:1px solid rgba(234,179,8,0.2); border-radius:8px; padding:0.6rem; margin-top:0.6rem; color:#eab308; font-size:0.68rem; font-weight:600; line-height:1.4; }
        .mphotos { display:flex; gap:0.5rem; flex-wrap:wrap; margin-top:0.8rem; }
        .mphoto-thumb { width:56px; height:56px; border-radius:8px; overflow:hidden; border:1px solid rgba(255,255,255,0.1); transition:transform 0.2s; }
        .mphoto-thumb:hover { transform:scale(1.1); border-color:#3b82f6; }
        .mphoto-thumb img { width:100%; height:100%; object-fit:cover; }
        .mpdf-btn { display:inline-flex; align-items:center; gap:0.4rem; padding:0.55rem 0.8rem; background:rgba(59,130,246,0.15); color:#60a5fa; border-radius:8px; font-size:0.65rem; font-weight:800; text-transform:uppercase; letter-spacing:0.05em; text-decoration:none; margin-top:0.8rem; transition:background 0.2s; border:1px solid rgba(59,130,246,0.3); }
        .mpdf-btn:hover { background:rgba(59,130,246,0.25); color:white; }
        .mhistory { display:flex; flex-direction:column; gap:0.4rem; }
        .mhistory-item { background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.04); border-radius:8px; padding:0.6rem 0.8rem; border-left:2px solid; }
        .mhistory-item:nth-child(even) { border-left-color: rgba(255,255,255,0.05); }
        .mhistory-item:nth-child(odd)  { border-left-color: #3b82f6; }
        .mhistory-line { display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap; }
      `}</style>
    </AdminLayout>
  );
}
