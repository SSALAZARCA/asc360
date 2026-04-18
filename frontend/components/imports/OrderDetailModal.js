'use client';
import { useState, useEffect, useRef } from 'react';
import { authFetch } from '../../lib/authFetch';
import StatusBadge from './StatusBadge';
import {
  X, Upload, Trash2, FileText, FileSpreadsheet, Image,
  File, Download, ChevronRight, Check, Clock, Package, AlertCircle,
} from 'lucide-react';

function API() {
  return (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/^http://(?!localhost)/, 'https://');
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmt(raw, dt) {
  if (raw) return raw;
  if (!dt) return '—';
  return dt.split('T')[0];
}

function Field({ label, value }) {
  return (
    <div>
      <p style={{ margin: 0, fontSize: '9px', fontWeight: 700, color: '#606075', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{label}</p>
      <p style={{ margin: '2px 0 0', fontSize: '12px', color: value ? '#fff' : '#606075' }}>{value || '—'}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Timeline horizontal
// ---------------------------------------------------------------------------
const STAGES = [
  { key: 'etr', label: 'ETR', desc: 'Est. Ready' },
  { key: 'etl', label: 'ETL', desc: 'Est. Loading' },
  { key: 'etd', label: 'ETD', desc: 'Est. Departure' },
  { key: 'eta', label: 'ETA', desc: 'Est. Arrival' },
];

function TimelineBar({ order }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0, padding: '8px 0 4px', overflowX: 'auto' }}>
      {STAGES.map((stage, i) => {
        const raw = order[`${stage.key}_raw`];
        const dt = order[stage.key];
        const value = fmt(raw, dt);
        const isPast = dt && new Date(dt) < new Date();
        const isReady = raw?.toUpperCase?.().startsWith('READY');
        const reached = isPast || isReady;
        const isPending = !dt && !raw;

        const color = reached ? '#22c55e' : isPending ? '#606075' : '#ff5f33';
        const bg = reached ? 'rgba(34,197,94,0.12)' : isPending ? 'rgba(255,255,255,0.04)' : 'rgba(255,95,51,0.12)';

        return (
          <div key={stage.key} style={{ display: 'flex', alignItems: 'flex-start', flex: 1, minWidth: 90 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}>
              {/* Dot + line */}
              <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                {i > 0 && (
                  <div style={{ flex: 1, height: 2, background: reached ? 'rgba(34,197,94,0.4)' : 'rgba(255,255,255,0.08)' }} />
                )}
                <div style={{
                  width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                  background: bg, border: `2px solid ${color}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {reached
                    ? <Check size={12} color="#22c55e" />
                    : isPending
                      ? <Clock size={11} color="#606075" />
                      : <ChevronRight size={11} color="#ff5f33" />
                  }
                </div>
                {i < STAGES.length - 1 && (
                  <div style={{ flex: 1, height: 2, background: 'rgba(255,255,255,0.08)' }} />
                )}
              </div>
              {/* Labels */}
              <p style={{ margin: '6px 0 0', fontSize: '9px', fontWeight: 800, color, letterSpacing: '0.08em', textAlign: 'center' }}>{stage.label}</p>
              <p style={{ margin: '1px 0 0', fontSize: '9px', color: '#606075', textAlign: 'center' }}>{stage.desc}</p>
              <p style={{ margin: '2px 0 0', fontSize: '10px', color: value === '—' ? '#606075' : '#d1d5db', textAlign: 'center', fontWeight: 600 }}>{value}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// VINs Tab
// ---------------------------------------------------------------------------
function VinsTab({ units }) {
  if (!units || units.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0', color: '#606075', fontSize: '12px' }}>
        <Package size={28} style={{ margin: '0 auto 10px', display: 'block', opacity: 0.4 }} />
        No hay VINs cargados para este pedido
      </div>
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
        <thead>
          <tr>
            {['#', 'VIN', 'Motor', 'Color', 'Contenedor', 'Precinto'].map(h => (
              <th key={h} style={{
                padding: '8px 10px', textAlign: 'left', fontSize: '9px', fontWeight: 700,
                color: '#606075', textTransform: 'uppercase', letterSpacing: '0.07em',
                borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {units.map((u, i) => (
            <tr key={u.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <td style={{ padding: '7px 10px', color: '#606075' }}>{u.item_no ?? i + 1}</td>
              <td style={{ padding: '7px 10px', color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace' }}>{u.vin_number || '—'}</td>
              <td style={{ padding: '7px 10px', color: '#d1d5db', fontFamily: 'monospace', fontSize: '10px' }}>{u.engine_number || '—'}</td>
              <td style={{ padding: '7px 10px', color: '#d1d5db' }}>{u.color || '—'}</td>
              <td style={{ padding: '7px 10px', color: '#9ca3af', fontFamily: 'monospace', fontSize: '10px' }}>{u.container_no || '—'}</td>
              <td style={{ padding: '7px 10px', color: '#9ca3af', fontFamily: 'monospace', fontSize: '10px' }}>{u.seal_no || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Docs Tab
// ---------------------------------------------------------------------------
const FILE_TYPE_OPTIONS = [
  { value: 'BL', label: 'Bill of Lading' },
  { value: 'COMMERCIAL_INVOICE', label: 'Commercial Invoice' },
  { value: 'PACKING_LIST', label: 'Packing List' },
  { value: 'CERT_ORIGIN', label: 'Certificado de Origen' },
  { value: 'OTHER', label: 'Otro' },
];

function fileIcon(name, contentType) {
  if (contentType?.startsWith('image/')) return <Image size={14} />;
  if (name?.endsWith('.xlsx') || name?.endsWith('.xls')) return <FileSpreadsheet size={14} />;
  if (name?.endsWith('.pdf') || contentType === 'application/pdf') return <FileText size={14} />;
  return <File size={14} />;
}

function DocsTab({ orderId, userRole }) {
  const [attachments, setAttachments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selectedType, setSelectedType] = useState('OTHER');
  const [error, setError] = useState(null);
  const inputRef = useRef();

  const fetchAttachments = async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API()}/imports/shipment-orders/${orderId}/attachments`);
      const data = await res.json();
      setAttachments(Array.isArray(data) ? data : []);
    } catch {
      setAttachments([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAttachments(); }, [orderId]);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await authFetch(
        `${API()}/imports/shipment-orders/${orderId}/attachments?file_type=${selectedType}`,
        { method: 'POST', body: formData, headers: {} }
      );
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || 'Error al subir archivo');
      }
      await fetchAttachments();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('¿Eliminar este adjunto?')) return;
    try {
      await authFetch(`${API()}/imports/attachments/${id}`, { method: 'DELETE' });
      setAttachments(prev => prev.filter(a => a.id !== id));
    } catch {
      alert('Error al eliminar adjunto');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Upload toolbar */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          value={selectedType}
          onChange={e => setSelectedType(e.target.value)}
          style={{
            padding: '7px 10px', borderRadius: '8px', fontSize: '11px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.1)',
            color: '#d1d5db', outline: 'none',
          }}
        >
          {FILE_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '7px 14px', borderRadius: '8px', border: 'none',
            background: uploading ? 'rgba(255,95,51,0.2)' : 'rgba(255,95,51,0.15)',
            color: '#ff5f33', fontSize: '11px', fontWeight: 700, cursor: uploading ? 'not-allowed' : 'pointer',
          }}
        >
          <Upload size={12} />{uploading ? 'Subiendo...' : 'Subir archivo'}
        </button>
        <input ref={inputRef} type="file" onChange={handleFile} style={{ display: 'none' }}
          accept=".pdf,.xlsx,.xls,.jpg,.jpeg,.png" />
      </div>

      {error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 12px', borderRadius: '8px', background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)' }}>
          <AlertCircle size={13} color="#f87171" />
          <span style={{ color: '#f87171', fontSize: '11px' }}>{error}</span>
        </div>
      )}

      {/* List */}
      {loading ? (
        <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '20px 0' }}>Cargando adjuntos...</p>
      ) : attachments.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: '#606075', fontSize: '12px' }}>
          <FileText size={28} style={{ margin: '0 auto 10px', display: 'block', opacity: 0.4 }} />
          No hay documentos adjuntos
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {attachments.map(att => (
            <div key={att.id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 12px', borderRadius: '10px',
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                <span style={{ color: '#60a5fa', flexShrink: 0 }}>{fileIcon(att.file_name, att.content_type)}</span>
                <div style={{ minWidth: 0 }}>
                  <p style={{ margin: 0, fontSize: '11px', fontWeight: 600, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {att.file_name}
                  </p>
                  <p style={{ margin: '2px 0 0', fontSize: '9px', color: '#606075' }}>
                    {FILE_TYPE_OPTIONS.find(o => o.value === att.file_type)?.label || att.file_type}
                    {' · '}
                    {new Date(att.uploaded_at).toLocaleDateString('es-CO')}
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                {att.presigned_url && (
                  <a
                    href={att.presigned_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      display: 'flex', alignItems: 'center', padding: '5px 7px', borderRadius: '6px',
                      background: 'rgba(255,255,255,0.05)', border: 'none', color: '#9ca3af', cursor: 'pointer', textDecoration: 'none',
                    }}
                  >
                    <Download size={12} />
                  </a>
                )}
                {userRole === 'superadmin' && (
                  <button
                    onClick={() => handleDelete(att.id)}
                    style={{ padding: '5px 7px', borderRadius: '6px', background: 'rgba(248,113,113,0.08)', border: 'none', color: '#f87171', cursor: 'pointer' }}
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Modal
// ---------------------------------------------------------------------------
export default function OrderDetailModal({ order, onClose, userRole }) {
  const [tab, setTab] = useState('detail');

  useEffect(() => {
    setTab('detail');
  }, [order?.id]);

  if (!order) return null;

  const tabs = [
    { id: 'detail', label: 'Detalle' },
    ...(!order.is_spare_part ? [{ id: 'vins', label: `VINs${order.moto_units?.length ? ` (${order.moto_units.length})` : ''}` }] : []),
    { id: 'docs', label: 'Documentos' },
  ];

  return (
    <>
      {/* Overlay */}
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(2px)' }}
      />

      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 201,
        width: 'min(640px, 95vw)',
        background: '#13131a', borderLeft: '1px solid rgba(255,255,255,0.08)',
        display: 'flex', flexDirection: 'column',
        boxShadow: '-8px 0 32px rgba(0,0,0,0.5)',
      }}>

        {/* Header */}
        <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <h2 style={{ margin: 0, color: '#fff', fontWeight: 800, fontSize: '16px', letterSpacing: '-0.01em' }}>
                  {order.pi_number}
                </h2>
                {order.is_spare_part && (
                  <span style={{ fontSize: '10px', fontWeight: 800, padding: '2px 7px', borderRadius: '6px', background: 'rgba(251,146,60,0.15)', color: '#fb923c' }}>
                    REPUESTOS
                  </span>
                )}
                <StatusBadge status={order.computed_status} type="computed_status" />
              </div>
              <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#9ca3af' }}>{order.model}</p>
            </div>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}>
              <X size={18} />
            </button>
          </div>

          {/* Timeline */}
          <div style={{ marginTop: '16px' }}>
            <TimelineBar order={order} />
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: '2px', padding: '0 24px', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                padding: '10px 16px', fontSize: '11px', fontWeight: 700, letterSpacing: '0.06em',
                textTransform: 'uppercase', background: 'transparent', border: 'none', cursor: 'pointer',
                color: tab === t.id ? '#ff5f33' : '#606075',
                borderBottom: tab === t.id ? '2px solid #ff5f33' : '2px solid transparent',
                transition: 'all 0.2s',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>

          {/* --- DETALLE --- */}
          {tab === 'detail' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Info general */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
                <Field label="Ciclo" value={order.cycle} />
                <Field label="PI Number" value={order.pi_number} />
                <Field label="Factura" value={order.invoice_number} />
                <Field label="Modelo" value={order.model} />
                <Field label="Año" value={order.model_year} />
                <Field label="Cantidad" value={order.qty} />
                <Field label="Unidades totales" value={order.total_units} />
                <Field label="Contenedores" value={order.containers} />
                <Field label="Puerto salida" value={order.departure_port} />
              </div>

              <div style={{ height: 1, background: 'rgba(255,255,255,0.05)' }} />

              {/* Logística */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '14px' }}>
                <Field label="Barco / Vessel" value={order.vessel} />
                <Field label="BL / Contenedor" value={order.bl_container} />
              </div>

              <div style={{ height: 1, background: 'rgba(255,255,255,0.05)' }} />

              {/* Docs */}
              <div>
                <p style={{ margin: '0 0 10px', fontSize: '9px', fontWeight: 700, color: '#606075', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Documentación</p>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                  <div>
                    <p style={{ margin: '0 0 4px', fontSize: '9px', color: '#606075' }}>Digital</p>
                    <StatusBadge status={order.digital_docs_status} type="docs_status" />
                  </div>
                  <div>
                    <p style={{ margin: '0 0 4px', fontSize: '9px', color: '#606075' }}>Original</p>
                    <StatusBadge status={order.original_docs_status} type="docs_status" />
                  </div>
                </div>
              </div>

              {/* Remarks */}
              {order.remarks && (
                <>
                  <div style={{ height: 1, background: 'rgba(255,255,255,0.05)' }} />
                  <div>
                    <p style={{ margin: '0 0 6px', fontSize: '9px', fontWeight: 700, color: '#606075', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Observaciones</p>
                    <p style={{ margin: 0, fontSize: '12px', color: '#d1d5db', lineHeight: 1.5 }}>{order.remarks}</p>
                  </div>
                </>
              )}

              {/* SP info */}
              {order.is_spare_part && order.parent_pi_number && (
                <>
                  <div style={{ height: 1, background: 'rgba(255,255,255,0.05)' }} />
                  <Field label="PI Moto Padre" value={order.parent_pi_number} />
                </>
              )}
            </div>
          )}

          {/* --- VINs --- */}
          {tab === 'vins' && <VinsTab units={order.moto_units} />}

          {/* --- DOCUMENTOS --- */}
          {tab === 'docs' && <DocsTab orderId={order.id} userRole={userRole} />}
        </div>
      </div>
    </>
  );
}
