'use client';
import { useState, useEffect } from 'react';
import { authFetch } from '../../lib/authFetch';
import { ArrowUp, ArrowDown, ChevronsUpDown, RefreshCw, Download } from 'lucide-react';

const ROT = {
  baja:  { bg: 'rgba(74,222,128,0.12)',  color: '#4ade80',  border: 'rgba(74,222,128,0.3)',  label: 'BAJA'  },
  media: { bg: 'rgba(251,191,36,0.12)',  color: '#fbbf24',  border: 'rgba(251,191,36,0.3)',  label: 'MEDIA' },
  alta:  { bg: 'rgba(239,68,68,0.12)',   color: '#f87171',  border: 'rgba(239,68,68,0.3)',   label: 'ALTA'  },
};

const PI_STYLES = {
  '':          { bg: 'rgba(255,255,255,0.05)', border: 'rgba(255,255,255,0.1)',  piColor: 'rgba(255,255,255,0.7)', qtyColor: '#38bdf8',  prefix: null },
  'revisado':  { bg: 'rgba(74,222,128,0.1)',   border: 'rgba(74,222,128,0.35)', piColor: '#bbf7d0',               qtyColor: '#4ade80',  prefix: '✓' },
  'cancelar':  { bg: 'rgba(239,68,68,0.12)',   border: 'rgba(239,68,68,0.35)',   piColor: '#fca5a5',               qtyColor: '#f87171',  prefix: '✕' },
  'cambiar':   { bg: 'rgba(251,191,36,0.1)',   border: 'rgba(251,191,36,0.35)',  piColor: '#fde68a',               qtyColor: '#fbbf24',  prefix: '↺' },
};

function RotBadge({ rc }) {
  const s = ROT[rc] || {};
  return (
    <span style={{
      fontSize: '0.58rem', fontWeight: 800, textTransform: 'uppercase',
      letterSpacing: '0.08em', padding: '2px 8px', borderRadius: '20px',
      background: s.bg, color: s.color, border: `1px solid ${s.border}`, whiteSpace: 'nowrap',
    }}>{s.label}</span>
  );
}

function SortIcon({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <ChevronsUpDown size={10} style={{ opacity: 0.25, marginLeft: 3 }} />;
  return sortDir === 'asc'
    ? <ArrowUp   size={10} style={{ color: '#ff5f33', marginLeft: 3 }} />
    : <ArrowDown size={10} style={{ color: '#ff5f33', marginLeft: 3 }} />;
}

function ChangeModal({ fpn, lotId, lot, initialDetails, onSave, onUnmark, onClose }) {
  const [qty,  setQty]  = useState(initialDetails?.new_quantity ?? lot.qty);
  const [note, setNote] = useState(initialDetails?.change_note  ?? '');

  const inputStyle = {
    width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: '8px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.8rem',
    outline: 'none', boxSizing: 'border-box',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1001,
      background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#12121c', border: '1px solid rgba(251,191,36,0.3)',
        borderRadius: '16px', padding: '1.75rem', maxWidth: '400px', width: '90%',
      }}>
        <h3 style={{ margin: '0 0 0.3rem', color: '#fbbf24', fontSize: '0.9rem', fontWeight: 800 }}>
          ↺ Ajuste de cantidad / observación
        </h3>
        <p style={{ margin: '0 0 1.25rem', fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)' }}>
          <span style={{ fontFamily: 'monospace', color: '#ff5f33' }}>{fpn}</span>
          {' · '}
          <span style={{ color: 'rgba(255,255,255,0.6)' }}>{lotId}</span>
          {' · '}
          cantidad actual: <strong style={{ color: '#fff' }}>{lot.qty}</strong>
        </p>

        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.65rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>
            Nueva cantidad
          </label>
          <input
            type="number"
            min={1}
            value={qty}
            onChange={e => setQty(Number(e.target.value) || 1)}
            style={inputStyle}
          />
        </div>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', fontSize: '0.65rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>
            Observación <span style={{ fontWeight: 400, textTransform: 'none' }}>(opcional)</span>
          </label>
          <input
            type="text"
            value={note}
            onChange={e => setNote(e.target.value)}
            placeholder="Ej: venga sin pintar, color base"
            style={inputStyle}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.6rem', justifyContent: 'space-between' }}>
          <button
            onClick={onUnmark}
            style={{
              padding: '0.45rem 0.9rem', borderRadius: '8px', fontSize: '0.72rem', fontWeight: 700,
              background: 'none', border: '1px solid rgba(255,255,255,0.12)',
              color: 'rgba(255,255,255,0.35)', cursor: 'pointer',
            }}
          >
            Desmarcar
          </button>
          <div style={{ display: 'flex', gap: '0.6rem' }}>
            <button
              onClick={onClose}
              style={{
                padding: '0.45rem 0.9rem', borderRadius: '8px', fontSize: '0.72rem', fontWeight: 700,
                background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                color: 'rgba(255,255,255,0.5)', cursor: 'pointer',
              }}
            >
              Cancelar
            </button>
            <button
              onClick={() => onSave({
              new_quantity:      qty !== (initialDetails?.original_quantity ?? lot.qty) ? qty : null,
              change_note:       note,
              original_quantity: initialDetails?.original_quantity ?? lot.qty,
            })}
              style={{
                padding: '0.45rem 1.1rem', borderRadius: '8px', fontSize: '0.72rem', fontWeight: 800,
                background: 'rgba(251,191,36,0.15)', border: '1px solid rgba(251,191,36,0.4)',
                color: '#fbbf24', cursor: 'pointer',
              }}
            >
              Guardar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AnalisisRepuestosTab() {
  const [data,      setData]      = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [exporting, setExporting] = useState(false);
  const [rotFilter, setRotFilter] = useState('all');
  const [sortCol,   setSortCol]   = useState('rotation');
  const [sortDir,   setSortDir]   = useState('asc');

  // { "fpn::lotId": 'cancelar' | 'cambiar' }
  const [marked,      setMarked]      = useState({});
  // { "fpn::lotId": { new_quantity, change_note } }
  const [details,     setDetails]     = useState({});
  // Modal de detalle para ítems amarillos
  const [changeModal, setChangeModal] = useState(null);

  const [search,      setSearch]      = useState('');
  const [executing,   setExecuting]   = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [execResult,  setExecResult]  = useState(null);

  const load = () => {
    setLoading(true);
    Promise.all([
      authFetch('/parts/admin/analysis/low-rotation-ordered').then(r => r.ok ? r.json() : null),
      authFetch('/parts/admin/analysis/decisions').then(r => r.ok ? r.json() : null),
    ]).then(([analysisData, savedDecisions]) => {
      if (analysisData) setData(analysisData);
      if (savedDecisions !== null) {
        const marks = {};
        const dets  = {};
        for (const [key, val] of Object.entries(savedDecisions)) {
          const decision = typeof val === 'string' ? val : val.decision;
          if (decision) marks[key] = decision;
          if (typeof val === 'object' && (val.new_quantity != null || val.change_note || val.original_quantity != null)) {
            dets[key] = { new_quantity: val.new_quantity, change_note: val.change_note || '', original_quantity: val.original_quantity ?? null };
          }
        }
        setMarked(marks);
        setDetails(dets);
      }
      setLoading(false);
    }).catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const markKey = (fpn, lotId) => `${fpn}::${lotId}`;

  const toggleMark = (fpn, lotId, lot) => {
    const key     = markKey(fpn, lotId);
    const current = marked[key] || '';

    if (current === 'cambiar') {
      setChangeModal({ key, fpn, lotId, lot });
      return;
    }

    const next = current === '' ? 'revisado' : current === 'revisado' ? 'cancelar' : 'cambiar';

    setMarked(prev => ({ ...prev, [key]: next }));

    authFetch('/parts/admin/analysis/decisions', {
      method: 'POST',
      body: JSON.stringify({ factory_part_number: fpn, lot_identifier: lotId, decision: next }),
    }).catch(() => {
      setMarked(prev => {
        const copy = { ...prev };
        if (!current) delete copy[key]; else copy[key] = current;
        return copy;
      });
    });
  };

  const handleSaveDetails = async (det) => {
    const { key, fpn, lotId } = changeModal;
    setChangeModal(null);
    setDetails(prev => ({ ...prev, [key]: det }));
    await authFetch('/parts/admin/analysis/decisions', {
      method: 'POST',
      body: JSON.stringify({
        factory_part_number: fpn,
        lot_identifier:      lotId,
        decision:            'cambiar',
        new_quantity:        det.new_quantity,
        original_quantity:   det.original_quantity ?? null,
        change_note:         det.change_note || null,
      }),
    });
  };

  const handleUnmarkFromModal = async () => {
    const { key, fpn, lotId } = changeModal;
    setChangeModal(null);
    setMarked(prev => { const c = { ...prev }; delete c[key]; return c; });
    setDetails(prev => { const c = { ...prev }; delete c[key]; return c; });
    await authFetch('/parts/admin/analysis/decisions', {
      method: 'POST',
      body: JSON.stringify({ factory_part_number: fpn, lot_identifier: lotId, decision: '' }),
    });
  };

  const handleExecuteAdjustments = async () => {
    setConfirmOpen(false);
    setExecuting(true);
    setExecResult(null);
    try {
      const res  = await authFetch('/parts/admin/analysis/decisions/execute', { method: 'POST' });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || 'Error al ejecutar');
      setExecResult(json);
      load();
    } catch (e) {
      setExecResult({ error: e.message });
    } finally {
      setExecuting(false);
    }
  };

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir(col === 'rotation' ? 'asc' : 'desc'); }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await authFetch('/parts/admin/analysis/low-rotation-ordered/export', {
        method: 'POST',
        body: JSON.stringify({ marked }),
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `analisis_repuestos_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  const searchNorm = search.trim().toUpperCase();
  const items = (data?.items || []).filter(i =>
    (rotFilter === 'all' || i.rotation_class === rotFilter) &&
    (!searchNorm || i.factory_part_number.toUpperCase().includes(searchNorm))
  );

  const sorted = [...items].sort((a, b) => {
    let av, bv;
    if      (sortCol === 'rotation')  { av = a.rotation_class === 'baja' ? 0 : 1; bv = b.rotation_class === 'baja' ? 0 : 1; }
    else if (sortCol === 'total_qty') { av = a.total_qty;   bv = b.total_qty;   }
    else                              { av = a.lots.length; bv = b.lots.length; }
    return sortDir === 'asc' ? av - bv : bv - av;
  });

  const markedCancelar = Object.entries(marked)
    .filter(([, v]) => v === 'cancelar')
    .map(([k]) => { const [fpn, pi] = k.split('::'); return { fpn, pi }; });
  const markedCambiar  = Object.entries(marked)
    .filter(([, v]) => v === 'cambiar')
    .map(([k]) => { const [fpn, pi] = k.split('::'); return { fpn, pi, det: details[k] }; });
  const hasMarked = markedCancelar.length > 0 || markedCambiar.length > 0;

  const cancelFobTotal = markedCancelar.reduce((total, { fpn, pi }) => {
    const item = (data?.items || []).find(i => i.factory_part_number === fpn);
    const lot  = item?.lots.find(l => l.lot_identifier === pi);
    if (!lot || lot.fob_unit == null) return total;
    return total + lot.fob_unit * lot.qty;
  }, 0);
  const cancelFobHasData = markedCancelar.some(({ fpn, pi }) => {
    const item = (data?.items || []).find(i => i.factory_part_number === fpn);
    const lot  = item?.lots.find(l => l.lot_identifier === pi);
    return lot?.fob_unit != null;
  });

  const cambiarFobDelta = markedCambiar.reduce((total, { fpn, pi, det }) => {
    if (det?.new_quantity == null) return total;
    const item     = (data?.items || []).find(i => i.factory_part_number === fpn);
    const lot      = item?.lots.find(l => l.lot_identifier === pi);
    if (!lot || lot.fob_unit == null) return total;
    const original = det.original_quantity ?? lot.qty;
    const delta    = original - det.new_quantity;
    if (delta <= 0) return total;
    return total + lot.fob_unit * delta;
  }, 0);
  const cambiarFobHasData = markedCambiar.some(({ fpn, pi, det }) => {
    if (det?.new_quantity == null) return false;
    const item = (data?.items || []).find(i => i.factory_part_number === fpn);
    const lot  = item?.lots.find(l => l.lot_identifier === pi);
    return lot?.fob_unit != null;
  });
  const markedCambiarConReduccion = markedCambiar.filter(({ fpn, pi, det }) => {
    if (det?.new_quantity == null) return false;
    const item     = (data?.items || []).find(i => i.factory_part_number === fpn);
    const lot      = item?.lots.find(l => l.lot_identifier === pi);
    const original = det.original_quantity ?? lot?.qty ?? 0;
    return det.new_quantity < original;
  });

  const cambiarFobAumento = markedCambiar.reduce((total, { fpn, pi, det }) => {
    if (det?.new_quantity == null) return total;
    const item     = (data?.items || []).find(i => i.factory_part_number === fpn);
    const lot      = item?.lots.find(l => l.lot_identifier === pi);
    if (!lot || lot.fob_unit == null) return total;
    const original = det.original_quantity ?? lot.qty;
    const delta    = det.new_quantity - original;
    if (delta <= 0) return total;
    return total + lot.fob_unit * delta;
  }, 0);
  const cambiarFobAumentoHasData = markedCambiar.some(({ fpn, pi, det }) => {
    if (det?.new_quantity == null) return false;
    const item     = (data?.items || []).find(i => i.factory_part_number === fpn);
    const lot      = item?.lots.find(l => l.lot_identifier === pi);
    if (!lot) return false;
    const original = det.original_quantity ?? lot.qty;
    return det.new_quantity > original && lot.fob_unit != null;
  });
  const markedCambiarConAumento = markedCambiar.filter(({ fpn, pi, det }) => {
    if (det?.new_quantity == null) return false;
    const item     = (data?.items || []).find(i => i.factory_part_number === fpn);
    const lot      = item?.lots.find(l => l.lot_identifier === pi);
    const original = det.original_quantity ?? lot?.qty ?? 0;
    return det.new_quantity > original;
  });

  const thStyle = {
    padding: '0.65rem 1rem', fontSize: '0.58rem', fontWeight: 800,
    color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.1em',
    borderBottom: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.015)',
    backdropFilter: 'blur(10px)', cursor: 'pointer', whiteSpace: 'nowrap',
    textAlign: 'left', userSelect: 'none', position: 'sticky', top: 0, zIndex: 10,
  };

  return (
    <div style={{ padding: '0 0 2rem' }}>

      {/* Modal de detalle de cambio */}
      {changeModal && (
        <ChangeModal
          fpn={changeModal.fpn}
          lotId={changeModal.lotId}
          lot={changeModal.lot}
          initialDetails={details[changeModal.key]}
          onSave={handleSaveDetails}
          onUnmark={handleUnmarkFromModal}
          onClose={() => setChangeModal(null)}
        />
      )}

      {/* Modal de confirmación de ajustes */}
      {confirmOpen && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            background: '#12121c', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '16px', padding: '2rem', maxWidth: '480px', width: '90%', maxHeight: '80vh', overflowY: 'auto',
          }}>
            <h3 style={{ margin: '0 0 1rem', color: '#fff', fontSize: '1rem', fontWeight: 800 }}>
              ¿Ejecutar ajustes?
            </h3>

            {markedCancelar.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <p style={{ margin: '0 0 0.5rem', fontSize: '0.72rem', fontWeight: 800, color: '#f87171' }}>
                  ✕ Cancelaciones ({markedCancelar.length})
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                  {markedCancelar.map(({ fpn, pi }) => (
                    <span key={`${fpn}::${pi}`} style={{
                      fontFamily: 'monospace', fontSize: '0.65rem', padding: '2px 8px', borderRadius: '5px',
                      background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)', color: '#fca5a5',
                    }}>
                      {fpn} · {pi}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {markedCambiar.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <p style={{ margin: '0 0 0.5rem', fontSize: '0.72rem', fontWeight: 800, color: '#fbbf24' }}>
                  ↺ Cambios de cantidad ({markedCambiar.length})
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  {markedCambiar.map(({ fpn, pi, det }) => (
                    <div key={`${fpn}::${pi}`} style={{
                      fontFamily: 'monospace', fontSize: '0.65rem', padding: '5px 10px', borderRadius: '5px',
                      background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.2)',
                    }}>
                      <span style={{ color: '#fde68a' }}>{fpn} · {pi}</span>
                      {det?.new_quantity != null && (
                        <span style={{ color: 'rgba(255,255,255,0.5)', marginLeft: '0.5rem' }}>
                          → <strong style={{ color: '#fff' }}>{det.new_quantity}</strong> u
                        </span>
                      )}
                      {det?.change_note && (
                        <span style={{ color: 'rgba(255,255,255,0.4)', marginLeft: '0.5rem', fontFamily: 'sans-serif', fontSize: '0.6rem' }}>
                          · {det.change_note}
                        </span>
                      )}
                      {!det?.new_quantity && !det?.change_note && (
                        <span style={{ color: 'rgba(255,255,255,0.25)', marginLeft: '0.5rem', fontFamily: 'sans-serif', fontSize: '0.6rem' }}>
                          · sin detalle definido
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p style={{ margin: '0.5rem 0 1.5rem', fontSize: '0.68rem', color: 'rgba(255,255,255,0.3)' }}>
              Solo se procesan lotes sin packing list recibido. Esta acción no se puede deshacer.
            </p>

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setConfirmOpen(false)}
                style={{
                  padding: '0.5rem 1rem', borderRadius: '8px', fontSize: '0.75rem', fontWeight: 700,
                  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                  color: 'rgba(255,255,255,0.5)', cursor: 'pointer',
                }}
              >
                Volver
              </button>
              <button
                onClick={handleExecuteAdjustments}
                style={{
                  padding: '0.5rem 1.25rem', borderRadius: '8px', fontSize: '0.75rem', fontWeight: 800,
                  background: 'rgba(255,165,0,0.15)', border: '1px solid rgba(255,165,0,0.4)',
                  color: '#ffa500', cursor: 'pointer',
                }}
              >
                Ejecutar ajustes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 900, color: '#fff' }}>Ajuste de Pedidos</h2>
          <p style={{ margin: '0.2rem 0 0', fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)' }}>
            Baja/media rotación en pedido — click en un PI para marcarlo
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={load} disabled={loading} style={{
            display: 'flex', alignItems: 'center', gap: '0.35rem',
            padding: '0.5rem 0.9rem', borderRadius: '8px',
            background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
            color: 'rgba(255,255,255,0.4)', fontSize: '0.68rem', fontWeight: 700,
            cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.5 : 1,
          }}>
            <RefreshCw size={12} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Actualizar
          </button>
          <button onClick={handleExport} disabled={exporting || !data} style={{
            display: 'flex', alignItems: 'center', gap: '0.35rem',
            padding: '0.5rem 0.9rem', borderRadius: '8px',
            background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.25)',
            color: '#4ade80', fontSize: '0.68rem', fontWeight: 700,
            cursor: (exporting || !data) ? 'not-allowed' : 'pointer',
            opacity: (exporting || !data) ? 0.5 : 1,
          }}>
            <Download size={12} />
            {exporting ? 'Exportando...' : 'Exportar Excel'}
          </button>
        </div>
      </div>

      {/* Summary chips */}
      {data && (
        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
          {[
            { label: 'Para revisar',    value: data.total_references, color: '#fff'    },
            { label: 'Unidades totales', value: data.total_qty,        color: '#38bdf8' },
            { label: 'Baja rotación',   value: data.baja_count,        color: '#4ade80' },
            { label: 'Media rotación',  value: data.media_count,       color: '#fbbf24' },
            { label: 'Alta rotación',   value: data.alta_count ?? 0,   color: '#f87171' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '10px', padding: '0.6rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.2rem',
            }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 700, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</span>
              <span style={{ fontSize: '1.2rem', fontWeight: 900, color, fontFamily: 'monospace' }}>{value.toLocaleString()}</span>
            </div>
          ))}

          {(markedCancelar.length > 0 || markedCambiarConReduccion.length > 0) && (
            <div style={{
              background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: '10px', padding: '0.6rem 1rem',
              display: 'flex', flexDirection: 'column', gap: '0.2rem',
            }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 700, color: 'rgba(248,113,113,0.7)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Total ajuste
              </span>
              <span style={{ fontSize: '1.2rem', fontWeight: 900, color: '#f87171', fontFamily: 'monospace' }}>
                {(cancelFobHasData || cambiarFobHasData)
                  ? `$${(cancelFobTotal + cambiarFobDelta).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                  : '—'}
              </span>
              <span style={{ fontSize: '0.58rem', color: 'rgba(255,255,255,0.25)' }}>
                FOB · {markedCancelar.length + markedCambiarConReduccion.length} ref{(markedCancelar.length + markedCambiarConReduccion.length) !== 1 ? 's' : ''}
                {!(cancelFobHasData || cambiarFobHasData) ? ' · sin precio' : ''}
              </span>
            </div>
          )}

          {markedCambiarConAumento.length > 0 && (
            <div style={{
              background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.3)',
              borderRadius: '10px', padding: '0.6rem 1rem',
              display: 'flex', flexDirection: 'column', gap: '0.2rem',
            }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 700, color: 'rgba(74,222,128,0.7)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Total aumento
              </span>
              <span style={{ fontSize: '1.2rem', fontWeight: 900, color: '#4ade80', fontFamily: 'monospace' }}>
                {cambiarFobAumentoHasData
                  ? `$${cambiarFobAumento.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                  : '—'}
              </span>
              <span style={{ fontSize: '0.58rem', color: 'rgba(255,255,255,0.25)' }}>
                FOB · {markedCambiarConAumento.length} ref{markedCambiarConAumento.length !== 1 ? 's' : ''}
                {!cambiarFobAumentoHasData ? ' · sin precio' : ''}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Filter toggle */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', alignItems: 'center' }}>
        {[
          { val: 'all',   label: 'Todas' },
          { val: 'baja',  label: 'Baja',  color: '#4ade80' },
          { val: 'media', label: 'Media', color: '#fbbf24' },
          { val: 'alta',  label: 'Alta',  color: '#f87171' },
        ].map(({ val, label, color }) => {
          const active = rotFilter === val;
          return (
            <button key={val} onClick={() => setRotFilter(val)} style={{
              padding: '0.4rem 0.85rem', borderRadius: '8px', fontSize: '0.7rem',
              fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em',
              cursor: 'pointer', border: '1px solid', transition: 'all 0.15s',
              background:   active ? (color ? `${color}22` : 'rgba(255,255,255,0.08)') : 'rgba(255,255,255,0.03)',
              borderColor:  active ? (color ? `${color}66` : 'rgba(255,255,255,0.2)')  : 'rgba(255,255,255,0.08)',
              color:        active ? (color || '#fff') : 'rgba(255,255,255,0.4)',
            }}>{label}</button>
          );
        })}

        <input
          placeholder="Buscar referencia..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            padding: '0.4rem 0.75rem', borderRadius: '8px', fontSize: '0.7rem',
            background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
            color: '#fff', outline: 'none', width: '180px',
          }}
        />

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)' }}>
          <span>Click en un PI:</span>
          {[['revisado','#4ade80','rgba(74,222,128,0.1)'], ['cancelar','#f87171','rgba(239,68,68,0.12)'], ['cambiar','#fbbf24','rgba(251,191,36,0.1)']].map(([lbl, clr, bg]) => (
            <span key={lbl} style={{ padding: '1px 7px', borderRadius: '4px', background: bg, color: clr, fontWeight: 700, textTransform: 'uppercase', fontSize: '0.58rem' }}>{lbl}</span>
          ))}
        </div>
      </div>

      {/* Tabla */}
      <div className="glass table-scroll-wrapper rounded-2xl border border-white/5 shadow-2xl">
        {loading ? (
          <div style={{ padding: '4rem', textAlign: 'center', color: 'rgba(255,255,255,0.25)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            Cargando análisis...
          </div>
        ) : sorted.length === 0 ? (
          <div style={{ padding: '4rem', textAlign: 'center', color: 'rgba(255,255,255,0.2)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {data ? 'Sin repuestos para revisar en este filtro' : 'Error al cargar datos'}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle} onClick={() => toggleSort('rotation')}>
                  Rotación <SortIcon col="rotation" sortCol={sortCol} sortDir={sortDir} />
                </th>
                <th style={thStyle}>Código</th>
                <th style={thStyle}>Descripción</th>
                <th style={thStyle}>Modelos</th>
                <th style={{ ...thStyle, textAlign: 'center' }} onClick={() => toggleSort('lots')}>
                  N° PIs <SortIcon col="lots" sortCol={sortCol} sortDir={sortDir} />
                </th>
                <th style={{ ...thStyle, textAlign: 'right' }} onClick={() => toggleSort('total_qty')}>
                  Total <SortIcon col="total_qty" sortCol={sortCol} sortDir={sortDir} />
                </th>
                <th style={{ ...thStyle, textAlign: 'right', cursor: 'default' }}>Costo FOB</th>
                <th style={{ ...thStyle, cursor: 'default' }}>PI numbers · cantidad <span style={{ fontWeight: 400, opacity: 0.5, textTransform: 'none', letterSpacing: 0 }}>— click para marcar</span></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item, idx) => (
                <tr key={item.factory_part_number} style={{
                  borderBottom: '1px solid rgba(255,255,255,0.05)',
                  background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
                }}>
                  <td style={{ padding: '0.7rem 1rem' }}><RotBadge rc={item.rotation_class} /></td>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700, color: '#ff5f33', whiteSpace: 'nowrap' }}>
                      {item.factory_part_number}
                    </span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', maxWidth: '280px' }}>
                    <span style={{
                      color: item.description_es ? '#4ade80' : 'rgba(255,255,255,0.6)',
                      fontSize: '0.72rem', display: 'block',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {item.description_es || item.description}
                    </span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                      {(item.models || []).map(m => (
                        <span key={m} style={{
                          fontSize: '0.6rem', fontWeight: 700, padding: '2px 7px', borderRadius: '5px',
                          background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.25)',
                          color: '#a5b4fc', whiteSpace: 'nowrap',
                        }}>{m}</span>
                      ))}
                    </div>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', textAlign: 'center' }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)' }}>
                      {item.lots.length}
                    </span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', textAlign: 'right' }}>
                    <span style={{ fontFamily: 'monospace', fontWeight: 900, fontSize: '0.85rem', color: '#fff' }}>{item.total_qty}</span>
                    <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', marginLeft: '0.3rem' }}>u</span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {item.fob_unit != null ? (
                      <>
                        <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', color: '#fbbf24', fontWeight: 700 }}>
                          ${item.fob_unit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                        <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', marginLeft: '0.25rem' }}>USD</span>
                      </>
                    ) : (
                      <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.2)' }}>—</span>
                    )}
                  </td>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                      {item.lots.map(lot => {
                        const key   = markKey(item.factory_part_number, lot.lot_identifier);
                        const state = marked[key] || '';
                        const det   = details[key];
                        const s     = PI_STYLES[state];
                        const hasDetail = state === 'cambiar' && (det?.new_quantity != null || det?.change_note);
                        return (
                          <button
                            key={lot.lot_identifier}
                            onClick={() => toggleMark(item.factory_part_number, lot.lot_identifier, lot)}
                            title={
                              state === 'cambiar'
                                ? `Ajuste: ${det?.new_quantity != null ? `→ ${det.new_quantity}u` : 'sin cantidad'} ${det?.change_note ? `· ${det.change_note}` : ''} — click para editar`
                                : state === 'cancelar'
                                ? 'Marcado para cancelar — click para pasar a ajuste'
                                : state === 'revisado'
                                ? 'Revisado OK — click para marcar como cancelar'
                                : 'Click para marcar como revisado'
                            }
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                              padding: '2px 8px', borderRadius: '6px', cursor: 'pointer',
                              background: s.bg, border: `1px solid ${s.border}`,
                              fontSize: '0.68rem', fontFamily: 'monospace', whiteSpace: 'nowrap',
                              transition: 'all 0.15s',
                            }}
                          >
                            {s.prefix && (
                              <span style={{ fontSize: '0.65rem', fontWeight: 900, color: s.piColor }}>{s.prefix}</span>
                            )}
                            <span style={{ color: s.piColor }}>{lot.lot_identifier}</span>
                            <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: '0.6rem' }}>×</span>
                            <span style={{ color: s.qtyColor, fontWeight: 800 }}>
                              {state === 'cambiar' && det?.new_quantity != null ? det.new_quantity : lot.qty}
                            </span>
                            {hasDetail && (
                              <span style={{ fontSize: '0.6rem', color: '#fbbf24', opacity: 0.7 }}>✎</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Barra de decisiones marcadas */}
      {hasMarked && (
        <div style={{
          marginTop: '1rem', padding: '0.875rem 1.25rem',
          background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: '12px', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-start',
        }}>
          {markedCancelar.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 800, color: '#f87171', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                ✕ Cancelar ({markedCancelar.length})
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                {markedCancelar.map(({ fpn, pi }) => (
                  <span key={`${fpn}::${pi}`} style={{
                    fontFamily: 'monospace', fontSize: '0.65rem', padding: '2px 8px', borderRadius: '5px',
                    background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)', color: '#fca5a5',
                    display: 'flex', gap: '0.3rem', alignItems: 'center',
                  }}>
                    <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.58rem' }}>{fpn}</span>
                    <span style={{ color: 'rgba(255,255,255,0.2)' }}>·</span>
                    <span>{pi}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          {markedCambiar.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 800, color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                ↺ Cambiar ({markedCambiar.length})
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                {markedCambiar.map(({ fpn, pi, det }) => (
                  <span key={`${fpn}::${pi}`} style={{
                    fontFamily: 'monospace', fontSize: '0.65rem', padding: '2px 8px', borderRadius: '5px',
                    background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)', color: '#fde68a',
                    display: 'flex', gap: '0.3rem', alignItems: 'center',
                  }}>
                    <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.58rem' }}>{fpn}</span>
                    <span style={{ color: 'rgba(255,255,255,0.2)' }}>·</span>
                    <span>{pi}</span>
                    {det?.new_quantity != null && (
                      <span style={{ color: '#fbbf24', fontWeight: 800 }}>→ {det.new_quantity}u</span>
                    )}
                    {det?.change_note && (
                      <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.58rem' }}>✎</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => setConfirmOpen(true)}
            disabled={executing}
            style={{
              alignSelf: 'center', padding: '0.45rem 1.1rem', borderRadius: '8px',
              background: executing ? 'rgba(255,165,0,0.06)' : 'rgba(255,165,0,0.15)',
              border: '1px solid rgba(255,165,0,0.4)',
              color: executing ? '#606075' : '#ffa500',
              fontSize: '0.7rem', fontWeight: 800, cursor: executing ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: '0.4rem',
            }}
          >
            {executing ? 'Ejecutando...' : `Ejecutar ajustes (${markedCancelar.length + markedCambiar.length})`}
          </button>

          <button
            onClick={() => {
              Object.keys(marked).forEach(key => {
                const [fpn, lotId] = key.split('::');
                authFetch('/parts/admin/analysis/decisions', {
                  method: 'POST',
                  body: JSON.stringify({ factory_part_number: fpn, lot_identifier: lotId, decision: '' }),
                }).catch(() => {});
              });
              setMarked({});
              setDetails({});
            }}
            style={{
              marginLeft: 'auto', alignSelf: 'center', padding: '0.35rem 0.75rem', borderRadius: '7px',
              background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.3)',
              fontSize: '0.62rem', fontWeight: 700, cursor: 'pointer',
            }}
          >
            Limpiar marcas
          </button>
        </div>
      )}

      {execResult && !execResult.error && (
        <div style={{
          marginTop: '0.75rem', padding: '0.875rem 1.25rem',
          background: 'rgba(74,222,128,0.06)', border: '1px solid rgba(74,222,128,0.2)',
          borderRadius: '12px', fontSize: '0.72rem',
        }}>
          <span style={{ color: '#4ade80', fontWeight: 800 }}>✓ Ajustes ejecutados — </span>
          <span style={{ color: 'rgba(255,255,255,0.6)' }}>
            {execResult.cancelled_items > 0 && `${execResult.cancelled_items} ítem(s) cancelado(s)`}
            {execResult.cancelled_items > 0 && (execResult.changed_items || 0) > 0 && ', '}
            {(execResult.changed_items || 0) > 0 && `${execResult.changed_items} ítem(s) con cantidad actualizada`}
            {execResult.cancelled_items === 0 && (execResult.changed_items || 0) === 0 && 'sin cambios en ítems'}
            {` en ${execResult.affected_references?.length || 0} referencia(s).`}
            {execResult.skipped_lots?.length > 0 && ` ${execResult.skipped_lots.length} lote(s) omitido(s) (PL ya recibido).`}
          </span>
        </div>
      )}
      {execResult?.error && (
        <div style={{
          marginTop: '0.75rem', padding: '0.875rem 1.25rem',
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: '12px', fontSize: '0.72rem', color: '#f87171',
        }}>
          Error: {execResult.error}
        </div>
      )}

      <style jsx>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
