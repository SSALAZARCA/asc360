'use client';

/**
 * File picker + preview for the signed delivery-act document, introduced in:
 *   sdd/distributor-vehicle-delivery, Phase 7 (frontend, PR7)
 *
 * Accepts images OR PDF (2026-07-29 decision) -- a Distribuidor's delivery
 * act is a different document than a workshop's damage-reception photos,
 * commonly scanned/signed as PDF.
 *
 * Pure, controlled, presentational component — no fetch/upload logic here.
 * The caller (`app/distribuidor/entrega/page.js`) owns the `File` object
 * and decides how to send it (today: appended inline as the `photo` field
 * of the multipart `POST /distributor/deliveries` request, per Design
 * ADR 18). Namespaced under `components/distribuidor/` so a future
 * parts-sale screen for the same role can reuse it unmodified.
 *
 * Props:
 * - value: File | null — currently selected photo (controlled)
 * - onChange(file: File | null): called with the newly picked file
 * - required: boolean — Distribuidor MUST attach a photo (ADR 17); a
 *   superadmin backfilling a legacy vehicle MAY omit it. This only affects
 *   the visible hint text — the actual submit-blocking validation lives in
 *   the page, since only it knows the current actor's role.
 * - label / labelStyle / inputStyle / hintStyle: style hooks matching the
 *   rest of the page's field conventions (see historical-orders/page.js)
 */
export default function DeliveryActUpload({
  value,
  onChange,
  required = false,
  label = 'Foto del acta de entrega',
  labelStyle,
  inputStyle,
  hintStyle,
}) {
  function handleChange(e) {
    const file = e.target.files?.[0] || null;
    onChange(file);
  }

  return (
    <label style={labelStyle}>
      {label}{required ? ' (obligatorio)' : ' (opcional)'}
      <input
        aria-label={label}
        type="file"
        accept="image/*,application/pdf"
        onChange={handleChange}
        style={inputStyle}
      />
      {value && (
        <p style={{ ...hintStyle, color: '#22c55e' }}>✓ {value.name}</p>
      )}
      {!value && required && (
        <p style={hintStyle}>El acta firmada es obligatoria para Distribuidor.</p>
      )}
    </label>
  );
}
