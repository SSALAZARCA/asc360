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
import { useEffect, useState } from 'react';
import {
  listMaestros,
  createMaestro,
  updateMaestro,
  deactivateMaestro,
} from '../../../lib/motored/api';
import BulkUploadModal from './BulkUploadModal';
import FormField from './FormField';
import InfoTooltip from '../InfoTooltip';

const ENTIDAD_PLURAL = 'sucursales';
const ENTIDAD_SINGULAR = 'sucursal';

const emptyForm = {
  nombre: '', sic: '', dias_seguridad: '2.5',
  dias_empaque: '', dias_transito: '', bodega_principal: '',
  departamento: '', ciudad: '', fecha_apertura: '',
};

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

function SucursalForm({ form, setForm, editingId, onSubmit, onCancel }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      {FIELDS.map((f) => (
        <FormField
          key={f.key}
          label={f.label}
          tooltip={f.tooltip}
          required={f.required}
          type={f.type}
          placeholder={f.placeholder}
          value={form[f.key]}
          onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
        />
      ))}
      <button type="submit" className="motored-btn motored-btn-primary">{editingId ? 'Guardar cambios' : 'Crear sucursal'}</button>
      {editingId && (
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      )}
    </form>
  );
}

function SucursalesTable({ sucursales, onEdit, onDeactivate }) {
  const handleDeactivateClick = (s) => {
    if (window.confirm(`¿Desactivar la sucursal "${s.nombre}"? No se elimina, queda marcada como inactiva.`)) {
      onDeactivate(s.id);
    }
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
      <thead>
        <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          <th style={{ padding: '0 12px 8px 0' }}>Nombre</th>
          <th style={{ padding: '0 12px 8px 0' }}>
            SIC
            <InfoTooltip text="Código con el que el proveedor (HMCL) identifica esta sucursal en sus sistemas." />
          </th>
          <th style={{ padding: '0 12px 8px 0' }}>
            Días seguridad
            <InfoTooltip text="Colchón de días extra sobre el tiempo normal de reposición, para cubrir imprevistos. Por defecto 2.5 días." />
          </th>
          <th style={{ padding: '0 12px 8px 0' }}>
            Días empaque
            <InfoTooltip text="Días propios de esta sucursal para armar un pedido (distinto del valor por defecto del proveedor)." />
          </th>
          <th style={{ padding: '0 12px 8px 0' }}>
            Días tránsito
            <InfoTooltip text="Días propios de esta sucursal para que le llegue un pedido (distinto del valor por defecto del proveedor)." />
          </th>
          <th style={{ padding: '0 12px 8px 0' }}>Bodega principal</th>
          <th style={{ padding: '0 12px 8px 0' }}>Departamento</th>
          <th style={{ padding: '0 12px 8px 0' }}>Ciudad</th>
          <th style={{ padding: '0 12px 8px 0' }}>Fecha apertura</th>
          <th style={{ padding: '0 12px 8px 0' }}>Estado</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {sucursales.map((s) => (
          <tr key={s.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.nombre}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.sic || <em>sin SIC</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.dias_seguridad}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.dias_empaque ?? <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.dias_transito ?? <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.bodega_principal || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.departamento || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.ciudad || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.fecha_apertura || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{s.activa ? 'Activa' : 'Inactiva'}</td>
            <td style={{ display: 'flex', gap: '1rem', padding: '10px 0' }}>
              {/* Nunca un botón rojo dentro de una tabla (regla del sistema
              real) -- acciones de fila usan .motored-row-action, texto
              neutro, no el rojo destructivo. */}
              <button type="button" className="motored-row-action" onClick={() => onEdit(s)}>Editar</button>
              {s.activa && (
                <button type="button" className="motored-row-action" onClick={() => handleDeactivateClick(s)}>Desactivar</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SucursalesHeader({ onOpenBulk }) {
  return (
    <div
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '0.85rem 1rem', background: 'var(--motored-surface-alt, #f4f4f5)',
        border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: 'var(--motored-radius-md, 8px)',
      }}
    >
      <div>
        <h2 className="motored-h-seccion">Sucursales</h2>
        <p style={{ margin: '0.2rem 0 0', fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          ¿Tenés muchas sucursales para cargar de una vez? Subí un archivo CSV con "Carga masiva" en vez de crearlas una por una.
        </p>
      </div>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={onOpenBulk}>
        Carga masiva
      </button>
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

  return { sucursales, loading, error, save, deactivate, reload: load };
}

function useSucursalesEditor(save) {
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);

  const startEdit = (s) => {
    setEditingId(s.id);
    setForm({
      nombre: s.nombre,
      sic: s.sic || '',
      dias_seguridad: String(s.dias_seguridad),
      dias_empaque: s.dias_empaque != null ? String(s.dias_empaque) : '',
      dias_transito: s.dias_transito != null ? String(s.dias_transito) : '',
      bodega_principal: s.bodega_principal || '',
      departamento: s.departamento || '',
      ciudad: s.ciudad || '',
      fecha_apertura: s.fecha_apertura || '',
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const ok = await save(
      {
        nombre: form.nombre,
        sic: form.sic || null,
        dias_seguridad: form.dias_seguridad,
        dias_empaque: form.dias_empaque ? Number(form.dias_empaque) : null,
        dias_transito: form.dias_transito ? Number(form.dias_transito) : null,
        bodega_principal: form.bodega_principal || null,
        departamento: form.departamento || null,
        ciudad: form.ciudad || null,
        fecha_apertura: form.fecha_apertura || null,
      },
      editingId
    );
    if (ok) cancelEdit();
  };

  return { form, setForm, editingId, startEdit, cancelEdit, handleSubmit };
}

export default function SucursalesTab() {
  const { sucursales, loading, error, save, deactivate, reload } = useSucursales();
  const { form, setForm, editingId, startEdit, cancelEdit, handleSubmit } = useSucursalesEditor(save);
  const [showBulkModal, setShowBulkModal] = useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <SucursalesHeader onOpenBulk={() => setShowBulkModal(true)} />

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}

      <SucursalForm
        form={form}
        setForm={setForm}
        editingId={editingId}
        onSubmit={handleSubmit}
        onCancel={cancelEdit}
      />

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <SucursalesTable sucursales={sucursales} onEdit={startEdit} onDeactivate={deactivate} />
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
