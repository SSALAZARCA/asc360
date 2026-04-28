'use client';
import { useState, useEffect } from 'react';
import { authFetch } from '../../lib/authFetch';
import { X, CheckCircle, AlertCircle, XCircle, Plus, Upload, RefreshCw } from 'lucide-react';

function API() {
  return (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');
}

const RESULT_CFG = {
  COMPLETE:      { label: 'Completo',       color: '#22c55e', bg: 'rgba(34,197,94,0.1)',    border: 'rgba(34,197,94,0.25)',   icon: CheckCircle },
  PARTIAL:       { label: 'Parcial',        color: '#fb923c', bg: 'rgba(251,146,60,0.1)',   border: 'rgba(251,146,60,0.25)',  icon: AlertCircle },
  MISSING:       { label: 'Faltante',       color: '#f87171', bg: 'rgba(248,113,113,0.1)',  border: 'rgba(248,113,113,0.25)', icon: XCircle },
  EXTRA:         { label: 'Extra',          color: '#a78bfa', bg: 'rgba(167,139,250,0.1)',  border: 'rgba(167,139,250,0.25)', icon: Plus },
  EXTRA_APPLIED: { label: 'Extra → BO',    color: '#34d399', bg: 'rgba(52,211,153,0.1)',   border: 'rgba(52,211,153,0.25)',  icon: CheckCircle },
};

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

function EditableReconciliationCell({ resultId, field, current, type = 'text', align = 'left', cellStyle = {}, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [hover, setHover] = useState(false);
  const [value, setValue] = useState(current ?? '');

  const save = async () => {
    setEditing(false);
    const parsed = type === 'number' ? (value === '' ? null : parseInt(value, 10)) : (String(value).trim() || null);
    if (parsed === (current ?? null)) return;
    try {
      await authFetch(`${API()}/imports/reconciliation-results/${resultId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: parsed }),
      });
      onSaved?.();
    } catch { setValue(current ?? ''); }
  };

  if (editing) {
    return (
      <input
        autoFocus
        type={type}
        value={value}
        onChange={e => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setValue(current ?? ''); setEditing(false); } }}
        style={{
          width: type === 'number' ? 65 : '100%', minWidth: type === 'text' ? 80 : undefined,
          fontSize: '11px', padding: '2px 6px', borderRadius: '6px',
          background: '#1a1a24', border: '1px solid #60a5fa', color: '#fff', outline: 'none',
          textAlign: align, ...cellStyle,
        }}
      />
    );
  }

  return (
    <span
      onClick={() => { setEditing(true); setValue(current ?? ''); }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title="Click para editar"
      style={{
        cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: '2px 5px', borderRadius: 5, textAlign: align,
        background: hover ? 'rgba(96,165,250,0.1)' : 'transparent',
        border: hover ? '1px solid rgba(96,165,250,0.3)' : '1px solid transparent',
        transition: 'all 0.15s', ...cellStyle,
      }}
    >
      {current != null && current !== '' ? current : <span style={{ color: '#3f3f55' }}>—</span>}
      {hover && <span style={{ fontSize: 9, opacity: 0.6 }}>✏</span>}
    </span>
  );
}

export default function ReconciliationModal({ lot, onClose, onConfirmed }) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [filterResult, setFilterResult] = useState('');
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  const fetchResults = async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API()}/imports/spare-part-lots/${lot.id}/reconciliation`);
      const data = await res.json();
      setResults(Array.isArray(data) ? data : []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchResults(); }, [lot.id]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await authFetch(
        `${API()}/imports/spare-part-lots/${lot.id}/packing-list`,
        { method: 'POST', body: formData, headers: {} }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Error al procesar el archivo');
      setUploadResult(data);
      await fetchResults();
    } catch (err) {
      setUploadResult({ error: err.message });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleConfirm = async () => {
    setShowConfirmDialog(false);
    setConfirming(true);
    try {
      const res = await authFetch(
        `${API()}/imports/spare-part-lots/${lot.id}/reconciliation/confirm`,
        { method: 'POST' }
      );
      if (!res.ok) throw new Error('Error al confirmar');
      setConfirmed(true);
      onConfirmed?.();
    } catch (err) {
      alert(err.message);
    } finally {
      setConfirming(false);
    }
  };

  // Conteos
  const counts = { COMPLETE: 0, PARTIAL: 0, MISSING: 0, EXTRA: 0, EXTRA_APPLIED: 0 };
  results.forEach(r => { if (counts[r.result] !== undefined) counts[r.result]++; });

  const filtered = filterResult ? results.filter(r => r.result === filterResult) : results;
  const hasResults = results.length > 0;

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 300, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(3px)' }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
        zIndex: 301, width: 'min(780px, 95vw)', maxHeight: '88vh',
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', display: 'flex', flexDirection: 'column',
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>

        {/* Header */}
        <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h2 style={{ margin: 0, color: '#fff', fontWeight: 800, fontSize: '15px' }}>Reconciliación de Packing List</h2>
              <p style={{ margin: '3px 0 0', fontSize: '11px', color: '#60a5fa', fontFamily: 'monospace' }}>{lot.lot_identifier}</p>
            </div>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}>
              <X size={18} />
            </button>
          </div>

          {/* Upload section */}
          <div style={{ marginTop: '14px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
            <label style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px',
              background: uploading ? 'rgba(255,95,51,0.1)' : 'rgba(255,95,51,0.15)',
              color: '#ff5f33', fontSize: '11px', fontWeight: 700,
              cursor: uploading ? 'not-allowed' : 'pointer', border: 'none',
            }}>
              <Upload size={12} />
              {uploading ? 'Procesando...' : hasResults ? 'Reemplazar Packing List' : 'Subir Packing List'}
              <input type="file" accept=".xlsx" onChange={handleUpload} disabled={uploading} style={{ display: 'none' }} />
            </label>
            {hasResults && (
              <button onClick={fetchResults} style={{ padding: '7px 9px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer', color: '#9ca3af' }}>
                <RefreshCw size={12} />
              </button>
            )}
            {uploadResult?.error && (
              <span style={{ fontSize: '11px', color: '#f87171' }}>{uploadResult.error}</span>
            )}
            {uploadResult && !uploadResult.error && (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', color: '#22c55e', fontWeight: 700 }}>
                  ✓ {uploadResult.total_parts_in_pl} partes leídas
                  {uploadResult.is_invoice && <span style={{ color: '#a78bfa', marginLeft: '4px' }}>(Invoice)</span>}
                </span>
                {[
                  { key: 'complete', label: 'Completo', color: '#22c55e' },
                  { key: 'partial',  label: 'Parcial',  color: '#fb923c' },
                  { key: 'missing',  label: 'Faltante', color: '#f87171' },
                  { key: 'extra',    label: 'Extra',    color: '#a78bfa' },
                ].filter(s => uploadResult[s.key] > 0).map(s => (
                  <span key={s.key} style={{ fontSize: '10px', fontWeight: 700, color: s.color }}>
                    {uploadResult[s.key]} {s.label}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Cuerpo */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {loading ? (
            <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '40px 0' }}>Cargando resultados...</p>
          ) : !hasResults ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: '#606075' }}>
              <Upload size={32} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
              <p style={{ fontSize: '13px', margin: 0 }}>Subí el packing list para comparar contra los ítems del lote</p>
            </div>
          ) : (
            <>
              {/* KPI cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px', marginBottom: '20px' }}>
                <SummaryCard label="Completo"    count={counts.COMPLETE}      result="COMPLETE"      />
                <SummaryCard label="Parcial"     count={counts.PARTIAL}       result="PARTIAL"       />
                <SummaryCard label="Faltante"    count={counts.MISSING}       result="MISSING"       />
                <SummaryCard label="Extra"       count={counts.EXTRA}         result="EXTRA"         />
                <SummaryCard label="Extra→BO"   count={counts.EXTRA_APPLIED} result="EXTRA_APPLIED" />
              </div>

              {/* Filtro */}
              <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap' }}>
                {['', 'COMPLETE', 'PARTIAL', 'MISSING', 'EXTRA', 'EXTRA_APPLIED'].map(r => (
                  <button
                    key={r || 'all'}
                    onClick={() => setFilterResult(r)}
                    style={{
                      padding: '4px 12px', borderRadius: '20px', fontSize: '10px', fontWeight: 700,
                      cursor: 'pointer', border: 'none',
                      background: filterResult === r
                        ? (r ? RESULT_CFG[r]?.bg : 'rgba(255,255,255,0.1)')
                        : 'rgba(255,255,255,0.04)',
                      color: filterResult === r
                        ? (r ? RESULT_CFG[r]?.color : '#fff')
                        : '#606075',
                    }}
                  >
                    {r ? RESULT_CFG[r]?.label : `Todos (${results.length})`}
                  </button>
                ))}
              </div>

              {/* Aviso inventario físico */}
              {!lot.packing_list_received && (
                <p style={{ margin: '0 0 10px', fontSize: '10px', color: '#fb923c', opacity: 0.7 }}>
                  ⚠ La columna <strong>Inv. Físico</strong> se habilita después de confirmar el cruce.
                </p>
              )}

              {/* Tabla */}
              <div style={{ overflowX: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
                  <thead>
                    <tr style={{ background: '#0e0e14' }}>
                      {['Parte #', 'Descripción', 'Moto', 'Qty Ord.', 'Qty PL', 'Inv. Físico', 'Dif.', 'Resultado'].map(h => (
                        <th key={h} style={{ padding: '8px 12px', textAlign: h === 'Inv. Físico' ? 'right' : 'left', fontSize: '9px', fontWeight: 700, color: h === 'Inv. Físico' ? '#fb923c' : '#606075', textTransform: 'uppercase', letterSpacing: '0.07em', borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(r => {
                      const diff = (r.qty_in_packing ?? 0) - (r.qty_ordered ?? 0);
                      const diffColor = diff === 0 ? '#22c55e' : diff > 0 ? '#a78bfa' : '#f87171';
                      return (
                        <tr key={r.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                          onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                          <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                            <EditableReconciliationCell resultId={r.id} field="part_number" current={r.part_number} onSaved={fetchResults} cellStyle={{ color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace' }} />
                          </td>
                          <td style={{ padding: '8px 12px', fontSize: '10px', maxWidth: 180 }}>
                            <EditableReconciliationCell resultId={r.id} field="description_es" current={r.description_es} onSaved={fetchResults} cellStyle={{ color: '#9ca3af', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} />
                          </td>
                          <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                            <EditableReconciliationCell resultId={r.id} field="model_applicable" current={r.model_applicable} onSaved={fetchResults} cellStyle={{ fontSize: '9px', fontWeight: 700, color: '#60a5fa' }} />
                          </td>
                          <td style={{ padding: '8px 12px', color: '#d1d5db', textAlign: 'right' }}>{r.qty_ordered ?? '—'}</td>
                          <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                            <EditableReconciliationCell resultId={r.id} field="qty_in_packing" current={r.qty_in_packing ?? 0} type="number" align="right" onSaved={fetchResults} cellStyle={{ color: '#d1d5db' }} />
                          </td>
                          <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                            {lot.packing_list_received ? (
                              <EditableReconciliationCell
                                resultId={r.id}
                                field="qty_physical"
                                current={r.qty_physical ?? r.qty_in_packing ?? 0}
                                type="number"
                                align="right"
                                onSaved={fetchResults}
                                cellStyle={{
                                  color: r.qty_physical != null && r.qty_physical !== r.qty_in_packing ? '#f87171' : '#9ca3af',
                                  fontStyle: r.qty_physical == null ? 'italic' : 'normal',
                                  opacity: r.qty_physical == null ? 0.5 : 1,
                                }}
                              />
                            ) : (
                              <span style={{ color: '#3f3f55', fontSize: '10px' }}>—</span>
                            )}
                          </td>
                          <td style={{ padding: '8px 12px', color: diffColor, textAlign: 'right', fontWeight: 700 }}>
                            {r.qty_ordered != null ? (diff > 0 ? `+${diff}` : diff) : '—'}
                          </td>
                          <td style={{ padding: '8px 12px' }}><ResultBadge result={r.result} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {hasResults && (
          <div style={{ padding: '16px 24px', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
            <p style={{ margin: 0, fontSize: '11px', color: '#606075' }}>
              {counts.MISSING > 0 && `${counts.MISSING} parte${counts.MISSING !== 1 ? 's' : ''} faltante${counts.MISSING !== 1 ? 's' : ''} → se marcarán como Backorder`}
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
                <span style={{ padding: '8px 16px', fontSize: '12px', fontWeight: 700, color: '#22c55e' }}>✓ Recepción confirmada</span>
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
                <p style={{ margin: 0, fontWeight: 800, fontSize: '14px', color: '#fff' }}>Confirmar recepción</p>
                <p style={{ margin: '2px 0 0', fontSize: '11px', color: '#606075' }}>{lot.lot_identifier}</p>
              </div>
            </div>

            <p style={{ fontSize: '12px', color: '#9ca3af', lineHeight: 1.6, margin: '0 0 16px' }}>
              Esta acción actualizará el estado de todos los ítems según el resultado del cruce:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '20px', maxHeight: '280px', overflowY: 'auto' }}>
              {[
                { result: 'COMPLETE', text: 'Completos → Recibidos' },
                { result: 'PARTIAL',  text: 'Parciales → Backorder por faltante' },
                { result: 'MISSING',  text: 'Faltantes → Backorder por total' },
              ].filter(r => counts[r.result] > 0).map(r => {
                const cfg = RESULT_CFG[r.result];
                const items = results.filter(x => x.result === r.result);
                return (
                  <div key={r.result} style={{ borderRadius: '8px', background: cfg.bg, border: `1px solid ${cfg.border}`, overflow: 'hidden' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '7px 10px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 800, color: cfg.color, minWidth: '24px' }}>{counts[r.result]}</span>
                      <span style={{ fontSize: '11px', color: cfg.color, fontWeight: 600 }}>{r.text}</span>
                    </div>
                    {items.slice(0, 4).map(item => (
                      <div key={item.id} style={{ padding: '4px 10px 4px 32px', borderTop: `1px solid ${cfg.border}`, display: 'flex', gap: '8px', alignItems: 'baseline' }}>
                        <span style={{ fontSize: '10px', fontFamily: 'monospace', color: cfg.color, opacity: 0.8, flexShrink: 0 }}>{item.part_number}</span>
                        {item.description_es && <span style={{ fontSize: '10px', color: '#606075', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description_es}</span>}
                      </div>
                    ))}
                    {items.length > 4 && (
                      <div style={{ padding: '4px 10px 6px 32px', borderTop: `1px solid ${cfg.border}` }}>
                        <span style={{ fontSize: '10px', color: '#606075' }}>+{items.length - 4} más...</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

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
