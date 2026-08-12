'use client';
import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../../lib/authFetch';
import { getApiUrl } from '../../lib/api';
import { ChevronDown, ChevronRight, Search, RefreshCw, Package, ClipboardCheck, XCircle, UploadCloud, FileSpreadsheet, AlertTriangle } from 'lucide-react';
import { toast } from '../../lib/toast';
import ExcelUploadModal from './ExcelUploadModal';
import ReconciliationModal from './ReconciliationModal';
import BackorderReconciliationModal from './BackorderReconciliationModal';
import PhysicalInventoryUploadModal from './PhysicalInventoryUploadModal';
import ConfirmModal from '../ConfirmModal';
import { SUPERADMIN_ONLY_NAME_EDIT_MESSAGE } from './partNamePermission';

// ---------------------------------------------------------------------------
// Status badge para spare part items
// ---------------------------------------------------------------------------
const ITEM_STATUS = {
  PENDING:   { label: 'Pendiente',  color: '#9ca3af', bg: 'rgba(156,163,175,0.12)', border: 'rgba(156,163,175,0.3)' },
  PARTIAL:   { label: 'Parcial',    color: '#fb923c', bg: 'rgba(251,146,60,0.12)',  border: 'rgba(251,146,60,0.3)' },
  DECLARED:  { label: 'Declarado',  color: '#60a5fa', bg: 'rgba(96,165,250,0.12)',  border: 'rgba(96,165,250,0.3)' },
  RECEIVED:  { label: 'Recibido',   color: '#22c55e', bg: 'rgba(34,197,94,0.12)',   border: 'rgba(34,197,94,0.3)' },
  BACKORDER:         { label: 'Backorder',         color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
  BACKORDER_PARCIAL: { label: 'Backorder Parcial', color: '#fb923c', bg: 'rgba(251,146,60,0.12)',  border: 'rgba(251,146,60,0.3)' },
  CANCELLED:         { label: 'Cancelado',         color: '#6b7280', bg: 'rgba(107,114,128,0.12)', border: 'rgba(107,114,128,0.3)' },
  EXTRA:             { label: 'Extra (no pedido)', color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.3)' },
};

function ItemStatusBadge({ status }) {
  const cfg = ITEM_STATUS[status] || ITEM_STATUS.PENDING;
  return (
    <span style={{
      display: 'inline-block', fontSize: '9px', fontWeight: 700, letterSpacing: '0.05em',
      padding: '2px 7px', borderRadius: '20px',
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
      whiteSpace: 'nowrap',
    }}>{cfg.label}</span>
  );
}

// ---------------------------------------------------------------------------
// Inline editable cell genérica para texto y números
// ---------------------------------------------------------------------------
function EditableCell({ itemId, field, current, type = 'text', align = 'left', cellStyle = {}, onSaved, readOnly = false, readOnlyTitle = 'Reconciliación confirmada — no editable' }) {
  const [editing, setEditing] = useState(false);
  const [hover, setHover] = useState(false);
  const [value, setValue] = useState(current ?? '');

  if (readOnly) {
    return (
      <span
        title={readOnlyTitle}
        style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 5px', textAlign: align, ...cellStyle }}
      >
        {current != null && current !== '' ? current : <span style={{ color: '#3f3f55' }}>—</span>}
      </span>
    );
  }

  const save = async () => {
    setEditing(false);
    const parsed = type === 'number' ? (value === '' ? null : parseFloat(value)) : (String(value).trim() || null);
    if (parsed === (current ?? null)) return;
    try {
      const res = await authFetch(`${getApiUrl()}/imports/spare-part-items/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: parsed }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data?.detail;
        throw new Error(typeof detail === 'string' ? detail : detail?.detail || 'Error al guardar');
      }
      onSaved?.();
    } catch (err) {
      toast.error(err.message || 'Error al guardar');
      setValue(current ?? '');
    }
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
          width: type === 'number' ? 70 : '100%', minWidth: type === 'text' ? 80 : undefined,
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

// ---------------------------------------------------------------------------
// Inline editable cell para qty_received y status
// ---------------------------------------------------------------------------
function EditableStatus({ itemId, current, onSaved, readOnly = false }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(current);

  if (readOnly) {
    return (
      <span title="Reconciliación confirmada — no editable">
        <ItemStatusBadge status={value} />
      </span>
    );
  }

  const save = async (newVal) => {
    const previous = value;
    setValue(newVal);
    setEditing(false);
    try {
      const res = await authFetch(`${getApiUrl()}/imports/spare-part-items/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newVal }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data?.detail;
        throw new Error(typeof detail === 'string' ? detail : detail?.detail || 'Error al guardar el estado');
      }
      onSaved?.();
    } catch (err) {
      toast.error(err.message || 'Error al guardar el estado');
      setValue(previous);
    }
  };

  if (!editing) {
    return (
      <span onClick={() => setEditing(true)} style={{ cursor: 'pointer' }}>
        <ItemStatusBadge status={value} />
      </span>
    );
  }
  return (
    <select
      autoFocus
      value={value}
      onChange={e => save(e.target.value)}
      onBlur={() => setEditing(false)}
      style={{
        fontSize: '10px', padding: '2px 6px', borderRadius: '6px',
        background: '#1a1a24', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', outline: 'none',
      }}
    >
      {Object.entries(ITEM_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
    </select>
  );
}

function EditableQty({ itemId, current, max, onSaved, readOnly = false }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(current);

  if (readOnly) {
    return (
      <span title="Reconciliación confirmada — no editable" style={{ color: value > 0 ? '#22c55e' : '#9ca3af', fontWeight: 700 }}>
        {value}
      </span>
    );
  }

  const save = async () => {
    setEditing(false);
    const num = parseInt(value, 10);
    if (isNaN(num) || num === current) return;
    try {
      const res = await authFetch(`${getApiUrl()}/imports/spare-part-items/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qty_received: num }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data?.detail;
        throw new Error(typeof detail === 'string' ? detail : detail?.detail || 'Error al guardar la cantidad');
      }
      onSaved?.();
    } catch (err) {
      toast.error(err.message || 'Error al guardar la cantidad');
      setValue(current);
    }
  };

  if (!editing) {
    return (
      <span
        onClick={() => setEditing(true)}
        style={{ cursor: 'pointer', color: value > 0 ? '#22c55e' : '#9ca3af', fontWeight: 700 }}
      >
        {value}
      </span>
    );
  }
  return (
    <input
      autoFocus
      type="number"
      min={0}
      max={max}
      value={value}
      onChange={e => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setValue(current); setEditing(false); } }}
      style={{
        width: 60, fontSize: '11px', padding: '2px 6px', borderRadius: '6px',
        background: '#1a1a24', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', outline: 'none',
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Rotation badge clickable — cicla alta → media → baja → alta (solo superadmin)
// ---------------------------------------------------------------------------
const ROT_CYCLE = { alta: 'media', media: 'baja', baja: 'alta' };
const ROT_STYLES = {
  alta:  { background: 'rgba(239,68,68,0.12)',  color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)'  },
  media: { background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.3)' },
  baja:  { background: 'rgba(74,222,128,0.12)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.3)'  },
};

function RotationBadge({ partNumber, value, onSaved, canEdit }) {
  const [saving, setSaving] = useState(false);
  const [hover, setHover] = useState(false);
  const [local, setLocal] = useState(value);

  useEffect(() => { setLocal(value); }, [value]);

  const handleClick = async () => {
    if (!canEdit || saving) return;
    const next = local ? (ROT_CYCLE[local] || 'alta') : 'alta';
    setLocal(next);
    setSaving(true);
    try {
      await authFetch(`/parts/admin/catalog/${encodeURIComponent(partNumber)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rotation_class: next }),
      });
      onSaved?.();
    } catch {
      setLocal(value);
      toast.error('Error al cambiar clasificación');
    } finally {
      setSaving(false);
    }
  };

  const baseStyle = {
    display: 'inline-block', fontSize: '0.58rem', fontWeight: 800,
    textTransform: 'uppercase', padding: '2px 7px', borderRadius: '20px',
    transition: 'all 0.15s',
  };

  if (!canEdit) {
    if (!local) return <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: '0.68rem' }}>—</span>;
    return <span style={{ ...baseStyle, ...ROT_STYLES[local] }}>{local}</span>;
  }

  if (!local) {
    return (
      <span
        onClick={handleClick}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        title="Asignar clasificación de rotación"
        style={{
          ...baseStyle, cursor: saving ? 'wait' : 'pointer',
          background: hover ? 'rgba(255,255,255,0.08)' : 'transparent',
          color: 'rgba(255,255,255,0.25)',
          border: `1px solid ${hover ? 'rgba(255,255,255,0.2)' : 'transparent'}`,
        }}
      >
        {saving ? '…' : '+ rot'}
      </span>
    );
  }

  return (
    <span
      onClick={handleClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title="Click para cambiar rotación"
      style={{
        ...baseStyle, ...ROT_STYLES[local], cursor: saving ? 'wait' : 'pointer',
        opacity: saving ? 0.5 : hover ? 0.75 : 1,
        transform: hover && !saving ? 'scale(1.07)' : 'scale(1)',
      }}
    >
      {saving ? '…' : local}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Items table dentro de un lote expandido
// ---------------------------------------------------------------------------
function LotItemsTable({ lotId, userRole, isConfirmed }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [showPhysicalUpload, setShowPhysicalUpload] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (filterStatus) params.append('item_status', filterStatus);
      const res = await authFetch(`${getApiUrl()}/imports/spare-part-lots/${lotId}/items?${params}`);
      const data = await res.json();
      setItems(Array.isArray(data) ? data.filter(i => i.status !== 'CANCELLED') : []);
    } catch {
      setItems([]);
      toast.error('Error al cargar los ítems del lote');
    } finally {
      setLoading(false);
    }
  }, [lotId, search, filterStatus]);

  useEffect(() => { fetch(); }, [fetch]);

  const canEdit = userRole === 'superadmin' || userRole === 'proveedor';
  const canCancel = userRole === 'superadmin' || userRole === 'administrativo';

  return (
    <div style={{ padding: '12px 16px 16px', background: 'rgba(0,0,0,0.2)' }}>
      {showPhysicalUpload && (
        <PhysicalInventoryUploadModal
          lotId={lotId}
          onClose={() => setShowPhysicalUpload(false)}
          onApplied={() => fetch()}
        />
      )}

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 180, padding: '6px 10px', borderRadius: '8px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
          <Search size={11} color="#606075" />
          <input
            placeholder="Buscar parte o descripción..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '11px', outline: 'none', flex: 1 }}
          />
        </div>
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          style={{ padding: '6px 10px', borderRadius: '8px', background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)', color: filterStatus ? '#fff' : '#606075', fontSize: '11px', outline: 'none' }}
        >
          <option value="">Todos los estados</option>
          {Object.entries(ITEM_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <button onClick={fetch} style={{ padding: '6px 8px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer', color: '#9ca3af' }}>
          <RefreshCw size={12} />
        </button>
        {isConfirmed && canEdit && (
          <button
            onClick={() => setShowPhysicalUpload(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '6px 12px', borderRadius: '8px', border: '1px solid rgba(251,146,60,0.3)',
              background: 'rgba(251,146,60,0.08)', color: '#fb923c',
              fontSize: '11px', fontWeight: 600, cursor: 'pointer',
            }}
          >
            <UploadCloud size={12} />
            Inv. Físico Excel
          </button>
        )}
      </div>

      {loading ? (
        <p style={{ color: '#606075', fontSize: '11px', textAlign: 'center', margin: '20px 0' }}>Cargando ítems...</p>
      ) : items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '24px 0', color: '#606075', fontSize: '11px' }}>
          <Package size={24} style={{ margin: '0 auto 8px', display: 'block', opacity: 0.4 }} />
          No hay ítems en este lote
        </div>
      ) : (
        <div style={{ overflowX: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
            <thead>
              <tr style={{ background: '#0e0e14' }}>
                {['Parte #', 'Descripción', 'Modelo', 'Rot.', 'Pcs Ord.', 'Pcs Rec.', 'Inv. Físico', 'Diferencia', 'FOB PI', 'Unit Price', 'Amount', 'Estado', ''].map(h => (
                  <th key={h} style={{ padding: '8px 10px', textAlign: 'center', fontSize: '9px', fontWeight: 700, color: h === 'Inv. Físico' ? '#fb923c' : h === 'Diferencia' ? '#a78bfa' : '#606075', textTransform: 'uppercase', letterSpacing: '0.07em', borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <td style={{ padding: '8px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    {canEdit
                      ? <EditableCell itemId={item.id} field="part_number" current={item.part_number} onSaved={fetch} readOnly={isConfirmed} cellStyle={{ color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace' }} />
                      : <span style={{ color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace' }}>{item.part_number}</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', color: '#d1d5db', maxWidth: 220 }}>
                    {canEdit ? (
                      <>
                        {/* description_es is the field this change unifies: superadmin
                            edits here get mirrored to parts_references.description_es_manual
                            and every other row sharing this part_number (set_description_es).
                            description (English) never propagates -- it's kept superadmin-only
                            too, for consistency with "only superadmin edits any name/description
                            field" (owner's explicit decision), not because it's part of the
                            source-of-truth mirror. Unlike part_number/qty above, these two
                            fields stay editable even after the lot's reconciliation is
                            confirmed (backend G4 `snapshot_fields` excludes them on purpose --
                            see sdd/parts-description-source-of-truth spec, "Repuestos
                            confirmed-lot: no change"), so no isConfirmed readOnly here. */}
                        <EditableCell
                          itemId={item.id}
                          field="description_es"
                          current={item.description_es}
                          onSaved={fetch}
                          readOnly={userRole !== 'superadmin'}
                          readOnlyTitle={SUPERADMIN_ONLY_NAME_EDIT_MESSAGE}
                          cellStyle={{ display: 'block' }}
                        />
                        <EditableCell
                          itemId={item.id}
                          field="description"
                          current={item.description}
                          onSaved={fetch}
                          readOnly={userRole !== 'superadmin'}
                          readOnlyTitle={SUPERADMIN_ONLY_NAME_EDIT_MESSAGE}
                          cellStyle={{ display: 'block', fontSize: '9px', color: '#606075', marginTop: 2 }}
                        />
                      </>
                    ) : (
                      <>
                        <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.description_es || ''}>{item.description_es || '—'}</span>
                        {item.description && <span style={{ display: 'block', fontSize: '9px', color: '#606075', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description}</span>}
                      </>
                    )}
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    {canEdit
                      ? <EditableCell itemId={item.id} field="model_applicable" current={item.model_applicable} onSaved={fetch} cellStyle={{ color: '#9ca3af' }} />
                      : <span style={{ color: '#9ca3af' }}>{item.model_applicable || '—'}</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                    <RotationBadge
                      partNumber={item.part_number}
                      value={item.rotation_class}
                      onSaved={fetch}
                      canEdit={userRole === 'superadmin'}
                    />
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                    {canEdit
                      ? <EditableCell itemId={item.id} field="qty_ordered" current={item.qty_ordered} type="number" align="center" onSaved={fetch} readOnly={isConfirmed} cellStyle={{ color: '#d1d5db' }} />
                      : <span style={{ color: '#d1d5db' }}>{item.qty_ordered}</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                    {canEdit
                      ? <EditableQty itemId={item.id} current={item.qty_received} max={item.qty_ordered} onSaved={fetch} readOnly={isConfirmed} />
                      : <span style={{ color: item.qty_received > 0 ? '#22c55e' : '#9ca3af', fontWeight: 700 }}>{item.qty_received}</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                    {isConfirmed && canEdit ? (
                      <EditableCell
                        itemId={item.id}
                        field="qty_physical"
                        current={item.qty_physical ?? item.qty_received}
                        type="number"
                        align="center"
                        onSaved={fetch}
                        cellStyle={{
                          color: item.qty_physical != null && item.qty_physical !== item.qty_received ? '#f87171' : '#9ca3af',
                          fontStyle: item.qty_physical == null ? 'italic' : 'normal',
                          opacity: item.qty_physical == null ? 0.6 : 1,
                        }}
                      />
                    ) : (
                      <span style={{ color: '#3f3f55', fontSize: '10px' }}>—</span>
                    )}
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', fontWeight: 700 }}>
                    {(() => {
                      const ref = item.qty_physical != null ? item.qty_physical : item.qty_received;
                      const diff = (ref ?? 0) - (item.qty_ordered ?? 0);
                      if (diff > 0) return <span style={{ color: '#34d399' }}>+{diff}</span>;
                      if (diff < 0) return <span style={{ color: '#f87171' }}>{diff}</span>;
                      return <span style={{ color: '#3f3f55' }}>—</span>;
                    })()}
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    <span style={{ color: item.fob_pi != null ? '#34d399' : 'rgba(255,255,255,0.15)', fontWeight: item.fob_pi != null ? 700 : 400 }}>
                      {item.fob_pi != null ? `$${parseFloat(item.fob_pi).toFixed(2)}` : '—'}
                    </span>
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    {canEdit
                      ? <EditableCell itemId={item.id} field="unit_price" current={item.unit_price != null ? parseFloat(item.unit_price).toFixed(2) : null} type="number" align="center" onSaved={fetch} cellStyle={{ color: '#d1d5db' }} />
                      : <span style={{ color: '#d1d5db' }}>{item.unit_price != null ? `$${parseFloat(item.unit_price).toFixed(2)}` : '—'}</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    {canEdit
                      ? <EditableCell itemId={item.id} field="amount" current={item.amount != null ? parseFloat(item.amount).toFixed(2) : null} type="number" align="center" onSaved={fetch} cellStyle={{ color: '#a78bfa', fontWeight: 700 }} />
                      : <span style={{ color: '#a78bfa', fontWeight: 700 }}>{item.amount != null ? `$${parseFloat(item.amount).toFixed(2)}` : '—'}</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                    {canEdit
                      ? <EditableStatus itemId={item.id} current={item.status} onSaved={fetch} readOnly={isConfirmed} />
                      : <ItemStatusBadge status={item.status} />
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', width: 32 }}>
                    {canCancel && (item.status === 'BACKORDER' || item.status === 'BACKORDER_PARCIAL' || (item.status === 'PARTIAL' && (item.qty_pending ?? 0) > 0)) && (
                      <button
                        onClick={() => {
                          const qty = item.qty_pending ?? 0;
                          setPendingConfirm({
                            title: 'Cancelar pendientes',
                            message: `¿Cancelar las ${qty} unidades pendientes de ${item.part_number}? Esta acción cerrará el backorder.`,
                            danger: true,
                            confirmLabel: 'Sí, cancelar',
                            action: async () => {
                              try {
                                const res = await authFetch(`${getApiUrl()}/imports/spare-part-items/${item.id}/cancel-pending`, { method: 'POST' });
                                if (!res.ok) {
                                  const data = await res.json().catch(() => ({}));
                                  const detail = data?.detail;
                                  const message = typeof detail === 'string' ? detail : detail?.detail || 'Error al cancelar las unidades pendientes';
                                  throw new Error(message);
                                }
                                fetch();
                              } catch (err) {
                                toast.error(err.message || 'Error al cancelar las unidades pendientes');
                              }
                            },
                          });
                        }}
                        title="Cancelar unidades pendientes"
                        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '4px', borderRadius: '5px', border: 'none', background: 'transparent', color: '#6b7280', cursor: 'pointer' }}
                        onMouseEnter={e => e.currentTarget.style.color = '#f87171'}
                        onMouseLeave={e => e.currentTarget.style.color = '#6b7280'}
                      >
                        <XCircle size={13} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pendingConfirm && (
        <ConfirmModal
          title={pendingConfirm.title}
          message={pendingConfirm.message}
          danger={pendingConfirm.danger}
          confirmLabel={pendingConfirm.confirmLabel}
          onCancel={() => setPendingConfirm(null)}
          onConfirm={() => { setPendingConfirm(null); pendingConfirm.action(); }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fila de un lote (expandible)
// ---------------------------------------------------------------------------
function LotRow({ lot, userRole, onReconcile, onReconcileBackorders, onRefresh }) {
  const [expanded, setExpanded] = useState(false);
  const [deduplicating, setDeduplicating] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState(null);
  const [openBackordersCount, setOpenBackordersCount] = useState(0);

  const pctColor = lot.pct_received >= 100 ? '#22c55e' : lot.pct_received > 0 ? '#fb923c' : '#606075';

  useEffect(() => {
    let cancelled = false;
    authFetch(`${getApiUrl()}/imports/backorders?origin_pi=${encodeURIComponent(lot.lot_identifier)}&resolved=false`)
      .then(res => res.ok ? res.json() : [])
      .then(data => { if (!cancelled) setOpenBackordersCount(Array.isArray(data) ? data.length : 0); })
      .catch(() => { if (!cancelled) setOpenBackordersCount(0); });
    return () => { cancelled = true; };
  }, [lot.lot_identifier]);

  const handleRollback = (e) => {
    e.stopPropagation();
    setPendingConfirm({
      title: `Revertir lote ${lot.lot_identifier}`,
      message: `Se borrarán: ítems, backorders, reconciliación y packing list.\nEl lote quedará vacío para re-cargar desde cero.\n\nEsta acción no se puede deshacer.`,
      danger: true,
      confirmLabel: 'Sí, revertir',
      action: async () => {
        setDeduplicating(true);
        try {
          const res = await authFetch(
            `${getApiUrl()}/imports/spare-parts/rollback-lot?pi_number=${encodeURIComponent(lot.lot_identifier)}`,
            { method: 'POST' }
          );
          const data = await res.json();
          const msg = Object.entries(data.deleted).map(([k, v]) => `${k}: ${v}`).join(', ');
          toast.success(`Rollback completo. Eliminados → ${msg}`);
          onRefresh?.();
        } catch {
          toast.error('Error al ejecutar el rollback');
        } finally {
          setDeduplicating(false);
        }
      },
    });
  };

  const handleDeduplicate = (e) => {
    e.stopPropagation();
    setPendingConfirm({
      title: 'Eliminar duplicados',
      message: `¿Eliminar ítems duplicados sin backorders del lote ${lot.lot_identifier}? Esta acción no se puede deshacer.`,
      danger: true,
      confirmLabel: 'Sí, limpiar',
      action: async () => {
        setDeduplicating(true);
        try {
          const res = await authFetch(
            `${getApiUrl()}/imports/spare-parts/repair-deduplicate?pi_number=${encodeURIComponent(lot.lot_identifier)}`,
            { method: 'POST' }
          );
          const data = await res.json();
          toast.success(`Limpieza completa: ${data.deleted} duplicados eliminados, ${data.kept} ítems conservados.`);
        } catch {
          toast.error('Error al limpiar duplicados');
        } finally {
          setDeduplicating(false);
        }
      },
    });
  };

  return (
    <div style={{ border: '1px solid rgba(255,255,255,0.06)', borderRadius: '10px', overflow: 'hidden' }}>
      {/* Header del lote */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: '14px',
          padding: '12px 16px', cursor: 'pointer', background: expanded ? 'rgba(255,255,255,0.03)' : '#13131a',
          transition: 'background 0.15s',
        }}
        onMouseEnter={e => { if (!expanded) e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
        onMouseLeave={e => { if (!expanded) e.currentTarget.style.background = '#13131a'; }}
      >
        {expanded
          ? <ChevronDown size={14} color="#606075" style={{ flexShrink: 0 }} />
          : <ChevronRight size={14} color="#606075" style={{ flexShrink: 0 }} />
        }

        {/* Lot identifier + modelos */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ margin: '0 0 4px 0', fontSize: '12px', fontWeight: 700, color: '#60a5fa', fontFamily: 'monospace' }}>
            {lot.lot_identifier}
          </p>
          {lot.models?.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px' }}>
              {lot.models.map(m => (
                <span key={m} style={{ fontSize: '8px', fontWeight: 700, padding: '1px 6px', borderRadius: '20px', background: 'rgba(96,165,250,0.1)', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.2)', whiteSpace: 'nowrap' }}>{m}</span>
              ))}
            </div>
          )}
        </div>

        {/* Items count + total qty */}
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <div style={{ textAlign: 'center', minWidth: 50 }}>
            <p style={{ margin: 0, fontSize: '14px', fontWeight: 800, color: '#fff' }}>{lot.items_count}</p>
            <p style={{ margin: 0, fontSize: '9px', color: '#606075', fontWeight: 600 }}>refs</p>
          </div>
          <div style={{ textAlign: 'center', minWidth: 50 }}>
            <p style={{ margin: 0, fontSize: '14px', fontWeight: 800, color: '#e2e8f0' }}>{(lot.total_qty_ordered || 0).toLocaleString()}</p>
            <p style={{ margin: 0, fontSize: '9px', color: '#606075', fontWeight: 600 }}>unidades</p>
          </div>
        </div>

        {/* % recibido */}
        <div style={{ minWidth: 90 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ fontSize: '9px', color: '#606075', fontWeight: 600 }}>Recibido</span>
            <span style={{ fontSize: '10px', color: pctColor, fontWeight: 800 }}>{lot.pct_received}%</span>
          </div>
          <div style={{ height: 4, borderRadius: 4, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${Math.min(100, lot.pct_received)}%`, background: pctColor, borderRadius: 4, transition: 'width 0.4s' }} />
          </div>
        </div>

        {/* Valor pedido + valor PL apilados */}
        <div style={{ textAlign: 'right', minWidth: 120, display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {lot.fob_value != null
            ? <>
                <p style={{ margin: 0, fontSize: '13px', fontWeight: 800, color: lot.fob_value_is_estimate ? '#fb923c' : '#34d399' }}>
                  ${parseFloat(lot.fob_value).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </p>
                <p style={{ margin: 0, fontSize: '9px', color: '#606075' }}>
                  {lot.fob_value_is_estimate ? 'Pedido est. USD' : 'Pedido USD'}
                </p>
              </>
            : <p style={{ margin: 0, fontSize: '11px', color: '#3f3f55' }}>—</p>
          }
          {(lot.total_declared_value != null || lot.pl_value != null)
            ? <>
                <p style={{ margin: 0, fontSize: '12px', fontWeight: 700, color: '#a78bfa' }}>
                  ${parseFloat(lot.total_declared_value ?? lot.pl_value).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </p>
                <p style={{ margin: 0, fontSize: '9px', color: '#606075' }}>Packing list USD</p>
              </>
            : null
          }
        </div>

        {/* Rotación */}
        {lot.rotation_pct && Object.keys(lot.rotation_pct).length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', minWidth: 80 }}>
            {[['alta','#ef4444'],['media','#fbbf24'],['baja','#4ade80'],['sin_clasificar','#606075']].map(([rc, color]) =>
              lot.rotation_pct[rc] != null ? (
                <div key={rc} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                  <span style={{ fontSize: '8px', fontWeight: 800, color, textTransform: 'uppercase', width: 28 }}>{rc === 'sin_clasificar' ? 'S/C' : rc}</span>
                  <div style={{ flex: 1, height: 3, borderRadius: 3, background: 'rgba(255,255,255,0.06)', overflow: 'hidden', minWidth: 40 }}>
                    <div style={{ height: '100%', width: `${lot.rotation_pct[rc]}%`, background: color, borderRadius: 3 }} />
                  </div>
                  <span style={{ fontSize: '8px', color, fontWeight: 700, minWidth: 28, textAlign: 'right' }}>{lot.rotation_pct[rc]}%</span>
                </div>
              ) : null
            )}
          </div>
        )}

        {/* Detail loaded badge */}
        <div style={{ flexShrink: 0 }}>
          {lot.detail_loaded
            ? <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(34,197,94,0.1)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.25)' }}>CARGADO</span>
            : <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(249,115,22,0.1)', color: '#f97316', border: '1px solid rgba(249,115,22,0.25)' }}>PENDIENTE</span>
          }
        </div>

        {/* Botón reconciliación */}
        <button
          onClick={e => { e.stopPropagation(); onReconcile(lot); }}
          title="Reconciliar packing list del proveedor"
          style={{
            display: 'flex', alignItems: 'center', gap: '5px',
            padding: '5px 10px', borderRadius: '7px', border: 'none',
            background: lot.packing_list_received ? 'rgba(34,197,94,0.1)' : 'rgba(255,255,255,0.06)',
            color: lot.packing_list_received ? '#22c55e' : '#9ca3af',
            fontSize: '10px', fontWeight: 700, cursor: 'pointer', flexShrink: 0,
          }}
        >
          <ClipboardCheck size={12} />
          {lot.packing_list_received ? 'Ver PL' : 'Packing List'}
        </button>

        {/* Botón reconciliación de backorders — sólo si el lote tiene backorders abiertos */}
        {openBackordersCount > 0 && (
          <button
            onClick={e => { e.stopPropagation(); onReconcileBackorders(lot); }}
            title="Reconciliar packing list remanente contra los backorders abiertos"
            style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '5px 10px', borderRadius: '7px', border: 'none',
              background: 'rgba(248,113,113,0.1)', color: '#f87171',
              fontSize: '10px', fontWeight: 700, cursor: 'pointer', flexShrink: 0,
            }}
          >
            <AlertTriangle size={12} />
            Backorders ({openBackordersCount})
          </button>
        )}

        {/* TEMPORAL: rollback de lote — solo superadmin */}
        {userRole === 'superadmin' && (
          <button
            onClick={handleRollback}
            disabled={deduplicating}
            title="Revertir lote completo para re-cargar desde cero"
            style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '5px 10px', borderRadius: '7px', border: 'none',
              background: 'rgba(248,113,113,0.1)',
              color: deduplicating ? '#606075' : '#f87171',
              fontSize: '10px', fontWeight: 700,
              cursor: deduplicating ? 'not-allowed' : 'pointer', flexShrink: 0,
            }}
          >
            <XCircle size={12} />
            {deduplicating ? 'Revirtiendo...' : 'Rollback'}
          </button>
        )}

        {userRole === 'superadmin' && (
          <button
            onClick={handleDeduplicate}
            disabled={deduplicating}
            title="Eliminar ítems duplicados sin backorders"
            style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '5px 10px', borderRadius: '7px', border: 'none',
              background: 'rgba(248,113,113,0.1)',
              color: deduplicating ? '#606075' : '#f87171',
              fontSize: '10px', fontWeight: 700,
              cursor: deduplicating ? 'not-allowed' : 'pointer', flexShrink: 0,
            }}
          >
            <XCircle size={12} />
            {deduplicating ? 'Limpiando...' : 'Fix duplic.'}
          </button>
        )}
      </div>

      {/* Contenido expandido */}
      {expanded && <LotItemsTable lotId={lot.id} userRole={userRole} isConfirmed={!!lot.reconciliation_confirmed} />}

      {pendingConfirm && (
        <ConfirmModal
          title={pendingConfirm.title}
          message={pendingConfirm.message}
          danger={pendingConfirm.danger}
          confirmLabel={pendingConfirm.confirmLabel}
          onCancel={() => setPendingConfirm(null)}
          onConfirm={() => { setPendingConfirm(null); pendingConfirm.action(); }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SparePartsTab principal
// ---------------------------------------------------------------------------
export default function SparePartsTab({ userRole }) {
  const [lots, setLots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterLoaded, setFilterLoaded] = useState('');
  const [filterBL, setFilterBL] = useState(false);
  const [partSearch, setPartSearch] = useState('');
  const [partSearchResults, setPartSearchResults] = useState(null);
  const [lotStats, setLotStats] = useState({ unique_refs: null, declared_refs: null });
  const [reconcileLot, setReconcileLot] = useState(null);
  const [reconcileBackorderLot, setReconcileBackorderLot] = useState(null);
  const [repairingExtras, setRepairingExtras] = useState(false);
  const [repairingBackorders, setRepairingBackorders] = useState(false);
  const [exportingRepuestos, setExportingRepuestos] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState(null);

  // FOB PI upload
  const [showFobUpload, setShowFobUpload] = useState(false);
  const [fobFile, setFobFile]             = useState(null);
  const [fobUploading, setFobUploading]   = useState(false);
  const [fobResult, setFobResult]         = useState(null);

  const handleFobImport = async () => {
    if (!fobFile) return;
    setFobUploading(true);
    setFobResult(null);
    try {
      const fd = new FormData();
      fd.append('file', fobFile);
      const res  = await authFetch(`${getApiUrl()}/parts/admin/fob-preliminary-import`, { method: 'POST', body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setFobResult({ error: data.detail || `Error ${res.status}` });
      } else {
        setFobResult(data);
      }
    } catch { setFobResult({ error: 'Error de conexión' }); }
    finally { setFobUploading(false); }
  };

  const handleExportRepuestos = async () => {
    setExportingRepuestos(true);
    try {
      const params = new URLSearchParams();
      if (filterLoaded !== '') params.append('detail_loaded', filterLoaded);
      if (filterBL) params.append('has_bl', 'true');
      const res = await authFetch(`${getApiUrl()}/imports/spare-parts/export?${params}`);
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `repuestos_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Error al exportar el listado de repuestos');
    } finally {
      setExportingRepuestos(false);
    }
  };

  const handleRepairExtras = () => {
    setPendingConfirm({
      title: 'Reparar ítems EXTRA',
      message: 'Actualiza las Pcs Rec. de todos los ítems EXTRA que quedaron en 0. ¿Continuar?',
      danger: false,
      confirmLabel: 'Sí, reparar',
      action: async () => {
        setRepairingExtras(true);
        try {
          const res = await authFetch(`${getApiUrl()}/imports/backorders/repair-extra-received`, { method: 'POST' });
          const data = await res.json();
          toast.success(`Reparación completa: ${data.fixed} ítems actualizados${data.errors?.length ? `, ${data.errors.length} errores` : ''}`);
          fetchLots(); fetchStats();
        } catch { toast.error('Error en la reparación'); }
        finally { setRepairingExtras(false); }
      },
    });
  };

  const handleRepairUnresolvedBackorders = () => {
    setPendingConfirm({
      title: 'Reparar backorders sin cerrar',
      message: 'Cierra (resolved=true) los backorders que ya llegaron a 0 pendientes por un cruce de EXTRA pero quedaron abiertos por un bug ya corregido. ¿Continuar?',
      danger: false,
      confirmLabel: 'Sí, reparar',
      action: async () => {
        setRepairingBackorders(true);
        try {
          const res = await authFetch(`${getApiUrl()}/imports/backorders/repair-unresolved-zero-pending`, { method: 'POST' });
          const data = await res.json();
          toast.success(`Reparación completa: ${data.fixed} backorder${data.fixed !== 1 ? 's' : ''} cerrado${data.fixed !== 1 ? 's' : ''}`);
          fetchLots(); fetchStats();
        } catch { toast.error('Error en la reparación'); }
        finally { setRepairingBackorders(false); }
      },
    });
  };

  const fetchLots = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterLoaded !== '') params.append('detail_loaded', filterLoaded);
      if (filterBL) params.append('has_bl', 'true');
      const res = await authFetch(`${getApiUrl()}/imports/spare-part-lots?${params}`);
      const data = await res.json();
      setLots(Array.isArray(data) ? data : []);
    } catch {
      setLots([]);
      toast.error('Error al cargar los lotes de repuestos');
    } finally {
      setLoading(false);
    }
  }, [filterLoaded, filterBL]);

  const fetchStats = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filterLoaded !== '') params.append('detail_loaded', filterLoaded);
      if (filterBL) params.append('has_bl', 'true');
      const res = await authFetch(`${getApiUrl()}/imports/spare-part-lots/stats?${params}`);
      const data = await res.json();
      setLotStats(data);
    } catch {
      setLotStats({ unique_refs: null, declared_refs: null });
      toast.error('Error al cargar las estadísticas de lotes');
    }
  }, [filterLoaded, filterBL]);

  useEffect(() => { fetchLots(); fetchStats(); }, [fetchLots, fetchStats]);

  const handlePartSearch = async (q) => {
    const trimmed = q.trim();
    if (trimmed.length < 2) { setPartSearchResults(null); return; }
    try {
      const res = await authFetch(`${getApiUrl()}/imports/spare-parts/search?q=${encodeURIComponent(trimmed)}`);
      if (!res.ok) throw new Error();
      setPartSearchResults(await res.json());
    } catch {
      setPartSearchResults([]);
    }
  };

  // Totales del header
  const totalLots = lots.length;
  const totalItems = lots.reduce((acc, l) => acc + (l.total_qty_ordered || 0), 0);
  const totalValue = lots.reduce((acc, l) => acc + (parseFloat(l.total_declared_value) || 0), 0);
  const totalFobValue = lots.reduce((acc, l) => acc + (l.fob_value || 0), 0);
  const fobIsEstimate = lots.some(l => l.fob_value_is_estimate);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {/* KPIs rápidos */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '10px' }}>
        {[
          { label: 'Lotes activos', value: totalLots, color: '#60a5fa' },
          { label: 'Unidades totales', value: totalItems.toLocaleString(), color: '#a78bfa' },
          { label: 'Refs. únicas', value: lotStats.unique_refs ?? '—', color: '#f59e0b' },
          { label: 'Refs. declaradas', value: lotStats.declared_refs ?? '—', color: '#34d399' },
          { label: 'Valor declarado', value: totalValue > 0 ? `$${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—', color: '#22c55e' },
          {
            label: totalFobValue > 0 ? (fobIsEstimate ? 'Total FOB est. USD' : 'Total FOB USD') : 'Total FOB USD',
            value: totalFobValue > 0 ? `$${totalFobValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—',
            color: totalFobValue > 0 ? (fobIsEstimate ? '#fb923c' : '#34d399') : '#606075',
          },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ padding: '14px 16px', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <p style={{ margin: 0, fontSize: '18px', fontWeight: 800, color }}>{value}</p>
            <p style={{ margin: '2px 0 0', fontSize: '10px', color: '#606075', fontWeight: 600 }}>{label}</p>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          value={filterLoaded}
          onChange={e => setFilterLoaded(e.target.value)}
          style={{ padding: '7px 10px', borderRadius: '8px', background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)', color: filterLoaded === '' ? '#606075' : '#fff', fontSize: '11px', outline: 'none' }}
        >
          <option value="">Todos los lotes</option>
          <option value="true">Con detalle cargado</option>
          <option value="false">Sin detalle</option>
        </select>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '11px', color: filterBL ? '#fff' : '#606075', padding: '6px 10px', borderRadius: '8px', background: filterBL ? 'rgba(96,165,250,0.1)' : 'rgba(255,255,255,0.04)', border: `1px solid ${filterBL ? 'rgba(96,165,250,0.25)' : 'rgba(255,255,255,0.07)'}` }}>
          <input
            type="checkbox"
            checked={filterBL}
            onChange={e => setFilterBL(e.target.checked)}
            style={{ accentColor: '#60a5fa' }}
          />
          Solo con BL
        </label>
        <button onClick={fetchLots} style={{ padding: '7px 9px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer', color: '#9ca3af' }}>
          <RefreshCw size={13} />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 10px', borderRadius: '8px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', minWidth: '220px' }}>
          <Search size={13} style={{ color: '#606075', flexShrink: 0 }} />
          <input
            type="text"
            value={partSearch}
            onChange={e => setPartSearch(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handlePartSearch(partSearch); }}
            placeholder="Buscar referencia en pedidos..."
            style={{ background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: '11px', width: '100%' }}
          />
          {partSearch && (
            <button onClick={() => { setPartSearch(''); setPartSearchResults(null); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: 0, display: 'flex' }}>
              <XCircle size={13} />
            </button>
          )}
        </div>

        {/* Exportar Excel (solo superadmin) */}
        {userRole === 'superadmin' && (
          <button
            onClick={handleExportRepuestos}
            disabled={exportingRepuestos}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px', border: 'none',
              background: exportingRepuestos ? 'rgba(34,197,94,0.06)' : 'rgba(34,197,94,0.12)',
              color: exportingRepuestos ? '#606075' : '#22c55e',
              fontSize: '11px', fontWeight: 700, cursor: exportingRepuestos ? 'not-allowed' : 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            <FileSpreadsheet size={13} />
            {exportingRepuestos ? 'Exportando...' : 'Exportar Excel'}
          </button>
        )}

        {/* Cargar FOB de PI (solo superadmin) */}
        {userRole === 'superadmin' && (
          <button
            onClick={() => { setShowFobUpload(true); setFobFile(null); setFobResult(null); }}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px',
              border: '1px solid rgba(251,146,60,0.3)',
              background: 'rgba(251,146,60,0.1)', color: '#fb923c',
              fontSize: '11px', fontWeight: 700, cursor: 'pointer', letterSpacing: '0.04em',
            }}
          >
            <UploadCloud size={13} /> Cargar FOB PI
          </button>
        )}

        <span style={{ fontSize: '11px', color: '#606075', marginLeft: 'auto' }}>
          {totalLots} lote{totalLots !== 1 ? 's' : ''} encontrado{totalLots !== 1 ? 's' : ''}
        </span>

        {userRole === 'superadmin' && (
          <button
            onClick={handleRepairExtras}
            disabled={repairingExtras}
            title="Actualiza las Pcs Rec. de ítems EXTRA que quedaron en 0 antes del fix"
            style={{ padding: '7px 12px', borderRadius: '8px', border: '1px solid rgba(52,211,153,0.3)', background: 'rgba(52,211,153,0.08)', color: repairingExtras ? '#606075' : '#34d399', fontSize: '11px', fontWeight: 700, cursor: repairingExtras ? 'not-allowed' : 'pointer' }}
          >
            {repairingExtras ? 'Reparando...' : '⚙ Reparar Pcs Rec. extras'}
          </button>
        )}

        {userRole === 'superadmin' && (
          <button
            onClick={handleRepairUnresolvedBackorders}
            disabled={repairingBackorders}
            title="Cierra backorders que llegaron a 0 pendientes por cruce EXTRA pero quedaron abiertos por un bug ya corregido"
            style={{ padding: '7px 12px', borderRadius: '8px', border: '1px solid rgba(52,211,153,0.3)', background: 'rgba(52,211,153,0.08)', color: repairingBackorders ? '#606075' : '#34d399', fontSize: '11px', fontWeight: 700, cursor: repairingBackorders ? 'not-allowed' : 'pointer' }}
          >
            {repairingBackorders ? 'Reparando...' : '⚙ Reparar backorders sin cerrar'}
          </button>
        )}

      </div>

      {/* Resultados de búsqueda por referencia */}
      {partSearchResults !== null && (
        <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', padding: '14px 16px' }}>
          <p style={{ margin: '0 0 10px', fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#606075' }}>
            Resultados para &ldquo;{partSearch}&rdquo; — {partSearchResults.length} {partSearchResults.length === 1 ? 'pedido encontrado' : 'pedidos encontrados'}
          </p>
          {partSearchResults.length === 0 ? (
            <p style={{ margin: 0, fontSize: '12px', color: '#606075' }}>No se encontró esa referencia en ningún pedido.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {partSearchResults.map(lot => (
                <div key={lot.lot_id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '10px', padding: '10px 14px' }}>
                  <p style={{ margin: '0 0 8px', fontSize: '12px', fontWeight: 800, color: '#60a5fa' }}>{lot.lot_identifier}</p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {lot.items.map((item, i) => {
                      const s = ITEM_STATUS[item.status] || { label: item.status, color: '#9ca3af', bg: 'rgba(156,163,175,0.12)', border: 'rgba(156,163,175,0.3)' };
                      return (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '11px' }}>
                          <span style={{ fontWeight: 700, color: '#fff', fontFamily: 'monospace' }}>{item.part_number}</span>
                          {item.description_es && <span style={{ color: '#9ca3af' }}>{item.description_es}</span>}
                          <span style={{ marginLeft: 'auto', whiteSpace: 'nowrap', color: '#606075' }}>Ped: {item.qty_ordered} · Rec: {item.qty_received}</span>
                          <span style={{ padding: '2px 8px', borderRadius: '6px', fontSize: '10px', fontWeight: 700, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{s.label}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Lista de lotes */}
      {loading ? (
        <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '40px 0' }}>Cargando lotes...</p>
      ) : lots.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#606075' }}>
          <Package size={36} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
          <p style={{ fontSize: '13px', margin: 0 }}>No hay lotes de repuestos</p>
          <p style={{ fontSize: '11px', margin: '4px 0 0', color: '#404050' }}>Importá un Shipping Doc con SP para ver los lotes</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {lots.map(lot => (
            <LotRow
              key={lot.id}
              lot={lot}
              userRole={userRole}
              onReconcile={setReconcileLot}
              onReconcileBackorders={setReconcileBackorderLot}
              onRefresh={() => { fetchLots(); fetchStats(); }}
            />
          ))}
        </div>
      )}

      {/* Modal de reconciliación */}
      {reconcileLot && (
        <ReconciliationModal
          lot={reconcileLot}
          userRole={userRole}
          onClose={() => setReconcileLot(null)}
          onConfirmed={() => { fetchLots(); fetchStats(); setReconcileLot(null); }}
        />
      )}

      {/* Modal de reconciliación de backorders */}
      {reconcileBackorderLot && (
        <BackorderReconciliationModal
          lot={reconcileBackorderLot}
          onClose={() => setReconcileBackorderLot(null)}
          onConfirmed={() => { fetchLots(); fetchStats(); }}
        />
      )}

      {pendingConfirm && (
        <ConfirmModal
          title={pendingConfirm.title}
          message={pendingConfirm.message}
          danger={pendingConfirm.danger}
          confirmLabel={pendingConfirm.confirmLabel}
          onCancel={() => setPendingConfirm(null)}
          onConfirm={() => { setPendingConfirm(null); pendingConfirm.action(); }}
        />
      )}

      {showFobUpload && (
        <div onClick={() => !fobUploading && setShowFobUpload(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ background: '#0c0c0e', border: '1px solid rgba(251,146,60,0.25)', borderRadius: '16px', padding: '2rem', width: '100%', maxWidth: '480px', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <UploadCloud size={16} color="#fb923c" />
              <p style={{ color: '#fff', fontWeight: 900, fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>Cargar FOB desde PI</p>
            </div>
            <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)', margin: 0, lineHeight: 1.6 }}>
              Excel con columnas <strong style={{ color: 'rgba(255,255,255,0.6)' }}>referencia</strong> · <strong style={{ color: 'rgba(255,255,255,0.6)' }}>pi_number</strong> · <strong style={{ color: 'rgba(255,255,255,0.6)' }}>fob_price</strong>. Un solo archivo con todos los PIs.
            </p>
            <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem', padding: '1.5rem', borderRadius: '10px', border: `2px dashed ${fobFile ? 'rgba(251,146,60,0.4)' : 'rgba(255,255,255,0.1)'}`, background: fobFile ? 'rgba(251,146,60,0.05)' : 'rgba(255,255,255,0.02)', cursor: 'pointer' }}>
              <UploadCloud size={22} color={fobFile ? '#fb923c' : 'rgba(255,255,255,0.2)'} />
              <span style={{ fontSize: '0.72rem', color: fobFile ? '#fb923c' : 'rgba(255,255,255,0.3)', fontWeight: 600 }}>{fobFile ? fobFile.name : 'Seleccionar .xlsx'}</span>
              <input type="file" accept=".xlsx" style={{ display: 'none' }} onChange={e => { setFobFile(e.target.files[0] || null); setFobResult(null); }} />
            </label>
            {fobResult && !fobResult.error && (
              <div style={{ background: 'rgba(74,222,128,0.05)', border: '1px solid rgba(74,222,128,0.2)', borderRadius: '10px', padding: '0.875rem 1rem' }}>
                <p style={{ margin: '0 0 0.3rem', fontSize: '0.72rem', fontWeight: 700, color: '#4ade80' }}>✅ FOB cargado</p>
                <p style={{ margin: 0, fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', lineHeight: 1.7 }}>
                  Ítems: <strong style={{ color: '#fff' }}>{fobResult.items_updated}</strong> &nbsp;·&nbsp;
                  Catálogo: <strong style={{ color: '#fff' }}>{fobResult.refs_updated}</strong> refs &nbsp;·&nbsp;
                  PI no encontrados: <strong style={{ color: '#fb923c' }}>{fobResult.skipped_no_pi}</strong> &nbsp;·&nbsp;
                  Refs no encontradas: <strong style={{ color: '#ef4444' }}>{fobResult.refs_not_found}</strong>
                </p>
              </div>
            )}
            {fobResult?.error && <p style={{ fontSize: '0.72rem', color: '#ef4444', margin: 0 }}>⚠️ {fobResult.error}</p>}
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button onClick={handleFobImport} disabled={!fobFile || fobUploading}
                style={{ flex: 1, background: 'rgba(251,146,60,0.15)', color: '#fb923c', border: '1px solid rgba(251,146,60,0.3)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', cursor: (!fobFile || fobUploading) ? 'not-allowed' : 'pointer', opacity: (!fobFile || fobUploading) ? 0.4 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}>
                <UploadCloud size={13} /> {fobUploading ? 'Cargando...' : 'Cargar'}
              </button>
              <button onClick={() => setShowFobUpload(false)} disabled={fobUploading}
                style={{ flex: 1, background: 'rgba(255,255,255,0.03)', color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', cursor: 'pointer' }}>
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
