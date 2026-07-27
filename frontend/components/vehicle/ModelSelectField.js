'use client';

/**
 * Reusable model <select>, mirroring the exact `ModeloField` component in
 * `app/superadmin-data/page.js`.
 *
 * The master VIN catalog often supplies a model string that doesn't match
 * the standardized catalog letter-for-letter (e.g. "RENEGADE SPORT 200S" vs.
 * "Renegade 200" from `GET /vehicle-models`). Without an extra option, an
 * unmatched value would be invisible in the <select> even though the data
 * IS saved in the form -- this renders it as a visible extra option so the
 * user can see it and decide whether to correct it to a standard model.
 *
 * Props:
 * - models: array of `{ id, modelo }` (the real shape returned by
 *   `GET /vehicle-models`)
 * - value: string — current model value (controlled)
 * - onChange(value: string): called with the new value on selection/typing
 * - label: input/select label + aria-label (default "Modelo")
 * - labelStyle / inputStyle: optional style overrides
 *
 * Falls back to a plain text <input> when `models` is empty, so the field
 * still works if the catalog fetch failed or hasn't resolved yet.
 */
export default function ModelSelectField({
  models = [],
  value,
  onChange,
  label = 'Modelo',
  labelStyle,
  inputStyle,
}) {
  if (!models || models.length === 0) {
    return (
      <label style={labelStyle}>
        {label}
        <input
          aria-label={label}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={inputStyle}
        />
      </label>
    );
  }

  const hasMatch = models.some((m) => m.modelo === value);

  return (
    <label style={labelStyle}>
      {label}
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} style={inputStyle}>
        <option value="">— Seleccioná un modelo —</option>
        {value && !hasMatch && (
          <option value={value}>{value} (no está en el catálogo estándar)</option>
        )}
        {models.map((m) => (
          <option key={m.id} value={m.modelo}>{m.modelo}</option>
        ))}
      </select>
    </label>
  );
}
