'use client';
/**
 * frontend/components/motored/maestros/FormField.js
 *
 * Shared label+input(+tooltip) renderer for the Maestros tab forms
 * (SucursalesTab/ProveedoresTab/ReferenciasTab/BodegasTab). Extracted
 * after code review flagged the same block hand-duplicated 4-9 times per
 * form, mirroring the field-config pattern `BulkUploadModal.js` already
 * uses via `COLUMNAS_POR_ENTIDAD`. Selects and checkboxes stay inline in
 * each form since they need different behavior, not this component.
 */
import InfoTooltip from '../InfoTooltip';

const labelStyle = {
  display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)',
};

export default function FormField({ label, tooltip, required, type = 'text', value, onChange, placeholder }) {
  return (
    <label style={labelStyle}>
      <span>
        {label}
        {tooltip && <InfoTooltip text={tooltip} />}
      </span>
      <input type={type} value={value} onChange={onChange} required={required} placeholder={placeholder} />
    </label>
  );
}
