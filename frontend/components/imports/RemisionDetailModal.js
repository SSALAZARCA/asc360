'use client';
import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Package } from 'lucide-react';
import { useRemisiones } from '../../lib/useRemisiones';
import { TYPE_LABELS, StatusBadge } from './remisionLabels';

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' });
}

function Field({ label, value }) {
  return (
    <div>
      <p style={{ margin: 0, fontSize: '9px', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </p>
      <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#e5e7eb' }}>
        {value ?? '—'}
      </p>
    </div>
  );
}

export default function RemisionDetailModal({ remisionId, onClose }) {
  const api = useRemisiones();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.getRemision(remisionId);
        if (!res.ok) { if (!cancelled) setError('No se pudo cargar el detalle.'); return; }
        const data = await res.json();
        if (!cancelled) setDetail(data);
      } catch {
        if (!cancelled) setError('Error de conexión.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [remisionId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(4px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#13131f',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 12,
          padding: '1.5rem',
          width: '100%', maxWidth: 520,
          maxHeight: '80vh', overflowY: 'auto',
          margin: '0 1rem',
          boxShadow: '0 24px 48px rgba(0,0,0,0.6)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
          <Package size={16} color="#ff5f33" />
          <span style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>
            {detail?.remision_number || 'Detalle de Remisión'}
          </span>
          <button
            onClick={onClose}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '2px' }}
          >
            <X size={16} />
          </button>
        </div>

        {loading && <p style={{ fontSize: '12px', color: '#606075', textAlign: 'center', margin: '24px 0' }}>Cargando...</p>}
        {error && <p style={{ fontSize: '12px', color: '#f87171', textAlign: 'center', margin: '24px 0' }}>{error}</p>}

        {detail && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <StatusBadge status={detail.status} />
              <span style={{ fontSize: '11px', color: '#9ca3af' }}>{TYPE_LABELS[detail.type] || detail.type}</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <Field label="Creado" value={fmtDate(detail.created_at)} />
              <Field label="Despachado" value={detail.dispatched_at ? fmtDate(detail.dispatched_at) : '—'} />
              {detail.status === 'ANULADO' && (
                <>
                  <Field label="Anulado" value={fmtDate(detail.cancelled_at)} />
                  <Field label="Motivo de anulación" value={detail.cancellation_reason} />
                </>
              )}
            </div>

            {detail.notes && <Field label="Notas" value={detail.notes} />}

            <div>
              <p style={{ margin: '0 0 6px', fontSize: '9px', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Ítems despachados
              </p>
              {detail.items?.length ? (
                <div style={{ borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
                    <thead>
                      <tr style={{ background: '#0e0e14' }}>
                        <th style={{ padding: '8px 10px', textAlign: 'left', color: '#606075', fontSize: '9px', textTransform: 'uppercase' }}>Part Number</th>
                        <th style={{ padding: '8px 10px', textAlign: 'right', color: '#606075', fontSize: '9px', textTransform: 'uppercase' }}>Cantidad</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.items.map(it => (
                        <tr key={it.id} style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                          <td style={{ padding: '8px 10px', color: '#d1d5db', fontFamily: 'monospace' }}>{it.part_number}</td>
                          <td style={{ padding: '8px 10px', color: '#d1d5db', textAlign: 'right' }}>{it.qty_dispatched}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p style={{ fontSize: '11px', color: '#606075', margin: 0 }}>Sin ítems.</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
