'use client';
import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import AdminLayout from '../admin-layout';
import {
  DndContext, DragOverlay, pointerWithin,
  PointerSensor, KeyboardSensor, useSensor, useSensors, useDroppable,
  MeasuringStrategy,
} from '@dnd-kit/core';
import {
  SortableContext, useSortable, verticalListSortingStrategy,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { 
  Clock, MapPin, X, Wrench, AlertTriangle, CheckCircle2, Link as LinkIcon,
  ClipboardList, CalendarDays, Hourglass, CircleHelp, Factory, RefreshCw, Handshake
} from 'lucide-react';
import SoftwayHelperModal from '../../components/SoftwayHelperModal';
import { authFetch } from '../../lib/authFetch';

// ─── Estados reales del modelo ServiceStatus ───────────────────────────────
const COLUMNS = [
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
  warranty:  { label: 'Garantia',     color: '#eab308', bg: 'rgba(234,179,8,0.18)',  letter: 'G' },
  km_review: { label: 'Rev. KM',      color: '#22c55e', bg: 'rgba(34,197,94,0.18)',  letter: 'R' },
  regular:   { label: 'Mecanica',     color: '#3b82f6', bg: 'rgba(59,130,246,0.18)', letter: 'M' },
  pdi:       { label: 'Alistamiento', color: '#f97316', bg: 'rgba(249,115,22,0.18)', letter: 'A' },
};

const colById = Object.fromEntries(COLUMNS.map(c => [c.id, c]));
const API     = () => (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');

function dayColor(d) { return d > 5 ? '#ef4444' : d > 2 ? '#fbbf24' : '#10b981'; }
function fmtDate(iso) {
  if (!iso) return '-';
  const utc = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z';
  return new Date(utc).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Bogota' });
}
function colName(id) { return colById[id]?.name ?? id ?? '-'; }

// ─── Tarjeta draggable (toda la superficie) ────────────────────────────────
function KanbanCard({ order, onOpen }) {
  const [otpSending, setOtpSending] = useState(false);
  const [otpSent,    setOtpSent]    = useState(false);
  const [otpError,   setOtpError]   = useState('');

  const pending = order.estado === 'pending_signature';

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: order.order_id, data: { colId: order.estado } });
  const tc = TYPE_CFG[order.tipo_trabajo] || TYPE_CFG.regular;
  const d  = order.tiempo_taller_dias ?? 0;
  const dc = dayColor(d);

  const handleSendOtp = async (e) => {
    e.stopPropagation();
    setOtpSending(true); setOtpError('');
    try {
      const res = await authFetch(`/orders/${order.order_id}/otp/send`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setOtpError(data.detail || 'Error'); return; }
      setOtpSent(true);
    } catch { setOtpError('Error de conexión'); }
    finally { setOtpSending(false); }
  };

  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      style={{
        transform:  CSS.Transform.toString(transform),
        transition,
        opacity:    isDragging ? 0 : 1,
        borderLeft: `3px solid ${pending ? '#f59e0b' : tc.color}`,
        cursor:     pending ? 'default' : isDragging ? 'grabbing' : 'grab',
      }}
      className="kcard"
      onClick={() => !isDragging && onOpen(order)}
    >
      {/* Distintivo pendiente de firma */}
      {pending && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4, padding: '2px 4px', background: 'rgba(245,158,11,0.12)', borderRadius: 4, border: '1px solid rgba(245,158,11,0.25)' }}>
          <AlertTriangle size={8} color="#f59e0b" />
          <span style={{ fontSize: '0.55rem', fontWeight: 800, color: '#f59e0b', textTransform: 'uppercase' }}>Sin firma</span>
        </div>
      )}

      <div className="kcard-top">
        <span className="kcard-plate">{order.placa}</span>
        <span className="kcard-type" style={{ color: tc.color, background: tc.bg }}>{tc.letter}</span>
      </div>
      <p className="kcard-center"><MapPin size={9} />{order.centro_actual}</p>
      <div className="kcard-foot">
        <span style={{ color: dc, fontWeight: 800, fontSize: '0.6rem', display: 'flex', alignItems: 'center', gap: 3 }}>
          <Clock size={9} />{d}d
        </span>
        <span className="kcard-km">{(order.kilometraje || 0).toLocaleString()} km</span>
      </div>

      {/* Botón OTP inline — solo para pending_signature */}
      {pending && (
        <div onClick={e => e.stopPropagation()} style={{ marginTop: 6 }}>
          <button
            onClick={handleSendOtp}
            disabled={otpSending || otpSent}
            style={{
              width: '100%', padding: '3px 0',
              background: otpSent ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.15)',
              color: otpSent ? '#10b981' : '#f59e0b',
              border: `1px solid ${otpSent ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}`,
              borderRadius: 4, fontSize: '0.55rem', fontWeight: 800,
              cursor: otpSent || otpSending ? 'default' : 'pointer',
              textTransform: 'uppercase',
            }}
          >
            {otpSending ? 'Enviando...' : otpSent ? '✓ OTP enviado' : 'Enviar OTP'}
          </button>
          {otpError && <p style={{ fontSize: '0.5rem', color: '#ef4444', margin: '2px 0 0' }}>{otpError}</p>}
        </div>
      )}
    </div>
  );
}

// ─── Columna droppable ─────────────────────────────────────────────────────
function KanbanColumn({ col, cards, onOpen, isOver, animIdx }) {
  const { setNodeRef } = useDroppable({ id: col.id });
  return (
    <div
      className="kcol"
      style={{
        borderTop:  `3px solid ${col.color}`,
        background: isOver ? `${col.color}12` : 'rgba(255,255,255,0.025)',
        animationDelay: `${animIdx * 0.04}s`,
        transition: 'background 0.15s',
      }}
    >
      <div className="kcol-head">
        <span style={{ display: 'flex', alignItems: 'center', opacity: 0.9 }}>
          {col.icon && <col.icon size={14} style={{ color: col.color }} />}
        </span>
        <span className="kcol-name">{col.name}</span>
        <span className="kcol-count" style={{ color: col.color, background: `${col.color}20` }}>
          {cards.length}
        </span>
      </div>
      <SortableContext items={cards.map(c => c.order_id)} strategy={verticalListSortingStrategy}>
        <div ref={setNodeRef} className="kcol-body">
          {cards.length === 0
            ? (
              <div className="kcol-empty" style={{
                borderColor: isOver ? col.color : 'rgba(255,255,255,0.06)',
                background:  isOver ? `${col.color}08` : 'transparent',
              }}>
                {isOver ? 'Suelta aqui' : 'Sin tarjetas'}
              </div>
            )
            : cards.map(o => <KanbanCard key={o.order_id} order={o} onOpen={onOpen} />)
          }
        </div>
      </SortableContext>
    </div>
  );
}

// ─── Sección OTP ──────────────────────────────────────────────────────────
function OtpSection({ orderId, onAccepted, onBypassed }) {
  const [otpSent,    setOtpSent]    = useState(false);
  const [code,       setCode]       = useState('');
  const [error,      setError]      = useState('');
  const [sending,    setSending]    = useState(false);
  const [verifying,  setVerifying]  = useState(false);
  const [bypassing,  setBypassing]  = useState(false);
  const [cooldown,   setCooldown]   = useState(0);

  const currentUser = typeof window !== 'undefined'
    ? JSON.parse(sessionStorage.getItem('um_user') || '{}')
    : {};
  const canBypass = ['superadmin', 'jefe_taller'].includes(currentUser.role);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const handleSend = async () => {
    setSending(true); setError('');
    try {
      const res = await authFetch(`/orders/${orderId}/otp/send`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Error enviando OTP'); return; }
      setOtpSent(true);
      setCooldown(60);
    } catch { setError('Error de conexión'); }
    finally { setSending(false); }
  };

  const handleVerify = async () => {
    if (code.length !== 6) { setError('El código debe tener 6 dígitos'); return; }
    setVerifying(true); setError('');
    try {
      const res = await authFetch(`/orders/${orderId}/otp/verify`, {
        method: 'POST',
        body: JSON.stringify({ code }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Código incorrecto'); return; }
      onAccepted(data);
    } catch { setError('Error de conexión'); }
    finally { setVerifying(false); }
  };

  return (
    <div style={{ margin: '0.8rem 0', padding: '1rem', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.8rem' }}>
        <AlertTriangle size={14} color="#f59e0b" />
        <span style={{ fontSize: '0.7rem', fontWeight: 800, color: '#f59e0b', textTransform: 'uppercase' }}>
          Pendiente firma del cliente
        </span>
      </div>

      {!otpSent ? (
        <button
          onClick={handleSend}
          disabled={sending}
          style={{ width: '100%', padding: '0.6rem', background: 'rgba(245,158,11,0.2)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.4)', borderRadius: 6, fontSize: '0.7rem', fontWeight: 800, cursor: sending ? 'not-allowed' : 'pointer' }}
        >
          {sending ? 'Enviando SMS...' : 'Enviar OTP al cliente'}
        </button>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          <input
            type="text"
            inputMode="numeric"
            maxLength={6}
            placeholder="Código de 6 dígitos"
            value={code}
            onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
            style={{ padding: '0.6rem', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6, color: 'white', fontSize: '1rem', letterSpacing: '0.3rem', textAlign: 'center' }}
          />
          <button
            onClick={handleVerify}
            disabled={verifying || code.length !== 6}
            style={{ padding: '0.6rem', background: code.length === 6 ? 'rgba(16,185,129,0.2)' : 'rgba(255,255,255,0.04)', color: code.length === 6 ? '#10b981' : 'rgba(255,255,255,0.3)', border: `1px solid ${code.length === 6 ? 'rgba(16,185,129,0.4)' : 'rgba(255,255,255,0.1)'}`, borderRadius: 6, fontSize: '0.7rem', fontWeight: 800, cursor: code.length === 6 && !verifying ? 'pointer' : 'not-allowed' }}
          >
            {verifying ? 'Verificando...' : 'Verificar OTP'}
          </button>
          <button
            onClick={handleSend}
            disabled={cooldown > 0 || sending}
            style={{ padding: '0.4rem', background: 'transparent', color: cooldown > 0 ? 'rgba(255,255,255,0.2)' : 'rgba(245,158,11,0.7)', border: 'none', fontSize: '0.65rem', cursor: cooldown > 0 ? 'not-allowed' : 'pointer' }}
          >
            {cooldown > 0 ? `Reenviar en ${cooldown}s` : 'Reenviar SMS'}
          </button>
        </div>
      )}

      {error && (
        <p style={{ marginTop: '0.5rem', fontSize: '0.65rem', color: '#ef4444' }}>{error}</p>
      )}

      {/* Bypass — solo jefe_taller y superadmin */}
      {canBypass && (
        <div style={{ marginTop: '0.8rem', paddingTop: '0.8rem', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <button
            onClick={async () => {
              if (!window.confirm('¿Confirmás que querés autorizar esta orden sin OTP? Quedará registrado con tu usuario.')) return;
              setBypassing(true);
              try {
                const res = await authFetch(`/orders/${orderId}/otp/bypass`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) { setError(data.detail || 'Error al autorizar'); return; }
                onBypassed(data);
              } catch { setError('Error de conexión'); }
              finally { setBypassing(false); }
            }}
            disabled={bypassing}
            style={{ width: '100%', padding: '0.5rem', background: 'rgba(249,115,22,0.1)', color: '#f97316', border: '1px solid rgba(249,115,22,0.3)', borderRadius: 6, fontSize: '0.65rem', fontWeight: 800, cursor: bypassing ? 'not-allowed' : 'pointer', textTransform: 'uppercase' }}
          >
            {bypassing ? 'Autorizando...' : '⚠️ Autorizar sin OTP'}
          </button>
          <p style={{ marginTop: 4, fontSize: '0.55rem', color: 'rgba(255,255,255,0.25)', textAlign: 'center' }}>
            Solo jefe de taller / superadmin · Queda registrado
          </p>
        </div>
      )}
    </div>
  );
}

// ─── Modal de detalle con datos reales de BD ──────────────────────────────
function OrderModal({ order, onClose, onOrderAccepted }) {
  const [detail,  setDetail]  = useState(null);
  const [loading, setLoading] = useState(true);
  const [showSoftwayMode, setShowSoftwayMode] = useState(false);

  const tc  = TYPE_CFG[order.tipo_trabajo] || TYPE_CFG.regular;
  const col = colById[order.estado];
  const dc  = dayColor(order.tiempo_taller_dias ?? 0);

  useEffect(() => {
    const fn = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', fn);
    return () => window.removeEventListener('keydown', fn);
  }, [onClose]);

  // Carga detalle completo desde BD
  useEffect(() => {
    if (!order.order_id) return;
    (async () => {
      try {
        const res = await authFetch(`${API()}/orders/${order.order_id}/detail`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setDetail(await res.json());
      } catch (e) {
        console.error('Error cargando detalle:', e);
      } finally {
        setLoading(false);
      }
    })();
  }, [order.order_id]);

  const content = (
    <div className="mbackdrop" onClick={onClose}>
      <div className="mbox" onClick={e => e.stopPropagation()}>

        {/* Header fijo */}
        <div className="mhead" style={{ borderBottom: `2px solid ${tc.color}` }}>
          <div style={{ display:'flex', alignItems:'center', gap:'0.6rem', flexWrap:'wrap' }}>
            <span className="mplate">{order.placa}</span>
            <span className="mtype" style={{ color: tc.color, background: tc.bg }}>{tc.label}</span>
            {col && (
              <span className="mtype" style={{ color: col.color, background: `${col.color}20`, display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                <col.icon size={12} /> {col.name}
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

            {/* OTP — solo visible cuando la orden está pendiente de firma */}
            {order.estado === 'pending_signature' && (
              <OtpSection
                orderId={order.order_id}
                onAccepted={(data) => { onOrderAccepted(order.order_id); onClose(); }}
                onBypassed={(data) => { onOrderAccepted(order.order_id); onClose(); }}
              />
            )}

            {/* Semaforo */}
            <div className="msemaphore" style={{ borderColor: dc }}>
              <Clock size={14} color={dc} />
              <span style={{ color: dc, fontWeight: 900 }}>
                {detail?.dias_en_taller ?? order.tiempo_taller_dias ?? 0} dias en taller
              </span>
              {(detail?.dias_en_taller ?? 0) > 5
                ? <><AlertTriangle size={13} color={dc} /><span style={{ marginLeft:'auto', fontSize:'0.6rem', color: dc }}>Atencion requerida</span></>
                : <CheckCircle2 size={13} color={dc} />
              }
            </div>

            {/* Datos generales */}
            <div className="msection">
              <div className="mhead-actions" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.4rem', marginBottom: '0.8rem' }}>
                <h4 className="msection-title" style={{ borderBottom: 'none', margin: 0, paddingBottom: 0 }}><Wrench size={10} /> Datos del Expediente</h4>
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
                  ['Visitas Totales', order.v_totales ?? '-'],
                  ['Visitas 2 Meses', order.v_2meses ?? '-'],
                  ['Garantias Tot.',  order.g_totales ?? '-'],
                  ['KM Ingreso',      detail?.recepcion?.mileage_km
                    ? `${Number(detail.recepcion.mileage_km).toLocaleString()} km` : '-'],
                ].map(([l, v]) => (
                  <div key={l}>
                    <span className="mlbl">{l}</span>
                    <span className="mval">{v}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Cliente y Tecnico */}
            {(detail?.cliente || detail?.tecnico) && (
              <div className="msection">
                <h4 className="msection-title">Personal</h4>
                <div className="mgrid">
                  {detail.cliente && [
                    ['Cliente',     detail.cliente.nombre    ?? '-'],
                    ['Tel. Cliente',detail.cliente.telefono  ?? '-'],
                  ].map(([l, v]) => <div key={l}><span className="mlbl">{l}</span><span className="mval">{v}</span></div>)}
                  {detail.tecnico && [
                    ['Tecnico',     detail.tecnico.nombre    ?? '-'],
                    ['Tel. Tecnico',detail.tecnico.telefono  ?? '-'],
                  ].map(([l, v]) => <div key={l}><span className="mlbl">{l}</span><span className="mval">{v}</span></div>)}
                </div>
              </div>
            )}

            {/* Motivo de Ingreso (Recepcion) */}
            {detail?.recepcion && (
              <div className="msection">
                <h4 className="msection-title">Motivo de Ingreso</h4>

                {detail.recepcion.customer_notes
                  ? <div className="mtext-block">{detail.recepcion.customer_notes}</div>
                  : <p style={{ fontSize:'0.7rem', color:'rgba(255,255,255,0.3)' }}>Sin notas registradas</p>}

                {detail.recepcion.warranty_warnings && (
                  <div className="mwarning">
                    <AlertTriangle size={11} color="#eab308" />
                    <span>{detail.recepcion.warranty_warnings}</span>
                  </div>
                )}

                {detail.recepcion.gas_level && (
                  <div style={{ fontSize:'0.65rem', color:'rgba(255,255,255,0.45)', marginTop: 4 }}>
                    Combustible: <strong style={{ color:'white' }}>{detail.recepcion.gas_level}</strong>
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
                  <a
                    href={`${API()}/orders/${order.order_id}/pdf?token=${typeof window !== 'undefined' ? sessionStorage.getItem('um_token') : ''}`}
                    target="_blank"
                    rel="noreferrer"
                    className="mpdf-btn"
                  >
                    Ver Acta de Recepcion PDF
                  </a>
                )}
              </div>
            )}

            {/* Historial de estados */}
            {detail?.historial?.length > 0 && (
              <div className="msection">
                <h4 className="msection-title">Historial de Estado</h4>
                <div className="mhistory">
                  {detail.historial.map((h, i) => (
                    <div key={i} className="mhistory-item">
                      <div className="mhistory-line">
                        <span style={{ color: colById[h.from_status]?.color ?? 'rgba(255,255,255,0.3)', fontSize:'0.62rem' }}>
                          {colName(h.from_status)}
                        </span>
                        <span style={{ color:'rgba(255,255,255,0.25)', fontSize:'0.6rem' }}>→</span>
                        <span style={{ color: colById[h.to_status]?.color ?? '#10b981', fontSize:'0.62rem', fontWeight:800 }}>
                          {colName(h.to_status)}
                        </span>
                        {h.duration_minutes && (
                          <span style={{ marginLeft:'auto', fontSize:'0.55rem', color:'rgba(255,255,255,0.25)' }}>
                            {h.duration_minutes < 60
                              ? `${Math.round(h.duration_minutes)}min`
                              : `${(h.duration_minutes / 60).toFixed(1)}h`}
                          </span>
                        )}
                      </div>
                      <span style={{ fontSize:'0.55rem', color:'rgba(255,255,255,0.2)' }}>{fmtDate(h.changed_at)}</span>
                      {h.comments && (
                        <p style={{ fontSize:'0.65rem', color:'rgba(255,255,255,0.6)', marginTop:3, fontStyle:'italic' }}>
                          "{h.comments}"
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="mhint">Arrastra la tarjeta en el tablero para cambiar su estado</p>
          </div>
        )}
      </div>
    </div>
  );

  return typeof window !== 'undefined' ? createPortal(content, document.body) : null;
}

// ─── Pagina principal ──────────────────────────────────────────────────────
export default function KanbanPage() {
  const [orders,   setOrders]   = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [activeId, setActiveId] = useState(null);
  const [overId,   setOverId]   = useState(null);
  const [selected, setSelected] = useState(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  useEffect(() => {
    (async () => {
      try {
        const res  = await authFetch('/orders/analytics/services');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setOrders(Array.isArray(data) ? data : []);
      } catch (e) {
        console.error('Kanban error:', e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const getCards = useCallback(
    colId => orders.filter(o =>
      colId === 'received'
        ? (o.estado === 'received' || o.estado === 'pending_signature')
        : o.estado === colId
    ),
    [orders]
  );
  const activeOrder = orders.find(o => o.order_id === activeId);

  const resolveDestCol = ovId => {
    if (!ovId) return null;
    if (COLUMNS.find(c => c.id === ovId)) return ovId;
    return orders.find(o => o.order_id === ovId)?.estado ?? null;
  };

  const handleDragOver = ({ over }) => setOverId(over ? resolveDestCol(over.id) : null);

  const handleDragEnd = async ({ active, over }) => {
    setActiveId(null);
    setOverId(null);
    if (!over) return;
    const destCol  = resolveDestCol(over.id);
    const srcOrder = orders.find(o => o.order_id === active.id);
    if (!destCol || !srcOrder || destCol === srcOrder.estado) return;
    if (srcOrder.estado === 'pending_signature') return; // Bloqueado hasta validar OTP

    setOrders(prev => prev.map(o => o.order_id === active.id ? { ...o, estado: destCol } : o));

    try {
      await authFetch(`/orders/${active.id}/status`, {
        method:  'PUT',
        body:    JSON.stringify({ status: destCol }),
      });
    } catch (e) { console.error('Error actualizando estado:', e); }
  };

  return (
    <AdminLayout fullWidth>
      {/* Header compacto */}
      <div className="kb-header">
        <div>
          <h1 className="page-title">Tablero Kanban <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Operativo</span></h1>
          <p className="kb-subtitle">
            {loading ? 'Sincronizando...'
              : `${orders.length} motos activas — arrastra y suelta en la columna para cambiar estado`}
          </p>
        </div>
        <div className="kb-legend">
          {Object.entries(TYPE_CFG).map(([k, v]) => (
            <span key={k} className="kb-legend-item" style={{ color: v.color, background: v.bg }}>
              {v.letter} {v.label}
            </span>
          ))}
        </div>
      </div>

      {/* Tablero */}
      {loading ? (
        <div className="kb-loading">
          <div className="kb-spinner" />
          <p>Cargando base de datos...</p>
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={pointerWithin}
          measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}
          onDragStart={({ active }) => setActiveId(active.id)}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
          onDragCancel={() => { setActiveId(null); setOverId(null); }}
        >
          <div className="kb-board">
            {COLUMNS.map((col, i) => (
              <KanbanColumn
                key={col.id}
                col={col}
                animIdx={i}
                cards={getCards(col.id)}
                onOpen={setSelected}
                isOver={overId === col.id}
              />
            ))}
          </div>

          <DragOverlay dropAnimation={null}>
            {activeOrder ? (
              <div className="kcard drag-ghost" style={{
                borderLeft: `3px solid ${(TYPE_CFG[activeOrder.tipo_trabajo] || TYPE_CFG.regular).color}`,
              }}>
                <span className="kcard-plate">{activeOrder.placa}</span>
                <p style={{ fontSize:'0.65rem', color:'rgba(255,255,255,0.5)', marginTop:4 }}>{activeOrder.centro_actual}</p>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      {selected && (
        <OrderModal
          order={selected}
          onClose={() => setSelected(null)}
          onOrderAccepted={(orderId) =>
            setOrders(prev => prev.map(o =>
              o.order_id === orderId ? { ...o, estado: 'received' } : o
            ))
          }
        />
      )}

      <style jsx global>{`
        @keyframes colIn {
          from { opacity:0; transform:translateY(12px); }
          to   { opacity:1; transform:translateY(0); }
        }

        /* ── Layout header ── */
        .kb-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 0.6rem;
          margin-bottom: 0.7rem;
          flex-shrink: 0;
        }
        .kb-title {
          font-size: 1.35rem;
          font-weight: 900;
          background: linear-gradient(135deg, #fff 40%, #ff8c5a);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          margin: 0;
        }
        .kb-subtitle { font-size:0.68rem; color:rgba(255,255,255,0.38); margin:0.15rem 0 0; font-weight:500; }
        .kb-legend { display:flex; gap:0.4rem; flex-wrap:wrap; align-items:center; }
        .kb-legend-item { font-size:0.57rem; font-weight:800; padding:2px 7px; border-radius:6px; text-transform:uppercase; letter-spacing:0.06em; }

        /* ── Tablero full-height ── */
        .kb-board {
          display: grid;
          grid-template-columns: repeat(9, 1fr);
          gap: 0.65rem;
          /* Ocupa todo lo que queda de pantalla menos header (~120px) */
          height: calc(100vh - 140px);
          overflow: hidden;
          animation: boardIn 0.35s ease;
          min-width: 0;
        }

        @keyframes boardIn {
          from { opacity:0; transform:translateY(8px); }
          to   { opacity:1; transform:translateY(0); }
        }

        /* ── Columna: ocupa el 100% del tablero verticalmente ── */
        .kcol {
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          height: 100%;          /* Llena el grid row */
          overflow: hidden;
          animation: colIn 0.35s ease both;
          min-width: 0;
        }

        .kcol-head {
          display: flex;
          align-items: center;
          gap: 0.35rem;
          padding: 0.55rem 0.65rem;
          background: rgba(255,255,255,0.025);
          flex-shrink: 0;
        }
        .kcol-name {
          flex: 1;
          font-size: 0.6rem;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.07em;
          color: white;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .kcol-count { font-size:0.6rem; font-weight:700; padding:1px 6px; border-radius:7px; flex-shrink:0; }

        /* Zona scrollable de tarjetas, ocupa el resto de la columna */
        .kcol-body {
          padding: 0.5rem;
          display: flex;
          flex-direction: column;
          gap: 0.48rem;
          overflow-y: auto;
          flex: 1;
          min-height: 0;   /* CLAVE para que flex+overflow funcionen correctamente */
        }
        .kcol-body::-webkit-scrollbar { width:2px; }
        .kcol-body::-webkit-scrollbar-thumb { background:rgba(255,255,255,0.07); }

        .kcol-empty {
          display: flex;
          align-items: center;
          justify-content: center;
          flex: 1;
          min-height: 60px;
          font-size: 0.58rem;
          color: rgba(255,255,255,0.18);
          text-transform: uppercase;
          letter-spacing: 0.1em;
          border: 1px dashed;
          border-radius: 8px;
          text-align: center;
          padding: 0.75rem;
          transition: all 0.15s;
        }

        /* ── Tarjeta ── */
        .kcard {
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 9px;
          padding: 0.55rem 0.6rem;
          transition: border-color 0.15s, transform 0.12s, box-shadow 0.12s;
          min-width: 0;
          flex-shrink: 0;
        }
        .kcard:hover {
          border-color: rgba(255,255,255,0.14);
          transform: translateY(-2px);
          box-shadow: 0 6px 18px rgba(0,0,0,0.3);
        }
        .drag-ghost {
          opacity: 0.92;
          transform: rotate(1.8deg) scale(1.03);
          box-shadow: 0 24px 48px rgba(0,0,0,0.55);
          cursor: grabbing;
        }

        .kcard-top { display:flex; align-items:center; gap:0.3rem; margin-bottom:0.3rem; }
        .kcard-plate { flex:1; font-weight:900; font-size:0.82rem; color:#ff8c5a; letter-spacing:0.04em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .kcard-type  { font-size:0.52rem; font-weight:900; padding:1px 4px; border-radius:4px; flex-shrink:0; }

        .kcard-center {
          display: flex; align-items:center; gap:0.25rem;
          font-size:0.58rem; color:rgba(255,255,255,0.38);
          margin-bottom:0.35rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }
        .kcard-foot {
          display: flex; align-items:center; justify-content:space-between;
          padding-top:0.35rem; border-top:1px solid rgba(255,255,255,0.05);
        }
        .kcard-km { font-size:0.55rem; color:rgba(255,255,255,0.25); }

        /* ── Spinner ── */
        .kb-loading { display:flex; align-items:center; gap:1rem; padding:4rem; justify-content:center; color:rgba(255,255,255,0.4); font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em; }
        .kb-spinner { width:26px; height:26px; border:3px solid rgba(255,95,51,0.15); border-top-color:#ff5f33; border-radius:50%; animation:spin 0.8s linear infinite; }
        @keyframes spin { to { transform:rotate(360deg); } }

        /* ── Modal backdrop ── */
        .mbackdrop {
          position: fixed; inset:0;
          background: rgba(0,0,0,0.75);
          backdrop-filter: blur(8px);
          z-index: 9999;
          display: flex; align-items:center; justify-content:center;
          padding: 1.5rem;
          animation: fadeIn 0.15s ease;
        }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }

        .mbox {
          background: #0d0d12;
          border: 1px solid rgba(255,255,255,0.09);
          border-radius: 18px;
          width: 100%; max-width: 560px;
          max-height: 88vh;
          overflow-y: auto;
          box-shadow: 0 40px 80px rgba(0,0,0,0.65);
          animation: slideUp 0.2s cubic-bezier(0.34,1.56,0.64,1);
          display: flex; flex-direction:column;
        }
        @keyframes slideUp {
          from { opacity:0; transform:translateY(20px) scale(0.97); }
          to   { opacity:1; transform:translateY(0)    scale(1); }
        }
        .mbox::-webkit-scrollbar { width:3px; }
        .mbox::-webkit-scrollbar-thumb { background:rgba(255,255,255,0.08); }

        .mhead {
          display:flex; align-items:center; justify-content:space-between;
          padding:1.1rem 1.4rem;
          position: sticky; top:0; background:#0d0d12; z-index:1;
          flex-shrink:0;
        }
        .mplate { font-size:1.6rem; font-weight:900; color:white; letter-spacing:0.06em; }
        .mtype { font-size:0.6rem; font-weight:800; padding:3px 8px; border-radius:7px; text-transform:uppercase; letter-spacing:0.07em; }
        .mclose { background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.09); border-radius:50%; width:30px; height:30px; display:flex; align-items:center; justify-content:center; cursor:pointer; color:rgba(255,255,255,0.5); transition:all 0.15s; }
        .mclose:hover { background:rgba(255,255,255,0.12); color:white; }

        .mbody { padding:0.9rem 1.4rem 1.4rem; display:flex; flex-direction:column; gap:1rem; }

        .msemaphore { display:flex; align-items:center; gap:0.55rem; padding:0.65rem 0.9rem; border-radius:9px; border:1px solid; background:rgba(255,255,255,0.02); font-size:0.8rem; font-weight:800; }

        .msection { display:flex; flex-direction:column; gap:0.5rem; }
        .msection-title { display:flex; align-items:center; gap:0.35rem; font-size:0.58rem; font-weight:900; text-transform:uppercase; letter-spacing:0.12em; color:rgba(255,255,255,0.3); }
        .mgrid { display:grid; grid-template-columns:1fr 1fr; gap:0.55rem; }
        .mlbl { display:block; font-size:0.55rem; font-weight:700; text-transform:uppercase; letter-spacing:0.07em; color:rgba(255,255,255,0.28); margin-bottom:1px; }
        .mval { display:block; font-size:0.75rem; font-weight:700; color:white; }

        /* Texto largo */
        .mtext-block { font-size:0.72rem; line-height:1.6; color:rgba(255,255,255,0.75); background:rgba(255,255,255,0.03); padding:0.65rem 0.8rem; border-radius:8px; border:1px solid rgba(255,255,255,0.05); }

        /* Advertencia garantia */
        .mwarning { display:flex; align-items:flex-start; gap:0.4rem; font-size:0.65rem; color:#eab308; background:rgba(234,179,8,0.08); padding:0.5rem 0.7rem; border-radius:7px; border:1px solid rgba(234,179,8,0.15); margin-top:4px; }

        /* Fotos */
        .mphotos { display:flex; gap:0.4rem; flex-wrap:wrap; margin-top:6px; }
        .mphoto-thumb { width:64px; height:64px; border-radius:7px; overflow:hidden; border:1px solid rgba(255,255,255,0.1); }
        .mphoto-thumb img { width:100%; height:100%; object-fit:cover; }

        /* Boton PDF */
        .mpdf-btn { display:inline-block; margin-top:8px; font-size:0.65rem; font-weight:800; padding:6px 12px; border-radius:8px; background:rgba(255,95,51,0.15); color:#ff8c5a; border:1px solid rgba(255,95,51,0.2); text-decoration:none; transition:all 0.15s; }
        .mpdf-btn:hover { background:rgba(255,95,51,0.25); }

        /* Historial */
        .mhistory { display:flex; flex-direction:column; gap:0.5rem; }
        .mhistory-item { background:rgba(255,255,255,0.025); border-radius:7px; padding:0.5rem 0.65rem; }
        .mhistory-line { display:flex; align-items:center; gap:0.4rem; margin-bottom:2px; }

        .mhint { font-size:0.6rem; color:rgba(255,255,255,0.25); text-align:center; padding:0.5rem; border-top:1px solid rgba(255,255,255,0.05); font-style:italic; }
      `}</style>
    </AdminLayout>
  );
}
