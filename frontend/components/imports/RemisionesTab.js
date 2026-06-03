'use client';
import { useState, useEffect, useCallback } from 'react';
import { useRemisiones } from '../../lib/useRemisiones';
import { toast } from '../../lib/toast';
import { RefreshCw, Plus, Package } from 'lucide-react';
import ConfirmModal from '../ConfirmModal';
import RemisionForm from './RemisionForm';

// ---------------------------------------------------------------------------
// Status badge configuration
// ---------------------------------------------------------------------------
const STATUS_CONFIG = {
  BORRADOR:   { label: 'Borrador',   color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  border: 'rgba(251,191,36,0.3)'  },
  DESPACHADO: { label: 'Despachado', color: '#22c55e', bg: 'rgba(34,197,94,0.12)',   border: 'rgba(34,197,94,0.3)'   },
  ANULADO:    { label: 'Anulado',    color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
};

const TYPE_LABELS = {
  PEDIDO:         'Pedido',
  GARANTIA:       'Garantía',
  CORTESIA:       'Cortesía',
  VEHICULO_PROPIO: 'Vehículo Propio',
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, color: '#9ca3af', bg: 'rgba(156,163,175,0.1)', border: 'rgba(156,163,175,0.3)' };
  return (
    <span style={{
      fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '20px',
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
      textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap',
    }}>
      {cfg.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Modal: Cancel remision (requires reason)
// ---------------------------------------------------------------------------
function CancelReasonModal({ onConfirm, onCancel }) {
  const [reason, setReason] = useState('');
  const valid = reason.trim().length >= 5;

  return (
    <div
      onClick={onCancel}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: '#16161f', border: '1px solid rgba(248,113,113,0.3)',
          borderRadius: '14px', padding: '24px', width: 380, margin: '0 16px',
          display: 'flex', flexDirection: 'column', gap: '14px',
        }}
      >
        <p style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#f87171' }}>
          Anular Remisión
        </p>
        <p style={{ margin: 0, fontSize: '11px', color: '#9ca3af', lineHeight: 1.5 }}>
          Ingresá la razón de anulación (mínimo 5 caracteres). Esta acción revierte el stock.
        </p>
        <textarea
          autoFocus
          rows={3}
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Motivo de la anulación..."
          style={{
            padding: '9px 12px', borderRadius: '8px', fontSize: '12px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.15)',
            color: '#fff', outline: 'none', width: '100%', boxSizing: 'border-box',
            resize: 'vertical', lineHeight: 1.5,
          }}
        />
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '7px 16px', borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.1)',
              background: 'transparent', color: '#9ca3af',
              fontSize: '11px', cursor: 'pointer',
            }}
          >
            Cancelar
          </button>
          <button
            onClick={() => valid && onConfirm(reason.trim())}
            disabled={!valid}
            style={{
              padding: '7px 16px', borderRadius: '8px', border: 'none',
              background: valid ? 'rgba(248,113,113,0.85)' : 'rgba(248,113,113,0.2)',
              color: valid ? '#fff' : '#606075',
              fontSize: '11px', fontWeight: 700, cursor: valid ? 'pointer' : 'not-allowed',
            }}
          >
            Anular
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function RemisionesTab({ userRole }) {
  const api = useRemisiones();

  const [remisiones, setRemisiones] = useState([]);
  const [loading, setLoading] = useState(true);

  const [filterStatus, setFilterStatus] = useState('');
  const [filterType, setFilterType] = useState('');

  // Form modal state
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null); // remision to edit, null = create

  // Confirm dispatch modal
  const [pendingDispatch, setPendingDispatch] = useState(null);

  // Cancel reason modal
  const [pendingCancel, setPendingCancel] = useState(null);

  // Confirm delete modal
  const [pendingDelete, setPendingDelete] = useState(null);

  const isSuperadmin = userRole === 'superadmin';

  // -------------------------------------------------------------------------
  // Fetch
  // -------------------------------------------------------------------------
  const fetchRemisiones = useCallback(async () => {
    setLoading(true);
    try {
      const filters = {};
      if (filterStatus) filters.status = filterStatus;
      if (filterType)   filters.type   = filterType;
      const res = await api.getRemisiones(filters);
      if (res.ok) {
        const data = await res.json();
        setRemisiones(Array.isArray(data) ? data : (data.items ?? []));
      } else {
        toast.error('Error al cargar remisiones');
      }
    } catch (e) {
      console.error('Error cargando remisiones:', e);
      toast.error('Error de conexión');
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterType]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchRemisiones(); }, [fetchRemisiones]);

  // -------------------------------------------------------------------------
  // Dispatch
  // -------------------------------------------------------------------------
  const handleDispatch = async (remision) => {
    try {
      const res = await api.dispatchRemision(remision.id);
      if (res.ok) {
        toast.success(`Remisión ${remision.remision_number || ''} despachada.`);
        fetchRemisiones();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Error al despachar');
      }
    } catch {
      toast.error('Error de conexión al despachar');
    }
  };

  // -------------------------------------------------------------------------
  // Delete (BORRADOR only)
  // -------------------------------------------------------------------------
  const handleDelete = async (remision) => {
    setPendingDelete(null);
    try {
      const res = await api.deleteRemision(remision.id);
      if (res.ok || res.status === 204) {
        toast.success('Remisión eliminada.');
        fetchRemisiones();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Error al eliminar');
      }
    } catch {
      toast.error('Error de conexión al eliminar');
    }
  };

  // -------------------------------------------------------------------------
  // Cancel
  // -------------------------------------------------------------------------
  const handleCancel = async (remision, reason) => {
    setPendingCancel(null);
    try {
      const res = await api.cancelRemision(remision.id, reason);
      if (res.ok) {
        toast.success('Remisión anulada. Stock restaurado.');
        fetchRemisiones();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Error al anular');
      }
    } catch {
      toast.error('Error de conexión al anular');
    }
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        {/* Filter by status */}
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          style={{
            padding: '8px 12px', borderRadius: '8px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
            color: filterStatus === '' ? '#606075' : '#fff', fontSize: '12px', outline: 'none',
          }}
        >
          <option value="">Todos los estados</option>
          <option value="BORRADOR">Borrador</option>
          <option value="DESPACHADO">Despachado</option>
          <option value="ANULADO">Anulado</option>
        </select>

        {/* Filter by type */}
        <select
          value={filterType}
          onChange={e => setFilterType(e.target.value)}
          style={{
            padding: '8px 12px', borderRadius: '8px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
            color: filterType === '' ? '#606075' : '#fff', fontSize: '12px', outline: 'none',
          }}
        >
          <option value="">Todos los tipos</option>
          {Object.entries(TYPE_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>

        {/* Refresh */}
        <button
          onClick={fetchRemisiones}
          style={{
            padding: '8px', borderRadius: '8px',
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.08)',
            cursor: 'pointer', color: '#9ca3af',
          }}
        >
          <RefreshCw size={14} />
        </button>

        {/* Nueva Remisión — superadmin only */}
        {isSuperadmin && (
          <button
            onClick={() => { setEditTarget(null); setFormOpen(true); }}
            style={{
              marginLeft: 'auto',
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '8px 14px', borderRadius: '8px', border: 'none',
              background: 'rgba(255,95,51,0.15)', color: '#ff5f33',
              fontSize: '11px', fontWeight: 700, cursor: 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            <Plus size={13} /> Nueva Remisión
          </button>
        )}
      </div>

      {/* Counter */}
      <p style={{ margin: 0, fontSize: '11px', color: '#606075' }}>
        {remisiones.length} remisión{remisiones.length !== 1 ? 'es' : ''}
      </p>

      {/* Table or empty state */}
      {loading ? (
        <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '40px 0' }}>
          Cargando remisiones...
        </p>
      ) : remisiones.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#606075' }}>
          <Package size={36} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
          <p style={{ fontSize: '13px', margin: 0 }}>No hay remisiones</p>
          <p style={{ fontSize: '11px', margin: '4px 0 0', color: '#404050' }}>
            Creá una nueva remisión con el botón "Nueva Remisión"
          </p>
        </div>
      ) : (
        <div style={{
          overflowX: 'auto', borderRadius: '12px',
          border: '1px solid rgba(255,255,255,0.06)', background: '#13131a',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
            <thead>
              <tr style={{ background: '#0e0e14' }}>
                {['Número', 'Tipo', 'Fecha', 'Estado', 'Ítems', 'Acciones'].map(h => (
                  <th key={h} style={{
                    padding: '10px 14px',
                    textAlign: h === 'Acciones' ? 'center' : 'left',
                    fontSize: '9px', fontWeight: 700, color: '#606075',
                    textTransform: 'uppercase', letterSpacing: '0.07em',
                    borderBottom: '1px solid rgba(255,255,255,0.06)',
                    whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {remisiones.map(rem => (
                <tr
                  key={rem.id}
                  style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                >
                  {/* Número */}
                  <td style={{ padding: '10px 14px', fontFamily: 'monospace', color: '#d1d5db', fontWeight: 700 }}>
                    {rem.remision_number || <span style={{ color: '#606075', fontStyle: 'italic', fontFamily: 'inherit' }}>Borrador</span>}
                  </td>

                  {/* Tipo */}
                  <td style={{ padding: '10px 14px', color: '#9ca3af' }}>
                    {TYPE_LABELS[rem.type] || rem.type}
                  </td>

                  {/* Fecha */}
                  <td style={{ padding: '10px 14px', color: '#606075', whiteSpace: 'nowrap' }}>
                    {rem.created_at ? new Date(rem.created_at).toLocaleDateString('es-CO') : '—'}
                  </td>

                  {/* Estado */}
                  <td style={{ padding: '10px 14px' }}>
                    <StatusBadge status={rem.status} />
                  </td>

                  {/* Ítems count */}
                  <td style={{ padding: '10px 14px', textAlign: 'center', color: '#9ca3af' }}>
                    {rem.items_count ?? 0}
                  </td>

                  {/* Acciones */}
                  <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                    {isSuperadmin && (
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', justifyContent: 'center' }}>
                        {rem.status === 'BORRADOR' && (
                          <>
                            {/* Despachar */}
                            <button
                              onClick={() => setPendingDispatch(rem)}
                              style={{
                                padding: '4px 10px', borderRadius: '6px', border: 'none',
                                background: 'rgba(34,197,94,0.15)', color: '#22c55e',
                                fontSize: '10px', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
                              }}
                            >
                              Despachar
                            </button>
                            {/* Editar */}
                            <button
                              onClick={() => { setEditTarget(rem); setFormOpen(true); }}
                              style={{
                                padding: '4px 10px', borderRadius: '6px', border: 'none',
                                background: 'rgba(96,165,250,0.12)', color: '#60a5fa',
                                fontSize: '10px', fontWeight: 700, cursor: 'pointer',
                              }}
                            >
                              Editar
                            </button>
                            {/* Eliminar */}
                            <button
                              onClick={() => setPendingDelete(rem)}
                              style={{
                                padding: '4px 10px', borderRadius: '6px', border: 'none',
                                background: 'rgba(248,113,113,0.12)', color: '#f87171',
                                fontSize: '10px', fontWeight: 700, cursor: 'pointer',
                              }}
                            >
                              Eliminar
                            </button>
                          </>
                        )}

                        {rem.status === 'DESPACHADO' && (
                          <button
                            onClick={() => setPendingCancel(rem)}
                            style={{
                              padding: '4px 10px', borderRadius: '6px', border: 'none',
                              background: 'rgba(248,113,113,0.12)', color: '#f87171',
                              fontSize: '10px', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
                            }}
                          >
                            Anular
                          </button>
                        )}

                        {rem.status === 'ANULADO' && (
                          <span style={{ fontSize: '10px', color: '#606075', fontStyle: 'italic' }}>
                            Sin acciones
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Form modal (create / edit) */}
      {formOpen && (
        <RemisionForm
          remision={editTarget}
          onClose={() => { setFormOpen(false); setEditTarget(null); }}
          onSuccess={() => { setFormOpen(false); setEditTarget(null); fetchRemisiones(); }}
        />
      )}

      {/* Confirm dispatch */}
      {pendingDispatch && (
        <ConfirmModal
          title="Despachar Remisión"
          message={`¿Confirmás el despacho de esta remisión? Se descontará el stock de los ítems incluidos.\n\nEsta acción no puede deshacerse directamente — sólo puede anularse después.`}
          confirmLabel="Sí, despachar"
          onCancel={() => setPendingDispatch(null)}
          onConfirm={() => { const r = pendingDispatch; setPendingDispatch(null); handleDispatch(r); }}
        />
      )}

      {/* Cancel with reason */}
      {pendingCancel && (
        <CancelReasonModal
          onCancel={() => setPendingCancel(null)}
          onConfirm={(reason) => handleCancel(pendingCancel, reason)}
        />
      )}

      {/* Confirm delete BORRADOR */}
      {pendingDelete && (
        <ConfirmModal
          title="Eliminar Remisión"
          message="¿Confirmás que querés eliminar esta remisión en borrador? Esta acción es permanente."
          confirmLabel="Sí, eliminar"
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => handleDelete(pendingDelete)}
        />
      )}
    </div>
  );
}
