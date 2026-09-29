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
 * - `sustituida_por` (optional) -- a server-side type-ahead
 *   (`SustitutaTypeahead.js`) limited to the SELECTED proveedor, excluding
 *   the row being edited (the same-proveedor rule is also enforced
 *   server-side); setting it deactivates this referencia server-side
 *   (`services/maestros.py::update_referencia`).
 *
 * Pagination (`odd/tasks/motored-referencias-paginacion.md`): the catalog
 * is too big to load at once, so only the current page is fetched
 * (`useReferenciasPagina.js`), with server-side search and filters. Each
 * row carries `sustituta_codigo` from the backend, since the sustituta is
 * rarely on the same page.
 *
 * `unidad_empaque` and the price split (`precio_normal` vs. `precio_publico`)
 * are exactly the two locked business rules from the proposal most likely to
 * confuse a business user, so both get a real InfoTooltip, not just a label.
 *
 * Referencia layout (owner request 2026-09-28, table trimmed afterwards): the
 * form and the `.xlsx` template / bulk parser (`BulkUploadModal.js` / backend
 * `carga_excel.py`) use 9 labels, in this order: Código, Código del
 * proveedor, Nombre, Línea comercial, Unidad de empaque, Precio Normal antes
 * de IVA, Precio Público antes de IVA, Código de referencia sustituta,
 * Homologados otras marcas. The TABLE shows only the first 7 (plus Estado):
 * by business decision "Código de referencia sustituta" and "Homologados
 * otras marcas" are hidden from it, but stay as data and as form fields so
 * they can still be maintained. `precio_venta` is no longer shown or sent
 * (the DB column is kept untouched).
 */
import MotoredTableScroll from '../MotoredTableScroll';
import MotoredIconAction from '../MotoredIconAction';
import { useEffect, useState } from 'react';
import { listMaestros } from '../../../lib/motored/api';
import BulkUploadModal from './BulkUploadModal';
import FormField from './FormField';
import ReferenciasFiltros from './ReferenciasFiltros';
import ReferenciasPaginador from './ReferenciasPaginador';
import SustitutaTypeahead from './SustitutaTypeahead';
import useReferenciasPagina, { useLineasComerciales } from './useReferenciasPagina';
import InfoTooltip from '../InfoTooltip';
import { formatCOP } from '../../../lib/motored/formatCOP';

const ENTIDAD_SINGULAR = 'referencia';

const emptyForm = {
  codigo: '', proveedor_id: '', nombre: '', linea_comercial: '', unidad_empaque: '1',
  precio_normal: '', precio_publico: '', sustituida_por: '', sustituta_codigo: '', homologados: '',
};

const HELP = {
  proveedor: 'El código del proveedor tal como aparece en la pestaña de Proveedores (ej: HMCL). Identifica al proveedor, no es un número de parte.',
  unidadEmpaque: 'Cuántas unidades vienen por paquete del proveedor. Nunca puede ser 0: si lo dejás vacío o en 0, el sistema lo corrige automáticamente a 1 y lo marca como advertencia en el tablero de salud.',
  precioNormal: 'Precio sin IVA. Es el precio que usa el sistema para calcular el valor de los pedidos.',
  precioPublico: 'Precio al público sin IVA. Informativo únicamente — no se usa para calcular el valor de los pedidos.',
  sustituta: 'Si esta referencia fue reemplazada por otra del MISMO proveedor, acá va el código de esa otra referencia. Al guardar, esta referencia queda desactivada automáticamente. La referencia sustituta debe ser del mismo proveedor.',
  homologados: 'Modelos de moto de otras marcas con los que este repuesto es compatible. Podés poner varios separados por coma o punto y coma (ej: Yamaha FZ 150; Honda CB 190R).',
};

const PRECIO_FIELDS = [
  { key: 'precio_normal', label: 'Precio Normal antes de IVA', help: HELP.precioNormal },
  { key: 'precio_publico', label: 'Precio Público antes de IVA', help: HELP.precioPublico },
];

// Same rule as the backend (`texto.split_multivalor`): split on comma or
// semicolon, trim, drop empties, dedupe preserving order.
function splitHomologados(text) {
  const values = String(text || '').split(/[,;]/).map((v) => v.trim()).filter(Boolean);
  return [...new Set(values)];
}

function formatHomologados(values) {
  return Array.isArray(values) ? values.join(', ') : '';
}

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

function ProveedorSelect({ form, setForm, proveedores }) {
  // A sustituta always belongs to the proveedor it was chosen for, so
  // changing the proveedor drops it.
  const onProveedorChange = (proveedorId) => {
    setForm({ ...form, proveedor_id: proveedorId, sustituida_por: '', sustituta_codigo: '' });
  };

  return (
    <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
      <span>
        Código del proveedor
        <InfoTooltip text={HELP.proveedor} />
      </span>
      <select value={form.proveedor_id} onChange={(e) => onProveedorChange(e.target.value)} required>
        <option value="" style={{ color: '#1a1a18' }}>— Elegir —</option>
        {proveedores.map((p) => (
          <option key={p.id} value={p.id} style={{ color: '#1a1a18' }}>{p.codigo} — {p.nombre}</option>
        ))}
      </select>
    </label>
  );
}

function SustitutaField({ form, setForm, editingId }) {
  return (
    <SustitutaTypeahead
      proveedorId={form.proveedor_id}
      excludeId={editingId}
      help={HELP.sustituta}
      value={{ id: form.sustituida_por, codigo: form.sustituta_codigo }}
      onChange={({ id, codigo }) => setForm({ ...form, sustituida_por: id, sustituta_codigo: codigo })}
    />
  );
}

function ReferenciaForm({ form, setForm, editingId, proveedores, onSubmit, onCancel }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <FormField label="Código" required value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} />
      <ProveedorSelect form={form} setForm={setForm} proveedores={proveedores} />
      <FormField label="Nombre" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
      <FormField
        label="Línea comercial"
        tooltip="Ej: REPUESTOS, ACCESORIOS. No es una lista cerrada, se escribe como texto libre."
        value={form.linea_comercial}
        onChange={(e) => setForm({ ...form, linea_comercial: e.target.value })}
      />
      <FormField
        label="Unidad de empaque"
        tooltip={HELP.unidadEmpaque}
        value={form.unidad_empaque}
        onChange={(e) => setForm({ ...form, unidad_empaque: e.target.value })}
      />
      <PrecioFields form={form} setForm={setForm} />
      <SustitutaField form={form} setForm={setForm} editingId={editingId} />
      <FormField
        label="Homologados otras marcas"
        tooltip={HELP.homologados}
        value={form.homologados}
        placeholder="AK 125 FLEX, APACHE 160, CB 100"
        onChange={(e) => setForm({ ...form, homologados: e.target.value })}
      />
      <button type="submit" className="motored-btn motored-btn-primary">{editingId ? 'Guardar cambios' : 'Crear referencia'}</button>
      {editingId && (
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      )}
    </form>
  );
}

const TABLE_COLUMNS = [
  { label: 'Código' },
  { label: 'Código del proveedor', help: HELP.proveedor },
  { label: 'Nombre' },
  { label: 'Línea comercial' },
  { label: 'Unidad de empaque', help: HELP.unidadEmpaque },
  { label: 'Precio Normal antes de IVA', help: HELP.precioNormal, numeric: true },
  { label: 'Precio Público antes de IVA', help: HELP.precioPublico, numeric: true },
  { label: 'Estado' },
];

const thStyle = { padding: '0 12px 8px 0' };
const tdStyle = { padding: '10px 12px 10px 0' };
const numericTdStyle = { ...tdStyle, textAlign: 'right', whiteSpace: 'nowrap' };

function ReferenciasTable({ referencias, proveedorCodigoPorId, onEdit, onDeactivate, onReactivate }) {
  const handleDeactivateClick = (r) => {
    if (window.confirm(`¿Desactivar la referencia "${r.codigo}"? No se elimina, queda marcada como inactiva.`)) {
      onDeactivate(r.id);
    }
  };
  const handleReactivateClick = (r) => {
    if (window.confirm(`¿Reactivar la referencia "${r.codigo}"? Queda marcada como activa.`)) {
      onReactivate(r.id);
    }
  };

  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
            {TABLE_COLUMNS.map(({ label, help, numeric }) => (
              <th key={label} style={numeric ? { ...thStyle, textAlign: 'right' } : thStyle}>
                {label}
                {help && <InfoTooltip text={help} />}
              </th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {referencias.map((r) => (
            <tr key={r.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
              <td style={tdStyle}>{r.codigo}</td>
              <td style={tdStyle}>{proveedorCodigoPorId[r.proveedor_id] || <em>desconocido</em>}</td>
              <td style={tdStyle}>{r.nombre || <em>sin nombre</em>}</td>
              <td style={tdStyle}>{r.linea_comercial || <em>—</em>}</td>
              <td style={tdStyle}>
                {r.unidad_empaque}
                {r.unidad_empaque_advertencia && (
                  <span style={{ marginLeft: '0.35rem', color: 'var(--motored-warning, #d97706)', fontSize: '0.7rem' }}>(corregida)</span>
                )}
              </td>
              <td style={numericTdStyle}>{formatCOP(r.precio_normal)}</td>
              <td style={numericTdStyle}>{formatCOP(r.precio_publico)}</td>
              <td style={tdStyle}>{r.activa ? 'Activa' : 'Inactiva'}</td>
              <td style={{ display: 'flex', gap: '1rem', padding: '10px 0' }}>
                <MotoredIconAction action="Editar" onClick={() => onEdit(r)} />
                {r.activa ? (
                  <MotoredIconAction action="Desactivar" onClick={() => handleDeactivateClick(r)} />
                ) : (
                  <MotoredIconAction action="Reactivar" onClick={() => handleReactivateClick(r)} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
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
  const codigoPorId = Object.fromEntries(proveedores.map((p) => [p.id, p.codigo]));
  return { proveedores, proveedorCodigoPorId: codigoPorId, proveedoresError: error };
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
      precio_publico: r.precio_publico != null ? String(r.precio_publico) : '',
      sustituida_por: r.sustituida_por || '',
      sustituta_codigo: r.sustituta_codigo || '',
      homologados: formatHomologados(r.homologados),
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
        precio_publico: form.precio_publico ? Number(form.precio_publico) : null,
        sustituida_por: form.sustituida_por || null,
        homologados: splitHomologados(form.homologados),
      },
      editingId
    );
    if (ok) cancelEdit();
  };

  return { form, setForm, editingId, startEdit, cancelEdit, handleSubmit };
}

const mutedText = { color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' };

function ReferenciasListado({ pagina, proveedorCodigoPorId, onEdit }) {
  const { items, total, loading, page, pageSize, setPage, setPageSize, deactivate, reactivate } = pagina;
  if (loading && items.length === 0) return <p style={mutedText}>Cargando...</p>;
  return (
    <>
      <ReferenciasTable referencias={items} proveedorCodigoPorId={proveedorCodigoPorId} onEdit={onEdit} onDeactivate={deactivate} onReactivate={reactivate} />
      {items.length === 0 && <p style={mutedText}>No hay referencias que coincidan con la búsqueda.</p>}
      <ReferenciasPaginador page={page} pageSize={pageSize} total={total} onPageChange={setPage} onPageSizeChange={setPageSize} />
    </>
  );
}

export default function ReferenciasTab() {
  const pagina = useReferenciasPagina();
  const lineas = useLineasComerciales(pagina.version);
  const { form, setForm, editingId, startEdit, cancelEdit, handleSubmit } = useReferenciasEditor(pagina.save);
  const { proveedores, proveedorCodigoPorId, proveedoresError } = useProveedoresOptions();
  const [showBulkModal, setShowBulkModal] = useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <ReferenciasHeader onOpenBulk={() => setShowBulkModal(true)} />

      {pagina.error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{pagina.error}</p>}
      {proveedoresError && (
        <p style={{ color: 'var(--motored-warning, #d97706)', fontSize: '0.8rem' }}>
          No se pudo cargar la lista de proveedores para el desplegable ({proveedoresError}).
        </p>
      )}

      <ReferenciaForm
        form={form} setForm={setForm} editingId={editingId} proveedores={proveedores}
        onSubmit={handleSubmit} onCancel={cancelEdit}
      />

      <ReferenciasFiltros filtros={pagina.filtros} lineas={lineas} onChange={pagina.setFiltros} />
      <ReferenciasListado pagina={pagina} proveedorCodigoPorId={proveedorCodigoPorId} onEdit={startEdit} />

      {showBulkModal && (
        <BulkUploadModal
          entidad={ENTIDAD_SINGULAR}
          onClose={() => setShowBulkModal(false)}
          onSuccess={() => {
            setShowBulkModal(false);
            pagina.reload();
          }}
        />
      )}
    </div>
  );
}
