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

const ENTIDAD_PLURAL = 'sucursales';
const ENTIDAD_SINGULAR = 'sucursal';

const emptyForm = { nombre: '', sic: '', dias_seguridad: '2.5' };

function SucursalForm({ form, setForm, editingId, onSubmit, onCancel }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Nombre
        <input
          value={form.nombre}
          onChange={(e) => setForm({ ...form, nombre: e.target.value })}
          required
        />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        SIC
        <input value={form.sic} onChange={(e) => setForm({ ...form, sic: e.target.value })} />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Días seguridad
        <input
          value={form.dias_seguridad}
          onChange={(e) => setForm({ ...form, dias_seguridad: e.target.value })}
        />
      </label>
      <button type="submit">{editingId ? 'Guardar cambios' : 'Crear sucursal'}</button>
      {editingId && (
        <button type="button" onClick={onCancel}>
          Cancelar
        </button>
      )}
    </form>
  );
}

function SucursalesTable({ sucursales, onEdit, onDeactivate }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
      <thead>
        <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          <th>Nombre</th>
          <th>SIC</th>
          <th>Días seguridad</th>
          <th>Estado</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {sucursales.map((s) => (
          <tr key={s.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
            <td>{s.nombre}</td>
            <td>{s.sic || <em>sin SIC</em>}</td>
            <td>{s.dias_seguridad}</td>
            <td>{s.activa ? 'Activa' : 'Inactiva'}</td>
            <td style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" onClick={() => onEdit(s)}>Editar</button>
              {s.activa && (
                <button type="button" onClick={() => onDeactivate(s.id)}>Desactivar</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
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

export default function SucursalesTab() {
  const { sucursales, loading, error, save, deactivate, reload } = useSucursales();
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [showBulkModal, setShowBulkModal] = useState(false);

  const startEdit = (s) => {
    setEditingId(s.id);
    setForm({ nombre: s.nombre, sic: s.sic || '', dias_seguridad: String(s.dias_seguridad) });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const ok = await save(
      { nombre: form.nombre, sic: form.sic || null, dias_seguridad: form.dias_seguridad },
      editingId
    );
    if (ok) cancelEdit();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: 'var(--motored-text, #1a1a18)' }}>
          Sucursales
        </h2>
        <button type="button" onClick={() => setShowBulkModal(true)}>
          Carga masiva
        </button>
      </div>

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
