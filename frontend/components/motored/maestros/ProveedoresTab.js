'use client';
/**
 * frontend/components/motored/maestros/ProveedoresTab.js
 *
 * Proveedores tab (sdd/motored-pedidos-cimientos, proposal §7.12/§4.1).
 * Mirrors `SucursalesTab.js`'s exact pattern (form/table/bulk-upload/
 * tooltips hooks) -- same shape, different fields. Built before
 * `ReferenciasTab.js` on purpose: a referencia needs an existing proveedor
 * to pick from.
 */
import { useEffect, useState } from 'react';
import {
  listMaestros,
  createMaestro,
  updateMaestro,
  deactivateMaestro,
} from '../../../lib/motored/api';
import BulkUploadModal from './BulkUploadModal';
import InfoTooltip from '../InfoTooltip';

const ENTIDAD_PLURAL = 'proveedores';
const ENTIDAD_SINGULAR = 'proveedor';

const emptyForm = {
  codigo: '', nombre: '', es_principal: false,
  dias_empaque_default: '', dias_transito_default: '',
};

function ProveedorForm({ form, setForm, editingId, onSubmit, onCancel }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Código
        <input value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} required />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Nombre
        <input value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        <span>
          Días empaque (por defecto)
          <InfoTooltip text="Días que tarda este proveedor en armar un pedido para envío. Se usa cuando una sucursal no tiene su propio valor cargado." />
        </span>
        <input
          value={form.dias_empaque_default}
          onChange={(e) => setForm({ ...form, dias_empaque_default: e.target.value })}
        />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        <span>
          Días tránsito (por defecto)
          <InfoTooltip text="Días que tarda un pedido en llegar desde este proveedor. Se usa cuando una sucursal no tiene su propio valor cargado." />
        </span>
        <input
          value={form.dias_transito_default}
          onChange={(e) => setForm({ ...form, dias_transito_default: e.target.value })}
        />
      </label>
      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        <input
          type="checkbox"
          style={{ width: 'auto', height: 'auto' }}
          checked={form.es_principal}
          onChange={(e) => setForm({ ...form, es_principal: e.target.checked })}
        />
        <span>
          Proveedor principal
          <InfoTooltip text="Marcá esto para HMCL, el proveedor principal de Motored. Los demás proveedores quedan sin marcar." />
        </span>
      </label>
      <button type="submit" className="motored-btn motored-btn-primary">{editingId ? 'Guardar cambios' : 'Crear proveedor'}</button>
      {editingId && (
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      )}
    </form>
  );
}

function ProveedoresTable({ proveedores, onEdit, onDeactivate }) {
  const handleDeactivateClick = (p) => {
    if (window.confirm(`¿Desactivar el proveedor "${p.nombre}"? No se elimina, queda marcado como inactivo.`)) {
      onDeactivate(p.id);
    }
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
      <thead>
        <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          <th style={{ padding: '0 12px 8px 0' }}>Código</th>
          <th style={{ padding: '0 12px 8px 0' }}>Nombre</th>
          <th style={{ padding: '0 12px 8px 0' }}>Principal</th>
          <th style={{ padding: '0 12px 8px 0' }}>Estado</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {proveedores.map((p) => (
          <tr key={p.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
            <td style={{ padding: '10px 12px 10px 0' }}>{p.codigo}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{p.nombre}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{p.es_principal ? 'Sí' : 'No'}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{p.activa ? 'Activo' : 'Inactivo'}</td>
            <td style={{ display: 'flex', gap: '1rem', padding: '10px 0' }}>
              <button type="button" className="motored-row-action" onClick={() => onEdit(p)}>Editar</button>
              {p.activa && (
                <button type="button" className="motored-row-action" onClick={() => handleDeactivateClick(p)}>Desactivar</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ProveedoresHeader({ onOpenBulk }) {
  return (
    <div
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '0.85rem 1rem', background: 'var(--motored-surface-alt, #f4f4f5)',
        border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: 'var(--motored-radius-md, 8px)',
      }}
    >
      <div>
        <h2 className="motored-h-seccion">Proveedores</h2>
        <p style={{ margin: '0.2rem 0 0', fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          ¿Tenés muchos proveedores para cargar de una vez? Subí un archivo CSV con "Carga masiva" en vez de crearlos uno por uno.
        </p>
      </div>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={onOpenBulk}>
        Carga masiva
      </button>
    </div>
  );
}

function useProveedores() {
  const [proveedores, setProveedores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setProveedores(await listMaestros(ENTIDAD_PLURAL));
    } catch (err) {
      setError(err.message || 'Error al cargar proveedores');
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
      setError(err.message || 'Error al guardar proveedor');
      return false;
    }
  };

  const deactivate = async (id) => {
    setError('');
    try {
      await deactivateMaestro(ENTIDAD_PLURAL, id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al desactivar proveedor');
    }
  };

  return { proveedores, loading, error, save, deactivate, reload: load };
}

function useProveedoresEditor(save) {
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);

  const startEdit = (p) => {
    setEditingId(p.id);
    setForm({
      codigo: p.codigo,
      nombre: p.nombre,
      es_principal: p.es_principal,
      dias_empaque_default: p.dias_empaque_default != null ? String(p.dias_empaque_default) : '',
      dias_transito_default: p.dias_transito_default != null ? String(p.dias_transito_default) : '',
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
        nombre: form.nombre,
        es_principal: form.es_principal,
        dias_empaque_default: form.dias_empaque_default ? Number(form.dias_empaque_default) : null,
        dias_transito_default: form.dias_transito_default ? Number(form.dias_transito_default) : null,
      },
      editingId
    );
    if (ok) cancelEdit();
  };

  return { form, setForm, editingId, startEdit, cancelEdit, handleSubmit };
}

export default function ProveedoresTab() {
  const { proveedores, loading, error, save, deactivate, reload } = useProveedores();
  const { form, setForm, editingId, startEdit, cancelEdit, handleSubmit } = useProveedoresEditor(save);
  const [showBulkModal, setShowBulkModal] = useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <ProveedoresHeader onOpenBulk={() => setShowBulkModal(true)} />

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}

      <ProveedorForm
        form={form}
        setForm={setForm}
        editingId={editingId}
        onSubmit={handleSubmit}
        onCancel={cancelEdit}
      />

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <ProveedoresTable proveedores={proveedores} onEdit={startEdit} onDeactivate={deactivate} />
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
