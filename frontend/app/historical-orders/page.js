'use client';

import { useState, useEffect } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { toast } from '../../lib/toast';
import ConfirmModal from '../../components/ConfirmModal';
import VinLookupField from '../../components/vehicle/VinLookupField';
import ModelSelectField from '../../components/vehicle/ModelSelectField';
import { bogotaInputValueToUtcIso } from '../../lib/bogotaTime';
import { CalendarClock, Save } from 'lucide-react';

// ---------------------------------------------------------------------------
// Whitelisted shape — MUST mirror `HistoricalOrderCreate`
// (backend/app/schemas/historical_order.py) exactly. NO cédula/identification
// field anywhere (Decision 6 of the design — a hard, decided non-goal).
// ---------------------------------------------------------------------------
const FORM_DEFAULTS = {
  tenant_id: '',
  plate: '',
  vin: '',
  brand: '',
  model: '',
  year: '',
  color: '',
  client_name: '',
  client_phone: '',
  status: 'received',
  service_type: 'regular',
  mileage_km: '',
  created_at: '',
  completed_at: '',
  delivered_at: '',
  diagnosis: '',
  customer_notes: '',
  general_observations: '',
};

// Mismos colores/labels que superadmin-data/page.js — mismo dato en dos
// pantallas distintas, misma nomenclatura visual.
const STATUS_OPTIONS = [
  { value: 'received', label: 'Recibido' },
  { value: 'completed', label: 'Completado' },
  { value: 'delivered', label: 'Entregado' },
];

const SERVICE_TYPE_OPTIONS = [
  { value: 'regular', label: 'Mec. General' },
  { value: 'warranty', label: 'Garantía' },
  { value: 'km_review', label: 'Revisión por Kilometraje' },
  { value: 'quick', label: 'Rápido' },
  { value: 'pdi', label: 'PDI' },
];

// ---------------------------------------------------------------------------
// Pure helpers — no React, no I/O.
// ---------------------------------------------------------------------------
function validate(form) {
  if (!form.tenant_id) return 'Seleccioná un taller.';
  if (!form.plate.trim()) return 'La placa es obligatoria.';
  if (!form.client_name.trim()) return 'El nombre del cliente es obligatorio.';
  if (!form.created_at) return 'La fecha de creación es obligatoria.';
  if (form.mileage_km === '' || Number.isNaN(Number(form.mileage_km)) || Number(form.mileage_km) < 0) {
    return 'El kilometraje es obligatorio.';
  }
  return null;
}

function buildPayload(form, acknowledgeDuplicate) {
  return {
    tenant_id: form.tenant_id,
    vehicle: {
      plate: form.plate.trim(),
      vin: form.vin.trim() || null,
      brand: form.brand.trim() || null,
      model: form.model.trim() || null,
      year: form.year !== '' ? Number(form.year) : null,
      color: form.color.trim() || null,
    },
    client: {
      name: form.client_name.trim(),
      phone: form.client_phone.trim() || null,
    },
    service_type: form.service_type,
    status: form.status,
    mileage_km: Number(form.mileage_km),
    created_at: bogotaInputValueToUtcIso(form.created_at),
    completed_at: bogotaInputValueToUtcIso(form.completed_at),
    delivered_at: bogotaInputValueToUtcIso(form.delivered_at),
    customer_notes: form.customer_notes.trim() || null,
    diagnosis: form.diagnosis.trim() || null,
    general_observations: form.general_observations.trim() || null,
    acknowledge_duplicate: acknowledgeDuplicate,
  };
}

function extractErrorMessage(detail, fallback) {
  if (detail == null) return fallback;
  if (typeof detail === 'object') return detail.detail || fallback;
  return detail;
}

function isDuplicateWarning(detail) {
  return !!detail && typeof detail === 'object' && detail.code === 'DUPLICATE_ORDER_WARNING';
}

// ---------------------------------------------------------------------------
// Shared presentational bits — mirrors the look of superadmin-data/page.js.
// ---------------------------------------------------------------------------
const sectionStyle = { display: 'flex', flexDirection: 'column', gap: '1rem' };
const fieldGridStyle = { display: 'flex', flexDirection: 'column', gap: '0.9rem', maxWidth: '480px', marginTop: '1rem' };
const labelStyle = { display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.72rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em' };
const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.6rem 0.85rem', color: '#fff', fontSize: '0.85rem', outline: 'none', textTransform: 'none' };
const hintStyle = { margin: 0, fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', textTransform: 'none', fontWeight: 400, letterSpacing: 'normal' };
const textareaStyle = { ...inputStyle, minHeight: '70px', resize: 'vertical', fontFamily: 'inherit' };
// Explicit background/color on every <option> -- without it, the dropdown
// popup inherits light text on the browser's default light background and
// is invisible until hovered.
const optionStyle = { background: '#1a1a22', color: '#fff' };

function Field({ label, type = 'text', value, onChange, required = false }) {
  return (
    <label style={labelStyle}>
      {label}
      <input aria-label={label} type={type} value={value} onChange={onChange} style={inputStyle} required={required} />
    </label>
  );
}

function TextAreaField({ label, value, onChange }) {
  return (
    <label style={labelStyle}>
      {label}
      <textarea aria-label={label} value={value} onChange={onChange} style={textareaStyle} />
    </label>
  );
}

// ---------------------------------------------------------------------------
// Data hooks
// ---------------------------------------------------------------------------
function useTenants() {
  const [tenants, setTenants] = useState([]);
  useEffect(() => {
    authFetch('/tenants')
      // `res.ok ? res.json() : []` never throws on an HTTP error status --
      // it silently resolves to an empty list, which never reaches
      // .catch(). Throwing explicitly here is what makes a 401/403/500
      // actually surface to the user instead of just leaving the required
      // Taller <select> empty with no explanation.
      .then((res) => { if (!res.ok) throw new Error('tenants fetch failed'); return res.json(); })
      .then((data) => setTenants(Array.isArray(data) ? data : []))
      .catch(() => {
        setTenants([]);
        toast.error('No se pudo cargar la lista de talleres.');
      });
  }, []);
  return tenants;
}

function useVehicleModels() {
  const [vehicleModels, setVehicleModels] = useState([]);
  useEffect(() => {
    authFetch('/vehicle-models')
      .then((res) => { if (!res.ok) throw new Error('vehicle-models fetch failed'); return res.json(); })
      .then((data) => setVehicleModels(Array.isArray(data) ? data : []))
      .catch(() => {
        setVehicleModels([]);
        // Non-blocking (ModelSelectField falls back to free text), but the
        // user should still know why the standardized dropdown is missing.
        toast.error('No se pudo cargar el catálogo de modelos.');
      });
  }, []);
  return vehicleModels;
}

// Same 17-char-trigger contract as superadmin-data's VinField, wired through
// the reusable VinLookupField component built in PR3.
function useVinLookup(setForm) {
  const [vinLookupStatus, setVinLookupStatus] = useState('idle');

  const lookupVin = async (rawVin) => {
    const vin = rawVin.trim().toUpperCase();
    setVinLookupStatus('loading');
    try {
      const res = await authFetch(`/vehicles/vin/${encodeURIComponent(vin)}`);
      if (!res.ok) { setVinLookupStatus('not_found'); return; }
      const data = await res.json();
      setForm((f) => ({
        ...f,
        model: data.model || f.model,
        year: data.year ? String(data.year) : f.year,
        color: data.color || f.color,
      }));
      setVinLookupStatus('found');
    } catch {
      setVinLookupStatus('not_found');
    }
  };

  return { vinLookupStatus, setVinLookupStatus, lookupVin };
}

function useHistoricalOrderSubmit(form, resetForm) {
  const [saving, setSaving] = useState(false);
  const [confirmState, setConfirmState] = useState(null); // { message, matches } | null
  const [success, setSuccess] = useState(null); // { id } | null

  const submit = async (acknowledgeDuplicate) => {
    setSaving(true);
    try {
      const res = await authFetch('/superadmin/data/historical-orders', {
        method: 'POST',
        body: JSON.stringify(buildPayload(form, acknowledgeDuplicate)),
      });
      if (res.ok) {
        const data = await res.json();
        setConfirmState(null);
        setSuccess({ id: data.id });
        toast.success('Orden histórica creada correctamente.');
        resetForm();
      } else {
        const err = await res.json().catch(() => ({}));
        if (res.status === 409 && isDuplicateWarning(err.detail)) {
          const matches = err.detail.matches || [];
          const matchLines = matches
            .map((m) => `- ${m.plate} · ${m.created_at ? m.created_at.slice(0, 10) : '-'} · ${m.status}`)
            .join('\n');
          const message = matchLines ? `${err.detail.detail}\n\n${matchLines}` : err.detail.detail;
          setConfirmState({ message, matches });
        } else {
          setConfirmState(null);
          toast.error(extractErrorMessage(err.detail, 'Error al crear la orden histórica.'));
        }
      }
    } catch {
      setConfirmState(null);
      toast.error('Error de conexión.');
    } finally {
      setSaving(false);
    }
  };

  const trySubmit = async () => {
    const error = validate(form);
    if (error) {
      toast.error(error);
      return;
    }
    await submit(false);
  };

  return {
    saving, success, confirmState,
    trySubmit,
    confirmDuplicate: () => submit(true),
    cancelConfirm: () => setConfirmState(null),
  };
}

// ---------------------------------------------------------------------------
// Presentational sections
// ---------------------------------------------------------------------------
function TallerField({ tenants, value, onChange }) {
  return (
    <label style={labelStyle}>
      Taller
      <select aria-label="Taller" value={value} onChange={onChange} style={inputStyle} required>
        <option value="" style={optionStyle}>— Seleccioná un taller —</option>
        {tenants.map((t) => (
          <option key={t.id} value={t.id} style={optionStyle}>{t.name}</option>
        ))}
      </select>
    </label>
  );
}

function PageHeader() {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-title">
          Orden <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Histórica</span>
        </h1>
        <p className="page-subtitle">Carga de órdenes de servicio en papel — uso exclusivo de superadmin</p>
      </div>
    </header>
  );
}

function VehicleSection({ form, setForm, tenants, vehicleModels, vinApi }) {
  return (
    <>
      <TallerField
        tenants={tenants}
        value={form.tenant_id}
        onChange={(e) => setForm({ ...form, tenant_id: e.target.value })}
      />
      <Field label="Placa" value={form.plate} onChange={(e) => setForm({ ...form, plate: e.target.value })} required />
      <VinLookupField
        value={form.vin}
        onChange={(value) => { setForm((f) => ({ ...f, vin: value })); vinApi.setVinLookupStatus('idle'); }}
        onLookup={vinApi.lookupVin}
        lookupStatus={vinApi.vinLookupStatus}
        labelStyle={labelStyle}
        inputStyle={inputStyle}
        hintStyle={hintStyle}
      />
      <Field label="Marca" value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} />
      <ModelSelectField
        models={vehicleModels}
        value={form.model}
        onChange={(value) => setForm({ ...form, model: value })}
        labelStyle={labelStyle}
        inputStyle={inputStyle}
      />
      <Field label="Color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
      <Field label="Año" type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} />
    </>
  );
}

function ClientSection({ form, setForm }) {
  return (
    <>
      <Field label="Nombre del cliente" value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} required />
      <Field label="Teléfono del cliente" value={form.client_phone} onChange={(e) => setForm({ ...form, client_phone: e.target.value })} />
    </>
  );
}

function DatesAndStatusSection({ form, setForm }) {
  return (
    <>
      <Field label="Fecha de creación" type="datetime-local" value={form.created_at} onChange={(e) => setForm({ ...form, created_at: e.target.value })} required />
      <Field label="Fecha de finalización" type="datetime-local" value={form.completed_at} onChange={(e) => setForm({ ...form, completed_at: e.target.value })} />
      <Field label="Fecha de entrega" type="datetime-local" value={form.delivered_at} onChange={(e) => setForm({ ...form, delivered_at: e.target.value })} />

      <label style={labelStyle}>
        Estado
        <select aria-label="Estado" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} style={inputStyle}>
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} style={optionStyle}>{opt.label}</option>
          ))}
        </select>
      </label>
      <label style={labelStyle}>
        Tipo de servicio
        <select aria-label="Tipo de servicio" value={form.service_type} onChange={(e) => setForm({ ...form, service_type: e.target.value })} style={inputStyle}>
          {SERVICE_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} style={optionStyle}>{opt.label}</option>
          ))}
        </select>
      </label>
    </>
  );
}

function NotesSection({ form, setForm }) {
  return (
    <>
      <Field label="Kilometraje" type="number" value={form.mileage_km} onChange={(e) => setForm({ ...form, mileage_km: e.target.value })} required />
      <TextAreaField label="Diagnóstico" value={form.diagnosis} onChange={(e) => setForm({ ...form, diagnosis: e.target.value })} />
      <TextAreaField label="Notas del cliente" value={form.customer_notes} onChange={(e) => setForm({ ...form, customer_notes: e.target.value })} />
      <TextAreaField label="Observaciones generales" value={form.general_observations} onChange={(e) => setForm({ ...form, general_observations: e.target.value })} />
    </>
  );
}

function SubmitSection({ submitApi }) {
  return (
    <>
      <button
        className="btn-primary"
        onClick={submitApi.trySubmit}
        disabled={submitApi.saving}
        style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', justifyContent: 'center' }}
      >
        <Save size={13} /> {submitApi.saving ? 'Creando...' : 'Crear Orden Histórica'}
      </button>

      {submitApi.success && (
        <p style={{ ...hintStyle, color: '#22c55e', fontSize: '0.8rem' }}>
          <CalendarClock size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
          Orden {submitApi.success.id.slice(0, 8)} creada correctamente.
        </p>
      )}
    </>
  );
}

export default function HistoricalOrdersPage() {
  const [form, setForm] = useState(FORM_DEFAULTS);
  const tenants = useTenants();
  const vehicleModels = useVehicleModels();
  const vinApi = useVinLookup(setForm);
  const resetForm = () => { setForm(FORM_DEFAULTS); vinApi.setVinLookupStatus('idle'); };
  const submitApi = useHistoricalOrderSubmit(form, resetForm);

  return (
    <AdminLayout>
      <PageHeader />
      <section className="glass p-6" style={sectionStyle}>
        <div style={fieldGridStyle}>
          <VehicleSection form={form} setForm={setForm} tenants={tenants} vehicleModels={vehicleModels} vinApi={vinApi} />
          <ClientSection form={form} setForm={setForm} />
          <DatesAndStatusSection form={form} setForm={setForm} />
          <NotesSection form={form} setForm={setForm} />
          <SubmitSection submitApi={submitApi} />
        </div>
      </section>

      {submitApi.confirmState && (
        <ConfirmModal
          title="Posible orden duplicada"
          message={submitApi.confirmState.message}
          danger
          confirmLabel="Cargar de todas formas"
          cancelLabel="Cancelar"
          onConfirm={submitApi.confirmDuplicate}
          onCancel={submitApi.cancelConfirm}
        />
      )}
    </AdminLayout>
  );
}
