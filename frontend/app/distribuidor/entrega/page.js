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

function validate(form, photo, isSuperadmin) {
  if (!form.client_name.trim()) return 'El nombre del cliente es obligatorio.';
  if (!form.client_identification.trim()) return 'La cédula del cliente es obligatoria.';
  if (!form.plate.trim()) return 'La placa es obligatoria.';
  if (!form.delivery_date) return 'La fecha de entrega es obligatoria.';
  if (isFutureDate(form.delivery_date)) return 'La fecha de entrega no puede ser futura.';
  if (!photo && !isSuperadmin) return 'El acta de entrega firmada es obligatoria.';
  return null;
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
// Shared presentational bits — mirrors historical-orders/page.js's look.
// ---------------------------------------------------------------------------
const sectionStyle = { display: 'flex', flexDirection: 'column', gap: '1rem' };
const fieldGridStyle = { display: 'flex', flexDirection: 'column', gap: '0.9rem', maxWidth: '480px', marginTop: '1rem' };
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
          Entrega de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Motos</span>
        </h1>
        <p className="page-subtitle">Registro de venta/entrega — uso exclusivo de Distribuidor</p>
      </div>
    </header>
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

function SubmitSection({ submitApi }) {
  return (
    <>
      <button
        className="btn-primary"
        onClick={submitApi.trySubmit}
        disabled={submitApi.saving}
        style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', justifyContent: 'center' }}
      >
        <Save size={13} /> {submitApi.saving ? 'Registrando...' : 'Registrar Entrega'}
      </button>

      {submitApi.success && (
        <p style={{ ...hintStyle, color: '#22c55e', fontSize: '0.8rem' }}>
          <Truck size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
          Entrega registrada correctamente.
        </p>
      )}
    </>
  );
}

export default function DistribuidorEntregaPage() {
  const [form, setForm] = useState(FORM_DEFAULTS);
  const [photo, setPhoto] = useState(null);
  const user = useCurrentUser();
  const isSuperadmin = user?.role === 'superadmin';
  const vehicleModels = useVehicleModels();
  const vinApi = useVinLookup(setForm);
  const resetForm = () => { setForm(FORM_DEFAULTS); setPhoto(null); vinApi.setVinLookupStatus('idle'); };
  const submitApi = useDeliverySubmit(form, photo, isSuperadmin, resetForm);

  return (
    <AdminLayout>
      <PageHeader />
      <section className="glass p-6" style={sectionStyle}>
        <div style={fieldGridStyle}>
          <ClientSection form={form} setForm={setForm} />
          <VehicleSection form={form} setForm={setForm} vehicleModels={vehicleModels} vinApi={vinApi} />
          <DeliverySection form={form} setForm={setForm} photo={photo} setPhoto={setPhoto} isSuperadmin={isSuperadmin} />
          <SubmitSection submitApi={submitApi} />
        </div>
      </section>
    </AdminLayout>
  );
}
