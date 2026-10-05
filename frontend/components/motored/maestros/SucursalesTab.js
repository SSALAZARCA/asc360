'use client';
/**
 * frontend/components/motored/maestros/SucursalesTab.js
 *
 * Working masters screen for ONE entity end-to-end (sdd/motored-pedidos-
 * cimientos, Phase 6, task 6.2/6.3) -- `sucursal` chosen over `proveedor`
 * because its fields (`nombre`, `sic`, `dias_seguridad`) are the simplest
 * to demo list/create/update/deactivate against the real
 * `backend/app/motored/api/maestros.py` contract (plural entidad key
 * `sucursales`).
 *
 * Deactivate is ALWAYS soft-delete (`activa=false`) -- the DELETE call maps
 * to `deactivateMaestro`, never a real removal, matching the backend's own
 * "no endpoint offers hard delete" guarantee.
 */
import MotoredTableScroll from '../MotoredTableScroll';
import MotoredIconAction from '../MotoredIconAction';
import { Fragment, useEffect, useRef, useState } from 'react';
import {
  listMaestros,
  createMaestro,
  updateMaestro,
  deactivateMaestro,
  reactivateMaestro,
} from '../../../lib/motored/api';
import BulkUploadModal from './BulkUploadModal';
import FormField from './FormField';
import BodegasSecundariasEditor from './BodegasSecundariasEditor';
import InfoTooltip from '../InfoTooltip';
import SucursalesContadores from './SucursalesContadores';

const ENTIDAD_PLURAL = 'sucursales';
const ENTIDAD_SINGULAR = 'sucursal';

const emptyForm = {
  nombre: '', codigo_co: '', sic: '', dias_seguridad: '2.5',
  dias_empaque: '', dias_transito: '', bodega_principal: '',
  departamento: '', ciudad: '', fecha_apertura: '', principal_id: '',
  bodegas_secundarias: [],
};

// Without an explicit color the option text is invisible in the dark theme.
const optionStyle = { color: '#1a1a18' };

const PRINCIPAL_TOOLTIP = 'Tienda bajo la que opera este punto. El punto conserva sus propios datos, pero su pedido, ventas, inventario, presupuestos e indicadores se suman a los de la tienda principal: solo la principal recibe pedido. Dejá "Ninguna" si este punto es una tienda principal.';

const principalLabelStyle = {
  display: 'flex', flexDirection: 'column', fontSize: '0.7rem',
  color: 'var(--motored-text-muted, #5a5a5a)', minWidth: '180px',
};

// Stores that may be a principal: never the store itself, and never a store
// that is already associated to another one (depth 1).
function principalesPosibles(sucursales, editingId) {
  return sucursales.filter((s) => s.id !== editingId && !s.principal_id);
}

function asociadasDe(sucursales, id) {
  return sucursales.filter((s) => s.principal_id === id);
}

function PrincipalSelect({ form, setForm, sucursales, editingId }) {
  const tieneAsociadas = editingId && asociadasDe(sucursales, editingId).length > 0;
  return (
    <label style={principalLabelStyle}>
      <span>
        Tienda principal
        <InfoTooltip text={PRINCIPAL_TOOLTIP} />
      </span>
      <select
        value={form.principal_id}
        disabled={Boolean(tieneAsociadas)}
        title={tieneAsociadas ? 'Esta tienda ya tiene puntos asociados: no puede asociarse a otra.' : undefined}
        onChange={(e) => setForm({ ...form, principal_id: e.target.value })}
      >
        <option value="" style={optionStyle}>— Ninguna (es tienda principal) —</option>
        {principalesPosibles(sucursales, editingId).map((s) => (
          <option key={s.id} value={s.id} style={optionStyle}>
            {s.nombre}{s.activa === false ? ' (inactiva)' : ''}
          </option>
        ))}
      </select>
    </label>
  );
}

const CODIGO_CO_TOOLTIP = 'Código del centro de operación en el ERP (ej: E05). Cada C.O. es una tienda distinta.';

const codigoCoLabelStyle = {
  display: 'flex', flexDirection: 'column', fontSize: '0.7rem',
  color: 'var(--motored-text-muted, #5a5a5a)',
};

// Same rule as the backend's CODIGO_CO_PATRON (one letter, two digits); the
// form checks it before saving, the backend has the final word.
const CODIGO_CO_PATRON = /^[A-Z][0-9]{2}$/;
const CODIGO_CO_OBLIGATORIO = 'El Código C.O. es obligatorio: identifica a la sucursal.';
const CODIGO_CO_NO_SE_BORRA = 'El Código C.O. no se puede borrar: identifica a la sucursal.';

// The C.O. identifies the store, so it is required, except when editing a
// legacy store that has none yet (it still edits without one). The input
// uses aria-required, not required: the browser's own bubble would hide
// this Spanish message.
function errorCodigoCo(codigo, editingId, codigoGuardado) {
  if (!codigo) {
    if (!editingId) return CODIGO_CO_OBLIGATORIO;
    return codigoGuardado ? CODIGO_CO_NO_SE_BORRA : '';
  }
  if (CODIGO_CO_PATRON.test(codigo)) return '';
  return `Código C.O. '${codigo}' no es válido: debe ser una letra seguida de dos números (ej: E05).`;
}

function CodigoCoField({ form, setForm, required }) {
  return (
    <label style={codigoCoLabelStyle}>
      <span>
        Código C.O. <span aria-hidden="true">*</span>
        <InfoTooltip text={CODIGO_CO_TOOLTIP} />
      </span>
      <input
        type="text"
        value={form.codigo_co}
        aria-required={required}
        maxLength={3}
        pattern="[A-Za-z][0-9]{2}"
        title="Una letra y dos números (ej: E05)"
        placeholder="ej: E05"
        style={{ width: '6rem' }}
        onChange={(e) => setForm({ ...form, codigo_co: e.target.value.trim().toUpperCase() })}
      />
    </label>
  );
}

const FIELDS = [
  { key: 'nombre', label: 'Nombre', required: true },
  { key: 'sic', label: 'SIC', tooltip: 'Código con el que el proveedor (HMCL) identifica esta sucursal en sus sistemas. Sin este dato, el sistema no puede cruzar automáticamente las facturas y envíos que llegan de HMCL con la sucursal correcta.' },
  { key: 'dias_seguridad', label: 'Días seguridad', tooltip: 'Colchón de días extra que se suma al tiempo normal de reposición (empaque + transporte) para cubrir imprevistos como demoras o picos de demanda. Por defecto 2.5 días.' },
  { key: 'dias_empaque', label: 'Días empaque', tooltip: 'Días propios de ESTA sucursal para armar un pedido. Es distinto del valor por defecto del proveedor: si lo dejás vacío, el cálculo usa ese valor por defecto en su lugar.' },
  { key: 'dias_transito', label: 'Días tránsito', tooltip: 'Días propios de ESTA sucursal para que le llegue un pedido. Es distinto del valor por defecto del proveedor: si lo dejás vacío, el cálculo usa ese valor por defecto en su lugar.' },
  { key: 'bodega_principal', label: 'Bodega principal', tooltip: 'Código de la bodega principal de esta sucursal (ej: BE051).', placeholder: 'ej: BE051' },
  { key: 'departamento', label: 'Departamento', tooltip: 'Departamento donde queda esta sucursal.' },
  { key: 'ciudad', label: 'Ciudad', tooltip: 'Ciudad donde queda esta sucursal.' },
  { key: 'fecha_apertura', label: 'Fecha de apertura', tooltip: 'Fecha en que la sucursal abrió operaciones. Se usa más adelante para no contar meses en los que todavía no existía.', type: 'date' },
];

function SucursalFormField({ f, form, setForm }) {
  return (
    <FormField
      label={f.label}
      tooltip={f.tooltip}
      required={f.required}
      type={f.type}
      placeholder={f.placeholder}
      value={form[f.key]}
      onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
    />
  );
}

// The C.O. goes first: it identifies the store. The name may change.
function SucursalForm({ form, setForm, editingId, codigoRequerido, onSubmit, onCancel, sucursales }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <CodigoCoField form={form} setForm={setForm} required={codigoRequerido} />
      {FIELDS.map((f) => (
        <Fragment key={f.key}>
          <SucursalFormField f={f} form={form} setForm={setForm} />
          {/* The secondaries sit next to the principal they chain to. */}
          {f.key === 'bodega_principal' && (
            <BodegasSecundariasEditor
              value={form.bodegas_secundarias}
              onChange={(codigos) => setForm((actual) => ({ ...actual, bodegas_secundarias: codigos }))}
            />
          )}
        </Fragment>
      ))}
      <PrincipalSelect form={form} setForm={setForm} sucursales={sucursales} editingId={editingId} />
      <button type="submit" className="motored-btn motored-btn-primary">{editingId ? 'Guardar cambios' : 'Crear sucursal'}</button>
      {editingId && (
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      )}
    </form>
  );
}

// SIC and the three "Días" values are hidden from the table (business
// decision) but stay as data and as form fields (FIELDS above).
function RelacionPrincipal({ s, sucursales }) {
  if (s.principal_id) {
    const principal = sucursales.find((p) => p.id === s.principal_id);
    return <span>Asociada a: {principal ? principal.nombre : '—'}</span>;
  }
  const total = asociadasDe(sucursales, s.id).length;
  if (total === 0) return <em>—</em>;
  return <span>Principal de {total} {total === 1 ? 'punto' : 'puntos'}</span>;
}

const TABLE_COLUMNS = [
  { label: 'Nombre', cell: (s) => s.nombre },
  { label: 'Código C.O.', cell: (s) => s.codigo_co || <em>—</em> },
  { label: 'Tienda principal', cell: (s, todas) => <RelacionPrincipal s={s} sucursales={todas} /> },
  { label: 'Bodega principal', cell: (s) => s.bodega_principal || <em>—</em> },
  {
    label: 'Bodegas secundarias',
    cell: (s) => (s.bodegas_secundarias && s.bodegas_secundarias.length ? s.bodegas_secundarias.join(', ') : <em>—</em>),
  },
  { label: 'Departamento', cell: (s) => s.departamento || <em>—</em> },
  { label: 'Ciudad', cell: (s) => s.ciudad || <em>—</em> },
  { label: 'Fecha apertura', cell: (s) => s.fecha_apertura || <em>—</em> },
  { label: 'Estado', cell: (s) => (s.activa ? 'Activa' : 'Inactiva') },
];

const thStyle = { padding: '0 12px 8px 0' };
const tdStyle = { padding: '10px 12px 10px 0' };

function SucursalRowActions({ s, onEdit, onDeactivate, onReactivate }) {
  const confirmThen = (verb, done) => () => {
    const msg = verb === 'Desactivar'
      ? `¿Desactivar la sucursal "${s.nombre}"? No se elimina, queda marcada como inactiva.`
      : `¿Reactivar la sucursal "${s.nombre}"? Queda marcada como activa.`;
    if (window.confirm(msg)) done(s.id);
  };
  return (
    <td style={{ display: 'flex', gap: '1rem', padding: '10px 0' }}>
      {/* Nunca un botón rojo dentro de una tabla (regla del sistema
      real) -- acciones de fila usan MotoredIconAction, icono
      neutro, no el rojo destructivo. */}
      <MotoredIconAction action="Editar" onClick={() => onEdit(s)} />
      {s.activa ? (
        <MotoredIconAction action="Desactivar" onClick={confirmThen('Desactivar', onDeactivate)} />
      ) : (
        <MotoredIconAction action="Reactivar" onClick={confirmThen('Reactivar', onReactivate)} />
      )}
    </td>
  );
}

function SucursalesTable({ sucursales, onEdit, onDeactivate, onReactivate }) {
  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
            {TABLE_COLUMNS.map(({ label }) => (
              <th key={label} style={thStyle}>{label}</th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {sucursales.map((s) => (
            <tr key={s.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
              {TABLE_COLUMNS.map(({ label, cell }) => (
                <td key={label} style={tdStyle}>{cell(s, sucursales)}</td>
              ))}
              <SucursalRowActions s={s} onEdit={onEdit} onDeactivate={onDeactivate} onReactivate={onReactivate} />
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}

function SucursalesHeader({ onOpenBulk, sucursales, loading }) {
  return (
    <div
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem',
        padding: '0.85rem 1rem', background: 'var(--motored-surface-alt, #f4f4f5)',
        border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: 'var(--motored-radius-md, 8px)',
      }}
    >
      <div style={{ flex: '1 1 260px', minWidth: 0 }}>
        <h2 className="motored-h-seccion">Sucursales</h2>
        <p style={{ margin: '0.2rem 0 0', fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          ¿Tenés muchas sucursales para cargar de una vez? Subí un archivo CSV con "Carga masiva" en vez de crearlas una por una.
        </p>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
        <SucursalesContadores sucursales={sucursales} loading={loading} />
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onOpenBulk}>
          Carga masiva
        </button>
      </div>
    </div>
  );
}

function useSucursales() {
  const [sucursales, setSucursales] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await listMaestros(ENTIDAD_PLURAL);
      setSucursales(data);
    } catch (err) {
      setError(err.message || 'Error al cargar sucursales');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async (payload, editingId) => {
    setError('');
    try {
      if (editingId) {
        await updateMaestro(ENTIDAD_PLURAL, editingId, payload);
      } else {
        await createMaestro(ENTIDAD_PLURAL, payload);
      }
      await load();
      return true;
    } catch (err) {
      setError(err.message || 'Error al guardar sucursal');
      return false;
    }
  };

  const deactivate = async (id) => {
    setError('');
    try {
      await deactivateMaestro(ENTIDAD_PLURAL, id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al desactivar sucursal');
    }
  };

  const reactivate = async (id) => {
    setError('');
    try {
      await reactivateMaestro(ENTIDAD_PLURAL, id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al reactivar sucursal');
    }
  };

  return { sucursales, loading, error, save, deactivate, reactivate, reload: load };
}

function useSucursalesEditor(save) {
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [codigoGuardado, setCodigoGuardado] = useState('');
  const [formError, setFormError] = useState('');

  const startEdit = (s) => {
    setEditingId(s.id);
    setCodigoGuardado(s.codigo_co || '');
    setFormError('');
    setForm({
      nombre: s.nombre,
      codigo_co: s.codigo_co || '',
      sic: s.sic || '',
      dias_seguridad: String(s.dias_seguridad),
      dias_empaque: s.dias_empaque != null ? String(s.dias_empaque) : '',
      dias_transito: s.dias_transito != null ? String(s.dias_transito) : '',
      bodega_principal: s.bodega_principal || '',
      departamento: s.departamento || '',
      ciudad: s.ciudad || '',
      fecha_apertura: s.fecha_apertura || '',
      principal_id: s.principal_id || '',
      bodegas_secundarias: s.bodegas_secundarias || [],
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setCodigoGuardado('');
    setFormError('');
    setForm(emptyForm);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const codigo = form.codigo_co.trim().toUpperCase();
    const errorCodigo = errorCodigoCo(codigo, editingId, codigoGuardado);
    setFormError(errorCodigo);
    if (errorCodigo) return;
    const ok = await save(
      {
        nombre: form.nombre,
        codigo_co: codigo || null,
        sic: form.sic || null,
        dias_seguridad: form.dias_seguridad,
        dias_empaque: form.dias_empaque ? Number(form.dias_empaque) : null,
        dias_transito: form.dias_transito ? Number(form.dias_transito) : null,
        // Same normalization as the secondaries, so a swap matches codes.
        bodega_principal: form.bodega_principal.trim().toUpperCase() || null,
        departamento: form.departamento || null,
        ciudad: form.ciudad || null,
        fecha_apertura: form.fecha_apertura || null,
        principal_id: form.principal_id || null,
        // The final set: the backend links, releases and validates it.
        bodegas_secundarias: form.bodegas_secundarias,
      },
      editingId
    );
    if (ok) cancelEdit();
  };

  const codigoRequerido = !editingId || Boolean(codigoGuardado);
  return { form, setForm, editingId, codigoRequerido, formError, startEdit, cancelEdit, handleSubmit };
}

export default function SucursalesTab() {
  const { sucursales, loading, error, save, deactivate, reactivate, reload } = useSucursales();
  const {
    form, setForm, editingId, codigoRequerido, formError, startEdit, cancelEdit, handleSubmit,
  } = useSucursalesEditor(save);
  const [showBulkModal, setShowBulkModal] = useState(false);
  // The form sits above a long table: editing a row far down, or a failed
  // save, must bring the form and its message into view.
  const formRef = useRef(null);
  const mostrarFormulario = () => formRef.current?.scrollIntoView?.(
    { behavior: 'smooth', block: 'start' }
  );
  const editar = (s) => {
    startEdit(s);
    mostrarFormulario();
  };
  const nombreEditado = sucursales.find((s) => s.id === editingId)?.nombre;

  useEffect(() => {
    if (error || formError) mostrarFormulario();
  }, [error, formError]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <SucursalesHeader sucursales={sucursales} loading={loading} onOpenBulk={() => setShowBulkModal(true)} />

      <div ref={formRef} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {editingId && (
        <p style={{ fontSize: '0.85rem', fontWeight: 600 }}>
          Editando: {nombreEditado || 'sucursal'}
        </p>
      )}

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}

      {formError && <p role="alert" style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{formError}</p>}

      <SucursalForm
        form={form}
        setForm={setForm}
        editingId={editingId}
        codigoRequerido={codigoRequerido}
        onSubmit={handleSubmit}
        onCancel={cancelEdit}
        sucursales={sucursales}
      />
      </div>

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <SucursalesTable sucursales={sucursales} onEdit={editar} onDeactivate={deactivate} onReactivate={reactivate} />
      )}

      {showBulkModal && (
        <BulkUploadModal
          entidad={ENTIDAD_SINGULAR}
          onClose={() => setShowBulkModal(false)}
          onSuccess={() => {
            setShowBulkModal(false);
            reload();
          }}
        />
      )}
    </div>
  );
}
