'use client';
/**
 * frontend/components/motored/maestros/VendedorForm.js
 *
 * Formulario de alta/edición de un vendedor del maestro (feature motored-
 * tablero-asesores, T3). El cargo es texto libre con sugerencias (datalist);
 * el usuario enlazado se elige de los usuarios existentes y NUNCA se asigna por
 * coincidencia de nombres. Todo `<option>` lleva color explícito: sin él el
 * texto queda invisible en el tema oscuro.
 */
import InfoTooltip from '../InfoTooltip';

export const CARGOS_SUGERIDOS = [
  'ASESOR DE REPUESTOS',
  'ASESOR DE REPUESTOS SUPERNUMERARIO',
  'ASESOR COMERCIAL DE SERVICIO POSVENTA',
  'JEFE DE TALLER',
  'CAJERO POSVENTA',
  'OTRO',
];

export const optionStyle = { color: '#1a1a18' };
export const emptyVendedorForm = { nombre: '', cargo: '', sucursal_id: '', cedula: '', usuario_id: '' };

const labelStyle = {
  display: 'flex', flexDirection: 'column', fontSize: '0.7rem',
  color: 'var(--motored-text-muted, #5a5a5a)', flex: '1 1 200px', minWidth: '180px',
};
const LISTA_CARGOS_ID = 'vendedor-cargos-sugeridos';

function Campo({ label, tooltip, children }) {
  return (
    <label style={labelStyle}>
      <span>
        {label}
        <InfoTooltip text={tooltip} />
      </span>
      {children}
    </label>
  );
}

export default function VendedorForm({ form, setForm, sucursales, usuarios, editingId, onSubmit, onCancel }) {
  const set = (campo) => (e) => setForm({ ...form, [campo]: e.target.value });
  return (
    <form
      id="vendedor-form"
      onSubmit={onSubmit}
      style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}
    >
      <Campo
        label="Nombre vendedor"
        tooltip="Tiene que ser igual al nombre que aparece en la columna Vendedor del archivo de ventas del ERP. Se compara sin tildes, sin mayúsculas y sin espacios de más, pero las letras deben ser las mismas."
      >
        <input type="text" value={form.nombre} onChange={set('nombre')} required />
      </Campo>
      <Campo
        label="Cargo"
        tooltip="Lo que hace la persona. Elegí una sugerencia o escribí otro cargo. Se guarda en mayúsculas."
      >
        <input type="text" list={LISTA_CARGOS_ID} value={form.cargo} onChange={set('cargo')} required />
        <datalist id={LISTA_CARGOS_ID}>
          {CARGOS_SUGERIDOS.map((c) => <option key={c} value={c} style={optionStyle} />)}
        </datalist>
      </Campo>
      <Campo label="Sucursal" tooltip="Sucursal principal donde trabaja esta persona. Es opcional.">
        <select value={form.sucursal_id} onChange={set('sucursal_id')}>
          <option value="" style={optionStyle}>Sin sucursal</option>
          {sucursales.map((s) => (
            <option key={s.id} value={s.id} style={optionStyle}>{s.nombre}{s.activa === false ? ' (inactiva)' : ''}</option>
          ))}
        </select>
      </Campo>
      <Campo
        label="Cédula"
        tooltip="Documento de identidad, solo números. Es obligatoria. Si la misma persona aparece en el ERP con dos nombres, cargá las dos filas con la misma cédula: el tablero las junta en una sola persona."
      >
        <input
          type="text" inputMode="numeric" value={form.cedula} onChange={set('cedula')} required
          pattern="[0-9.\s]+" title="Solo números (se aceptan puntos y espacios)."
        />
      </Campo>
      <Campo
        label="Usuario enlazado"
        tooltip="Si esta persona también entra a la app, elegí su usuario para unirlos. Nunca se enlaza solo por parecido de nombres. Es opcional."
      >
        <select value={form.usuario_id} onChange={set('usuario_id')}>
          <option value="" style={optionStyle}>Sin usuario</option>
          {usuarios.map((u) => (
            <option key={u.id} value={u.id} style={optionStyle}>{u.nombre} ({u.role})</option>
          ))}
        </select>
      </Campo>
      <button type="submit" className="motored-btn motored-btn-primary">
        {editingId ? 'Guardar cambios' : 'Crear vendedor'}
      </button>
      {editingId && (
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      )}
    </form>
  );
}
