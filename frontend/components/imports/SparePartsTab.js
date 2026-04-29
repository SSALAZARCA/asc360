'use client';
import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../../lib/authFetch';
import { ChevronDown, ChevronRight, Search, RefreshCw, Package, ClipboardCheck, XCircle } from 'lucide-react';
import ExcelUploadModal from './ExcelUploadModal';
import ReconciliationModal from './ReconciliationModal';

function API() {
  return (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');
}

// ---------------------------------------------------------------------------
// Status badge para spare part items
// ---------------------------------------------------------------------------
const ITEM_STATUS = {
  PENDING:   { label: 'Pendiente',  color: '#9ca3af', bg: 'rgba(156,163,175,0.12)', border: 'rgba(156,163,175,0.3)' },
  PARTIAL:   { label: 'Parcial',    color: '#fb923c', bg: 'rgba(251,146,60,0.12)',  border: 'rgba(251,146,60,0.3)' },
  RECEIVED:  { label: 'Recibido',   color: '#22c55e', bg: 'rgba(34,197,94,0.12)',   border: 'rgba(34,197,94,0.3)' },
  BACKORDER: { label: 'Backorder',  color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
  CANCELLED: { label: 'Cancelado',  color: '#6b7280', bg: 'rgba(107,114,128,0.12)', border: 'rgba(107,114,128,0.3)' },
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
function EditableCell({ itemId, field, current, type = 'text', align = 'left', cellStyle = {}, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [hover, setHover] = useState(false);
  const [value, setValue] = useState(current ?? '');

  const save = async () => {
    setEditing(false);
    const parsed = type === 'number' ? (value === '' ? null : parseFloat(value)) : (String(value).trim() || null);
    if (parsed === (current ?? null)) return;
    try {
      await authFetch(`${API()}/imports/spare-part-items/${itemId}`, {
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
function EditableStatus({ itemId, current, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(current);

  const save = async (newVal) => {
    setValue(newVal);
    setEditing(false);
    try {
      await authFetch(`${API()}/imports/spare-part-items/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newVal }),
      });
      onSaved?.();
    } catch { /* silencioso */ }
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

function EditableQty({ itemId, current, max, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(current);

  const save = async () => {
    setEditing(false);
    const num = parseInt(value, 10);
    if (isNaN(num) || num === current) return;
    try {
      await authFetch(`${API()}/imports/spare-part-items/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qty_received: num }),
      });
      onSaved?.();
    } catch { setValue(current); }
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
// Items table dentro de un lote expandido
// ---------------------------------------------------------------------------
function LotItemsTable({ lotId, userRole, isConfirmed }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (filterStatus) params.append('item_status', filterStatus);
      const res = await authFetch(`${API()}/imports/spare-part-lots/${lotId}/items?${params}`);
      const data = await res.json();
      setItems(Array.isArray(data) ? data.filter(i => i.status !== 'CANCELLED') : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [lotId, search, filterStatus]);

  useEffect(() => { fetch(); }, [fetch]);

  const canEdit = userRole === 'superadmin' || userRole === 'proveedor';
  const canCancel = userRole === 'superadmin' || userRole === 'administrativo';

  return (
    <div style={{ padding: '12px 16px 16px', background: 'rgba(0,0,0,0.2)' }}>
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
                {['Parte #', 'Descripción', 'Modelo', 'Pcs Ord.', 'Pcs Rec.', 'Inv. Físico', 'Pendiente', 'Unit Price', 'Amount', 'Estado', ''].map(h => (
                  <th key={h} style={{ padding: '8px 10px', textAlign: 'center', fontSize: '9px', fontWeight: 700, color: h === 'Inv. Físico' ? '#fb923c' : '#606075', textTransform: 'uppercase', letterSpacing: '0.07em', borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap' }}>{h}</th>
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
                      ? <EditableCell itemId={item.id} field="part_number" current={item.part_number} onSaved={fetch} cellStyle={{ color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace' }} />
                      : <span style={{ color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace' }}>{item.part_number}</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', color: '#d1d5db', maxWidth: 220 }}>
                    {canEdit ? (
                      <>
                        <EditableCell itemId={item.id} field="description_es" current={item.description_es} onSaved={fetch} cellStyle={{ display: 'block' }} />
                        <EditableCell itemId={item.id} field="description" current={item.description} onSaved={fetch} cellStyle={{ display: 'block', fontSize: '9px', color: '#606075', marginTop: 2 }} />
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
                    {canEdit
                      ? <EditableCell itemId={item.id} field="qty_ordered" current={item.qty_ordered} type="number" align="center" onSaved={fetch} cellStyle={{ color: '#d1d5db' }} />
                      : <span style={{ color: '#d1d5db' }}>{item.qty_ordered}</span>
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                    {canEdit
                      ? <EditableQty itemId={item.id} current={item.qty_received} max={item.qty_ordered} onSaved={fetch} />
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
                  <td style={{ padding: '8px 10px', textAlign: 'center', color: (item.qty_pending ?? 0) > 0 ? '#f97316' : '#606075', fontWeight: 700 }}>
                    {item.qty_pending ?? Math.max(0, item.qty_ordered - item.qty_received)}
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
                      ? <EditableStatus itemId={item.id} current={item.status} onSaved={fetch} />
                      : <ItemStatusBadge status={item.status} />
                    }
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'center', width: 32 }}>
                    {canCancel && (item.status === 'BACKORDER' || (item.status === 'PARTIAL' && (item.qty_pending ?? 0) > 0)) && (
                      <button
                        onClick={async () => {
                          const qty = item.qty_pending ?? 0;
                          if (!confirm(`¿Cancelar las ${qty} unidades pendientes de ${item.part_number}? Esta acción cerrará el backorder.`)) return;
                          try {
                            await authFetch(`${API()}/imports/spare-part-items/${item.id}/cancel-pending`, { method: 'POST' });
                            fetch();
                          } catch { alert('Error al cancelar pendiente'); }
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fila de un lote (expandible)
// ---------------------------------------------------------------------------
function LotRow({ lot, userRole, onReconcile }) {
  const [expanded, setExpanded] = useState(false);
  const [deduplicating, setDeduplicating] = useState(false);

  const pctColor = lot.pct_received >= 100 ? '#22c55e' : lot.pct_received > 0 ? '#fb923c' : '#606075';

  const handleDeduplicate = async (e) => {
    e.stopPropagation();
    if (!confirm(`¿Eliminar ítems duplicados sin backorders del lote ${lot.lot_identifier}? Esta acción no se puede deshacer.`)) return;
    setDeduplicating(true);
    try {
      const res = await authFetch(
        `${API()}/imports/spare-parts/repair-deduplicate?pi_number=${encodeURIComponent(lot.lot_identifier)}`,
        { method: 'POST' }
      );
      const data = await res.json();
      alert(`Limpieza completa: ${data.deleted} duplicados eliminados, ${data.kept} ítems conservados.`);
    } catch {
      alert('Error al limpiar duplicados');
    } finally {
      setDeduplicating(false);
    }
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

        {/* Lot identifier */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ margin: 0, fontSize: '12px', fontWeight: 700, color: '#60a5fa', fontFamily: 'monospace' }}>
            {lot.lot_identifier}
          </p>
        </div>

        {/* Items count */}
        <div style={{ textAlign: 'center', minWidth: 60 }}>
          <p style={{ margin: 0, fontSize: '14px', fontWeight: 800, color: '#fff' }}>{lot.items_count}</p>
          <p style={{ margin: 0, fontSize: '9px', color: '#606075', fontWeight: 600 }}>ítems</p>
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

        {/* Valor total */}
        <div style={{ textAlign: 'right', minWidth: 100 }}>
          {lot.total_declared_value != null
            ? <>
                <p style={{ margin: 0, fontSize: '13px', fontWeight: 800, color: '#a78bfa' }}>
                  ${parseFloat(lot.total_declared_value).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </p>
                <p style={{ margin: 0, fontSize: '9px', color: '#606075' }}>{lot.currency || 'USD'}</p>
              </>
            : <p style={{ margin: 0, fontSize: '11px', color: '#606075' }}>—</p>
          }
        </div>

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

        {/* TEMPORAL: botón deduplicar — solo superadmin */}
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
      {expanded && <LotItemsTable lotId={lot.id} userRole={userRole} isConfirmed={!!lot.packing_list_received} />}
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
  const [filterBL, setFilterBL] = useState(true);
  const [reconcileLot, setReconcileLot] = useState(null);

  const fetchLots = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterLoaded !== '') params.append('detail_loaded', filterLoaded);
      if (filterBL) params.append('has_bl', 'true');
      const res = await authFetch(`${API()}/imports/spare-part-lots?${params}`);
      const data = await res.json();
      setLots(Array.isArray(data) ? data : []);
    } catch {
      setLots([]);
    } finally {
      setLoading(false);
    }
  }, [filterLoaded, filterBL]);

  useEffect(() => { fetchLots(); }, [fetchLots]);

  // Totales del header
  const totalLots = lots.length;
  const totalItems = lots.reduce((acc, l) => acc + l.items_count, 0);
  const totalValue = lots.reduce((acc, l) => acc + (parseFloat(l.total_declared_value) || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {/* KPIs rápidos */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
        {[
          { label: 'Lotes activos', value: totalLots, color: '#60a5fa' },
          { label: 'Ítems totales', value: totalItems, color: '#a78bfa' },
          { label: 'Valor declarado', value: totalValue > 0 ? `$${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—', color: '#22c55e' },
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
        <span style={{ fontSize: '11px', color: '#606075', marginLeft: 'auto' }}>
          {totalLots} lote{totalLots !== 1 ? 's' : ''} encontrado{totalLots !== 1 ? 's' : ''}
        </span>
      </div>

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
            />
          ))}
        </div>
      )}

      {/* Modal de reconciliación */}
      {reconcileLot && (
        <ReconciliationModal
          lot={reconcileLot}
          onClose={() => setReconcileLot(null)}
          onConfirmed={() => { fetchLots(); setReconcileLot(null); }}
        />
      )}
    </div>
  );
}
