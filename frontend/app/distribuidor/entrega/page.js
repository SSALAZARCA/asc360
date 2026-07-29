'use client';

import { useState, useEffect } from 'react';
import AdminLayout from '../../admin-layout';
import { authFetch } from '../../../lib/authFetch';
import { toast } from '../../../lib/toast';
import VinLookupField from '../../../components/vehicle/VinLookupField';
import ModelSelectField from '../../../components/vehicle/ModelSelectField';
import DeliveryActUpload from '../../../components/distribuidor/DeliveryActUpload';
import { Truck, Save } from 'lucide-react';

// ---------------------------------------------------------------------------
// Whitelisted shape — MUST mirror `DeliveryCreate`
// (backend/app/schemas/distributor_delivery.py) exactly.
// ---------------------------------------------------------------------------
const FORM_DEFAULTS = {
  client_name: '',
  client_identification: '',
  client_birth_date: '',
  client_city: '',
  client_department: '',
  client_address: '',
  client_phone: '',
  client_email: '',
  plate: '',
  vin: '',
  model: '',
  color: '',
  year: '',
  engine_number: '',
  delivery_date: '',
};

// 4-step wizard (Cliente → Vehículo → Entrega → Confirmación), per the
// original design's "visually dynamic" multi-step requirement (Design,
// File Changes: "Multi-step form ... progress bar"). PR7 shipped this as a
// flat sectioned form instead (deviation flagged, not silent, in
// sdd/distributor-vehicle-delivery/apply-progress); this is the post-archive
// UX follow-up that reverses that deviation.
const STEPS = ['Cliente', 'Vehículo', 'Entrega', 'Confirmación'];
const STEP_CLIENT = 0;
const STEP_VEHICLE = 1;
const STEP_DELIVERY = 2;
const STEP_CONFIRM = 3;

// ---------------------------------------------------------------------------
// Pure helpers — no React, no I/O.
// ---------------------------------------------------------------------------

// Day-precision comparison against "today" in Bogotá (fixed UTC-5, no DST) —
// plain string comparison works because YYYY-MM-DD sorts lexically the same
// as chronologically.
function isFutureDate(dateStr) {
  if (!dateStr) return false;
  const todayBogota = new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString().slice(0, 10);
  return dateStr > todayBogota;
}

// Per-step validators — each returns the SAME toast message the original
// flat form used for that field, just evaluated at "Siguiente" time for the
// step that owns the field instead of only at final submit.
function validateClientStep(form) {
  if (!form.client_name.trim()) return 'El nombre del cliente es obligatorio.';
  if (!form.client_identification.trim()) return 'La cédula del cliente es obligatoria.';
  return null;
}

function validateVehicleStep(form) {
  if (!form.plate.trim()) return 'La placa es obligatoria.';
  return null;
}

function validateDeliveryStep(form, photo, isSuperadmin) {
  if (!form.delivery_date) return 'La fecha de entrega es obligatoria.';
  if (isFutureDate(form.delivery_date)) return 'La fecha de entrega no puede ser futura.';
  if (!photo && !isSuperadmin) return 'El acta de entrega firmada es obligatoria.';
  return null;
}

// Full-form validation — kept as a defense-in-depth safety net at final
// submit, combining every step's rule in the same order as before.
function validate(form, photo, isSuperadmin) {
  return (
    validateClientStep(form)
    || validateVehicleStep(form)
    || validateDeliveryStep(form, photo, isSuperadmin)
  );
}

function buildPayload(form) {
  return {
    client: {
      name: form.client_name.trim(),
      identification: form.client_identification.trim(),
      birth_date: form.client_birth_date || null,
      city: form.client_city.trim() || null,
      department: form.client_department.trim() || null,
      address: form.client_address.trim() || null,
      phone: form.client_phone.trim() || null,
      email: form.client_email.trim() || null,
    },
    vehicle: {
      plate: form.plate.trim(),
      vin: form.vin.trim() || null,
      model: form.model.trim() || null,
      color: form.color.trim() || null,
      year: form.year !== '' ? Number(form.year) : null,
      engine_number: form.engine_number.trim() || null,
    },
    // Raw "YYYY-MM-DD" string -- NOT run through bogotaTime's datetime
    // conversion, which would shift the day. `delivery_date` is a DATE
    // column, day precision only (Design ADR 2).
    delivery_date: form.delivery_date,
  };
}

function extractErrorMessage(detail, fallback) {
  if (detail == null) return fallback;
  if (typeof detail === 'object') return detail.detail || fallback;
  return detail;
}

// ---------------------------------------------------------------------------
// Shared presentational bits — dark theme, `glass` class, existing tokens.
// ---------------------------------------------------------------------------
const sectionStyle = { display: 'flex', flexDirection: 'column', gap: '1rem' };
// Centered card, wide enough that the wizard doesn't look stuck to one side
// with empty space next to it (was a flat maxWidth:480px column before).
const cardStyle = { maxWidth: '760px', margin: '0 auto', width: '100%' };
const stepFieldGridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
  gap: '0.9rem',
  marginTop: '1rem',
};
const labelStyle = { display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.72rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em' };
const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.6rem 0.85rem', color: '#fff', fontSize: '0.85rem', outline: 'none', textTransform: 'none' };
const hintStyle = { margin: 0, fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', textTransform: 'none', fontWeight: 400, letterSpacing: 'normal' };

function Field({ label, type = 'text', value, onChange, required = false }) {
  return (
    <label style={labelStyle}>
      {label}
      <input aria-label={label} type={type} value={value} onChange={onChange} style={inputStyle} required={required} />
    </label>
  );
}

// ---------------------------------------------------------------------------
// Data hooks
// ---------------------------------------------------------------------------
function useCurrentUser() {
  const [user, setUser] = useState(null);
  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    if (stored) {
      try { setUser(JSON.parse(stored)); } catch { setUser(null); }
    }
  }, []);
  return user;
}

function useVehicleModels() {
  const [vehicleModels, setVehicleModels] = useState([]);
  useEffect(() => {
    authFetch('/vehicle-models')
      .then((res) => { if (!res.ok) throw new Error('vehicle-models fetch failed'); return res.json(); })
      .then((data) => setVehicleModels(Array.isArray(data) ? data : []))
      .catch(() => {
        setVehicleModels([]);
        toast.error('No se pudo cargar el catálogo de modelos.');
      });
  }, []);
  return vehicleModels;
}

// Same 17-char-trigger contract as historical-orders/page.js, but also
// autofills `engine_number` (Design: "autofills model/year/color/engine_number").
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
        engine_number: data.engine_number || f.engine_number,
      }));
      setVinLookupStatus('found');
    } catch {
      setVinLookupStatus('not_found');
    }
  };

  return { vinLookupStatus, setVinLookupStatus, lookupVin };
}

function useDeliverySubmit(form, photo, isSuperadmin, resetForm) {
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(null); // { id } | null

  const submit = async () => {
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('payload', JSON.stringify(buildPayload(form)));
      if (photo) fd.append('photo', photo, photo.name);

      const res = await authFetch('/distributor/deliveries', { method: 'POST', body: fd });
      if (res.ok) {
        const data = await res.json();
        setSuccess({ id: data.id });
        toast.success('Entrega registrada correctamente.');
        resetForm();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, 'Error al registrar la entrega.'));
      }
    } catch {
      toast.error('Error de conexión.');
    } finally {
      setSaving(false);
    }
  };

  const trySubmit = async () => {
    const error = validate(form, photo, isSuperadmin);
    if (error) {
      toast.error(error);
      return;
    }
    await submit();
  };

  return { saving, success, trySubmit };
}

// ---------------------------------------------------------------------------
// Presentational sections
// ---------------------------------------------------------------------------
function PageHeader() {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-title">
          Registro de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Motocicletas</span>
        </h1>
        <p className="page-subtitle">Registro de venta/entrega — uso exclusivo de Distribuidor</p>
      </div>
    </header>
  );
}

function stepCircleStyle(state) {
  const base = { width: '28px', height: '28px', minWidth: '28px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700 };
  if (state === 'done') return { ...base, background: 'var(--accent-orange)', color: '#1a1a22' };
  if (state === 'active') return { ...base, background: 'rgba(255,95,51,0.15)', border: '2px solid var(--accent-orange)', color: '#fff' };
  return { ...base, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' };
}

function stepLabelStyle(state) {
  return {
    fontSize: '0.7rem',
    fontWeight: state === 'active' ? 700 : 500,
    color: state === 'pending' ? 'rgba(255,255,255,0.4)' : '#fff',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  };
}

const stepperStyle = { display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1.5rem', flexWrap: 'wrap' };
const stepItemStyle = { display: 'flex', alignItems: 'center', gap: '0.5rem' };
const stepConnectorStyle = (done) => ({ flex: '1 0 24px', height: '2px', minWidth: '24px', background: done ? 'var(--accent-orange)' : 'rgba(255,255,255,0.12)' });

function Stepper({ current }) {
  return (
    <div style={stepperStyle}>
      {STEPS.map((label, idx) => {
        const state = idx < current ? 'done' : idx === current ? 'active' : 'pending';
        return (
          <div key={label} style={{ display: 'contents' }}>
            <div style={stepItemStyle}>
              <span style={stepCircleStyle(state)}>{idx + 1}</span>
              <span style={stepLabelStyle(state)}>{label}</span>
            </div>
            {idx < STEPS.length - 1 && <div style={stepConnectorStyle(idx < current)} />}
          </div>
        );
      })}
    </div>
  );
}

const stepHeadingStyle = { margin: 0, fontSize: '1rem', fontWeight: 700, color: '#fff', textTransform: 'uppercase', letterSpacing: '0.04em' };

function StepHeading({ title }) {
  return <h2 style={stepHeadingStyle}>{title}</h2>;
}

const stepNavStyle = { display: 'flex', gap: '0.75rem', marginTop: '1.5rem', justifyContent: 'flex-end' };

function StepNav({ onBack, onNext, submitApi }) {
  return (
    <div style={stepNavStyle}>
      {onBack && (
        <button type="button" className="btn-secondary" onClick={onBack}>Atrás</button>
      )}
      {onNext && (
        <button type="button" className="btn-primary" onClick={onNext}>Siguiente</button>
      )}
      {submitApi && (
        <button
          type="button"
          className="btn-primary"
          onClick={submitApi.trySubmit}
          disabled={submitApi.saving}
          style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', justifyContent: 'center' }}
        >
          <Save size={13} /> {submitApi.saving ? 'Registrando...' : 'Registrar Entrega'}
        </button>
      )}
    </div>
  );
}

function ClientSection({ form, setForm }) {
  return (
    <>
      <Field label="Nombre del cliente" value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} required />
      <Field label="Cédula" value={form.client_identification} onChange={(e) => setForm({ ...form, client_identification: e.target.value })} required />
      <Field label="Fecha de nacimiento" type="date" value={form.client_birth_date} onChange={(e) => setForm({ ...form, client_birth_date: e.target.value })} />
      <Field label="Teléfono" value={form.client_phone} onChange={(e) => setForm({ ...form, client_phone: e.target.value })} />
      <Field label="Email" type="email" value={form.client_email} onChange={(e) => setForm({ ...form, client_email: e.target.value })} />
      <Field label="Ciudad" value={form.client_city} onChange={(e) => setForm({ ...form, client_city: e.target.value })} />
      <Field label="Departamento" value={form.client_department} onChange={(e) => setForm({ ...form, client_department: e.target.value })} />
      <Field label="Dirección" value={form.client_address} onChange={(e) => setForm({ ...form, client_address: e.target.value })} />
    </>
  );
}

function VehicleSection({ form, setForm, vehicleModels, vinApi }) {
  return (
    <>
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
      <ModelSelectField
        models={vehicleModels}
        value={form.model}
        onChange={(value) => setForm({ ...form, model: value })}
        labelStyle={labelStyle}
        inputStyle={inputStyle}
      />
      <Field label="Color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
      <Field label="Año" type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} />
      <Field label="Número de motor" value={form.engine_number} onChange={(e) => setForm({ ...form, engine_number: e.target.value })} />
    </>
  );
}

function DeliverySection({ form, setForm, photo, setPhoto, isSuperadmin }) {
  return (
    <>
      <Field label="Fecha de entrega" type="date" value={form.delivery_date} onChange={(e) => setForm({ ...form, delivery_date: e.target.value })} required />
      <DeliveryActUpload
        value={photo}
        onChange={setPhoto}
        required={!isSuperadmin}
        labelStyle={labelStyle}
        inputStyle={inputStyle}
        hintStyle={hintStyle}
      />
    </>
  );
}

const summaryListStyle = { display: 'flex', flexDirection: 'column', gap: '0.6rem', marginTop: '1rem' };
const summaryGroupTitleStyle = { ...hintStyle, textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em', color: 'rgba(255,255,255,0.5)', marginTop: '0.5rem' };
const summaryRowStyle = { display: 'flex', justifyContent: 'space-between', gap: '1rem', fontSize: '0.85rem', color: '#fff', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '0.35rem' };
const summaryLabelStyle = { color: 'rgba(255,255,255,0.5)' };

function SummaryRow({ label, value }) {
  return (
    <div style={summaryRowStyle}>
      <span style={summaryLabelStyle}>{label}</span>
      <span>{value || '—'}</span>
    </div>
  );
}

// Read-only review of everything entered across the 3 previous steps.
function ConfirmationSummary({ form, photo }) {
  return (
    <div style={summaryListStyle}>
      <p style={summaryGroupTitleStyle}>Cliente</p>
      <SummaryRow label="Nombre del cliente" value={form.client_name} />
      <SummaryRow label="Cédula" value={form.client_identification} />
      <SummaryRow label="Fecha de nacimiento" value={form.client_birth_date} />
      <SummaryRow label="Teléfono" value={form.client_phone} />
      <SummaryRow label="Email" value={form.client_email} />
      <SummaryRow label="Ciudad" value={form.client_city} />
      <SummaryRow label="Departamento" value={form.client_department} />
      <SummaryRow label="Dirección" value={form.client_address} />

      <p style={summaryGroupTitleStyle}>Vehículo</p>
      <SummaryRow label="Placa" value={form.plate} />
      <SummaryRow label="VIN" value={form.vin} />
      <SummaryRow label="Modelo" value={form.model} />
      <SummaryRow label="Color" value={form.color} />
      <SummaryRow label="Año" value={form.year} />
      <SummaryRow label="Número de motor" value={form.engine_number} />

      <p style={summaryGroupTitleStyle}>Entrega</p>
      <SummaryRow label="Fecha de entrega" value={form.delivery_date} />
      <SummaryRow label="Acta de entrega" value={photo ? photo.name : null} />
    </div>
  );
}

function SuccessNotice({ submitApi }) {
  if (!submitApi.success) return null;
  return (
    <p style={{ ...hintStyle, color: '#22c55e', fontSize: '0.8rem', marginTop: '1rem' }}>
      <Truck size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
      Entrega registrada correctamente.
    </p>
  );
}

export default function DistribuidorEntregaPage() {
  const [form, setForm] = useState(FORM_DEFAULTS);
  const [photo, setPhoto] = useState(null);
  const [step, setStep] = useState(STEP_CLIENT);
  const user = useCurrentUser();
  const isSuperadmin = user?.role === 'superadmin';
  const vehicleModels = useVehicleModels();
  const vinApi = useVinLookup(setForm);
  // Resets the form data after a successful submit but deliberately stays
  // on Confirmación so the success notice remains visible; the user can
  // click Atrás to start a fresh entry once they've seen it.
  const resetForm = () => {
    setForm(FORM_DEFAULTS);
    setPhoto(null);
    vinApi.setVinLookupStatus('idle');
  };
  const submitApi = useDeliverySubmit(form, photo, isSuperadmin, resetForm);

  const stepValidators = {
    [STEP_CLIENT]: () => validateClientStep(form),
    [STEP_VEHICLE]: () => validateVehicleStep(form),
    [STEP_DELIVERY]: () => validateDeliveryStep(form, photo, isSuperadmin),
  };

  const goNext = () => {
    const validator = stepValidators[step];
    const error = validator ? validator() : null;
    if (error) {
      toast.error(error);
      return;
    }
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const goBack = () => setStep((s) => Math.max(s - 1, 0));

  return (
    <AdminLayout>
      <PageHeader />
      <section className="glass p-6" style={{ ...sectionStyle, ...cardStyle }}>
        <Stepper current={step} />

        {step === STEP_CLIENT && (
          <>
            <StepHeading title="Cliente" />
            <div style={stepFieldGridStyle}>
              <ClientSection form={form} setForm={setForm} />
            </div>
            <StepNav onNext={goNext} />
          </>
        )}

        {step === STEP_VEHICLE && (
          <>
            <StepHeading title="Vehículo" />
            <div style={stepFieldGridStyle}>
              <VehicleSection form={form} setForm={setForm} vehicleModels={vehicleModels} vinApi={vinApi} />
            </div>
            <StepNav onBack={goBack} onNext={goNext} />
          </>
        )}

        {step === STEP_DELIVERY && (
          <>
            <StepHeading title="Entrega" />
            <div style={stepFieldGridStyle}>
              <DeliverySection form={form} setForm={setForm} photo={photo} setPhoto={setPhoto} isSuperadmin={isSuperadmin} />
            </div>
            <StepNav onBack={goBack} onNext={goNext} />
          </>
        )}

        {step === STEP_CONFIRM && (
          <>
            <StepHeading title="Confirmación" />
            <ConfirmationSummary form={form} photo={photo} />
            <StepNav onBack={goBack} submitApi={submitApi} />
            <SuccessNotice submitApi={submitApi} />
          </>
        )}
      </section>
    </AdminLayout>
  );
}
