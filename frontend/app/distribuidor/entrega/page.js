'use client';

import { useState, useEffect } from 'react';
import AdminLayout from '../../admin-layout';
import { authFetch } from '../../../lib/authFetch';
import { getApiUrl } from '../../../lib/api';
import { toast } from '../../../lib/toast';
import VinLookupField from '../../../components/vehicle/VinLookupField';
import ModelSelectField from '../../../components/vehicle/ModelSelectField';
import DeliveryActUpload from '../../../components/distribuidor/DeliveryActUpload';
import { Save, Pencil, X, Download } from 'lucide-react';

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
  // Which Distribuidora made the sale. Meaningless/ignored by the backend
  // for a tenant-scoped actor (their own tenant is forced server-side) --
  // only superadmin's selection here actually matters.
  registered_by_tenant_id: '',
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

function validateDeliveryStep(form, photo, isNetworkWide) {
  if (!form.delivery_date) return 'La fecha de entrega es obligatoria.';
  if (isFutureDate(form.delivery_date)) return 'La fecha de entrega no puede ser futura.';
  if (!photo && !isNetworkWide) return 'El acta de entrega firmada es obligatoria.';
  // Superadmin has no tenant of their own -- unlike a Distribuidor, who
  // gets their own tienda attributed implicitly, superadmin MUST explicitly
  // say which Distribuidora made the sale (mirrors the backend's own
  // rejection in `_resolve_registered_by_tenant_id`).
  if (isNetworkWide && !form.registered_by_tenant_id) return 'Debe seleccionar la tienda que realizó la venta.';
  return null;
}

// Full-form validation — kept as a defense-in-depth safety net at final
// submit, combining every step's rule in the same order as before.
function validate(form, photo, isNetworkWide, vinLookupStatus) {
  return (
    validateClientStep(form)
    || validateVehicleStep(form, vinLookupStatus)
    || validateDeliveryStep(form, photo, isNetworkWide)
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
    registered_by_tenant_id: form.registered_by_tenant_id || null,
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
// Explicit background/color on every <option> -- without it, the dropdown
// popup inherits light text on the browser's default light background and
// is invisible until hovered (same convention as `frontend/app/tenants/page.js`).
const optionStyle = { background: '#1a1a22', color: '#fff' };

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

// Bugfix (2026-07-30): fixed-height flex column -- header/footer are
// `flexShrink: 0` (always visible/pinned) and only `modalBodyStyle` (the
// field grid in the middle) scrolls (`overflowY: 'auto'`, `flex: 1`,
// `minHeight: 0`, the standard "sticky header/footer, scrollable middle" CSS
// pattern), so a 15-field form no longer pushes the close button or the
// Guardar/Cancelar buttons off-screen. Widened from 520px -> 860px (bug 3)
// so `modalBodyStyle`'s grid can reflow into 2-3 columns like the wizard's
// `stepFieldGridStyle` already does, without being as wide as the full
// page's 1200px `cardStyle`.
const modalBackdropStyle = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' };
const modalBoxStyle = { background: '#0c0c0e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', width: '100%', maxWidth: '860px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', boxShadow: '0 25px 50px rgba(0,0,0,0.8)' };
const modalHeadStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.25rem 1.5rem', borderBottom: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 };
const modalBodyStyle = { padding: '1.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.9rem', overflowY: 'auto', flex: 1, minHeight: 0 };
const modalFootStyle = { display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', padding: '1.25rem 1.5rem', borderTop: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 };
const closeBtnStyle = { width: '28px', height: '28px', borderRadius: '8px', background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' };

function Field({ label, type = 'text', value, onChange, required = false, disabled = false }) {
  return (
    <label style={labelStyle}>
      {label}
      <input
        aria-label={label}
        type={type}
        value={value}
        onChange={onChange}
        style={disabled ? { ...inputStyle, opacity: 0.6, cursor: 'not-allowed' } : inputStyle}
        required={required}
        disabled={disabled}
      />
    </label>
  );
}

// Shared by the wizard's Entrega step (superadmin only) and the edit modal
// (always superadmin, per its own access boundary) -- a Distribuidor never
// sees this select, their own tienda is implicit and read-only instead.
function TenantSelect({ value, onChange, tenants }) {
  return (
    <label style={labelStyle}>
      Tienda
      <select
        aria-label="Tienda"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={inputStyle}
      >
        <option value="" style={optionStyle}>— Seleccionar —</option>
        {tenants.map((t) => <option key={t.id} value={t.id} style={optionStyle}>{t.name}</option>)}
      </select>
    </label>
  );
}

// Department -> city cascading selects backed by the DIVIPOLA catalog
// (`GET /tenants/divipola/departments`, `GET /tenants/divipola/cities`) --
// same catalog and UX as `frontend/app/tenants/page.js`, so client
// geography is never free text. `departmentField`/`cityField` are the
// `form` keys to read/write (`client_department`/`client_city` in both the
// wizard and the edit dialog).
function GeoFields({ form, setForm, geo, departmentField = 'client_department', cityField = 'client_city' }) {
  return (
    <>
      <label style={labelStyle}>
        Departamento
        <select
          aria-label="Departamento"
          value={form[departmentField]}
          onChange={(e) => {
            const dpto = e.target.value;
            setForm({ ...form, [departmentField]: dpto, [cityField]: '' });
            geo.fetchCities(dpto);
          }}
          style={inputStyle}
        >
          <option value="" style={optionStyle}>— Seleccionar —</option>
          {geo.departments.map((d) => <option key={d} value={d} style={optionStyle}>{d}</option>)}
        </select>
      </label>
      <label style={labelStyle}>
        Ciudad
        <select
          aria-label="Ciudad"
          value={form[cityField]}
          onChange={(e) => setForm({ ...form, [cityField]: e.target.value })}
          disabled={!form[departmentField]}
          style={inputStyle}
        >
          <option value="" style={optionStyle}>— Seleccionar —</option>
          {geo.cities.map((c) => <option key={c} value={c} style={optionStyle}>{c}</option>)}
        </select>
      </label>
    </>
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

// DIVIPOLA department/city catalog -- mirrors `frontend/app/tenants/page.js`'s
// `fetchDepartments`/`fetchCities` (public endpoints, plain `fetch`, no
// auth needed). `initialDepartment` pre-loads that department's cities once
// on mount, for the edit dialog opening on a delivery that already has a
// `client_department` set (so the current city renders as selected).
function useGeo(initialDepartment) {
  const [departments, setDepartments] = useState([]);
  const [cities, setCities] = useState([]);

  useEffect(() => {
    fetch(`${getApiUrl()}/tenants/divipola/departments`)
      .then((res) => res.json())
      .then((data) => setDepartments(Array.isArray(data) ? data : []))
      .catch(() => setDepartments([]));
  }, []);

  const fetchCities = async (dpto) => {
    if (!dpto) { setCities([]); return; }
    try {
      const res = await fetch(`${getApiUrl()}/tenants/divipola/cities?departamento=${encodeURIComponent(dpto)}`);
      setCities(await res.json());
    } catch { setCities([]); }
  };

  useEffect(() => {
    if (initialDepartment) fetchCities(initialDepartment);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { departments, cities, fetchCities };
}

// Network-wide tenant list for superadmin's "Tienda" select (create wizard
// AND the edit modal, both superadmin-only) -- reuses `GET /tenants`
// verbatim (`frontend/app/tenants/page.js`'s own fetch), no parallel
// endpoint. Only fetched when `enabled` (superadmin) -- a Distribuidor has
// no access to this endpoint (403) and doesn't need the list anyway, their
// own tienda is shown read-only instead.
function useTenants(enabled) {
  const [tenants, setTenants] = useState([]);
  useEffect(() => {
    if (!enabled) return;
    authFetch('/tenants')
      .then((res) => { if (!res.ok) throw new Error('tenants fetch failed'); return res.json(); })
      .then((data) => setTenants(Array.isArray(data) ? data : []))
      .catch(() => setTenants([]));
  }, [enabled]);
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

function useDeliverySubmit(form, photo, isNetworkWide, vinLookupStatus, resetForm, onSuccess) {
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('payload', JSON.stringify(buildPayload(form)));
      if (photo) fd.append('photo', photo, photo.name);

      const res = await authFetch('/distributor/deliveries', { method: 'POST', body: fd });
      if (res.ok) {
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
    const error = validate(form, photo, isNetworkWide, vinLookupStatus);
    if (error) {
      toast.error(error);
      return;
    }
    await submit();
  };

  return { saving, trySubmit };
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

function ClientSection({ form, setForm, geoApi }) {
  return (
    <>
      <Field label="Nombre del cliente" value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} required />
      <Field label="Cédula" value={form.client_identification} onChange={(e) => setForm({ ...form, client_identification: e.target.value })} required />
      <Field label="Fecha de nacimiento" type="date" value={form.client_birth_date} onChange={(e) => setForm({ ...form, client_birth_date: e.target.value })} />
      <Field label="Teléfono" value={form.client_phone} onChange={(e) => setForm({ ...form, client_phone: e.target.value })} />
      <Field label="Email" type="email" value={form.client_email} onChange={(e) => setForm({ ...form, client_email: e.target.value })} />
      <GeoFields form={form} setForm={setForm} geo={geoApi} />
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

function DeliverySection({ form, setForm, photo, setPhoto, isNetworkWide, user, tenants }) {
  return (
    <>
      <Field label="Fecha de entrega" type="date" value={form.delivery_date} onChange={(e) => setForm({ ...form, delivery_date: e.target.value })} required />
      {isNetworkWide ? (
        <TenantSelect
          value={form.registered_by_tenant_id}
          onChange={(v) => setForm({ ...form, registered_by_tenant_id: v })}
          tenants={tenants}
        />
      ) : (
        <Field label="Tienda" value={user?.tenant_name || ''} onChange={() => {}} disabled />
      )}
      <DeliveryActUpload
        value={photo}
        onChange={setPhoto}
        required={!isNetworkWide}
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
function ConfirmationSummary({ form, photo, isNetworkWide, user, tenants }) {
  const tiendaLabel = isNetworkWide
    ? (tenants.find((t) => t.id === form.registered_by_tenant_id)?.name || null)
    : (user?.tenant_name || null);
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
      <SummaryRow label="Tienda" value={tiendaLabel} />
      <SummaryRow label="Acta de entrega" value={photo ? photo.name : null} />
    </div>
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

function DeliveryRow({ delivery: d, isNetworkWide, onEdit }) {
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
      {isNetworkWide && (
        <td style={tdStyle}>
          {d.registered_by_tenant_name && (
            <span style={tenantBadgeStyle}>{d.registered_by_tenant_name}</span>
          )}
        </td>
      )}
      {isNetworkWide && (
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
// A delivery matches the search box if the query is a substring (case
// insensitive) of its cédula, VIN, or placa -- any one of the three is
// enough, no need to match all.
function matchesDeliverySearch(delivery, query) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [delivery.client_identification, delivery.vin, delivery.plate].some(
    (value) => (value || '').toLowerCase().includes(q)
  );
}

const deliveriesSearchRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginTop: '1rem', flexWrap: 'wrap' };
const deliveriesSearchInputStyle = { ...inputStyle, minWidth: '280px', flex: '1 1 320px' };
const deliveriesCountStyle = { ...hintStyle, fontSize: '0.75rem', whiteSpace: 'nowrap' };
const exportBtnStyle = { display: 'inline-flex', alignItems: 'center', gap: '0.35rem', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', borderRadius: '6px', padding: '0.35rem 0.7rem', fontSize: '0.75rem', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' };

// Mirrors `frontend/app/tenants/page.js`'s `handleExport` exactly (blob ->
// object URL -> synthetic <a download> click) -- same download mechanics,
// different endpoint/filename.
async function exportDeliveries(setExporting) {
  setExporting(true);
  try {
    const res = await authFetch('/distributor/deliveries/export');
    if (!res.ok) {
      toast.error('No se pudieron exportar los registros.');
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `entregas_registradas_${new Date().toISOString().slice(0, 10)}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    toast.error('No se pudieron exportar los registros.');
  } finally {
    setExporting(false);
  }
}

function DeliveriesSection({ deliveries, loading, isNetworkWide, onEdit }) {
  const [search, setSearch] = useState('');
  const [exporting, setExporting] = useState(false);
  const filtered = deliveries.filter((d) => matchesDeliverySearch(d, search));
  const isSearching = search.trim() !== '';

  return (
    <section className="glass p-6" style={listSectionStyle}>
      <StepHeading title="Registros Realizados" />
      <div style={deliveriesSearchRowStyle}>
        <input
          aria-label="Buscar por cédula, VIN o placa"
          placeholder="Buscar por cédula, VIN o placa…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={deliveriesSearchInputStyle}
        />
        <span style={deliveriesCountStyle}>
          {isSearching
            ? `Mostrando ${filtered.length} de ${deliveries.length} registros`
            : `${deliveries.length} registros`}
        </span>
        <button
          type="button"
          onClick={() => exportDeliveries(setExporting)}
          disabled={exporting}
          style={{ ...exportBtnStyle, opacity: exporting ? 0.6 : 1, cursor: exporting ? 'wait' : 'pointer' }}
        >
          <Download size={13} /> {exporting ? 'Exportando...' : 'Exportar Excel'}
        </button>
      </div>
      {loading ? (
        <p style={emptyStateStyle}>Cargando registros...</p>
      ) : deliveries.length === 0 ? (
        <p style={emptyStateStyle}>Todavía no hay registros.</p>
      ) : filtered.length === 0 ? (
        <p style={emptyStateStyle}>Sin resultados para tu búsqueda.</p>
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
                {isNetworkWide && <th style={thStyle}>Distribuidora</th>}
                {isNetworkWide && <th style={thStyle}>Acciones</th>}
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <DeliveryRow key={d.id} delivery={d} isNetworkWide={isNetworkWide} onEdit={onEdit} />
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
  'registered_by_tenant_id',
];

// Bugfix (2026-07-30): source the "original" prefill values from the FULL
// `DeliveryDetailOut` fetch (`GET /distributor/deliveries/{id}`), not the
// sparse `DeliveryListItemOut` list row this dialog opens from --
// `DeliveryListItemOut` only ever carried `id, plate, vin, model,
// delivery_date, client_name, registered_by_tenant_name, delivery_act_url`,
// so every other field used to start blank even though it was already saved
// in the DB. `year` (a number on the wire) is coerced to string here, same
// as the wizard's own form state, so `buildEditPatch`'s trim/compare logic
// below works uniformly.
function originalEditValues(detail) {
  return {
    client_name: detail.client_name || '',
    client_phone: detail.client_phone || '',
    client_identification: detail.client_identification || '',
    client_birth_date: detail.client_birth_date || '',
    client_city: detail.client_city || '',
    client_department: detail.client_department || '',
    client_address: detail.client_address || '',
    client_email: detail.client_email || '',
    plate: detail.plate || '',
    vin: detail.vin || '',
    model: detail.model || '',
    color: detail.color || '',
    year: detail.year != null ? String(detail.year) : '',
    engine_number: detail.engine_number || '',
    delivery_date: detail.delivery_date || '',
    registered_by_tenant_id: detail.registered_by_tenant_id || '',
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

// Bugfix (2026-07-30): fetches the FULL delivery record
// (`GET /distributor/deliveries/{id}`, superadmin-only, same 403 boundary as
// the `PATCH` on this same path) when the edit modal opens, so the modal's
// "original" prefill baseline is real DB data instead of the sparse list row.
function useDeliveryDetail(deliveryId) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    (async () => {
      try {
        const res = await authFetch(`/distributor/deliveries/${deliveryId}`);
        if (!res.ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        const data = await res.json();
        if (!cancelled) setDetail(data);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [deliveryId]);

  return { detail, loading, failed };
}

function EditClientFields({ form, setForm, geoApi }) {
  return (
    <>
      <Field label="Nombre del cliente" value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
      <Field label="Cédula" value={form.client_identification} onChange={(e) => setForm({ ...form, client_identification: e.target.value })} />
      <Field label="Fecha de nacimiento" type="date" value={form.client_birth_date} onChange={(e) => setForm({ ...form, client_birth_date: e.target.value })} />
      <Field label="Teléfono del cliente" value={form.client_phone} onChange={(e) => setForm({ ...form, client_phone: e.target.value })} />
      <Field label="Email" type="email" value={form.client_email} onChange={(e) => setForm({ ...form, client_email: e.target.value })} />
      <GeoFields form={form} setForm={setForm} geo={geoApi} />
      <Field label="Dirección" value={form.client_address} onChange={(e) => setForm({ ...form, client_address: e.target.value })} />
    </>
  );
}

function EditVehicleFields({ form, setForm, vinApi, tenants }) {
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
      <TenantSelect
        value={form.registered_by_tenant_id}
        onChange={(v) => setForm({ ...form, registered_by_tenant_id: v })}
        tenants={tenants}
      />
    </>
  );
}

// The actual edit form -- only mounts once `detail` (the
// `GET /distributor/deliveries/{id}` response) has loaded, so its initial
// `form` state (and the `original` diff baseline `buildEditPatch` compares
// against) is sourced from real DB data, not a placeholder.
function EditDeliveryForm({ deliveryId, detail, tenants, onClose, onSaved }) {
  const original = originalEditValues(detail);
  const [form, setForm] = useState(original);
  const [saving, setSaving] = useState(false);
  // Own instance of the wizard's VIN-lookup hook -- this dialog manages
  // separate form state from the wizard, so it needs its own autofill wiring
  // rather than sharing the wizard's `vinApi`.
  const vinApi = useVinLookup(setForm);
  // Own instance of the geo hook too, seeded with the record's current
  // department so its city options are pre-loaded and the stored city
  // renders as selected instead of blank.
  const geoApi = useGeo(original.client_department);

  const handleSave = async () => {
    const patch = buildEditPatch(form, original);
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    const ok = await submitEditPatch(deliveryId, patch);
    setSaving(false);
    if (ok) onSaved(patch);
  };

  return (
    <>
      <div style={modalBodyStyle}>
        <EditClientFields form={form} setForm={setForm} geoApi={geoApi} />
        <EditVehicleFields form={form} setForm={setForm} vinApi={vinApi} tenants={tenants} />
      </div>
      <div style={modalFootStyle}>
        <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancelar</button>
        <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Guardando...' : 'Guardar'}
        </button>
      </div>
    </>
  );
}

// Superadmin-only edit dialog. Bugfix (2026-07-30): fetches the full record
// on open instead of trusting the sparse list row (see `useDeliveryDetail`);
// on fetch failure, shows a toast error and closes rather than risk showing
// blank/broken data. Clicking the backdrop closes the dialog without saving
// (same convention as `components/ConfirmModal.js`); clicking inside the box
// does not (`stopPropagation` on the inner box).
function EditDeliveryModal({ delivery, tenants, onClose, onSaved }) {
  const { detail, loading, failed } = useDeliveryDetail(delivery.id);

  useEffect(() => {
    if (failed) {
      toast.error('No se pudo cargar el registro.');
      onClose();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [failed]);

  return (
    <div style={modalBackdropStyle} onClick={onClose}>
      <div style={modalBoxStyle} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Editar Registro">
        <div style={modalHeadStyle}>
          <h2 style={stepHeadingStyle}>Editar Registro</h2>
          <button type="button" onClick={onClose} style={closeBtnStyle} aria-label="Cerrar">
            <X size={16} />
          </button>
        </div>
        {(loading || failed) ? (
          <div style={modalBodyStyle}>
            <p style={emptyStateStyle}>Cargando registro...</p>
          </div>
        ) : (
          <EditDeliveryForm deliveryId={delivery.id} detail={detail} tenants={tenants} onClose={onClose} onSaved={onSaved} />
        )}
      </div>
    </div>
  );
}

// One render function per wizard step -- keeps the main component to just
// wiring/navigation, each step's own JSX lives and reads on its own.
function ClientStep({ form, setForm, geoApi, onNext }) {
  return (
    <>
      <StepHeading title="Cliente" />
      <div style={stepFieldGridStyle}>
        <ClientSection form={form} setForm={setForm} geoApi={geoApi} />
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

function DeliveryStep({ form, setForm, photo, setPhoto, isNetworkWide, user, tenants, onBack, onNext }) {
  return (
    <>
      <StepHeading title="Entrega" />
      <div style={stepFieldGridStyle}>
        <DeliverySection form={form} setForm={setForm} photo={photo} setPhoto={setPhoto} isNetworkWide={isNetworkWide} user={user} tenants={tenants} />
      </div>
      <StepNav onBack={onBack} onNext={onNext} />
    </>
  );
}

function ConfirmStep({ form, photo, submitApi, isNetworkWide, user, tenants, onBack }) {
  return (
    <>
      <StepHeading title="Confirmación" />
      <ConfirmationSummary form={form} photo={photo} isNetworkWide={isNetworkWide} user={user} tenants={tenants} />
      <StepNav onBack={onBack} submitApi={submitApi} />
    </>
  );
}

// Per-step "Siguiente"/"Atrás" navigation, kept out of the main component
// so it stays wiring-only.
function useWizardNavigation(form, photo, isNetworkWide, vinLookupStatus) {
  const [step, setStep] = useState(STEP_CLIENT);

  const stepValidators = {
    [STEP_CLIENT]: () => validateClientStep(form),
    [STEP_VEHICLE]: () => validateVehicleStep(form, vinLookupStatus),
    [STEP_DELIVERY]: () => validateDeliveryStep(form, photo, isNetworkWide),
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

  const resetStep = () => setStep(STEP_CLIENT);

  return { step, goNext, goBack, resetStep };
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
  const isNetworkWide = user?.role === 'superadmin' || user?.role === 'administrativo';
  const vehicleModels = useVehicleModels();
  const vinApi = useVinLookup(setForm);
  const geoApi = useGeo();
  const tenants = useTenants(isNetworkWide);
  const deliveriesApi = useDeliveries();
  const [editingDelivery, setEditingDelivery] = useState(null);
  const { step, goNext, goBack, resetStep } = useWizardNavigation(form, photo, isNetworkWide, vinApi.vinLookupStatus);
  // Resets the form data AND returns to Cliente after a successful submit,
  // so staff can start registering the next delivery right away.
  const resetForm = () => {
    setForm(FORM_DEFAULTS);
    setPhoto(null);
    vinApi.setVinLookupStatus('idle');
    resetStep();
  };
  const submitApi = useDeliverySubmit(form, photo, isNetworkWide, vinApi.vinLookupStatus, resetForm, deliveriesApi.fetchDeliveries);

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
          isNetworkWide={isNetworkWide}
          user={user}
          tenants={tenants}
          vehicleModels={vehicleModels}
          vinApi={vinApi}
          geoApi={geoApi}
          submitApi={submitApi}
          onBack={goBack}
          onNext={goNext}
        />
      </section>

      <DeliveriesSection
        deliveries={deliveriesApi.deliveries}
        loading={deliveriesApi.loadingDeliveries}
        isNetworkWide={isNetworkWide}
        onEdit={setEditingDelivery}
      />

      {isNetworkWide && editingDelivery && (
        <EditDeliveryModal
          delivery={editingDelivery}
          tenants={tenants}
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
