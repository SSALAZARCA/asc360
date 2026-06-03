'use client';
import { useState, useMemo } from 'react';
import StatusBadge from './StatusBadge';
import { Eye, Pencil, Trash2, ChevronLeft, ChevronRight, ChevronUp, ChevronDown as ChevronDownIcon } from 'lucide-react';
import ConfirmModal from '../ConfirmModal';

const COL_STYLE = {
  padding: '10px 14px',
  fontSize: '11px',
  borderBottom: '1px solid rgba(255,255,255,0.04)',
  whiteSpace: 'nowrap',
  color: '#d1d5db',
};


function SortIcon({ field, sortKey, sortDir }) {
  const active = sortKey === field;
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', marginLeft: '4px', verticalAlign: 'middle', gap: '1px' }}>
      <ChevronUp size={8} style={{ color: active && sortDir === 'asc' ? '#ff5f33' : 'rgba(255,255,255,0.2)', display: 'block' }} />
      <ChevronDownIcon size={8} style={{ color: active && sortDir === 'desc' ? '#ff5f33' : 'rgba(255,255,255,0.2)', display: 'block' }} />
    </span>
  );
}

const TH = ({ children, sortField, sortKey, sortDir, onSort, style = {} }) => (
  <th
    onClick={() => sortField && onSort && onSort(sortField)}
    style={{
      padding: '10px 14px', fontSize: '10px', fontWeight: 700,
      letterSpacing: '0.08em', color: sortKey === sortField ? '#ff5f33' : '#606075',
      textTransform: 'uppercase', borderBottom: '1px solid rgba(255,255,255,0.06)',
      whiteSpace: 'nowrap', background: '#0e0e14',
      cursor: sortField ? 'pointer' : 'default',
      userSelect: 'none',
      ...style,
    }}
  >
    {children}
    {sortField && <SortIcon field={sortField} sortKey={sortKey} sortDir={sortDir} />}
  </th>
);

const NACION_OPTIONS = [
  { value: '', label: '—' },
  { value: 'parcial', label: 'Parcial' },
  { value: 'completo', label: 'Completo' },
];

const NACION_COLORS = {
  parcial: { bg: 'rgba(251,146,60,0.15)', color: '#fb923c' },
  completo: { bg: 'rgba(34,197,94,0.15)', color: '#22c55e' },
};

export default function ShipmentTable({ orders, total, page, pageSize, onPageChange, onRowClick, onEdit, onDelete, onNacionalizacion, userRole, loading }) {
  const [deletingId, setDeletingId] = useState(null);
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [pendingConfirm, setPendingConfirm] = useState(null);
  const [nacionLoading, setNacionLoading] = useState({});

  const handleNacion = async (e, orderId) => {
    e.stopPropagation();
    const newStatus = e.target.value || null;
    setNacionLoading(prev => ({ ...prev, [orderId]: true }));
    try {
      await onNacionalizacion(orderId, newStatus);
    } finally {
      setNacionLoading(prev => ({ ...prev, [orderId]: false }));
    }
  };
  const totalPages = Math.ceil(total / pageSize);

  const handleSort = (field) => {
    if (sortKey === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(field);
      setSortDir('asc');
    }
  };

  const sorted = useMemo(() => {
    if (!sortKey) return orders;
    return [...orders].sort((a, b) => {
      let va = a[sortKey] ?? '';
      let vb = b[sortKey] ?? '';
      if (sortKey === 'cycle' || sortKey === 'qty_numeric') {
        va = Number(va) || 0;
        vb = Number(vb) || 0;
        return sortDir === 'asc' ? va - vb : vb - va;
      }
      if (sortKey === 'eta' || sortKey === 'etd') {
        va = va ? new Date(va).getTime() : 0;
        vb = vb ? new Date(vb).getTime() : 0;
        return sortDir === 'asc' ? va - vb : vb - va;
      }
      va = String(va).toLowerCase();
      vb = String(vb).toLowerCase();
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    });
  }, [orders, sortKey, sortDir]);

  const handleDelete = (e, order) => {
    e.stopPropagation();
    setPendingConfirm({
      title: 'Eliminar pedido',
      message: `¿Eliminar ${order.pi_number} — ${order.model}?`,
      danger: true,
      confirmLabel: 'Sí, eliminar',
      action: async () => {
        setDeletingId(order.id);
        await onDelete(order.id);
        setDeletingId(null);
      },
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Tabla */}
      <div style={{ overflowX: 'auto', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.06)', background: '#13131a' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'auto' }}>
          <thead>
            <tr>
              <TH sortField="cycle" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Ciclo</TH>
              <TH sortField="pi_number" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>PI Number</TH>
              <TH sortField="model" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Modelo</TH>
              <TH sortField="qty_numeric" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>QTY</TH>
              <TH sortField="order_date" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>F. Pedido</TH>
              <TH sortField="etd" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>ETD</TH>
              <TH sortField="eta" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>ETA</TH>
              <TH sortField="bl_container" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>BL / Contenedor</TH>
              <TH sortField="digital_docs_status" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Docs Digital</TH>
              <TH sortField="original_docs_status" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Docs Original</TH>
              <TH sortField="computed_status" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Estado</TH>
              <TH>Nacion.</TH>
              <TH></TH>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={13} style={{ ...COL_STYLE, textAlign: 'center', color: '#606075', padding: '32px' }}>
                  Cargando...
                </td>
              </tr>
            )}
            {!loading && orders.length === 0 && (
              <tr>
                <td colSpan={13} style={{ ...COL_STYLE, textAlign: 'center', color: '#606075', padding: '32px' }}>
                  No hay pedidos que mostrar
                </td>
              </tr>
            )}
            {!loading && sorted.map((order) => {
              const isSP = order.is_spare_part;
              const rowBg = isSP ? 'rgba(59,130,246,0.05)' : 'transparent';

              return (
                <tr
                  key={order.id}
                  onClick={() => onRowClick(order)}
                  style={{ background: rowBg, cursor: 'pointer', transition: 'background 0.15s' }}
                  onMouseEnter={e => e.currentTarget.style.background = isSP ? 'rgba(59,130,246,0.1)' : 'rgba(255,255,255,0.02)'}
                  onMouseLeave={e => e.currentTarget.style.background = rowBg}
                >
                  <td style={{ ...COL_STYLE, fontWeight: 700, color: '#fff' }}>
                    {order.cycle ?? '—'}
                  </td>
                  <td style={COL_STYLE}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontWeight: 700, color: isSP ? '#60a5fa' : '#fff', fontSize: '11px' }}>
                        {order.pi_number}
                      </span>
                      {isSP && (
                        <span style={{
                          fontSize: '9px', fontWeight: 800, padding: '1px 5px',
                          borderRadius: '4px', background: 'rgba(251,146,60,0.15)',
                          color: '#fb923c', letterSpacing: '0.05em',
                        }}>SP</span>
                      )}
                    </div>
                  </td>
                  <td style={COL_STYLE}>
                    <span style={{ color: '#d1d5db', fontSize: '11px' }}>{order.model}</span>
                  </td>

                  {/* Columnas normales */}
                  <td style={COL_STYLE}>
                    {isSP
                      ? (order.total_units != null ? order.total_units.toLocaleString() : '1LOT')
                      : (order.qty ?? '—')}
                  </td>
                  <td style={COL_STYLE}>{order.order_date ?? '—'}</td>
                  <td style={COL_STYLE}>{order.etd_raw ?? order.etd?.split('T')[0] ?? '—'}</td>
                  <td style={COL_STYLE}>{order.eta_raw ?? order.eta?.split('T')[0] ?? '—'}</td>
                  <td style={{ ...COL_STYLE, maxWidth: 160 }}>
                    <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '10px' }}>
                      {order.bl_container ?? '—'}
                    </span>
                  </td>
                  <td style={COL_STYLE}>
                    <StatusBadge status={order.digital_docs_status} type="docs_status" />
                  </td>
                  <td style={COL_STYLE}>
                    <StatusBadge status={order.original_docs_status} type="docs_status" />
                  </td>
                  <td style={COL_STYLE}>
                    <StatusBadge status={order.computed_status} type="computed_status" />
                  </td>
                  <td style={{ ...COL_STYLE }} onClick={e => e.stopPropagation()}>
                    {isSP ? (
                      <select
                        value={order.nacionalizacion_status ?? ''}
                        disabled={nacionLoading[order.id]}
                        onChange={e => handleNacion(e, order.id)}
                        style={{
                          background: order.nacionalizacion_status
                            ? NACION_COLORS[order.nacionalizacion_status]?.bg
                            : 'rgba(255,255,255,0.04)',
                          color: order.nacionalizacion_status
                            ? NACION_COLORS[order.nacionalizacion_status]?.color
                            : '#606075',
                          border: '1px solid rgba(255,255,255,0.08)',
                          borderRadius: '6px',
                          fontSize: '10px',
                          fontWeight: 700,
                          padding: '3px 6px',
                          cursor: nacionLoading[order.id] ? 'wait' : 'pointer',
                          outline: 'none',
                          letterSpacing: '0.04em',
                        }}
                      >
                        {NACION_OPTIONS.map(opt => (
                          <option key={opt.value} value={opt.value} style={{ background: '#1a1a24', color: '#d1d5db' }}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span style={{ color: '#3a3a50', fontSize: '11px' }}>—</span>
                    )}
                  </td>
                  <td style={{ ...COL_STYLE, textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }} onClick={e => e.stopPropagation()}>
                      <button
                        onClick={() => onRowClick(order)}
                        title="Ver detalle"
                        style={{ background: 'rgba(255,255,255,0.05)', border: 'none', borderRadius: '6px', padding: '5px 7px', cursor: 'pointer', color: '#9ca3af' }}
                      >
                        <Eye size={13} />
                      </button>
                      {(userRole === 'superadmin' || userRole === 'imports_editor') && onEdit && (
                        <button
                          onClick={(e) => { e.stopPropagation(); onEdit(order); }}
                          title="Editar pedido"
                          style={{ background: 'rgba(255,95,51,0.08)', border: 'none', borderRadius: '6px', padding: '5px 7px', cursor: 'pointer', color: '#ff5f33' }}
                        >
                          <Pencil size={13} />
                        </button>
                      )}
                      {(userRole === 'superadmin' || userRole === 'administrativo') && (
                        <button
                          onClick={(e) => handleDelete(e, order)}
                          disabled={deletingId === order.id}
                          title="Eliminar"
                          style={{ background: 'rgba(248,113,113,0.08)', border: 'none', borderRadius: '6px', padding: '5px 7px', cursor: 'pointer', color: '#f87171' }}
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Paginación */}
      {total > pageSize && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 0' }}>
          <span style={{ fontSize: '11px', color: '#606075' }}>
            {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} de {total} pedidos
          </span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page === 1}
              style={{ background: 'rgba(255,255,255,0.05)', border: 'none', borderRadius: '6px', padding: '5px 8px', cursor: page === 1 ? 'not-allowed' : 'pointer', color: page === 1 ? '#606075' : '#fff' }}
            >
              <ChevronLeft size={14} />
            </button>
            <span style={{ fontSize: '11px', color: '#9ca3af', padding: '5px 8px' }}>{page} / {totalPages}</span>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              style={{ background: 'rgba(255,255,255,0.05)', border: 'none', borderRadius: '6px', padding: '5px 8px', cursor: page >= totalPages ? 'not-allowed' : 'pointer', color: page >= totalPages ? '#606075' : '#fff' }}
            >
              <ChevronRight size={14} />
            </button>
          </div>
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
