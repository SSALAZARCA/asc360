'use client';

import { useState } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { toast } from '../../lib/toast';
import ConfirmModal from '../../components/ConfirmModal';
import { Search, Save, Wand2, ArrowRight } from 'lucide-react';
import { utcIsoToBogotaInputValue, bogotaInputValueToUtcIso } from './bogotaTime';

// ---------------------------------------------------------------------------
// Whitelisted field sets — MUST mirror the backend's Pydantic schemas
// exactly (`VehicleQuickFixUpdate` / `OrderQuickFixUpdate` in
// backend/app/api/v1/superadmin_data.py). No other field is ever sent.
// ---------------------------------------------------------------------------
const VEHICLE_FORM_DEFAULTS = { id: '', plate: '', vin: '', brand: '', model: '', color: '', year: '', mileage: '' };
const ORDER_FORM_DEFAULTS = { id: '', plate: '', status: '', created_at: '', delivered_at: '', mileage_km: '', service_type: '' };

// Mismos colores que TYPE_CFG en services/page.js — mantener consistencia
// visual con el resto de la app para el mismo dato (tipo de servicio).
const SERVICE_TYPE_OPTIONS = [
  { value: 'regular', label: 'Mec. General', color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
  { value: 'warranty', label: 'Garantía', color: '#eab308', bg: 'rgba(234,179,8,0.15)' },
  { value: 'km_review', label: 'Revisión por Kilometraje', color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
  { value: 'quick', label: 'Rápido', color: '#a855f7', bg: 'rgba(168,85,247,0.15)' },
  { value: 'pdi', label: 'PDI', color: '#f97316', bg: 'rgba(249,115,22,0.15)' },
];

// ---------------------------------------------------------------------------
// Pure helpers — no React, no I/O. Kept outside the component tree so they
// stay trivially testable in isolation from rendering.
// ---------------------------------------------------------------------------

// The backend's error envelope is either a plain string (`detail: "..."`) or,
// for the confirm-then-delete flow, a nested object
// (`detail: {"detail": message, "code": "CONFIRM_DELETE_EVENT"}`). This reads
// the human-readable message out of either shape.
function extractErrorMessage(detail, fallback) {
  if (detail == null) return fallback;
  if (typeof detail === 'object') return detail.detail || fallback;
  return detail;
}

function isConfirmDeleteEvent(detail) {
  return !!detail && typeof detail === 'object' && detail.code === 'CONFIRM_DELETE_EVENT';
}

function populateVehicleForm(data) {
  return {
    id: data.id,
    plate: data.plate || '',
    vin: data.vin || '',
    brand: data.brand || '',
    model: data.model || '',
    color: data.color || '',
    year: data.year ?? '',
    mileage: data.mileage ?? '',
  };
}

function populateOrderForm(data) {
  return {
    id: data.id,
    plate: data.plate || '',
    status: data.status || '',
    created_at: utcIsoToBogotaInputValue(data.created_at),
    delivered_at: utcIsoToBogotaInputValue(data.delivered_at),
    mileage_km: data.mileage_km ?? '',
    service_type: data.service_type || '',
  };
}

function buildVehiclePayload(form) {
  return {
    plate: form.plate.trim(),
    brand: form.brand.trim(),
    model: form.model.trim(),
    vin: form.vin.trim() || null,
    color: form.color.trim() || null,
    year: form.year !== '' ? Number(form.year) : null,
    mileage: form.mileage !== '' ? Number(form.mileage) : null,
  };
}

function buildOrderPayload(form, confirmDeleteEvent) {
  return {
    created_at: bogotaInputValueToUtcIso(form.created_at),
    delivered_at: bogotaInputValueToUtcIso(form.delivered_at),
    mileage_km: form.mileage_km !== '' ? Number(form.mileage_km) : null,
    service_type: form.service_type || null,
    confirm_delete_event: confirmDeleteEvent,
  };
}

// ---------------------------------------------------------------------------
// Shared presentational bits — style objects + tiny leaf components so each
// tab's JSX stays a short list of one-line fields instead of repeated
// label/input boilerplate.
// ---------------------------------------------------------------------------
const sectionStyle = { display: 'flex', flexDirection: 'column', gap: '1rem' };
const fieldGridStyle = { display: 'flex', flexDirection: 'column', gap: '0.9rem', maxWidth: '420px', marginTop: '1rem' };
const labelStyle = { display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.72rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em' };
const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.6rem 0.85rem', color: '#fff', fontSize: '0.85rem', outline: 'none', textTransform: 'none' };

function Field({ label, type = 'text', value, onChange }) {
  return (
    <label style={labelStyle}>
      {label}
      <input aria-label={label} type={type} value={value} onChange={onChange} style={inputStyle} />
    </label>
  );
}

function SearchBar({ children, onSearch, searching }) {
  return (
    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
      {children}
      <button className="btn-primary" onClick={onSearch} disabled={searching} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
        <Search size={13} /> {searching ? 'Buscando...' : 'Buscar'}
      </button>
    </div>
  );
}

function SaveButton({ onClick, saving }) {
  return (
    <button className="btn-primary" onClick={onClick} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', justifyContent: 'center' }}>
      <Save size={13} /> {saving ? 'Guardando...' : 'Guardar'}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Vehículo tab — state + API calls live in a hook so the component below is
// pure rendering of that hook's return value.
// ---------------------------------------------------------------------------
function useVehicleQuickFix() {
  const [plateQuery, setPlateQuery] = useState('');
  const [form, setForm] = useState(VEHICLE_FORM_DEFAULTS);
  const [found, setFound] = useState(false);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);

  const search = async () => {
    if (!plateQuery.trim()) return;
    setSearching(true);
    try {
      const res = await authFetch(`/superadmin/data/vehicles?plate=${encodeURIComponent(plateQuery.trim())}`);
      if (res.ok) {
        setForm(populateVehicleForm(await res.json()));
        setFound(true);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, 'Vehículo no encontrado'));
        setFound(false);
        setForm(VEHICLE_FORM_DEFAULTS);
      }
    } catch {
      toast.error('Error de conexión.');
    } finally {
      setSearching(false);
    }
  };

  const save = async () => {
    if (!found) return;
    setSaving(true);
    try {
      const res = await authFetch(`/superadmin/data/vehicles/${form.id}`, {
        method: 'PUT',
        body: JSON.stringify(buildVehiclePayload(form)),
      });
      if (res.ok) {
        setForm(populateVehicleForm(await res.json()));
        toast.success('Vehículo actualizado correctamente.');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, 'Error al guardar el vehículo.'));
      }
    } catch {
      toast.error('Error de conexión.');
    } finally {
      setSaving(false);
    }
  };

  return { plateQuery, setPlateQuery, form, setForm, found, searching, saving, search, save };
}

function VehicleTab() {
  const v = useVehicleQuickFix();
  return (
    <section className="glass p-6" style={sectionStyle}>
      <SearchBar onSearch={v.search} searching={v.searching}>
        <input
          aria-label="Buscar vehículo por placa"
          placeholder="Placa"
          value={v.plateQuery}
          onChange={(e) => v.setPlateQuery(e.target.value)}
          style={inputStyle}
        />
      </SearchBar>

      {v.found && (
        <div style={fieldGridStyle}>
          <Field label="Placa" value={v.form.plate} onChange={(e) => v.setForm({ ...v.form, plate: e.target.value })} />
          <Field label="VIN" value={v.form.vin} onChange={(e) => v.setForm({ ...v.form, vin: e.target.value })} />
          <Field label="Marca" value={v.form.brand} onChange={(e) => v.setForm({ ...v.form, brand: e.target.value })} />
          <Field label="Modelo" value={v.form.model} onChange={(e) => v.setForm({ ...v.form, model: e.target.value })} />
          <Field label="Color" value={v.form.color} onChange={(e) => v.setForm({ ...v.form, color: e.target.value })} />
          <Field label="Año" type="number" value={v.form.year} onChange={(e) => v.setForm({ ...v.form, year: e.target.value })} />
          <Field label="Kilometraje" type="number" value={v.form.mileage} onChange={(e) => v.setForm({ ...v.form, mileage: e.target.value })} />
          <SaveButton onClick={v.save} saving={v.saving} />
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Orden tab — same shape as Vehículo, plus the confirm-then-delete flow.
// ---------------------------------------------------------------------------
// Búsqueda (por placa u orden) + selección de coincidencia cuando la placa
// matchea varias órdenes. `setForm`/`setFound` vienen del orquestador de
// abajo porque el resultado de una búsqueda es lo que puebla el formulario
// que el hook de guardado (useOrderSave) después lee y envía.
function useOrderSearch(setForm, setFound) {
  const [searchMode, setSearchMode] = useState('plate');
  const [searchValue, setSearchValue] = useState('');
  const [matches, setMatches] = useState(null); // list of candidates | null
  const [searching, setSearching] = useState(false);

  const search = async () => {
    if (!searchValue.trim()) return;
    setSearching(true);
    setMatches(null);
    try {
      const param = searchMode === 'order_id'
        ? `order_id=${encodeURIComponent(searchValue.trim())}`
        : `plate=${encodeURIComponent(searchValue.trim())}`;
      const res = await authFetch(`/superadmin/data/orders?${param}`);
      if (res.ok) {
        const data = await res.json();
        if (data.multiple_matches) {
          // Several orders share this plate — let the caller pick instead
          // of silently correcting whichever one happens to be newest.
          setFound(false);
          setForm(ORDER_FORM_DEFAULTS);
          setMatches(data.matches);
        } else {
          setForm(populateOrderForm(data));
          setFound(true);
        }
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, 'Orden no encontrada'));
        setFound(false);
        setForm(ORDER_FORM_DEFAULTS);
      }
    } catch {
      toast.error('Error de conexión.');
    } finally {
      setSearching(false);
    }
  };

  // The multiple_matches list is a lightweight summary (no mileage_km, per
  // design — the picker doesn't need it) — trusting it directly here would
  // always show that field blank. Re-fetch the full order by id instead.
  const selectMatch = async (match) => {
    setMatches(null);
    setSearching(true);
    try {
      const res = await authFetch(`/superadmin/data/orders?order_id=${encodeURIComponent(match.id)}`);
      if (res.ok) {
        setForm(populateOrderForm(await res.json()));
        setFound(true);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, 'Orden no encontrada'));
      }
    } catch {
      toast.error('Error de conexión.');
    } finally {
      setSearching(false);
    }
  };

  return { searchMode, setSearchMode, searchValue, setSearchValue, matches, searching, search, selectMatch };
}

// Guardado + flujo de confirmar-antes-de-borrar. Lee/actualiza el `form`
// compartido con useOrderSearch a través del orquestador de abajo.
function useOrderSave(form, found, setForm) {
  const [saving, setSaving] = useState(false);
  const [confirmState, setConfirmState] = useState(null); // { message } | null

  // Shared by the first attempt (`confirm_delete_event: false`) and the
  // confirmed resubmit (`confirm_delete_event: true`) — same payload, same
  // endpoint, only the flag changes.
  const submit = async (confirmDeleteEvent) => {
    setSaving(true);
    try {
      const res = await authFetch(`/superadmin/data/orders/${form.id}`, {
        method: 'PUT',
        body: JSON.stringify(buildOrderPayload(form, confirmDeleteEvent)),
      });
      if (res.ok) {
        setForm(populateOrderForm(await res.json()));
        setConfirmState(null);
        toast.success('Orden actualizada correctamente.');
      } else {
        const err = await res.json().catch(() => ({}));
        if (res.status === 409 && isConfirmDeleteEvent(err.detail)) {
          setConfirmState({ message: err.detail.detail });
        } else {
          setConfirmState(null);
          toast.error(extractErrorMessage(err.detail, 'Error al guardar la orden.'));
        }
      }
    } catch {
      setConfirmState(null);
      toast.error('Error de conexión.');
    } finally {
      setSaving(false);
    }
  };

  const save = async () => {
    if (!found) return;
    await submit(false);
  };

  return {
    saving, save, confirmState,
    confirmDelete: () => submit(true),
    cancelConfirm: () => setConfirmState(null),
  };
}

// Orquestador delgado: mantiene el `form`/`found` compartido y compone los
// dos hooks de arriba en la misma forma de API que ya consume OrderTab.
function useOrderQuickFix() {
  const [form, setForm] = useState(ORDER_FORM_DEFAULTS);
  const [found, setFound] = useState(false);

  const searchApi = useOrderSearch(setForm, setFound);
  const saveApi   = useOrderSave(form, found, setForm);

  return { form, setForm, found, ...searchApi, ...saveApi };
}

function serviceTypeLabel(value) {
  return SERVICE_TYPE_OPTIONS.find((opt) => opt.value === value)?.label || value || '-';
}

function OrderMatchRow({ match, onSelect }) {
  const tc = SERVICE_TYPE_OPTIONS.find((opt) => opt.value === match.service_type);
  return (
    <button
      onClick={() => onSelect(match)}
      style={{
        display: 'flex', alignItems: 'center', gap: '0.9rem',
        width: '100%', textAlign: 'left', cursor: 'pointer',
        padding: '0.7rem 0.9rem', borderRadius: '10px',
        background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
        transition: 'background 0.15s, border-color 0.15s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; }}
    >
      <span style={{
        fontFamily: 'monospace', fontSize: '0.68rem', fontWeight: 700,
        color: 'rgba(255,255,255,0.5)', background: 'rgba(255,255,255,0.06)',
        borderRadius: '6px', padding: '3px 8px', flexShrink: 0,
      }}>
        {match.id.slice(0, 8)}
      </span>

      <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', color: 'rgba(255,255,255,0.75)', flex: 1 }}>
        <span>{match.created_at ? utcIsoToBogotaInputValue(match.created_at).slice(0, 10) : '-'}</span>
        <ArrowRight size={12} style={{ color: 'rgba(255,255,255,0.3)', flexShrink: 0 }} />
        <span style={{ color: match.delivered_at ? 'rgba(255,255,255,0.75)' : 'rgba(255,255,255,0.35)' }}>
          {match.delivered_at ? utcIsoToBogotaInputValue(match.delivered_at).slice(0, 10) : 'Sin entregar'}
        </span>
      </span>

      <span style={{
        fontSize: '0.62rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.03em',
        color: tc?.color || 'rgba(255,255,255,0.5)', background: tc?.bg || 'rgba(255,255,255,0.06)',
        borderRadius: '6px', padding: '3px 9px', whiteSpace: 'nowrap', flexShrink: 0,
      }}>
        {serviceTypeLabel(match.service_type)}
      </span>
    </button>
  );
}

function OrderMatchPicker({ matches, onSelect }) {
  return (
    <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', maxWidth: '560px' }}>
      <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.6)' }}>
        Esta placa tiene varias órdenes — elegí cuál corregir:
      </p>
      {matches.map((m) => (
        <OrderMatchRow key={m.id} match={m} onSelect={onSelect} />
      ))}
    </div>
  );
}

function OrderTab() {
  const o = useOrderQuickFix();
  return (
    <section className="glass p-6" style={sectionStyle}>
      <SearchBar onSearch={o.search} searching={o.searching}>
        <select aria-label="Buscar por" value={o.searchMode} onChange={(e) => o.setSearchMode(e.target.value)} style={inputStyle}>
          <option value="plate">Placa</option>
          <option value="order_id">ID de Orden</option>
        </select>
        <input
          aria-label="Valor de búsqueda de orden"
          placeholder={o.searchMode === 'plate' ? 'Placa' : 'ID de Orden'}
          value={o.searchValue}
          onChange={(e) => o.setSearchValue(e.target.value)}
          style={inputStyle}
        />
      </SearchBar>

      {o.matches && !o.found && <OrderMatchPicker matches={o.matches} onSelect={o.selectMatch} />}

      {o.found && (
        <div style={fieldGridStyle}>
          <Field label="Fecha de creación" type="datetime-local" value={o.form.created_at} onChange={(e) => o.setForm({ ...o.form, created_at: e.target.value })} />
          <Field label="Fecha de entrega" type="datetime-local" value={o.form.delivered_at} onChange={(e) => o.setForm({ ...o.form, delivered_at: e.target.value })} />
          <Field label="Kilometraje de orden" type="number" value={o.form.mileage_km} onChange={(e) => o.setForm({ ...o.form, mileage_km: e.target.value })} />
          <label style={labelStyle}>
            Tipo de servicio
            <select aria-label="Tipo de servicio" value={o.form.service_type} onChange={(e) => o.setForm({ ...o.form, service_type: e.target.value })} style={inputStyle}>
              {SERVICE_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
          <SaveButton onClick={o.save} saving={o.saving} />
        </div>
      )}

      {o.confirmState && (
        <ConfirmModal
          title="Confirmar eliminación de evento"
          message={o.confirmState.message}
          danger
          confirmLabel="Sí, eliminar y guardar"
          cancelLabel="Cancelar"
          onConfirm={o.confirmDelete}
          onCancel={o.cancelConfirm}
        />
      )}
    </section>
  );
}

function TabSwitcher({ tab, setTab }) {
  return (
    <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
      <button className={tab === 'vehicle' ? 'btn-primary' : 'btn'} onClick={() => setTab('vehicle')} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <Wand2 size={14} /> Vehículo
      </button>
      <button className={tab === 'order' ? 'btn-primary' : 'btn'} onClick={() => setTab('order')} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <Wand2 size={14} /> Orden
      </button>
    </div>
  );
}

function PageHeader() {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-title">
          Datos <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Rápidos</span>
        </h1>
        <p className="page-subtitle">Corrección puntual de datos de Vehículo y Orden — uso exclusivo de superadmin</p>
      </div>
    </header>
  );
}

export default function SuperadminDataPage() {
  const [tab, setTab] = useState('vehicle');
  return (
    <AdminLayout>
      <PageHeader />
      <TabSwitcher tab={tab} setTab={setTab} />
      {tab === 'vehicle' ? <VehicleTab /> : <OrderTab />}
    </AdminLayout>
  );
}
