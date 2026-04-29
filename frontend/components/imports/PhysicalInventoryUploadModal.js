'use client';
import { useState, useRef } from 'react';
import { authFetch } from '../../lib/authFetch';
import { Upload, CheckCircle, XCircle, MinusCircle, AlertTriangle, RefreshCw } from 'lucide-react';

function API() {
  return (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');
}

function Section({ icon: Icon, color, title, count, children }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={{ borderRadius: '10px', border: `1px solid ${color}22`, overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
          padding: '10px 14px', background: `${color}11`, border: 'none', cursor: 'pointer', textAlign: 'left',
        }}
      >
        <Icon size={13} color={color} />
        <span style={{ fontSize: '11px', fontWeight: 700, color, flex: 1 }}>{title}</span>
        <span style={{
          fontSize: '10px', fontWeight: 800, color, background: `${color}22`,
          padding: '1px 8px', borderRadius: '20px',
        }}>{count}</span>
        <span style={{ fontSize: '9px', color: '#606075' }}>{open ? '▲' : '▼'}</span>
      </button>
      {open && children}
    </div>
  );
}

function ItemRow({ partNumber, description, tag, tagColor }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '8px',
      padding: '6px 14px', borderBottom: '1px solid rgba(255,255,255,0.03)',
    }}>
      <span style={{ fontFamily: 'monospace', fontSize: '10px', fontWeight: 700, color: '#60a5fa', minWidth: 100 }}>
        {partNumber}
      </span>
      <span style={{ fontSize: '10px', color: '#9ca3af', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {description || '—'}
      </span>
      {tag != null && (
        <span style={{ fontSize: '10px', fontWeight: 700, color: tagColor, whiteSpace: 'nowrap' }}>
          {tag}
        </span>
      )}
    </div>
  );
}

export default function PhysicalInventoryUploadModal({ lotId, onClose, onApplied }) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef();

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError('');
    setPreview(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await authFetch(`${API()}/imports/lots/${lotId}/physical-inspection-preview`, {
        method: 'POST',
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.detail || err?.detail || 'Error al procesar el archivo');
      }
      setPreview(await res.json());
    } catch (err) {
      setError(err.message || 'Error al procesar el archivo');
    } finally {
      setLoading(false);
      e.target.value = '';
    }
  };

  const handleApply = async () => {
    if (!preview) return;
    setApplying(true);
    try {
      const items = [
        ...preview.matched.map(m => ({ item_id: m.item_id, qty_physical: m.qty_physical })),
        ...preview.zeroed.map(z => ({ item_id: z.item_id, qty_physical: 0 })),
      ];
      const res = await authFetch(`${API()}/imports/lots/${lotId}/physical-inspection-apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.detail || err?.detail || 'Error al aplicar');
      }
      const result = await res.json();
      onApplied?.(result.applied);
      onClose();
    } catch (err) {
      setError(err.message || 'Error al aplicar inventario');
    } finally {
      setApplying(false);
    }
  };

  const totalToApply = preview ? preview.matched.length + preview.zeroed.length : 0;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#16161f', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px',
        width: 560, maxHeight: '85vh', display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{ padding: '18px 20px 14px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Upload size={15} color="#fb923c" />
          <span style={{ fontWeight: 700, fontSize: '13px', color: '#fff', flex: 1 }}>
            Cargar inventario físico desde Excel
          </span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', fontSize: '16px', lineHeight: 1 }}>×</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>

          {/* File picker */}
          <div
            onClick={() => fileRef.current?.click()}
            style={{
              border: '2px dashed rgba(251,146,60,0.3)', borderRadius: '10px',
              padding: '20px', textAlign: 'center', cursor: 'pointer',
              background: 'rgba(251,146,60,0.04)',
              transition: 'border-color 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'rgba(251,146,60,0.6)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(251,146,60,0.3)'}
          >
            <input ref={fileRef} type="file" accept=".xlsx,.xls" onChange={handleFile} style={{ display: 'none' }} />
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', color: '#9ca3af', fontSize: '12px' }}>
                <RefreshCw size={13} style={{ animation: 'spin 1s linear infinite' }} />
                Procesando archivo...
              </div>
            ) : (
              <>
                <Upload size={18} color="#fb923c" style={{ margin: '0 auto 6px', display: 'block' }} />
                <p style={{ margin: 0, fontSize: '12px', color: '#d1d5db', fontWeight: 600 }}>
                  {preview ? 'Seleccionar otro archivo' : 'Seleccionar archivo Excel'}
                </p>
                <p style={{ margin: '4px 0 0', fontSize: '10px', color: '#606075' }}>
                  Dos columnas: código de parte · cantidad física
                </p>
              </>
            )}
          </div>

          {error && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', borderRadius: '8px', background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.2)' }}>
              <AlertTriangle size={13} color="#f87171" />
              <span style={{ fontSize: '11px', color: '#f87171' }}>{error}</span>
            </div>
          )}

          {/* Preview */}
          {preview && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <Section icon={CheckCircle} color="#22c55e" title="Se van a actualizar" count={preview.matched.length}>
                {preview.matched.length === 0 ? (
                  <p style={{ margin: 0, padding: '10px 14px', fontSize: '10px', color: '#606075' }}>Ninguna parte coincide.</p>
                ) : preview.matched.map(m => (
                  <ItemRow key={m.item_id} partNumber={m.part_number} description={m.description_es} tag={`${m.qty_physical} uds`} tagColor="#22c55e" />
                ))}
              </Section>

              <Section icon={MinusCircle} color="#9ca3af" title="Se van a poner en 0 (no están en el Excel)" count={preview.zeroed.length}>
                {preview.zeroed.length === 0 ? (
                  <p style={{ margin: 0, padding: '10px 14px', fontSize: '10px', color: '#606075' }}>Ninguna.</p>
                ) : preview.zeroed.map(z => (
                  <ItemRow key={z.item_id} partNumber={z.part_number} description={z.description_es} tag="0 uds" tagColor="#9ca3af" />
                ))}
              </Section>

              {preview.ignored.length > 0 && (
                <Section icon={XCircle} color="#f87171" title="En el Excel pero no en este pedido (se ignoran)" count={preview.ignored.length}>
                  {preview.ignored.map(ig => (
                    <ItemRow key={ig.code} partNumber={ig.code} description={null} tag={`${ig.qty} uds`} tagColor="#f87171" />
                  ))}
                </Section>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: '14px 20px', borderTop: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{ padding: '8px 18px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)', background: 'transparent', color: '#9ca3af', fontSize: '11px', cursor: 'pointer' }}
          >
            Cancelar
          </button>
          {preview && (
            <button
              onClick={handleApply}
              disabled={applying || totalToApply === 0}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '8px 20px', borderRadius: '8px', border: 'none',
                background: totalToApply > 0 ? '#fb923c' : 'rgba(251,146,60,0.3)',
                color: totalToApply > 0 ? '#fff' : '#606075',
                fontSize: '11px', fontWeight: 700, cursor: totalToApply > 0 ? 'pointer' : 'default',
              }}
            >
              {applying ? <RefreshCw size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <CheckCircle size={11} />}
              Aplicar a {totalToApply} ítem{totalToApply !== 1 ? 's' : ''}
            </button>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
