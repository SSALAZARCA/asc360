'use client';
import { useState, useEffect } from 'react';
import { X, Save, Plus } from 'lucide-react';
import { authFetch } from '../../lib/authFetch';

const API = () => (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/^http://(?!localhost)/, 'https://');

const STATUS_OPTIONS = [
  { value: 'en_preparacion', label: 'En Preparación' },
  { value: 'listo_fabrica', label: 'Listo Fábrica' },
  { value: 'en_transito', label: 'En Tránsito' },
  { value: 'en_destino', label: 'En Destino' },
  { value: 'completado', label: 'Completado' },
  { value: 'backorder', label: 'Backorder' },
];

const DOCS_OPTIONS = [
  { value: 'PENDING',  label: 'Pendiente' },
  { value: 'UPLOADED', label: 'Recibido' },
];

const EMPTY = {
  order_date: '',
  cycle: '',
  pi_number: '',
  invoice_number: '',
  model: '',
  model_year: '',
  qty: '',
  containers: '',
  departure_port: '',
  bl_container: '',
  vessel: '',
  etr_raw: '',
  etl_raw: '',
  etd_raw: '',
  eta_raw: '',
  digital_docs_status: 'PENDING',
  original_docs_status: 'PENDING',
  remarks: '',
};

function Field({ label, children, required }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label style={{ fontSize: '10px', fontWeight: 700, color: '#606075', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
        {label}{required && <span style={{ color: '#ff5f33', marginLeft: '2px' }}>*</span>}
      </label>
      {children}
    </div>
  );
}

const inputStyle = {
  padding: '8px 10px', borderRadius: '8px',
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
  color: '#fff', fontSize: '12px', outline: 'none', width: '100%', boxSizing: 'border-box',
};

const selectStyle = {
  ...inputStyle,
  background: '#1a1a24',
};

export default function ShipmentOrderFormModal({ isOpen, onClose, onSuccess, order = null }) {
  const isEdit = !!order;
  const [form, setForm] = useState(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    if (isEdit && order) {
      setForm({
        order_date: order.order_date ?? '',
        cycle: order.cycle ?? '',
        pi_number: order.pi_number ?? '',
        invoice_number: order.invoice_number ?? '',
        model: order.model ?? '',
        model_year: order.model_year ?? '',
        qty: order.qty ?? '',
        containers: order.containers ?? '',
        departure_port: order.departure_port ?? '',
        bl_container: order.bl_container ?? '',
        vessel: order.vessel ?? '',
        etr_raw: order.etr_raw ?? '',
        etl_raw: order.etl_raw ?? '',
        etd_raw: order.etd_raw ?? '',
        eta_raw: order.eta_raw ?? '',
        digital_docs_status: order.digital_docs_status ?? 'PENDING',
        original_docs_status: order.original_docs_status ?? 'PENDING',
        remarks: order.remarks ?? '',
      });
    } else {
      setForm(EMPTY);
    }
    setError(null);
  }, [isOpen, order, isEdit]);

  if (!isOpen) return null;

  const set = (key) => (e) => setForm(f => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async () => {
    if (!form.pi_number.trim()) { setError('El número de PI es obligatorio'); return; }
    if (!form.model.trim()) { setError('El modelo es obligatorio'); return; }

    setLoading(true);
    setError(null);

    const payload = {
      order_date: form.order_date.trim() || null,
      cycle: form.cycle !== '' ? Number(form.cycle) : null,
      pi_number: form.pi_number.trim(),
      invoice_number: form.invoice_number.trim() || null,
      model: form.model.trim(),
      model_year: form.model_year !== '' ? Number(form.model_year) : null,
      qty: form.qty.trim() || null,
      containers: form.containers !== '' ? Number(form.containers) : null,
      departure_port: form.departure_port.trim() || null,
      bl_container: form.bl_container.trim() || null,
      vessel: form.vessel.trim() || null,
      etr_raw: form.etr_raw.trim() || null,
      etl_raw: form.etl_raw.trim() || null,
      etd_raw: form.etd_raw.trim() || null,
      eta_raw: form.eta_raw.trim() || null,
      digital_docs_status: form.digital_docs_status || 'PENDING',
      original_docs_status: form.original_docs_status || 'PENDING',
      remarks: form.remarks.trim() || null,
    };

    try {
      const url = isEdit
        ? `${API()}/imports/shipment-orders/${order.id}`
        : `${API()}/imports/shipment-orders`;
      const method = isEdit ? 'PATCH' : 'POST';

      const res = await authFetch(url, {
        method,
        body: JSON.stringify(payload),
      });

      const rawText = await res.text();
      let data;
      try { data = JSON.parse(rawText); } catch { data = { detail: rawText }; }

      if (!res.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : (data.detail?.detail ?? JSON.stringify(data.detail ?? data));
        throw new Error(detail);
      }

      if (onSuccess) onSuccess(data);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '20px',
    }}>
      <div style={{
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', padding: '28px', width: '680px', maxWidth: '100%',
        maxHeight: '90vh', overflowY: 'auto',
        display: 'flex', flexDirection: 'column', gap: '24px',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ color: '#fff', fontWeight: 800, fontSize: '15px', margin: 0 }}>
              {isEdit ? 'Editar Pedido' : 'Nuevo Pedido'}
            </h3>
            {isEdit && (
              <p style={{ color: '#606075', fontSize: '11px', margin: '3px 0 0' }}>
                {order.pi_number} — {order.model}
              </p>
            )}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}>
            <X size={18} />
          </button>
        </div>

        {/* Sección: Identificación */}
        <section>
          <p style={{ color: '#606075', fontSize: '10px', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', margin: '0 0 12px' }}>
            Identificación
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
            <Field label="Fecha de Pedido">
              <input type="date" value={form.order_date} onChange={set('order_date')} style={inputStyle} />
            </Field>
            <Field label="Ciclo">
              <input type="number" value={form.cycle} onChange={set('cycle')} style={inputStyle} placeholder="Ej: 26" />
            </Field>
            <Field label="Número PI" required>
              <input value={form.pi_number} onChange={set('pi_number')} style={inputStyle} placeholder="Ej: E0000573" />
            </Field>
            <Field label="Invoice">
              <input value={form.invoice_number} onChange={set('invoice_number')} style={inputStyle} placeholder="Ej: INV-2024-001" />
            </Field>
            <Field label="Modelo" required>
              <input value={form.model} onChange={set('model')} style={inputStyle} placeholder="Ej: JH70" />
            </Field>
            <Field label="Año Modelo">
              <input type="number" value={form.model_year} onChange={set('model_year')} style={inputStyle} placeholder="Ej: 2025" />
            </Field>
            <Field label="Cantidad">
              <input value={form.qty} onChange={set('qty')} style={inputStyle} placeholder="Ej: 200" />
            </Field>
          </div>
        </section>

        {/* Sección: Logística */}
        <section>
          <p style={{ color: '#606075', fontSize: '10px', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', margin: '0 0 12px' }}>
            Logística
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
            <Field label="Contenedores">
              <input type="number" value={form.containers} onChange={set('containers')} style={inputStyle} placeholder="Ej: 4" />
            </Field>
            <Field label="Puerto Salida">
              <input value={form.departure_port} onChange={set('departure_port')} style={inputStyle} placeholder="Ej: SHANGHAI" />
            </Field>
            <Field label="BL / Contenedor">
              <input value={form.bl_container} onChange={set('bl_container')} style={inputStyle} placeholder="Ej: MAEU123456" />
            </Field>
            <Field label="Nave / Buque">
              <input value={form.vessel} onChange={set('vessel')} style={inputStyle} placeholder="Ej: MAERSK LIMA" />
            </Field>
          </div>
        </section>

        {/* Sección: Fechas */}
        <section>
          <p style={{ color: '#606075', fontSize: '10px', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', margin: '0 0 12px' }}>
            Fechas (YYYY-MM-DD)
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '12px' }}>
            <Field label="ETR">
              <input value={form.etr_raw} onChange={set('etr_raw')} style={inputStyle} placeholder="2025-03-01" />
            </Field>
            <Field label="ETL">
              <input value={form.etl_raw} onChange={set('etl_raw')} style={inputStyle} placeholder="2025-04-15" />
            </Field>
            <Field label="ETD">
              <input value={form.etd_raw} onChange={set('etd_raw')} style={inputStyle} placeholder="2025-05-01" />
            </Field>
            <Field label="ETA">
              <input value={form.eta_raw} onChange={set('eta_raw')} style={inputStyle} placeholder="2025-06-01" />
            </Field>
          </div>
        </section>

        {/* Sección: Documentación */}
        <section>
          <p style={{ color: '#606075', fontSize: '10px', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', margin: '0 0 12px' }}>
            Documentación
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <Field label="Docs Digitales">
              <select value={form.digital_docs_status} onChange={set('digital_docs_status')} style={selectStyle}>
                {DOCS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
            <Field label="Docs Originales">
              <select value={form.original_docs_status} onChange={set('original_docs_status')} style={selectStyle}>
                {DOCS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
          </div>
        </section>

        {/* Observaciones */}
        <Field label="Observaciones">
          <textarea
            value={form.remarks}
            onChange={set('remarks')}
            rows={3}
            style={{ ...inputStyle, resize: 'vertical' }}
            placeholder="Notas internas sobre este pedido..."
          />
        </Field>

        {/* Error */}
        {error && (
          <div style={{
            background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
            borderRadius: '8px', padding: '12px', fontSize: '12px', color: '#f87171',
          }}>
            {error}
          </div>
        )}

        {/* Acciones */}
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            padding: '9px 18px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)',
            background: 'transparent', color: '#606075', cursor: 'pointer', fontSize: '12px', fontWeight: 600,
          }}>
            Cancelar
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '9px 20px', borderRadius: '8px', border: 'none',
              background: loading ? 'rgba(255,95,51,0.3)' : '#ff5f33',
              color: '#fff', cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '12px', fontWeight: 700,
            }}
          >
            {isEdit ? <Save size={13} /> : <Plus size={13} />}
            {loading ? 'Guardando...' : (isEdit ? 'Guardar Cambios' : 'Crear Pedido')}
          </button>
        </div>
      </div>
    </div>
  );
}
