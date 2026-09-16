'use client';
/**
 * frontend/components/motored/maestros/BodegasTab.js
 *
 * Bodegas tab (sdd/motored-pedidos-cimientos, proposal §7.12/§4.1). Mirrors
 * `SucursalesTab.js`'s exact pattern (form/table/bulk-upload/tooltips
 * hooks) -- same shape, different fields:
 * - `sucursal_id` is a REAL foreign key (`backend/app/motored/models/
 *   bodega.py`) -- rendered as a dropdown fed by the real sucursales list,
 *   never a free-text field a user could typo.
 * - `bodega_principal` is plain text (a bodega CODE, e.g. "BA061"), NOT a
 *   foreign key in Fase 1 -- the model's own docstring is explicit that
 *   consolidation resolution is a later phase's concern.
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

const ENTIDAD_PLURAL = 'bodegas';
const ENTIDAD_SINGULAR = 'bodega';

const emptyForm = { codigo: '', descripcion: '', sucursal_id: '', bodega_principal: '' };

function BodegaForm({ form, setForm, editingId, sucursales, onSubmit, onCancel }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <FormField label="Código" required value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} />
      <FormField label="Descripción" value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} />
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Sucursal
        <select value={form.sucursal_id} onChange={(e) => setForm({ ...form, sucursal_id: e.target.value })}>
          <option value="" style={{ color: '#1a1a18' }}>— Sin asignar —</option>
          {sucursales.map((s) => (
            <option key={s.id} value={s.id} style={{ color: '#1a1a18' }}>{s.nombre}</option>
          ))}
        </select>
      </label>
      <FormField
        label="Bodega principal"
        tooltip="Código de OTRA bodega hacia la que se consolida esta (ej: BA066 se consolida en BA061). Es solo un texto de referencia, no un vínculo automático todavía."
        placeholder="ej: BA061"
        value={form.bodega_principal}
        onChange={(e) => setForm({ ...form, bodega_principal: e.target.value })}
      />
      <button type="submit" className="motored-btn motored-btn-primary">{editingId ? 'Guardar cambios' : 'Crear bodega'}</button>
      {editingId && (
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      )}
    </form>
  );
}

function BodegasTable({ bodegas, sucursalesPorId, onEdit, onDeactivate }) {
  const handleDeactivateClick = (b) => {
    if (window.confirm(`¿Desactivar la bodega "${b.codigo}"? No se elimina, queda marcada como inactiva.`)) {
      onDeactivate(b.id);
    }
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
      <thead>
        <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          <th style={{ padding: '0 12px 8px 0' }}>Código</th>
          <th style={{ padding: '0 12px 8px 0' }}>Descripción</th>
          <th style={{ padding: '0 12px 8px 0' }}>Sucursal</th>
          <th style={{ padding: '0 12px 8px 0' }}>Bodega principal</th>
          <th style={{ padding: '0 12px 8px 0' }}>Estado</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {bodegas.map((b) => (
          <tr key={b.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
            <td style={{ padding: '10px 12px 10px 0' }}>{b.codigo}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{b.descripcion || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>
              {b.sucursal_id ? (sucursalesPorId[b.sucursal_id] || <em>sucursal desconocida</em>) : <em>sin asignar</em>}
            </td>
            <td style={{ padding: '10px 12px 10px 0' }}>{b.bodega_principal || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{b.activa ? 'Activa' : 'Inactiva'}</td>
            <td style={{ display: 'flex', gap: '1rem', padding: '10px 0' }}>
              <button type="button" className="motored-row-action" onClick={() => onEdit(b)}>Editar</button>
              {b.activa && (
                <button type="button" className="motored-row-action" onClick={() => handleDeactivateClick(b)}>Desactivar</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BodegasHeader({ onOpenBulk }) {
  return (
    <div
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '0.85rem 1rem', background: 'var(--motored-surface-alt, #f4f4f5)',
        border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: 'var(--motored-radius-md, 8px)',
      }}
    >
      <div>
        <h2 className="motored-h-seccion">Bodegas</h2>
        <p style={{ margin: '0.2rem 0 0', fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          ¿Tenés muchas bodegas para cargar de una vez? Subí un archivo CSV con "Carga masiva" en vez de crearlas una por una.
        </p>
      </div>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={onOpenBulk}>
        Carga masiva
      </button>
    </div>
  );
}

function useSucursalesOptions() {
  const [sucursales, setSucursales] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    listMaestros('sucursales')
      .then(setSucursales)
      .catch((err) => setError(err.message || 'No se pudo cargar la lista de sucursales'));
  }, []);
  const porId = Object.fromEntries(sucursales.map((s) => [s.id, s.nombre]));
  return { sucursales, sucursalesPorId: porId, sucursalesError: error };
}

function useBodegas() {
  const [bodegas, setBodegas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setBodegas(await listMaestros(ENTIDAD_PLURAL));
    } catch (err) {
      setError(err.message || 'Error al cargar bodegas');
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
      setError(err.message || 'Error al guardar bodega');
      return false;
    }
  };

  const deactivate = async (id) => {
    setError('');
    try {
      await deactivateMaestro(ENTIDAD_PLURAL, id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al desactivar bodega');
    }
  };

  return { bodegas, loading, error, save, deactivate, reload: load };
}

function useBodegasEditor(save) {
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);

  const startEdit = (b) => {
    setEditingId(b.id);
    setForm({
      codigo: b.codigo,
      descripcion: b.descripcion || '',
      sucursal_id: b.sucursal_id || '',
      bodega_principal: b.bodega_principal || '',
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
        descripcion: form.descripcion || null,
        sucursal_id: form.sucursal_id || null,
        bodega_principal: form.bodega_principal || null,
      },
      editingId
    );
    if (ok) cancelEdit();
  };

  return { form, setForm, editingId, startEdit, cancelEdit, handleSubmit };
}

export default function BodegasTab() {
  const { bodegas, loading, error, save, deactivate, reload } = useBodegas();
  const { form, setForm, editingId, startEdit, cancelEdit, handleSubmit } = useBodegasEditor(save);
  const { sucursales, sucursalesPorId, sucursalesError } = useSucursalesOptions();
  const [showBulkModal, setShowBulkModal] = useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <BodegasHeader onOpenBulk={() => setShowBulkModal(true)} />

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}
      {sucursalesError && (
        <p style={{ color: 'var(--motored-warning, #d97706)', fontSize: '0.8rem' }}>
          No se pudo cargar la lista de sucursales para el desplegable ({sucursalesError}).
        </p>
      )}

      <BodegaForm
        form={form}
        setForm={setForm}
        editingId={editingId}
        sucursales={sucursales}
        onSubmit={handleSubmit}
        onCancel={cancelEdit}
      />

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <BodegasTable bodegas={bodegas} sucursalesPorId={sucursalesPorId} onEdit={startEdit} onDeactivate={deactivate} />
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
