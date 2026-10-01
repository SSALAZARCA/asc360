'use client';
/**
 * frontend/components/motored/maestros/VendedoresTab.js
 *
 * Maestro de vendedores (feature motored-tablero-asesores, T3): toda persona que
 * vende, con o sin usuario en la app. Se carga por Excel (nunca borra gente) y
 * se edita a mano. "Vendedores sin registrar" muestra a quien aparece vendiendo
 * y falta agregar; "Agregar" precarga el formulario con su nombre del ERP.
 * Quien no esté en el maestro cuenta como "resto de compañía" en el tablero.
 */
import { useState } from 'react';
import BulkUploadModal from './BulkUploadModal';
import VendedorForm, { emptyVendedorForm } from './VendedorForm';
import VendedoresFiltros from './VendedoresFiltros';
import { VendedoresTable, VendedoresSinRegistrar } from './VendedoresTable';
import useVendedores from './useVendedores';

function Encabezado({ onOpenBulk }) {
  return (
    <div
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap',
        padding: '0.85rem 1rem', background: 'var(--motored-surface-alt, #f4f4f5)',
        border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: 'var(--motored-radius-md, 8px)',
      }}
    >
      <div>
        <h2 className="motored-h-seccion">Vendedores</h2>
        <p style={{ margin: '0.2rem 0 0', fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          Toda persona que vende. Subir un archivo agrega y actualiza, nunca borra a nadie. Quien no esté acá cuenta como
          &quot;resto de compañía&quot; en el tablero.
        </p>
      </div>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={onOpenBulk}>
        Carga masiva
      </button>
    </div>
  );
}

function payloadDe(form) {
  return {
    nombre: form.nombre,
    cargo: form.cargo,
    sucursal_id: form.sucursal_id || null,
    cedula: form.cedula,
    usuario_id: form.usuario_id || null,
  };
}

function useEditor(guardar) {
  const [form, setForm] = useState(emptyVendedorForm);
  const [editingId, setEditingId] = useState(null);

  const reiniciar = () => { setEditingId(null); setForm(emptyVendedorForm); };
  const editar = (v) => {
    setEditingId(v.id);
    setForm({
      nombre: v.nombre, cargo: v.cargo, sucursal_id: v.sucursal_id || '',
      cedula: v.cedula || '', usuario_id: v.usuario_id || '',
    });
  };
  const precargar = (item) => {
    setEditingId(null);
    setForm({ ...emptyVendedorForm, nombre: item.vendedor_ejemplo });
    document.getElementById('vendedor-form')?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  };
  const enviar = async (e) => {
    e.preventDefault();
    if (await guardar(payloadDe(form), editingId)) reiniciar();
  };
  return { form, setForm, editingId, editar, precargar, reiniciar, enviar };
}

export default function VendedoresTab() {
  const datos = useVendedores();
  const editor = useEditor(datos.guardar);
  const [showBulk, setShowBulk] = useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <Encabezado onOpenBulk={() => setShowBulk(true)} />

      {datos.error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{datos.error}</p>}

      <VendedorForm
        form={editor.form} setForm={editor.setForm} sucursales={datos.sucursales} usuarios={datos.usuarios}
        editingId={editor.editingId} onSubmit={editor.enviar} onCancel={editor.reiniciar}
      />

      <VendedoresFiltros
        filtros={datos.filtros} setFiltros={datos.setFiltros} vendedores={datos.vendedores}
        onAplicar={datos.aplicarFiltros}
      />

      {datos.loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <VendedoresTable
          vendedores={datos.vendedores} onEdit={editor.editar}
          onDeactivate={datos.desactivar} onReactivate={datos.reactivar}
        />
      )}

      <VendedoresSinRegistrar items={datos.sinRegistrar} error={datos.sinRegistrarError} onAgregar={editor.precargar} />

      {showBulk && (
        <BulkUploadModal
          entidad="vendedor"
          onClose={() => setShowBulk(false)}
          onSuccess={() => { setShowBulk(false); datos.recargar(); }}
        />
      )}
    </div>
  );
}
