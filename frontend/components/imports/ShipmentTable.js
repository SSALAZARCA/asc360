'use client';
import { useState, useMemo } from 'react';
import StatusBadge from './StatusBadge';
import { Eye, Pencil, Trash2, ChevronLeft, ChevronRight, ChevronUp, ChevronDown as ChevronDownIcon } from 'lucide-react';

const COL_STYLE = {
  padding: '10px 14px',
  fontSize: '11px',
  borderBottom: '1px solid rgba(255,255,255,0.04)',
  whiteSpace: 'nowrap',
  color: '#d1d5db',
};

const STICKY = {
  position: 'sticky',
  left: 0,
  zIndex: 2,
  background: '#13131a',
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

const TH = ({ children, sortField, sortKey, sortDir, onSort, sticky, style = {} }) => (
  <th
    onClick={() => sortField && onSort && onSort(sortField)}
    style={{
      padding: '10px 14px', fontSize: '10px', fontWeight: 700,
      letterSpacing: '0.08em', color: sortKey === sortField ? '#ff5f33' : '#606075',
      textTransform: 'uppercase', borderBottom: '1px solid rgba(255,255,255,0.06)',
      whiteSpace: 'nowrap', background: '#0e0e14',
      cursor: sortField ? 'pointer' : 'default',
      userSelect: 'none',
      ...(sticky ? STICKY : {}), ...style,
    }}
  >
    {children}
    {sortField && <SortIcon field={sortField} sortKey={sortKey} sortDir={sortDir} />}
  </th>
);

export default function ShipmentTable({ orders, total, page, pageSize, onPageChange, onRowClick, onEdit, onDelete, userRole, loading }) {
  const [deletingId, setDeletingId] = useState(null);
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
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

  const handleDelete = async (e, order) => {
    e.stopPropagation();
    if (!confirm(`¿Eliminar ${order.pi_number} — ${order.model}?`)) return;
    setDeletingId(order.id);
    await onDelete(order.id);
    setDeletingId(null);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Tabla */}
      <div style={{ overflowX: 'auto', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.06)', background: '#13131a' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'auto' }}>
          <thead>
            <tr>
              <TH sticky style={{ left: 0 }} sortField="cycle" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Ciclo</TH>
              <TH sticky style={{ left: 60 }} sortField="pi_number" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>PI Number</TH>
              <TH sticky style={{ left: 200 }} sortField="model" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Modelo</TH>
              <TH sortField="qty_numeric" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>QTY</TH>
              <TH sortField="order_date" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>F. Pedido</TH>
              <TH sortField="etd" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>ETD</TH>
              <TH sortField="eta" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>ETA</TH>
              <TH sortField="bl_container" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>BL / Contenedor</TH>
              <TH sortField="digital_docs_status" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Docs Digital</TH>
              <TH sortField="original_docs_status" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Docs Original</TH>
              <TH sortField="computed_status" sortKey={sortKey} sortDir={sortDir} onSort={handleSort}>Estado</TH>
              <TH></TH>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={12} style={{ ...COL_STYLE, textAlign: 'center', color: '#606075', padding: '32px' }}>
                  Cargando...
                </td>
              </tr>
            )}
            {!loading && orders.length === 0 && (
              <tr>
                <td colSpan={12} style={{ ...COL_STYLE, textAlign: 'center', color: '#606075', padding: '32px' }}>
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
                  {/* Columnas sticky */}
                  <td style={{ ...COL_STYLE, ...STICKY, left: 0, background: isSP ? '#0f1420' : '#13131a', fontWeight: 700, color: '#fff' }}>
                    {order.cycle ?? '—'}
                  </td>
                  <td style={{ ...COL_STYLE, ...STICKY, left: 60, background: isSP ? '#0f1420' : '#13131a' }}>
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
                  <td style={{ ...COL_STYLE, ...STICKY, left: 200, background: isSP ? '#0f1420' : '#13131a', maxWidth: 180 }}>
                    <span style={{ color: '#d1d5db', fontSize: '11px' }}>{order.model}</span>
                  </td>

                  {/* Columnas normales */}
                  <td style={COL_STYLE}>{order.qty ?? '—'}</td>
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
                      {userRole === 'superadmin' && (
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
    </div>
  );
}
