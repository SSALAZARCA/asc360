'use client';
import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../../lib/authFetch';
import { getApiUrl } from '../../lib/api';
import { useRemisiones } from '../../lib/useRemisiones';
import { toast } from '../../lib/toast';
import { Plus, Trash2, X } from 'lucide-react';

const REMISION_TYPES = [
  { value: 'PEDIDO',        label: 'Pedido' },
  { value: 'GARANTIA',      label: 'Garantía' },
  { value: 'CORTESIA',      label: 'Cortesía' },
  { value: 'VEHICULO_PROPIO', label: 'Vehículo Propio' },
];

// Minimal inline styles matching the project's dark theme
const inputStyle = {
  padding: '8px 12px', borderRadius: '8px', fontSize: '12px',
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
  color: '#fff', outline: 'none', width: '100%', boxSizing: 'border-box',
};

const selectStyle = {
  ...inputStyle,
  background: '#1a1a24',
  cursor: 'pointer',
};

const labelStyle = {
  display: 'block', fontSize: '10px', fontWeight: 700, color: '#606075',
  textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '5px',
};

/**
 * RemisionForm — modal-style form for creating or editing a BORRADOR remision.
 *
 * Props:
 *   remision  - existing remision object to edit, or null to create new
 *   onSuccess - callback after successful save (receives the saved remision)
 *   onClose   - callback to close the form without saving
 */
export default function RemisionForm({ remision = null, onClose, onSuccess }) {
  const api = useRemisiones();

  const [type, setType] = useState(remision?.type || 'GARANTIA');
  const [referenceLotId, setReferenceLotId] = useState(remision?.reference_lot_id || '');
  const [notes, setNotes] = useState(remision?.notes || '');

  // Items in the form: { spare_part_item_id, part_number, qty_available, qty_dispatched }
  const [items, setItems] = useState(
    remision?.items?.map(i => ({
      _key: i.id,
      spare_part_item_id: i.spare_part_item_id,
      part_number: i.part_number,
      qty_available: null,     // will be refreshed from availability
      qty_dispatched: i.qty_dispatched,
    })) || []
  );

  // Available spare part items from the VIEW
  const [availability, setAvailability] = useState([]);
  const [availLoading, setAvailLoading] = useState(false);

  // Lots for the PEDIDO reference selector
  const [lots, setLots] = useState([]);
  const [lotsLoading, setLotsLoading] = useState(false);

  const [saving, setSaving] = useState(false);

  // Search text per item row (keyed by _key) — drives the datalist input
  const [itemSearch, setItemSearch] = useState({});

  // -------------------------------------------------------------------------
  // Fetch availability
  // -------------------------------------------------------------------------
  const fetchAvailability = useCallback(async () => {
    setAvailLoading(true);
    try {
      const res = await api.getAvailability();
      if (res.ok) {
        const data = await res.json();
        setAvailability(Array.isArray(data) ? data : (data.items ?? []));
      }
    } catch (e) {
      console.error('Error cargando disponibilidad:', e);
    } finally {
      setAvailLoading(false);
    }
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // -------------------------------------------------------------------------
  // Fetch lots (for PEDIDO type)
  // -------------------------------------------------------------------------
  const fetchLots = useCallback(async () => {
    setLotsLoading(true);
    try {
      const res = await authFetch(`${getApiUrl()}/imports/spare-part-lots?page_size=200`);
      if (res.ok) {
        const data = await res.json();
        const items = Array.isArray(data) ? data : (data.items ?? []);
        setLots(items);
      }
    } catch (e) {
      console.error('Error cargando lotes:', e);
    } finally {
      setLotsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAvailability();
    fetchLots();
  }, [fetchAvailability, fetchLots]);

  // -------------------------------------------------------------------------
  // Item helpers
  // -------------------------------------------------------------------------
  const addItem = () => {
    setItems(prev => [
      ...prev,
      { _key: crypto.randomUUID(), spare_part_item_id: '', part_number: '', qty_available: null, qty_dispatched: 1 },
    ]);
  };

  const removeItem = (key) => {
    setItems(prev => prev.filter(i => i._key !== key));
    setItemSearch(prev => { const n = { ...prev }; delete n[key]; return n; });
  };

  const updateItemField = (key, field, value) => {
    setItems(prev => prev.map(i => i._key === key ? { ...i, [field]: value } : i));
  };

  const handleItemSelect = (key, sparePartItemId) => {
    const found = availability.find(a => a.spare_part_item_id === sparePartItemId);
    if (found) {
      setItems(prev => prev.map(i =>
        i._key === key
          ? {
              ...i,
              spare_part_item_id: sparePartItemId,
              part_number: found.part_number,
              qty_available: found.qty_available,
              qty_dispatched: Math.min(i.qty_dispatched || 1, found.qty_available),
            }
          : i
      ));
      setItemSearch(prev => ({ ...prev, [key]: found.part_number }));
    }
  };

  const handleItemSearchChange = (key, text) => {
    setItemSearch(prev => ({ ...prev, [key]: text }));
    // Find exact match (browser fires onChange when user selects from datalist)
    const match = availability.find(a => a.part_number === text);
    if (match) {
      handleItemSelect(key, match.spare_part_item_id);
    } else if (!text) {
      updateItemField(key, 'spare_part_item_id', '');
    }
  };

  // -------------------------------------------------------------------------
  // Validation
  // -------------------------------------------------------------------------
  const validate = () => {
    if (type === 'PEDIDO' && !referenceLotId) {
      toast.error('El tipo Pedido requiere un lote de referencia.');
      return false;
    }
    if (items.length === 0) {
      toast.error('Debe agregar al menos un ítem.');
      return false;
    }
    for (const item of items) {
      if (!item.spare_part_item_id) {
        toast.error('Seleccioná un repuesto en cada fila de ítems.');
        return false;
      }
      if (!item.qty_dispatched || item.qty_dispatched < 1) {
        toast.error(`La cantidad de ${item.part_number || 'un ítem'} debe ser mayor a 0.`);
        return false;
      }
      if (item.qty_available !== null && item.qty_dispatched > item.qty_available) {
        toast.error(`La cantidad de ${item.part_number} excede la disponibilidad (${item.qty_available}).`);
        return false;
      }
    }
    return true;
  };

  // -------------------------------------------------------------------------
  // Save
  // -------------------------------------------------------------------------
  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      const payload = {
        type,
        reference_lot_id: type === 'PEDIDO' ? (referenceLotId || null) : null,
        notes: notes || null,
        items: items.map(i => ({
          spare_part_item_id: i.spare_part_item_id,
          qty_dispatched: Number(i.qty_dispatched),
        })),
      };

      const res = remision?.id
        ? await api.updateRemision(remision.id, payload)
        : await api.createRemision(payload);

      if (res.ok) {
        const data = await res.json();
        toast.success(remision?.id ? 'Remisión actualizada.' : 'Remisión creada en borrador.');
        onSuccess?.(data);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || `Error al guardar (${res.status})`);
      }
    } catch (e) {
      console.error('Error guardando remisión:', e);
      toast.error('Error de conexión al guardar.');
    } finally {
      setSaving(false);
    }
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: '#16161f', border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '14px', padding: '24px',
          width: '100%', maxWidth: 640,
          maxHeight: '90vh', overflowY: 'auto',
          display: 'flex', flexDirection: 'column', gap: '18px',
          margin: '0 16px',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <p style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#fff' }}>
            {remision?.id ? 'Editar Remisión' : 'Nueva Remisión'}
          </p>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', padding: 0 }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Type */}
        <div>
          <label style={labelStyle}>Tipo</label>
          <select value={type} onChange={e => setType(e.target.value)} style={selectStyle}>
            {REMISION_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        {/* Reference Lot — only visible when type === PEDIDO */}
        {type === 'PEDIDO' && (
          <div>
            <label style={labelStyle}>Lote de Referencia <span style={{ color: '#f87171' }}>*</span></label>
            <select
              value={referenceLotId}
              onChange={e => setReferenceLotId(e.target.value)}
              style={selectStyle}
              disabled={lotsLoading}
            >
              <option value="">— Seleccionar lote —</option>
              {lots.map(lot => (
                <option key={lot.id} value={lot.id}>
                  {lot.lot_identifier}
                </option>
              ))}
            </select>
            {lotsLoading && (
              <p style={{ margin: '4px 0 0', fontSize: '10px', color: '#606075' }}>Cargando lotes...</p>
            )}
          </div>
        )}

        {/* Notes */}
        <div>
          <label style={labelStyle}>Notas (opcional)</label>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={2}
            placeholder="Observaciones sobre esta remisión..."
            style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5 }}
          />
        </div>

        {/* Items section */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <label style={{ ...labelStyle, margin: 0 }}>
              Ítems {items.length > 0 && <span style={{ color: '#9ca3af' }}>({items.length})</span>}
            </label>
            <button
              onClick={addItem}
              style={{
                display: 'flex', alignItems: 'center', gap: '5px',
                padding: '5px 12px', borderRadius: '7px', border: 'none',
                background: 'rgba(34,197,94,0.15)', color: '#22c55e',
                fontSize: '10px', fontWeight: 700, cursor: 'pointer',
                letterSpacing: '0.04em',
              }}
            >
              <Plus size={11} /> Agregar ítem
            </button>
          </div>

          {availLoading && (
            <p style={{ fontSize: '11px', color: '#606075', margin: '0 0 8px' }}>Cargando disponibilidad...</p>
          )}

          {items.length === 0 ? (
            <div style={{
              padding: '20px', borderRadius: '10px', textAlign: 'center',
              background: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.08)',
              fontSize: '11px', color: '#606075',
            }}>
              Sin ítems. Presioná "Agregar ítem" para incluir repuestos.
            </div>
          ) : (
            <div style={{
              borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)',
              overflow: 'hidden',
            }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
                <thead>
                  <tr style={{ background: '#0e0e14' }}>
                    {['Repuesto', 'Parte #', 'Disponible', 'A despachar', ''].map(h => (
                      <th key={h} style={{
                        padding: '8px 10px', textAlign: 'left',
                        fontSize: '9px', fontWeight: 700, color: '#606075',
                        textTransform: 'uppercase', letterSpacing: '0.07em',
                        borderBottom: '1px solid rgba(255,255,255,0.06)',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const avail = availability.find(a => a.spare_part_item_id === item.spare_part_item_id);
                    const maxQty = avail ? avail.qty_available : item.qty_available;
                    return (
                      <tr key={item._key} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                        {/* Repuesto selector — native datalist search */}
                        <td style={{ padding: '7px 10px', minWidth: 200 }}>
                          <input
                            type="text"
                            list={`avail-${item._key}`}
                            value={itemSearch[item._key] !== undefined ? itemSearch[item._key] : (item.part_number || '')}
                            placeholder="Buscar referencia..."
                            onChange={e => handleItemSearchChange(item._key, e.target.value)}
                            style={{ ...inputStyle, fontSize: '11px' }}
                          />
                          <datalist id={`avail-${item._key}`}>
                            {availability.map(a => (
                              <option key={a.spare_part_item_id} value={a.part_number} />
                            ))}
                          </datalist>
                        </td>

                        {/* Part number (auto) */}
                        <td style={{ padding: '7px 10px' }}>
                          <span style={{ fontFamily: 'monospace', color: item.part_number ? '#d1d5db' : '#606075', fontSize: '11px' }}>
                            {item.part_number || '—'}
                          </span>
                        </td>

                        {/* qty_available (readonly) */}
                        <td style={{ padding: '7px 10px', textAlign: 'center' }}>
                          <span style={{
                            fontSize: '11px', fontWeight: 700,
                            color: maxQty > 0 ? '#22c55e' : '#606075',
                          }}>
                            {maxQty !== null ? maxQty : '—'}
                          </span>
                        </td>

                        {/* qty_dispatched */}
                        <td style={{ padding: '7px 10px' }}>
                          <input
                            type="number"
                            min={1}
                            max={maxQty || undefined}
                            value={item.qty_dispatched}
                            onChange={e => {
                              const v = Math.max(1, Math.min(Number(e.target.value), maxQty || Infinity));
                              updateItemField(item._key, 'qty_dispatched', v);
                            }}
                            style={{ ...inputStyle, width: 70, textAlign: 'center' }}
                          />
                        </td>

                        {/* Delete row */}
                        <td style={{ padding: '7px 10px', textAlign: 'center' }}>
                          <button
                            onClick={() => removeItem(item._key)}
                            style={{
                              background: 'none', border: 'none',
                              color: '#606075', cursor: 'pointer', padding: '2px',
                            }}
                            title="Eliminar ítem"
                          >
                            <Trash2 size={13} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', paddingTop: '4px' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 18px', borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.1)',
              background: 'transparent', color: '#9ca3af',
              fontSize: '11px', cursor: 'pointer',
            }}
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving || items.length === 0}
            style={{
              padding: '8px 18px', borderRadius: '8px', border: 'none',
              background: saving || items.length === 0 ? 'rgba(255,95,51,0.2)' : 'rgba(255,95,51,0.85)',
              color: saving || items.length === 0 ? '#606075' : '#fff',
              fontSize: '11px', fontWeight: 700, cursor: saving || items.length === 0 ? 'not-allowed' : 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            {saving ? 'Guardando...' : 'Guardar Borrador'}
          </button>
        </div>
      </div>
    </div>
  );
}
