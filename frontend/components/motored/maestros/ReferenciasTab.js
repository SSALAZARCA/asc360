'use client';
/**
 * frontend/components/motored/maestros/ReferenciasTab.js
 *
 * Referencias tab (sdd/motored-pedidos-cimientos, proposal §7.12/§4.1/§5.8)
 * -- the catalog of ~13,200 HMCL parts. Mirrors `SucursalesTab.js`'s
 * pattern, with two real foreign keys rendered as dropdowns (never free
 * text, matching `BodegasTab.js`'s precedent):
 * - `proveedor_id` (required) -- fed by the real proveedores list. This is
 *   why Proveedores had to exist before this tab.
 * - `sustituida_por` (optional) -- fed by the referencias list itself
 *   (excluding the row being edited); setting it deactivates this
 *   referencia server-side (`services/maestros.py::update_referencia`).
 *
 * `unidad_empaque` and the 3-price split (`precio_normal` vs. `precio_venta`
 * /`precio_publico`) are exactly the two locked business rules from the
 * proposal most likely to confuse a business user, so both get a real
 * InfoTooltip, not just a label.
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

const ENTIDAD_PLURAL = 'referencias';
const ENTIDAD_SINGULAR = 'referencia';

const emptyForm = {
  codigo: '', proveedor_id: '', nombre: '', linea_comercial: '', unidad_empaque: '1',
  precio_normal: '', precio_venta: '', precio_publico: '', sustituida_por: '',
};

const PRECIO_FIELDS = [
  { key: 'precio_normal', label: 'Precio normal', help: 'Este es el precio que usa el sistema para calcular el valor de los pedidos. Los otros dos precios (venta y público) son solo informativos.' },
  { key: 'precio_venta', label: 'Precio venta', help: 'Informativo únicamente — no se usa para calcular el valor de los pedidos.' },
  { key: 'precio_publico', label: 'Precio público', help: 'Informativo únicamente — no se usa para calcular el valor de los pedidos.' },
];

function PrecioFields({ form, setForm }) {
  return PRECIO_FIELDS.map(({ key, label, help }) => (
    <label key={key} style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
      <span>
        {label}
        <InfoTooltip text={help} />
      </span>
      <input value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </label>
  ));
}

function ReferenciaForm({ form, setForm, editingId, proveedores, referenciasParaSustituir, onSubmit, onCancel }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <FormField label="Código" required value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} />
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Proveedor
        <select value={form.proveedor_id} onChange={(e) => setForm({ ...form, proveedor_id: e.target.value })} required>
          <option value="" style={{ color: '#1a1a18' }}>— Elegir —</option>
          {proveedores.map((p) => (
            <option key={p.id} value={p.id} style={{ color: '#1a1a18' }}>{p.nombre}</option>
          ))}
        </select>
      </label>
      <FormField label="Nombre" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
      <FormField
        label="Línea comercial"
        tooltip="Ej: REPUESTOS, ACCESORIOS. No es una lista cerrada, se escribe como texto libre."
        value={form.linea_comercial}
        onChange={(e) => setForm({ ...form, linea_comercial: e.target.value })}
      />
      <FormField
        label="Unidad de empaque"
        tooltip="Cuántas unidades vienen por paquete del proveedor. Nunca puede ser 0: si lo dejás vacío o en 0, el sistema lo corrige automáticamente a 1 y lo marca como advertencia en el tablero de salud."
        value={form.unidad_empaque}
        onChange={(e) => setForm({ ...form, unidad_empaque: e.target.value })}
      />
      <PrecioFields form={form} setForm={setForm} />
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        <span>
          Sustituida por
          <InfoTooltip text="Si esta referencia fue reemplazada por otra, elegila acá. Al guardar, esta referencia queda desactivada automáticamente." />
        </span>
        <select value={form.sustituida_por} onChange={(e) => setForm({ ...form, sustituida_por: e.target.value })}>
          <option value="" style={{ color: '#1a1a18' }}>— No aplica —</option>
          {referenciasParaSustituir.map((r) => (
            <option key={r.id} value={r.id} style={{ color: '#1a1a18' }}>{r.codigo}</option>
          ))}
        </select>
      </label>
      <button type="submit" className="motored-btn motored-btn-primary">{editingId ? 'Guardar cambios' : 'Crear referencia'}</button>
      {editingId && (
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      )}
    </form>
  );
}

function ReferenciasTable({ referencias, proveedoresPorId, onEdit, onDeactivate }) {
  const handleDeactivateClick = (r) => {
    if (window.confirm(`¿Desactivar la referencia "${r.codigo}"? No se elimina, queda marcada como inactiva.`)) {
      onDeactivate(r.id);
    }
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
      <thead>
        <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          <th style={{ padding: '0 12px 8px 0' }}>Código</th>
          <th style={{ padding: '0 12px 8px 0' }}>Nombre</th>
          <th style={{ padding: '0 12px 8px 0' }}>Proveedor</th>
          <th style={{ padding: '0 12px 8px 0' }}>Línea comercial</th>
          <th style={{ padding: '0 12px 8px 0' }}>Unidad empaque</th>
          <th style={{ padding: '0 12px 8px 0' }}>Precio normal</th>
          <th style={{ padding: '0 12px 8px 0' }}>Estado</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {referencias.map((r) => (
          <tr key={r.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
            <td style={{ padding: '10px 12px 10px 0' }}>{r.codigo}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{r.nombre || <em>sin nombre</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{proveedoresPorId[r.proveedor_id] || <em>desconocido</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{r.linea_comercial || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>
              {r.unidad_empaque}
              {r.unidad_empaque_advertencia && (
                <span style={{ marginLeft: '0.35rem', color: 'var(--motored-warning, #d97706)', fontSize: '0.7rem' }}>(corregida)</span>
              )}
            </td>
            <td style={{ padding: '10px 12px 10px 0' }}>{r.precio_normal != null ? r.precio_normal : <em>sin precio</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{r.activa ? 'Activa' : 'Inactiva'}</td>
            <td style={{ display: 'flex', gap: '1rem', padding: '10px 0' }}>
              <button type="button" className="motored-row-action" onClick={() => onEdit(r)}>Editar</button>
              {r.activa && (
                <button type="button" className="motored-row-action" onClick={() => handleDeactivateClick(r)}>Desactivar</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ReferenciasHeader({ onOpenBulk }) {
  return (
    <div
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '0.85rem 1rem', background: 'var(--motored-surface-alt, #f4f4f5)',
        border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: 'var(--motored-radius-md, 8px)',
      }}
    >
      <div>
        <h2 className="motored-h-seccion">Referencias</h2>
        <p style={{ margin: '0.2rem 0 0', fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          El catálogo de repuestos. ¿Tenés muchas referencias para cargar de una vez? Subí un archivo CSV con "Carga masiva" en vez de crearlas una por una.
        </p>
      </div>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={onOpenBulk}>
        Carga masiva
      </button>
    </div>
  );
}

function useProveedoresOptions() {
  const [proveedores, setProveedores] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    listMaestros('proveedores')
      .then(setProveedores)
      .catch((err) => setError(err.message || 'No se pudo cargar la lista de proveedores'));
  }, []);
  const porId = Object.fromEntries(proveedores.map((p) => [p.id, p.nombre]));
  return { proveedores, proveedoresPorId: porId, proveedoresError: error };
}

function useReferencias() {
  const [referencias, setReferencias] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setReferencias(await listMaestros(ENTIDAD_PLURAL));
    } catch (err) {
      setError(err.message || 'Error al cargar referencias');
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
      setError(err.message || 'Error al guardar referencia');
      return false;
    }
  };

  const deactivate = async (id) => {
    setError('');
    try {
      await deactivateMaestro(ENTIDAD_PLURAL, id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al desactivar referencia');
    }
  };

  return { referencias, loading, error, save, deactivate, reload: load };
}

function useReferenciasEditor(save) {
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);

  const startEdit = (r) => {
    setEditingId(r.id);
    setForm({
      codigo: r.codigo,
      proveedor_id: r.proveedor_id,
      nombre: r.nombre || '',
      linea_comercial: r.linea_comercial || '',
      unidad_empaque: String(r.unidad_empaque),
      precio_normal: r.precio_normal != null ? String(r.precio_normal) : '',
      precio_venta: r.precio_venta != null ? String(r.precio_venta) : '',
      precio_publico: r.precio_publico != null ? String(r.precio_publico) : '',
      sustituida_por: r.sustituida_por || '',
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
        codigo: form.codigo,
        proveedor_id: form.proveedor_id,
        nombre: form.nombre || null,
        linea_comercial: form.linea_comercial || null,
        unidad_empaque: form.unidad_empaque ? Number(form.unidad_empaque) : null,
        precio_normal: form.precio_normal ? Number(form.precio_normal) : null,
        precio_venta: form.precio_venta ? Number(form.precio_venta) : null,
        precio_publico: form.precio_publico ? Number(form.precio_publico) : null,
        sustituida_por: form.sustituida_por || null,
      },
      editingId
    );
    if (ok) cancelEdit();
  };

  return { form, setForm, editingId, startEdit, cancelEdit, handleSubmit };
}

export default function ReferenciasTab() {
  const { referencias, loading, error, save, deactivate, reload } = useReferencias();
  const { form, setForm, editingId, startEdit, cancelEdit, handleSubmit } = useReferenciasEditor(save);
  const { proveedores, proveedoresPorId, proveedoresError } = useProveedoresOptions();
  const [showBulkModal, setShowBulkModal] = useState(false);

  const referenciasParaSustituir = referencias.filter((r) => r.id !== editingId);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <ReferenciasHeader onOpenBulk={() => setShowBulkModal(true)} />

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}
      {proveedoresError && (
        <p style={{ color: 'var(--motored-warning, #d97706)', fontSize: '0.8rem' }}>
          No se pudo cargar la lista de proveedores para el desplegable ({proveedoresError}).
        </p>
      )}

      <ReferenciaForm
        form={form}
        setForm={setForm}
        editingId={editingId}
        proveedores={proveedores}
        referenciasParaSustituir={referenciasParaSustituir}
        onSubmit={handleSubmit}
        onCancel={cancelEdit}
      />

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <ReferenciasTable referencias={referencias} proveedoresPorId={proveedoresPorId} onEdit={startEdit} onDeactivate={deactivate} />
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
