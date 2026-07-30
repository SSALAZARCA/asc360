'use client';

import { useState, useEffect } from 'react';
import AdminLayout from '../../admin-layout';
import { authFetch } from '../../../lib/authFetch';
import { toast } from '../../../lib/toast';
import VinLookupField from '../../../components/vehicle/VinLookupField';
import ModelSelectField from '../../../components/vehicle/ModelSelectField';
import DeliveryActUpload from '../../../components/distribuidor/DeliveryActUpload';
import { Truck, Save, Pencil, X, Download } from 'lucide-react';

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

// Backend now REQUIRES the VIN to resolve against the VIN master catalog for
// EVERY actor, no role exception (unlike the mandatory-photo rule below,
// which DOES exempt superadmin) -- `_require_vin_in_master` in
// `distributor_delivery_service.py`. Mirrored client-side via the same
// `useVinLookup` status this page already wires into the Vehículo step.
const VIN_NOT_IN_MASTER_MESSAGE = 'El VIN debe corresponder a una moto registrada en el maestro.';

function validateVehicleStep(form, vinLookupStatus) {
  if (!form.plate.trim()) return 'La placa es obligatoria.';
  if (vinLookupStatus !== 'found') return VIN_NOT_IN_MASTER_MESSAGE;
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
function validate(form, photo, isSuperadmin, vinLookupStatus) {
  return (
    validateClientStep(form)
    || validateVehicleStep(form, vinLookupStatus)
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
// Centered card. Widened from 760px (post-archive follow-up, 2026-07-30) --
// on a wide desktop viewport the narrower card left a lot of unused space
// beside it and `stepFieldGridStyle`'s auto-fit grid only reflows into more
// columns once there's room to do so. 1200px keeps the wizard readable while
// using the screen better, in line with this app's other admin panels
// (`.main-content` caps out at 1600px, `globals.css`).
const cardStyle = { maxWidth: '1200px', margin: '0 auto', width: '100%' };
const stepFieldGridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
  gap: '0.9rem',
  marginTop: '1rem',
};
const labelStyle = { display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.72rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em' };
const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.6rem 0.85rem', color: '#fff', fontSize: '0.85rem', outline: 'none', textTransform: 'none' };
const hintStyle = { margin: 0, fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', textTransform: 'none', fontWeight: 400, letterSpacing: 'normal' };

// "Registros Realizados" list + edit dialog tokens.
const listSectionStyle = { ...sectionStyle, ...cardStyle, marginTop: '1.5rem' };
const tableWrapStyle = { overflowX: 'auto', marginTop: '1rem' };
const tableStyle = { width: '100%', borderCollapse: 'collapse' };
const thStyle = { textAlign: 'left', padding: '0.7rem 0.9rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const tdStyle = { padding: '0.7rem 0.9rem', fontSize: '0.82rem', color: '#fff', borderBottom: '1px solid rgba(255,255,255,0.06)' };
const emptyStateStyle = { ...hintStyle, fontSize: '0.85rem', textAlign: 'center', padding: '2rem 0' };
const tenantBadgeStyle = { display: 'inline-block', fontSize: '0.65rem', fontWeight: 700, color: 'var(--accent-orange)', background: 'rgba(255,95,51,0.12)', padding: '2px 8px', borderRadius: '999px', textTransform: 'uppercase', letterSpacing: '0.04em' };
const editBtnStyle = { display: 'inline-flex', alignItems: 'center', gap: '0.3rem', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', borderRadius: '6px', padding: '0.35rem 0.6rem', fontSize: '0.7rem', cursor: 'pointer' };
const actaLinkStyle = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '28px', height: '28px', borderRadius: '6px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: 'var(--accent-orange)' };

const modalBackdropStyle = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' };
const modalBoxStyle = { background: '#0c0c0e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', width: '100%', maxWidth: '520px', boxShadow: '0 25px 50px rgba(0,0,0,0.8)' };
const modalHeadStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.25rem 1.5rem', borderBottom: '1px solid rgba(255,255,255,0.05)' };
const modalBodyStyle = { padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.9rem' };
const modalFootStyle = { display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', padding: '1.25rem 1.5rem', borderTop: '1px solid rgba(255,255,255,0.05)' };
const closeBtnStyle = { width: '28px', height: '28px', borderRadius: '8px', background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' };

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

// "Registros Realizados" -- lists deliveries already made. A Distribuidor
// sees only their own tenant's rows, superadmin sees every Distribuidora's
// rows network-wide (`registered_by_tenant_name` populated per row) -- same
// dual-role guard as create (`GET /distributor/deliveries`), the
// role-scoping itself is decided server-side, not here.
function useDeliveries() {
  const [deliveries, setDeliveries] = useState([]);
  const [loadingDeliveries, setLoadingDeliveries] = useState(true);

  const fetchDeliveries = async () => {
    setLoadingDeliveries(true);
    try {
      const res = await authFetch('/distributor/deliveries');
      if (!res.ok) {
        setDeliveries([]);
        toast.error('No se pudieron cargar los registros.');
        return;
      }
      const data = await res.json();
      setDeliveries(Array.isArray(data) ? data : []);
    } catch {
      setDeliveries([]);
      toast.error('No se pudieron cargar los registros.');
    } finally {
      setLoadingDeliveries(false);
    }
  };

  useEffect(() => { fetchDeliveries(); }, []);

  // Applied after a successful PATCH edit -- merges only the fields the
  // edit dialog can change (client_name/plate/vin/delivery_date) into the
  // existing row, cheaper than a full re-fetch (`DeliveryOut`, the PATCH
  // response shape, doesn't even carry `client_name` -- only `client_id` --
  // so the caller merges from the edited form values, not the response).
  const updateDeliveryLocal = (id, patch) => {
    setDeliveries((rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  return { deliveries, loadingDeliveries, fetchDeliveries, updateDeliveryLocal };
}

function useDeliverySubmit(form, photo, isSuperadmin, vinLookupStatus, resetForm, onSuccess) {
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
        // Re-fetch so a freshly-created registration shows up in "Registros
        // Realizados" without a manual page reload.
        if (onSuccess) onSuccess();
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
    const error = validate(form, photo, isSuperadmin, vinLookupStatus);
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

// Bugfix (2026-07-30): `Vehicle.delivery_act_url`
// (`pdf_service.upload_file_to_minio`) is a hardcoded `localhost:9000` URL --
// that host resolves to the BROWSER's own machine, not the server, so
// linking to it directly gives `ERR_CONNECTION_REFUSED` in production.
// Downloads now go through the authenticated proxy endpoint
// (`GET /distributor/deliveries/{vehicle_id}/act-file`), mirroring the same
// `res.blob()` -> `URL.createObjectURL` technique this codebase already uses
// for `frontend/app/tg/parts/page.js`'s diagram-image fetch.
async function downloadDeliveryAct(vehicleId) {
  try {
    const res = await authFetch(`/distributor/deliveries/${vehicleId}/act-file`);
    if (!res.ok) {
      toast.error('No se pudo descargar el acta de entrega.');
      return;
    }
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    window.open(objectUrl, '_blank', 'noopener,noreferrer');
  } catch {
    toast.error('No se pudo descargar el acta de entrega.');
  }
}

function DeliveryRow({ delivery: d, isSuperadmin, onEdit }) {
  return (
    <tr>
      <td style={tdStyle}>{d.client_name || '—'}</td>
      <td style={tdStyle}>{[d.model, d.plate].filter(Boolean).join(' — ') || '—'}</td>
      <td style={tdStyle}>{d.vin || '—'}</td>
      <td style={tdStyle}>{d.delivery_date}</td>
      <td style={tdStyle}>
        {d.delivery_act_url ? (
          <button
            type="button"
            onClick={() => downloadDeliveryAct(d.id)}
            aria-label="Descargar acta de entrega"
            style={actaLinkStyle}
          >
            <Download size={14} />
          </button>
        ) : '—'}
      </td>
      {isSuperadmin && (
        <td style={tdStyle}>
          {d.registered_by_tenant_name && (
            <span style={tenantBadgeStyle}>{d.registered_by_tenant_name}</span>
          )}
        </td>
      )}
      {isSuperadmin && (
        <td style={tdStyle}>
          <button type="button" style={editBtnStyle} onClick={() => onEdit(d)}>
            <Pencil size={12} /> Editar
          </button>
        </td>
      )}
    </tr>
  );
}

// ---------------------------------------------------------------------------
// "Registros Realizados" -- list of deliveries already registered, plus a
// superadmin-only inline edit dialog (PATCH /distributor/deliveries/{id}).
// ---------------------------------------------------------------------------
function DeliveriesSection({ deliveries, loading, isSuperadmin, onEdit }) {
  return (
    <section className="glass p-6" style={listSectionStyle}>
      <StepHeading title="Registros Realizados" />
      {loading ? (
        <p style={emptyStateStyle}>Cargando registros...</p>
      ) : deliveries.length === 0 ? (
        <p style={emptyStateStyle}>Todavía no hay registros.</p>
      ) : (
        <div style={tableWrapStyle}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Cliente</th>
                <th style={thStyle}>Moto</th>
                <th style={thStyle}>VIN</th>
                <th style={thStyle}>Fecha de Entrega</th>
                <th style={thStyle}>Acta</th>
                {isSuperadmin && <th style={thStyle}>Distribuidora</th>}
                {isSuperadmin && <th style={thStyle}>Acciones</th>}
              </tr>
            </thead>
            <tbody>
              {deliveries.map((d) => (
                <DeliveryRow key={d.id} delivery={d} isSuperadmin={isSuperadmin} onEdit={onEdit} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// Follow-up fix (2026-07-30): expanded to cover every field from the
// original registration (`DeliveryEditIn`, backend schema), not just the
// original 5.
const EDIT_FIELDS = [
  'client_name', 'client_phone', 'client_identification', 'client_birth_date',
  'client_city', 'client_department', 'client_address', 'client_email',
  'plate', 'vin', 'model', 'color', 'year', 'engine_number', 'delivery_date',
];

function originalEditValues(delivery) {
  // `DeliveryListItemOut` (the list row this dialog opens from) only carries
  // `id, plate, vin, model, delivery_date, client_name,
  // registered_by_tenant_name, delivery_act_url` -- every other field has no
  // server-known original value here, so it starts blank, same established
  // pattern as `client_phone`: if left untouched it's correctly excluded
  // from the patch, never clobbered to an empty value.
  return {
    client_name: delivery.client_name || '',
    client_phone: '',
    client_identification: '',
    client_birth_date: '',
    client_city: '',
    client_department: '',
    client_address: '',
    client_email: '',
    plate: delivery.plate || '',
    vin: delivery.vin || '',
    model: delivery.model || '',
    color: '',
    year: '',
    engine_number: '',
    delivery_date: delivery.delivery_date || '',
  };
}

// Pure diff: only fields that actually changed vs. `original` end up in the
// patch, so an untouched field is never sent (exclude_unset semantics on
// the backend rely on this). `year` is sent as a number, matching
// `buildPayload`'s treatment on create (`DeliveryEditIn.year: Optional[int]`).
function buildEditPatch(form, original) {
  const patch = {};
  for (const key of EDIT_FIELDS) {
    const value = form[key].trim();
    if (value === original[key].trim()) continue;
    if (value === '') { patch[key] = null; continue; }
    patch[key] = key === 'year' ? Number(value) : value;
  }
  return patch;
}

async function submitEditPatch(deliveryId, patch) {
  try {
    const res = await authFetch(`/distributor/deliveries/${deliveryId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
    if (res.ok) {
      toast.success('Registro actualizado correctamente.');
      return true;
    }
    const err = await res.json().catch(() => ({}));
    toast.error(extractErrorMessage(err.detail, 'Error al actualizar el registro.'));
    return false;
  } catch {
    toast.error('Error de conexión.');
    return false;
  }
}

function EditClientFields({ form, setForm }) {
  return (
    <>
      <Field label="Nombre del cliente" value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
      <Field label="Cédula" value={form.client_identification} onChange={(e) => setForm({ ...form, client_identification: e.target.value })} />
      <Field label="Fecha de nacimiento" type="date" value={form.client_birth_date} onChange={(e) => setForm({ ...form, client_birth_date: e.target.value })} />
      <Field label="Teléfono del cliente" value={form.client_phone} onChange={(e) => setForm({ ...form, client_phone: e.target.value })} />
      <Field label="Email" type="email" value={form.client_email} onChange={(e) => setForm({ ...form, client_email: e.target.value })} />
      <Field label="Ciudad" value={form.client_city} onChange={(e) => setForm({ ...form, client_city: e.target.value })} />
      <Field label="Departamento" value={form.client_department} onChange={(e) => setForm({ ...form, client_department: e.target.value })} />
      <Field label="Dirección" value={form.client_address} onChange={(e) => setForm({ ...form, client_address: e.target.value })} />
    </>
  );
}

function EditVehicleFields({ form, setForm, vinApi }) {
  return (
    <>
      <Field label="Placa" value={form.plate} onChange={(e) => setForm({ ...form, plate: e.target.value })} />
      <VinLookupField
        value={form.vin}
        onChange={(value) => { setForm((f) => ({ ...f, vin: value })); vinApi.setVinLookupStatus('idle'); }}
        onLookup={vinApi.lookupVin}
        lookupStatus={vinApi.vinLookupStatus}
        labelStyle={labelStyle}
        inputStyle={inputStyle}
        hintStyle={hintStyle}
      />
      <Field label="Modelo" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
      <Field label="Color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
      <Field label="Año" type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} />
      <Field label="Número de motor" value={form.engine_number} onChange={(e) => setForm({ ...form, engine_number: e.target.value })} />
      <Field label="Fecha de entrega" type="date" value={form.delivery_date} onChange={(e) => setForm({ ...form, delivery_date: e.target.value })} />
    </>
  );
}

// Superadmin-only edit dialog.
function EditDeliveryModal({ delivery, onClose, onSaved }) {
  const original = originalEditValues(delivery);
  const [form, setForm] = useState(original);
  const [saving, setSaving] = useState(false);
  // Own instance of the wizard's VIN-lookup hook -- this dialog manages
  // separate form state from the wizard, so it needs its own autofill wiring
  // rather than sharing the wizard's `vinApi`.
  const vinApi = useVinLookup(setForm);

  const handleSave = async () => {
    const patch = buildEditPatch(form, original);
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    const ok = await submitEditPatch(delivery.id, patch);
    setSaving(false);
    if (ok) onSaved(patch);
  };

  return (
    <div style={modalBackdropStyle}>
      <div style={modalBoxStyle} role="dialog" aria-modal="true" aria-label="Editar Registro">
        <div style={modalHeadStyle}>
          <h2 style={stepHeadingStyle}>Editar Registro</h2>
          <button type="button" onClick={onClose} style={closeBtnStyle} aria-label="Cerrar">
            <X size={16} />
          </button>
        </div>
        <div style={modalBodyStyle}>
          <EditClientFields form={form} setForm={setForm} />
          <EditVehicleFields form={form} setForm={setForm} vinApi={vinApi} />
        </div>
        <div style={modalFootStyle}>
          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancelar</button>
          <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </div>
    </div>
  );
}

// One render function per wizard step -- keeps the main component to just
// wiring/navigation, each step's own JSX lives and reads on its own.
function ClientStep({ form, setForm, onNext }) {
  return (
    <>
      <StepHeading title="Cliente" />
      <div style={stepFieldGridStyle}>
        <ClientSection form={form} setForm={setForm} />
      </div>
      <StepNav onNext={onNext} />
    </>
  );
}

function VehicleStep({ form, setForm, vehicleModels, vinApi, onBack, onNext }) {
  return (
    <>
      <StepHeading title="Vehículo" />
      <div style={stepFieldGridStyle}>
        <VehicleSection form={form} setForm={setForm} vehicleModels={vehicleModels} vinApi={vinApi} />
      </div>
      <StepNav onBack={onBack} onNext={onNext} />
    </>
  );
}

function DeliveryStep({ form, setForm, photo, setPhoto, isSuperadmin, onBack, onNext }) {
  return (
    <>
      <StepHeading title="Entrega" />
      <div style={stepFieldGridStyle}>
        <DeliverySection form={form} setForm={setForm} photo={photo} setPhoto={setPhoto} isSuperadmin={isSuperadmin} />
      </div>
      <StepNav onBack={onBack} onNext={onNext} />
    </>
  );
}

function ConfirmStep({ form, photo, submitApi, onBack }) {
  return (
    <>
      <StepHeading title="Confirmación" />
      <ConfirmationSummary form={form} photo={photo} />
      <StepNav onBack={onBack} submitApi={submitApi} />
      <SuccessNotice submitApi={submitApi} />
    </>
  );
}

// Per-step "Siguiente"/"Atrás" navigation, kept out of the main component
// so it stays wiring-only.
function useWizardNavigation(form, photo, isSuperadmin, vinLookupStatus) {
  const [step, setStep] = useState(STEP_CLIENT);

  const stepValidators = {
    [STEP_CLIENT]: () => validateClientStep(form),
    [STEP_VEHICLE]: () => validateVehicleStep(form, vinLookupStatus),
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

  return { step, goNext, goBack };
}

function WizardStepBody(props) {
  const { step, onBack, onNext } = props;
  if (step === STEP_CLIENT) return <ClientStep {...props} onNext={onNext} />;
  if (step === STEP_VEHICLE) return <VehicleStep {...props} onBack={onBack} onNext={onNext} />;
  if (step === STEP_DELIVERY) return <DeliveryStep {...props} onBack={onBack} onNext={onNext} />;
  if (step === STEP_CONFIRM) return <ConfirmStep {...props} onBack={onBack} />;
  return null;
}

export default function DistribuidorEntregaPage() {
  const [form, setForm] = useState(FORM_DEFAULTS);
  const [photo, setPhoto] = useState(null);
  const user = useCurrentUser();
  const isSuperadmin = user?.role === 'superadmin';
  const vehicleModels = useVehicleModels();
  const vinApi = useVinLookup(setForm);
  const deliveriesApi = useDeliveries();
  const [editingDelivery, setEditingDelivery] = useState(null);
  const { step, goNext, goBack } = useWizardNavigation(form, photo, isSuperadmin, vinApi.vinLookupStatus);
  // Resets the form data after a successful submit but deliberately stays
  // on Confirmación so the success notice remains visible; the user can
  // click Atrás to start a fresh entry once they've seen it.
  const resetForm = () => {
    setForm(FORM_DEFAULTS);
    setPhoto(null);
    vinApi.setVinLookupStatus('idle');
  };
  const submitApi = useDeliverySubmit(form, photo, isSuperadmin, vinApi.vinLookupStatus, resetForm, deliveriesApi.fetchDeliveries);

  return (
    <AdminLayout>
      <PageHeader />
      <section className="glass p-6" style={{ ...sectionStyle, ...cardStyle }}>
        <Stepper current={step} />
        <WizardStepBody
          step={step}
          form={form}
          setForm={setForm}
          photo={photo}
          setPhoto={setPhoto}
          isSuperadmin={isSuperadmin}
          vehicleModels={vehicleModels}
          vinApi={vinApi}
          submitApi={submitApi}
          onBack={goBack}
          onNext={goNext}
        />
      </section>

      <DeliveriesSection
        deliveries={deliveriesApi.deliveries}
        loading={deliveriesApi.loadingDeliveries}
        isSuperadmin={isSuperadmin}
        onEdit={setEditingDelivery}
      />

      {isSuperadmin && editingDelivery && (
        <EditDeliveryModal
          delivery={editingDelivery}
          onClose={() => setEditingDelivery(null)}
          onSaved={(patch) => {
            deliveriesApi.updateDeliveryLocal(editingDelivery.id, patch);
            setEditingDelivery(null);
          }}
        />
      )}
    </AdminLayout>
  );
}
