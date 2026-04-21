'use client';
import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../../lib/authFetch';
import { RefreshCw, Search, CheckCircle, Clock, AlertTriangle, Tag } from 'lucide-react';

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

export default function BackorderTab({ userRole }) {
  const [backorders, setBackorders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showResolved, setShowResolved] = useState(false);
  const [search, setSearch] = useState('');
  const [filterPi, setFilterPi] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);

  const canEdit = userRole === 'superadmin' || userRole === 'proveedor';

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
    if (!confirm(`¿Marcar como resuelto el backorder de ${bo.part_number}?`)) return;
    try {
      await authFetch(`${API()}/imports/backorders/${bo.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved: true }),
      });
      fetchBackorders();
    } catch { alert('Error al resolver backorder'); }
  };

  // Filtro local por texto
  const filtered = search
    ? backorders.filter(b =>
        b.part_number?.toLowerCase().includes(search.toLowerCase()) ||
        b.origin_pi?.toLowerCase().includes(search.toLowerCase()) ||
        b.expected_in_pi?.toLowerCase().includes(search.toLowerCase()) ||
        b.description_es?.toLowerCase().includes(search.toLowerCase()) ||
        b.model_applicable?.toLowerCase().includes(search.toLowerCase())
      )
    : backorders;

  // Selección
  const activeFiltered = filtered.filter(b => !b.resolved);
  const allSelected = activeFiltered.length > 0 && activeFiltered.every(b => selected.has(b.id));
  const someSelected = activeFiltered.some(b => selected.has(b.id));

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(activeFiltered.map(b => b.id)));
    }
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
  const withoutPI = active.filter(b => !b.expected_in_pi).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {showBulkModal && (
        <BulkPIModal
          count={selected.size}
          onConfirm={handleBulkAssignPI}
          onCancel={() => setShowBulkModal(false)}
        />
      )}

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
        {[
          { label: 'Backorders activos', value: active.length, color: '#f87171' },
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

        {/* Acción bulk — aparece solo cuando hay selección */}
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

        <span style={{ fontSize: '11px', color: '#606075', marginLeft: 'auto' }}>
          {filtered.length} backorder{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tabla */}
      {loading ? (
        <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '40px 0' }}>Cargando backorders...</p>
      ) : filtered.length === 0 ? (
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
                {['Parte #', 'Descripción', 'Moto', 'PI Origen', 'PI Esperado', 'Uds. Pendientes', 'Días abierto', 'Estado', ''].map(h => (
                  <th key={h} style={{ padding: '9px 12px', textAlign: 'left', fontSize: '9px', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.07em', borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(bo => {
                const days = daysSince(bo.created_at);
                const isResolved = bo.resolved;
                const isSelected = selected.has(bo.id);
                return (
                  <tr
                    key={bo.id}
                    style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: isResolved ? 0.5 : 1, background: isSelected ? 'rgba(37,99,235,0.07)' : 'transparent' }}
                    onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = isSelected ? 'rgba(37,99,235,0.07)' : 'transparent'; }}
                  >
                    {canEdit && (
                      <td style={{ padding: '9px 12px' }}>
                        {!isResolved && (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelect(bo.id)}
                            style={{ accentColor: '#2563eb', cursor: 'pointer' }}
                          />
                        )}
                      </td>
                    )}
                    <td style={{ padding: '9px 12px', color: '#f87171', fontWeight: 700, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                      {bo.part_number}
                    </td>
                    <td style={{ padding: '9px 12px', color: '#d1d5db', fontSize: '11px', maxWidth: 200 }}>
                      <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {bo.description_es || '—'}
                      </span>
                    </td>
                    <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                      {bo.model_applicable
                        ? <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '4px', background: 'rgba(96,165,250,0.1)', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.2)' }}>{bo.model_applicable}</span>
                        : <span style={{ color: '#606075', fontSize: '11px' }}>—</span>
                      }
                    </td>
                    <td style={{ padding: '9px 12px', color: '#9ca3af', fontFamily: 'monospace', fontSize: '10px', whiteSpace: 'nowrap' }}>
                      {bo.origin_pi}
                    </td>
                    <td style={{ padding: '9px 12px' }}>
                      {!isResolved && canEdit
                        ? <EditableExpectedPI boId={bo.id} current={bo.expected_in_pi} onSaved={fetchBackorders} />
                        : <span style={{ fontSize: '11px', fontFamily: 'monospace', color: bo.expected_in_pi ? '#60a5fa' : '#606075' }}>
                            {bo.expected_in_pi || '—'}
                          </span>
                      }
                    </td>
                    <td style={{ padding: '9px 12px', textAlign: 'right' }}>
                      <span style={{ fontWeight: 800, color: bo.qty_pending > 0 ? '#fb923c' : '#606075', fontSize: '13px' }}>
                        {bo.qty_pending}
                      </span>
                    </td>
                    <td style={{ padding: '9px 12px' }}>
                      <DaysChip days={days} />
                    </td>
                    <td style={{ padding: '9px 12px' }}>
                      {isResolved ? (
                        <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(34,197,94,0.1)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.25)' }}>
                          RESUELTO
                        </span>
                      ) : (
                        <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(248,113,113,0.1)', color: '#f87171', border: '1px solid rgba(248,113,113,0.25)' }}>
                          ACTIVO
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '9px 12px', textAlign: 'right' }}>
                      {!isResolved && canEdit && (
                        <button
                          onClick={() => handleResolve(bo)}
                          title="Marcar como resuelto"
                          style={{ padding: '4px 10px', borderRadius: '7px', border: 'none', background: 'rgba(34,197,94,0.1)', color: '#22c55e', fontSize: '10px', fontWeight: 700, cursor: 'pointer' }}
                        >
                          <CheckCircle size={11} style={{ display: 'inline', marginRight: 4 }} />
                          Resolver
                        </button>
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
