'use client';
import { useState, useEffect } from 'react';
import { authFetch } from '../../lib/authFetch';
import { getApiUrl } from '../../lib/api';
import { X, CheckCircle, AlertCircle, XCircle, Plus, Upload, AlertTriangle } from 'lucide-react';
import { toast } from '../../lib/toast';

const RESULT_CFG = {
  COMPLETE: { label: 'Completo', color: '#22c55e', bg: 'rgba(34,197,94,0.1)', border: 'rgba(34,197,94,0.25)', icon: CheckCircle },
  PARTIAL:  { label: 'Parcial',  color: '#fb923c', bg: 'rgba(251,146,60,0.1)', border: 'rgba(251,146,60,0.25)', icon: AlertCircle },
  MISSING:  { label: 'Faltante', color: '#f87171', bg: 'rgba(248,113,113,0.1)', border: 'rgba(248,113,113,0.25)', icon: XCircle },
  EXTRA:    { label: 'Extra',    color: '#a78bfa', bg: 'rgba(167,139,250,0.1)', border: 'rgba(167,139,250,0.25)', icon: Plus },
};

const WARNING_LABELS = {
  duplicate_content: 'Este archivo ya fue subido antes para este lote (mismo contenido).',
  duplicate_filename: 'Ya existe un archivo con este mismo nombre pero contenido distinto.',
};

function extractErrorMessage(data, fallback) {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return detail.detail || fallback;
  return fallback;
}

function ResultBadge({ result }) {
  const cfg = RESULT_CFG[result] || RESULT_CFG.MISSING;
  return (
    <span style={{
      display: 'inline-block', fontSize: '9px', fontWeight: 700, letterSpacing: '0.05em',
      padding: '2px 7px', borderRadius: '20px',
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`, whiteSpace: 'nowrap',
    }}>{cfg.label}</span>
  );
}

function SummaryCard({ label, count, result }) {
  const cfg = RESULT_CFG[result];
  return (
    <div style={{ padding: '12px 16px', borderRadius: '10px', background: cfg.bg, border: `1px solid ${cfg.border}`, textAlign: 'center' }}>
      <p style={{ margin: 0, fontSize: '22px', fontWeight: 800, color: cfg.color }}>{count}</p>
      <p style={{ margin: '2px 0 0', fontSize: '9px', fontWeight: 700, color: cfg.color, letterSpacing: '0.06em', textTransform: 'uppercase' }}>{label}</p>
    </div>
  );
}

export default function BackorderReconciliationModal({ lot, onClose, onConfirmed }) {
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmResult, setConfirmResult] = useState(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [loadingExisting, setLoadingExisting] = useState(true);

  // Al abrir la ventana, preguntarle al servidor si ya hay un remanente
  // cargado/confirmado para este lote — para que no arranque siempre vacía
  // ni "olvide" que ya se confirmó, igual que la conciliación del pedido.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch(`${getApiUrl()}/imports/spare-part-lots/${lot.id}/backorder-reconciliation/latest`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled || !data.batch_id) return;

        setUploadResult({
          batch_id: data.batch_id,
          is_invoice: data.is_invoice,
          counts: data.counts,
          lines: data.lines,
          warnings: [],
        });

        if (data.status === 'CONFIRMED' && data.confirmed_summary) {
          setConfirmResult({
            confirmed: true,
            batch_id: data.batch_id,
            qty_applied: data.confirmed_summary.qty_applied,
            backorders_resolved: data.confirmed_summary.backorders_resolved,
            backorders_updated: data.confirmed_summary.backorders_updated,
            skipped_missing_price: data.skipped_missing_price || [],
          });
        }
      } catch {
        // Silencioso: si falla la consulta, la ventana arranca vacía como antes.
      } finally {
        if (!cancelled) setLoadingExisting(false);
      }
    })();
    return () => { cancelled = true; };
  }, [lot.id]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    setConfirmResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await authFetch(
        `${getApiUrl()}/imports/spare-part-lots/${lot.id}/backorder-packing-list`,
        { method: 'POST', body: formData, headers: {} }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(extractErrorMessage(data, 'Error al procesar el archivo'));
      setUploadResult(data);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleConfirm = async () => {
    if (!uploadResult?.batch_id) return;
    setShowConfirmDialog(false);
    setConfirming(true);
    try {
      const res = await authFetch(
        `${getApiUrl()}/imports/spare-part-lots/${lot.id}/backorder-reconciliation/confirm`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ batch_id: uploadResult.batch_id }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(extractErrorMessage(data, 'Error al confirmar'));
      setConfirmResult(data);
      onConfirmed?.();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setConfirming(false);
    }
  };

  const lines = uploadResult?.lines || [];
  const counts = uploadResult?.counts || { complete: 0, partial: 0, missing: 0, extra: 0 };
  const warnings = uploadResult?.warnings || [];
  const hasResult = !!uploadResult && !uploadError;
  const confirmed = !!confirmResult;

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 300, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(3px)' }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
        zIndex: 301, width: 'min(760px, 95vw)', maxHeight: '88vh',
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', display: 'flex', flexDirection: 'column',
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>

        {/* Header */}
        <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h2 style={{ margin: 0, color: '#fff', fontWeight: 800, fontSize: '15px' }}>Reconciliación de Backorders</h2>
              <p style={{ margin: '3px 0 0', fontSize: '11px', color: '#60a5fa', fontFamily: 'monospace' }}>{lot.lot_identifier}</p>
            </div>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}>
              <X size={18} />
            </button>
          </div>

          <div style={{ marginTop: '14px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
            <label style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px',
              background: uploading ? 'rgba(255,95,51,0.1)' : 'rgba(255,95,51,0.15)',
              color: '#ff5f33', fontSize: '11px', fontWeight: 700,
              cursor: uploading || confirmed ? 'not-allowed' : 'pointer', border: 'none',
            }}>
              <Upload size={12} />
              {uploading ? 'Procesando...' : hasResult ? 'Reemplazar packing list remanente' : 'Subir packing list remanente'}
              <input type="file" accept=".xlsx" onChange={handleUpload} disabled={uploading || confirmed} style={{ display: 'none' }} />
            </label>
            {uploadError && (
              <span style={{ fontSize: '11px', color: '#f87171' }}>{uploadError}</span>
            )}
          </div>

          {warnings.length > 0 && (
            <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {warnings.map(w => (
                <div key={w} style={{
                  display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px',
                  borderRadius: '8px', background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.25)',
                }}>
                  <AlertTriangle size={13} style={{ color: '#fbbf24', flexShrink: 0 }} />
                  <span style={{ fontSize: '11px', color: '#fbbf24' }}>{WARNING_LABELS[w] || w}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Cuerpo */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {loadingExisting ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: '#606075' }}>
              <p style={{ fontSize: '12px', margin: 0 }}>Cargando...</p>
            </div>
          ) : !hasResult ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: '#606075' }}>
              <Upload size={32} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
              <p style={{ fontSize: '13px', margin: 0 }}>Subí el packing list remanente para cruzarlo contra los backorders abiertos de este lote</p>
            </div>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '20px' }}>
                <SummaryCard label="Completo"  count={counts.complete} result="COMPLETE" />
                <SummaryCard label="Parcial"   count={counts.partial}  result="PARTIAL" />
                <SummaryCard label="Faltante"  count={counts.missing}  result="MISSING" />
                <SummaryCard label="Extra"     count={counts.extra}    result="EXTRA" />
              </div>

              <div style={{ overflowX: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
                  <thead>
                    <tr style={{ background: '#0e0e14' }}>
                      {['Parte #', 'Moto', 'Pendiente', 'En PL', 'A aplicar', 'Resultado'].map(h => (
                        <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: '9px', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.07em', borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map(l => (
                      <tr key={l.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                        <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace' }}>{l.part_number}</td>
                        <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', fontSize: '9px', fontWeight: 700, color: '#60a5fa' }}>{l.model_applicable || '—'}</td>
                        <td style={{ padding: '8px 12px', color: '#d1d5db', textAlign: 'right' }}>{l.qty_pending_snapshot ?? '—'}</td>
                        <td style={{ padding: '8px 12px', color: '#d1d5db', textAlign: 'right' }}>{l.qty_in_packing ?? 0}</td>
                        <td style={{ padding: '8px 12px', color: '#d1d5db', textAlign: 'right' }}>{l.qty_applied ?? 0}</td>
                        <td style={{ padding: '8px 12px' }}><ResultBadge result={l.result} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {confirmed && confirmResult?.skipped_missing_price?.length > 0 && (
                <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {confirmResult.skipped_missing_price.map(s => (
                    <div key={s.part_number} style={{
                      display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px',
                      borderRadius: '8px', background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.25)',
                    }}>
                      <AlertTriangle size={13} style={{ color: '#fbbf24', flexShrink: 0 }} />
                      <span style={{ fontSize: '11px', color: '#fbbf24' }}>{s.part_number}: sin precio en la factura — no se aplicó</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {hasResult && (
          <div style={{ padding: '16px 24px', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
            <p style={{ margin: 0, fontSize: '11px', color: '#606075' }}>
              {counts.missing > 0 && `${counts.missing} parte${counts.missing !== 1 ? 's' : ''} seguirá${counts.missing !== 1 ? 'n' : ''} en backorder`}
            </p>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button onClick={onClose} style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', background: 'transparent', color: '#606075', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}>
                Cerrar
              </button>
              {!confirmed ? (
                <button
                  onClick={() => setShowConfirmDialog(true)}
                  disabled={confirming}
                  style={{
                    padding: '8px 20px', borderRadius: '8px', border: 'none',
                    background: confirming ? 'rgba(34,197,94,0.3)' : '#22c55e',
                    color: '#fff', cursor: confirming ? 'not-allowed' : 'pointer',
                    fontSize: '12px', fontWeight: 700,
                  }}
                >
                  {confirming ? 'Confirmando...' : 'Confirmar recepción'}
                </button>
              ) : (
                <span style={{ padding: '8px 16px', fontSize: '12px', fontWeight: 700, color: '#22c55e' }}>
                  ✓ Confirmado — {confirmResult.qty_applied} unidades, {confirmResult.backorders_resolved} backorder{confirmResult.backorders_resolved !== 1 ? 's' : ''} resuelto{confirmResult.backorders_resolved !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Diálogo de confirmación inline */}
      {showConfirmDialog && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 400, background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowConfirmDialog(false)} />
          <div style={{
            position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
            zIndex: 401, width: '420px', maxWidth: '95vw',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '16px', padding: '28px',
            boxShadow: '0 32px 80px rgba(0,0,0,0.7)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: 'rgba(34,197,94,0.12)', border: '1px solid rgba(34,197,94,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <CheckCircle size={20} style={{ color: '#22c55e' }} />
              </div>
              <div>
                <p style={{ margin: 0, fontWeight: 800, fontSize: '14px', color: '#fff' }}>Confirmar recepción de backorders</p>
                <p style={{ margin: '2px 0 0', fontSize: '11px', color: '#606075' }}>{lot.lot_identifier}</p>
              </div>
            </div>

            <p style={{ fontSize: '12px', color: '#9ca3af', lineHeight: 1.6, margin: '0 0 20px' }}>
              Se sumará la cantidad recibida a lo que ya tenía cada ítem y se cerrarán los backorders que queden en 0. Las partes marcadas como Faltante quedan pendientes para una próxima carga.
            </p>

            <p style={{ fontSize: '11px', color: '#f87171', margin: '0 0 20px', fontWeight: 600 }}>
              Esta acción no se puede deshacer.
            </p>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowConfirmDialog(false)}
                style={{ padding: '9px 18px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', background: 'transparent', color: '#606075', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}
              >
                Cancelar
              </button>
              <button
                onClick={handleConfirm}
                style={{ padding: '9px 20px', borderRadius: '8px', border: 'none', background: '#22c55e', color: '#fff', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}
              >
                Sí, confirmar
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
