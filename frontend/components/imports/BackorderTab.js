'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { authFetch } from '../../lib/authFetch';
import { RefreshCw, Search, CheckCircle, Clock, AlertTriangle, Tag, FileUp, X, RotateCcw } from 'lucide-react';

function API() {
  return (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');
}

function daysSince(dateStr) {
  if (!dateStr) return null;
  const diff = Date.now() - new Date(dateStr).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

function DaysChip({ days }) {
  if (days === null) return null;
  const color = days > 60 ? '#f87171' : days > 30 ? '#fb923c' : '#9ca3af';
  return (
    <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(255,255,255,0.06)', color, whiteSpace: 'nowrap' }}>
      {days}d
    </span>
  );
}

function EditableExpectedPI({ boId, current, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(current || '');

  useEffect(() => { setValue(current || ''); }, [current]);

  const save = async () => {
    setEditing(false);
    if (value === (current || '')) return;
    try {
      await authFetch(`${API()}/imports/backorders/${boId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_in_pi: value || null }),
      });
      onSaved?.();
    } catch { setValue(current || ''); }
  };

  if (!editing) {
    return (
      <span
        onClick={() => setEditing(true)}
        title="Click para editar"
        style={{
          cursor: 'pointer', fontSize: '11px', fontFamily: 'monospace',
          color: value ? '#60a5fa' : '#606075',
          borderBottom: '1px dashed rgba(255,255,255,0.15)',
          paddingBottom: '1px',
        }}
      >
        {value || '+ asignar PI'}
      </span>
    );
  }

  return (
    <input
      autoFocus
      value={value}
      onChange={e => setValue(e.target.value.toUpperCase())}
      onBlur={save}
      onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setValue(current || ''); setEditing(false); } }}
      placeholder="Ej: E0000580-SP-1"
      style={{
        width: 140, fontSize: '11px', padding: '2px 6px', borderRadius: '6px',
        background: '#1a1a24', border: '1px solid rgba(255,255,255,0.2)',
        color: '#fff', outline: 'none', fontFamily: 'monospace',
      }}
    />
  );
}

function BulkPIModal({ count, onConfirm, onCancel }) {
  const [value, setValue] = useState('');
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#16161f', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '14px',
        padding: '24px', width: 360, display: 'flex', flexDirection: 'column', gap: '16px',
      }}>
        <p style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#fff' }}>
          Asignar PI esperado a {count} backorder{count !== 1 ? 's' : ''}
        </p>
        <input
          autoFocus
          value={value}
          onChange={e => setValue(e.target.value.toUpperCase())}
          onKeyDown={e => { if (e.key === 'Enter' && value) onConfirm(value); if (e.key === 'Escape') onCancel(); }}
          placeholder="Ej: E0000590-SP-1"
          style={{
            padding: '9px 12px', borderRadius: '8px', fontSize: '12px', fontFamily: 'monospace',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.15)',
            color: '#fff', outline: 'none', width: '100%', boxSizing: 'border-box',
          }}
        />
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button onClick={onCancel} style={{ padding: '7px 16px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)', background: 'transparent', color: '#9ca3af', fontSize: '11px', cursor: 'pointer' }}>
            Cancelar
          </button>
          <button
            onClick={() => value && onConfirm(value)}
            disabled={!value}
            style={{ padding: '7px 16px', borderRadius: '8px', border: 'none', background: value ? '#2563eb' : 'rgba(37,99,235,0.3)', color: value ? '#fff' : '#606075', fontSize: '11px', fontWeight: 700, cursor: value ? 'pointer' : 'default' }}
          >
            Asignar
          </button>
        </div>
      </div>
    </div>
  );
}

const GROUP_LABELS = {
  resolved:     { label: 'Se resuelven completamente', color: '#22c55e', bg: 'rgba(34,197,94,0.08)',  border: 'rgba(34,197,94,0.25)'  },
  partial:      { label: 'Quedan con saldo abierto',   color: '#fb923c', bg: 'rgba(251,146,60,0.08)', border: 'rgba(251,146,60,0.25)' },
  excess:       { label: 'Exceso (sobra mercadería)',  color: '#60a5fa', bg: 'rgba(96,165,250,0.08)',  border: 'rgba(96,165,250,0.25)' },
  no_backorder: { label: 'Sin backorder abierto',      color: '#f87171', bg: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.25)' },
};

function BulkResolveModal({ preview, onConfirm, onCancel, loading }) {
  const total = (preview?.resolved?.length || 0) + (preview?.partial?.length || 0) +
                (preview?.excess?.length || 0) + (preview?.no_backorder?.length || 0);
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#16161f', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '14px', padding: '24px', width: 520, maxWidth: '92vw', maxHeight: '82vh', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <p style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#fff' }}>
            Preview — {total} fila{total !== 1 ? 's' : ''} en el Excel
          </p>
          <button onClick={onCancel} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', padding: 0 }}><X size={14} /></button>
        </div>

        {Object.entries(GROUP_LABELS).map(([key, cfg]) => {
          const items = preview?.[key] || [];
          if (!items.length) return null;
          return (
            <div key={key}>
              <p style={{ margin: '0 0 8px', fontSize: '10px', fontWeight: 700, color: cfg.color, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {cfg.label} — {items.length}
              </p>
              {items.map((item, i) => (
                <div key={i} style={{ padding: '8px 10px', borderRadius: '8px', background: cfg.bg, border: `1px solid ${cfg.border}`, marginBottom: 6 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: '11px', fontWeight: 700, color: '#fff' }}>{item.part_number}</span>
                    <span style={{ fontSize: '10px', color: '#9ca3af' }}>{item.qty_excel} uds · origen: {item.origin_pi} · nuevo: {item.pi_nuevo}</span>
                    {item.excess_qty > 0 && <span style={{ fontSize: '10px', color: '#60a5fa' }}>+{item.excess_qty} exceso</span>}
                  </div>
                  {item.matches?.map((m, j) => (
                    <div key={j} style={{ fontSize: '9px', color: '#9ca3af', marginTop: 3, paddingLeft: 4 }}>
                      {m.spillover ? '↪ spillover' : '→'} {m.origin_pi}: {m.qty_applied} aplicadas
                      {m.qty_after > 0 ? ` · quedan ${m.qty_after}` : ' · cerrado'}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          );
        })}

        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', paddingTop: 4 }}>
          <button onClick={onCancel} style={{ padding: '7px 16px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)', background: 'transparent', color: '#9ca3af', fontSize: '11px', cursor: 'pointer' }}>
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            disabled={loading || !(preview?.resolved?.length || preview?.partial?.length || preview?.excess?.length)}
            style={{ padding: '7px 16px', borderRadius: '8px', border: 'none', background: '#2563eb', color: '#fff', fontSize: '11px', fontWeight: 700, cursor: 'pointer', opacity: loading ? 0.6 : 1 }}
          >
            {loading ? 'Aplicando...' : 'Confirmar y aplicar'}
          </button>
        </div>
      </div>
    </div>
  );
}

function RollbackModal({ onConfirm, onCancel, loading }) {
  const [piNuevo, setPiNuevo] = useState('');
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#16161f', border: '1px solid rgba(248,113,113,0.3)', borderRadius: '14px', padding: '24px', width: 380, display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(248,113,113,0.1)', flexShrink: 0 }}>
            <RotateCcw size={14} color="#f87171" />
          </div>
          <p style={{ margin: 0, fontSize: '12px', fontWeight: 700, color: '#f87171' }}>Revertir carga masiva</p>
          <button onClick={onCancel} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#606075', cursor: 'pointer', padding: 0 }}><X size={13} /></button>
        </div>
        <p style={{ margin: 0, fontSize: '11px', color: '#9ca3af', lineHeight: 1.5 }}>
          Ingresá el <strong style={{ color: '#fff' }}>PI Nuevo</strong> que fue cargado para revertir todos los backorders que resolvió esa importación.
        </p>
        <input
          autoFocus
          value={piNuevo}
          onChange={e => setPiNuevo(e.target.value.toUpperCase())}
          onKeyDown={e => { if (e.key === 'Enter' && piNuevo) onConfirm(piNuevo); if (e.key === 'Escape') onCancel(); }}
          placeholder="Ej: E0000590-SP-1"
          style={{ padding: '9px 12px', borderRadius: '8px', fontSize: '12px', fontFamily: 'monospace', background: '#1a1a24', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', outline: 'none', width: '100%', boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onCancel} style={{ padding: '7px 16px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)', background: 'transparent', color: '#9ca3af', fontSize: '11px', cursor: 'pointer' }}>
            Cancelar
          </button>
          <button
            onClick={() => piNuevo && onConfirm(piNuevo)}
            disabled={!piNuevo || loading}
            style={{ padding: '7px 16px', borderRadius: '8px', border: '1px solid rgba(248,113,113,0.3)', background: 'rgba(248,113,113,0.1)', color: '#f87171', fontSize: '11px', fontWeight: 700, cursor: piNuevo ? 'pointer' : 'default', opacity: loading ? 0.6 : 1 }}
          >
            {loading ? 'Revirtiendo...' : 'Revertir'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function BackorderTab({ userRole }) {
  const [backorders, setBackorders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showResolved, setShowResolved] = useState(false);
  const [search, setSearch] = useState('');
  const [filterPi, setFilterPi] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [repairing, setRepairing] = useState(false);

  const canEdit = userRole === 'superadmin' || userRole === 'proveedor';
  const isSuperadmin = userRole === 'superadmin';

  // Bulk resolve state
  const [bulkResolvePreview, setBulkResolvePreview] = useState(null);
  const [bulkResolveLoading, setBulkResolveLoading] = useState(false);
  const [pendingFile, setPendingFile] = useState(null);
  const [showRollbackModal, setShowRollbackModal] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState(false);

  const handleBulkResolveUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setBulkResolveLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await authFetch(`${API()}/imports/backorders/bulk-resolve-preview`, { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Error al procesar el Excel');
        return;
      }
      const preview = await res.json();
      setPendingFile(file);
      setBulkResolvePreview(preview);
    } catch { alert('Error de conexión al procesar el Excel'); }
    finally { setBulkResolveLoading(false); }
  };

  const handleBulkResolveApply = async () => {
    if (!pendingFile) return;
    setBulkResolveLoading(true);
    try {
      const form = new FormData();
      form.append('file', pendingFile);
      const res = await authFetch(`${API()}/imports/backorders/bulk-resolve-apply`, { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Error al aplicar');
        return;
      }
      setBulkResolvePreview(null);
      setPendingFile(null);
      fetchBackorders();
    } catch { alert('Error de conexión al aplicar'); }
    finally { setBulkResolveLoading(false); }
  };

  const handleRollback = async (piNuevo) => {
    setRollbackLoading(true);
    try {
      const res = await authFetch(`${API()}/imports/backorders/bulk-resolve-rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pi_nuevo: piNuevo }),
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.detail || 'Error al revertir');
        return;
      }
      setShowRollbackModal(false);
      alert(`Revertidos ${data.rolled_back} backorder${data.rolled_back !== 1 ? 's' : ''} del PI ${piNuevo}`);
      fetchBackorders();
    } catch { alert('Error de conexión al revertir'); }
    finally { setRollbackLoading(false); }
  };

  const handleRepair = async () => {
    if (!confirm('Esto re-calculará todos los backorders de inspección física. ¿Continuar?')) return;
    setRepairing(true);
    try {
      const res = await authFetch(`${API()}/imports/backorders/repair-physical-inspection`, { method: 'POST' });
      const data = await res.json();
      alert(`Reparación completa: ${data.fixed} ítems procesados${data.errors?.length ? `, ${data.errors.length} errores` : ''}`);
      fetchBackorders();
    } catch { alert('Error en la reparación'); }
    finally { setRepairing(false); }
  };

  const fetchBackorders = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (!showResolved) params.append('resolved', 'false');
      if (filterPi) params.append('origin_pi', filterPi);
      const res = await authFetch(`${API()}/imports/backorders?${params}`);
      const data = await res.json();
      setBackorders(Array.isArray(data) ? data : []);
      setSelected(new Set());
    } catch {
      setBackorders([]);
    } finally {
      setLoading(false);
    }
  }, [showResolved, filterPi]);

  useEffect(() => { fetchBackorders(); }, [fetchBackorders]);

  const handleResolve = async (bo) => {
    const label = bo.source === 'physical_inspection' ? 'cobrado (faltante físico)' : 'no cobrado (no enviado)';
    if (!confirm(`¿Marcar como resuelto el backorder ${label} de ${bo.part_number}?`)) return;
    try {
      await authFetch(`${API()}/imports/backorders/${bo.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved: true }),
      });
      fetchBackorders();
    } catch { alert('Error al resolver backorder'); }
  };

  // Filtro local
  const filtered = search
    ? backorders.filter(b =>
        b.part_number?.toLowerCase().includes(search.toLowerCase()) ||
        b.origin_pi?.toLowerCase().includes(search.toLowerCase()) ||
        b.expected_in_pi?.toLowerCase().includes(search.toLowerCase()) ||
        b.description_es?.toLowerCase().includes(search.toLowerCase()) ||
        b.model_applicable?.toLowerCase().includes(search.toLowerCase())
      )
    : backorders;

  // Agrupar por (part_number, origin_pi) para mostrar una fila consolidada
  const groupedFiltered = useMemo(() => {
    const groups = {};
    filtered.forEach(bo => {
      const key = `${bo.part_number}__${bo.origin_pi}`;
      if (!groups[key]) {
        groups[key] = {
          key,
          part_number: bo.part_number,
          origin_pi: bo.origin_pi,
          description_es: bo.description_es,
          model_applicable: bo.model_applicable,
          spare_part_item_id: bo.spare_part_item_id,
          reconciliation: null,
          physical_inspection: null,
        };
      }
      if (bo.source === 'physical_inspection') {
        groups[key].physical_inspection = bo;
      } else {
        groups[key].reconciliation = bo;
      }
    });
    return Object.values(groups);
  }, [filtered]);

  // Selección solo sobre backorders de reconciliación (los que necesitan asignación de PI)
  const selectableGroups = groupedFiltered.filter(g => g.reconciliation && !g.reconciliation.resolved);
  const allSelected = selectableGroups.length > 0 && selectableGroups.every(g => selected.has(g.reconciliation.id));
  const someSelected = selectableGroups.some(g => selected.has(g.reconciliation.id));

  const toggleSelectAll = () => {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(selectableGroups.map(g => g.reconciliation.id)));
  };

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleBulkAssignPI = async (piValue) => {
    setBulkLoading(true);
    try {
      await authFetch(`${API()}/imports/backorders/bulk-expected-pi`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: [...selected], expected_in_pi: piValue }),
      });
      setShowBulkModal(false);
      fetchBackorders();
    } catch {
      alert('Error al asignar PI');
    } finally {
      setBulkLoading(false);
    }
  };

  // KPIs
  const active = backorders.filter(b => !b.resolved);
  const totalPending = active.reduce((s, b) => s + (b.qty_pending || 0), 0);
  const oldestDays = active.length
    ? Math.max(...active.map(b => daysSince(b.created_at) || 0))
    : 0;
  // "Sin PI" solo cuenta grupos de reconciliación sin PI asignado
  const withoutPI = groupedFiltered.filter(g =>
    g.reconciliation && !g.reconciliation.resolved && !g.reconciliation.expected_in_pi
  ).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {showBulkModal && (
        <BulkPIModal
          count={selected.size}
          onConfirm={handleBulkAssignPI}
          onCancel={() => setShowBulkModal(false)}
        />
      )}

      {bulkResolvePreview && (
        <BulkResolveModal
          preview={bulkResolvePreview}
          onConfirm={handleBulkResolveApply}
          onCancel={() => { setBulkResolvePreview(null); setPendingFile(null); }}
          loading={bulkResolveLoading}
        />
      )}

      {showRollbackModal && (
        <RollbackModal
          onConfirm={handleRollback}
          onCancel={() => setShowRollbackModal(false)}
          loading={rollbackLoading}
        />
      )}

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
        {[
          { label: 'Partes en backorder', value: groupedFiltered.filter(g => {
            const rec = g.reconciliation;
            const phy = g.physical_inspection;
            return (!rec || !rec.resolved) || (!phy || !phy.resolved);
          }).length, color: '#f87171' },
          { label: 'Unidades pendientes', value: totalPending, color: '#fb923c' },
          { label: 'Sin PI asignado', value: withoutPI, color: '#9ca3af' },
          { label: 'Más antiguo (días)', value: oldestDays > 0 ? `${oldestDays}d` : '—', color: oldestDays > 60 ? '#f87171' : '#606075' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ padding: '13px 16px', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <p style={{ margin: 0, fontSize: '18px', fontWeight: 800, color }}>{value}</p>
            <p style={{ margin: '2px 0 0', fontSize: '10px', color: '#606075', fontWeight: 600 }}>{label}</p>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 180, padding: '7px 10px', borderRadius: '8px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
          <Search size={11} color="#606075" />
          <input
            placeholder="Buscar parte o PI..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '11px', outline: 'none', flex: 1 }}
          />
        </div>
        <input
          placeholder="Filtrar por PI origen..."
          value={filterPi}
          onChange={e => setFilterPi(e.target.value.toUpperCase())}
          style={{ padding: '7px 10px', borderRadius: '8px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', color: '#fff', fontSize: '11px', outline: 'none', width: 180, fontFamily: 'monospace' }}
        />
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '11px', color: '#9ca3af' }}>
          <input
            type="checkbox"
            checked={showResolved}
            onChange={e => setShowResolved(e.target.checked)}
            style={{ accentColor: '#ff5f33' }}
          />
          Ver resueltos
        </label>
        <button onClick={fetchBackorders} style={{ padding: '7px 9px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer', color: '#9ca3af' }}>
          <RefreshCw size={13} />
        </button>

        {canEdit && (
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 14px', borderRadius: '8px', border: '1px solid rgba(96,165,250,0.3)', background: 'rgba(96,165,250,0.08)', color: bulkResolveLoading ? '#606075' : '#60a5fa', fontSize: '11px', fontWeight: 700, cursor: bulkResolveLoading ? 'default' : 'pointer', whiteSpace: 'nowrap' }}>
            <FileUp size={12} />
            {bulkResolveLoading ? 'Procesando...' : 'Cargar Excel'}
            <input type="file" accept=".xlsx,.xls" onChange={handleBulkResolveUpload} style={{ display: 'none' }} disabled={bulkResolveLoading} />
          </label>
        )}

        {isSuperadmin && (
          <button
            onClick={() => setShowRollbackModal(true)}
            title="Revertir una carga masiva por PI Nuevo"
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 12px', borderRadius: '8px', border: '1px solid rgba(248,113,113,0.25)', background: 'rgba(248,113,113,0.06)', color: '#f87171', fontSize: '10px', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            <RotateCcw size={11} />
            Revertir carga
          </button>
        )}

        {selected.size > 0 && canEdit && (
          <button
            onClick={() => setShowBulkModal(true)}
            disabled={bulkLoading}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 14px', borderRadius: '8px', border: 'none', background: '#2563eb', color: '#fff', fontSize: '11px', fontWeight: 700, cursor: 'pointer' }}
          >
            <Tag size={11} />
            Asignar PI a {selected.size} seleccionado{selected.size !== 1 ? 's' : ''}
          </button>
        )}

        {/* TEMPORAL: reparar backorders físicos (oculto, cambiar false→true para activar) */}
        {false && isSuperadmin && (
          <button
            onClick={handleRepair}
            disabled={repairing}
            title="Recalcula los backorders de faltante físico para corregir datos inconsistentes"
            style={{ padding: '7px 12px', borderRadius: '8px', border: '1px solid rgba(251,146,60,0.3)', background: 'rgba(251,146,60,0.08)', color: repairing ? '#606075' : '#fb923c', fontSize: '10px', fontWeight: 700, cursor: repairing ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
          >
            {repairing ? 'Reparando...' : '⚙ Reparar backorders'}
          </button>
        )}


        <span style={{ fontSize: '11px', color: '#606075', marginLeft: 'auto' }}>
          {groupedFiltered.length} parte{groupedFiltered.length !== 1 ? 's' : ''} en backorder
        </span>
      </div>

      {/* Leyenda de columnas */}
      <div style={{ display: 'flex', gap: '16px', alignItems: 'center', padding: '6px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
        <span style={{ fontSize: '9px', color: '#606075', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Referencias:</span>
        <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '4px', background: 'rgba(250,204,21,0.1)', color: '#facc15', border: '1px solid rgba(250,204,21,0.25)' }}>Sin Cobrar</span>
        <span style={{ fontSize: '9px', color: '#606075' }}>No enviado por proveedor (no cobrado)</span>
        <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '4px', background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>Cobrado</span>
        <span style={{ fontSize: '9px', color: '#606075' }}>Cobrado en invoice pero no llegó físicamente</span>
        <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '4px', background: 'rgba(251,146,60,0.1)', color: '#fb923c', border: '1px solid rgba(251,146,60,0.25)' }}>Total</span>
        <span style={{ fontSize: '9px', color: '#606075' }}>Total pendiente contra la orden</span>
      </div>

      {/* Tabla */}
      {loading ? (
        <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '40px 0' }}>Cargando backorders...</p>
      ) : groupedFiltered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#606075' }}>
          <CheckCircle size={36} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
          <p style={{ fontSize: '13px', margin: 0 }}>
            {showResolved ? 'No hay backorders' : 'No hay backorders activos'}
          </p>
          <p style={{ fontSize: '11px', margin: '4px 0 0', color: '#404050' }}>
            Los backorders se crean al confirmar una reconciliación con ítems faltantes
          </p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.06)', background: '#13131a' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
            <thead>
              <tr style={{ background: '#0e0e14' }}>
                {canEdit && (
                  <th style={{ padding: '9px 12px', width: 32 }}>
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={el => { if (el) el.indeterminate = someSelected && !allSelected; }}
                      onChange={toggleSelectAll}
                      style={{ accentColor: '#2563eb', cursor: 'pointer' }}
                    />
                  </th>
                )}
                {['Parte #', 'Descripción', 'Moto', 'PI Origen', 'PI Esperado',
                  'Sin Cobrar', 'Cobrado', 'Total', 'Días', 'Estado', ''].map(h => (
                  <th key={h} style={{
                    padding: '9px 12px', textAlign: 'center', fontSize: '9px', fontWeight: 700,
                    color: h === 'Sin Cobrar' ? '#facc15' : h === 'Cobrado' ? '#f87171' : h === 'Total' ? '#fb923c' : '#606075',
                    textTransform: 'uppercase', letterSpacing: '0.07em',
                    borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groupedFiltered.map(group => {
                const rec = group.reconciliation;
                const phy = group.physical_inspection;

                // Fuente de verdad: datos del SparePartItem (vienen en cualquier BO del grupo)
                const primaryBo = rec || phy;
                const spOrdered   = primaryBo?.sp_qty_ordered  ?? 0;
                const spReceived  = primaryBo?.sp_qty_received ?? 0;
                const spPhysical  = primaryBo?.sp_qty_physical ?? null;
                const spPending   = primaryBo?.sp_qty_pending  ?? 0;

                // Sin Cobrar: estaba en la orden pero el proveedor no lo incluyó en el PL
                // = qty_ordered - qty_received (calculado desde el item, no del BO)
                const qtyNotCharged = Math.max(0, spOrdered - spReceived);

                // Cobrado: el proveedor lo incluyó en el PL (cobró) pero no llegó físicamente
                // = qty_received - qty_physical (solo aplica cuando hay inspección física)
                const qtyCobrado = spPhysical != null
                  ? Math.max(0, spReceived - spPhysical)
                  : (phy && !phy.resolved ? phy.qty_pending : 0);

                // Total: siempre igual a item.qty_pending (fuente de verdad)
                const qtyTotal = spPending;

                const isFullyResolved = (!rec || rec.resolved) && (!phy || phy.resolved);

                // Checkbox: solo para el BO de reconciliación (el que necesita PI)
                const selectableId = rec?.id;
                const isSelected = !!(selectableId && selected.has(selectableId));

                // Días abierto: el más antiguo entre los no resueltos
                const unresolvedDates = [rec, phy]
                  .filter(b => b && !b.resolved)
                  .map(b => b.created_at)
                  .sort();
                const days = daysSince(unresolvedDates[0] || null);

                return (
                  <tr
                    key={group.key}
                    style={{
                      borderBottom: '1px solid rgba(255,255,255,0.03)',
                      opacity: isFullyResolved ? 0.5 : 1,
                      background: isSelected ? 'rgba(37,99,235,0.07)' : 'transparent',
                    }}
                    onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = isSelected ? 'rgba(37,99,235,0.07)' : 'transparent'; }}
                  >
                    {canEdit && (
                      <td style={{ padding: '9px 12px' }}>
                        {selectableId && rec && !rec.resolved && (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelect(selectableId)}
                            style={{ accentColor: '#2563eb', cursor: 'pointer' }}
                          />
                        )}
                      </td>
                    )}

                    {/* Parte # */}
                    <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                      <span style={{ color: '#f87171', fontWeight: 700, fontFamily: 'monospace' }}>{group.part_number}</span>
                    </td>

                    {/* Descripción */}
                    <td style={{ padding: '9px 12px', color: '#d1d5db', fontSize: '11px', maxWidth: 200 }}>
                      <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {group.description_es || '—'}
                      </span>
                    </td>

                    {/* Moto */}
                    <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                      {group.model_applicable
                        ? <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '4px', background: 'rgba(96,165,250,0.1)', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.2)' }}>{group.model_applicable}</span>
                        : <span style={{ color: '#606075' }}>—</span>
                      }
                    </td>

                    {/* PI Origen */}
                    <td style={{ padding: '9px 12px', color: '#9ca3af', fontFamily: 'monospace', fontSize: '10px', whiteSpace: 'nowrap' }}>
                      {group.origin_pi}
                    </td>

                    {/* PI Esperado — solo aplica al BO de reconciliación */}
                    <td style={{ padding: '9px 12px' }}>
                      {rec && !rec.resolved && canEdit ? (
                        <EditableExpectedPI boId={rec.id} current={rec.expected_in_pi} onSaved={fetchBackorders} />
                      ) : rec?.expected_in_pi ? (
                        <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#60a5fa' }}>{rec.expected_in_pi}</span>
                      ) : phy && !phy.resolved ? (
                        <span style={{ fontSize: '9px', color: '#606075', fontStyle: 'italic' }}>Reclamo proveedor</span>
                      ) : (
                        <span style={{ color: '#606075' }}>—</span>
                      )}
                    </td>

                    {/* Sin Cobrar */}
                    <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                      {qtyNotCharged > 0
                        ? <span style={{ fontWeight: 700, color: '#facc15', fontSize: '13px' }}>{qtyNotCharged}</span>
                        : <span style={{ color: '#3f3f55', fontSize: '11px' }}>—</span>
                      }
                    </td>

                    {/* Cobrado */}
                    <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                      {qtyCobrado > 0
                        ? <span style={{ fontWeight: 700, color: '#f87171', fontSize: '13px' }}>{qtyCobrado}</span>
                        : <span style={{ color: '#3f3f55', fontSize: '11px' }}>—</span>
                      }
                    </td>

                    {/* Total */}
                    <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                      <span style={{ fontWeight: 800, color: qtyTotal > 0 ? '#fb923c' : '#606075', fontSize: '14px' }}>
                        {qtyTotal}
                      </span>
                    </td>

                    {/* Días */}
                    <td style={{ padding: '9px 12px' }}>
                      <DaysChip days={days} />
                    </td>

                    {/* Estado */}
                    <td style={{ padding: '9px 12px' }}>
                      {isFullyResolved ? (
                        <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(34,197,94,0.1)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.25)' }}>
                          RESUELTO
                        </span>
                      ) : (
                        <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(248,113,113,0.1)', color: '#f87171', border: '1px solid rgba(248,113,113,0.25)' }}>
                          ACTIVO
                        </span>
                      )}
                    </td>

                    {/* Acciones */}
                    <td style={{ padding: '9px 12px', textAlign: 'right' }}>
                      {!isFullyResolved && canEdit && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', alignItems: 'flex-end' }}>
                          {rec && !rec.resolved && (
                            <button
                              onClick={() => handleResolve(rec)}
                              title="Resolver pendiente no cobrado"
                              style={{ padding: '3px 8px', borderRadius: '6px', border: 'none', background: 'rgba(250,204,21,0.1)', color: '#facc15', fontSize: '9px', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}
                            >
                              <CheckCircle size={9} style={{ display: 'inline', marginRight: 3 }} />
                              No cobrado
                            </button>
                          )}
                          {phy && !phy.resolved && (
                            <button
                              onClick={() => handleResolve(phy)}
                              title="Resolver faltante físico cobrado"
                              style={{ padding: '3px 8px', borderRadius: '6px', border: 'none', background: 'rgba(239,68,68,0.1)', color: '#f87171', fontSize: '9px', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}
                            >
                              <CheckCircle size={9} style={{ display: 'inline', marginRight: 3 }} />
                              Cobrado
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
