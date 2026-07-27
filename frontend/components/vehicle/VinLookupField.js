'use client';

/**
 * Reusable VIN input that triggers a lookup callback as soon as the field
 * reaches exactly 17 characters (on `onChange`, not `onBlur`) — the same
 * behavior already fixed in `app/superadmin-data/page.js`'s `VinField`, but
 * built as a genuinely reusable, prop-driven component instead of
 * copy-pasting the page-specific hook logic.
 *
 * The caller owns all state and the actual fetch/lookup implementation:
 * this component only decides WHEN to call `onLookup` and how to render the
 * loading/found/not_found hint for a given `lookupStatus`.
 *
 * Props:
 * - value: string — current VIN input value (controlled)
 * - onChange(value: string): called on every keystroke with the raw input value
 * - onLookup(vin: string): called once the value's trimmed length is exactly 17
 * - lookupStatus: 'idle' | 'loading' | 'found' | 'not_found'
 * - label: input label / aria-label (default "VIN")
 * - labelStyle / inputStyle / hintStyle: optional style overrides for callers
 *   that want to match their own page's look (defaults to no inline style)
 */
export default function VinLookupField({
  value,
  onChange,
  onLookup,
  lookupStatus = 'idle',
  label = 'VIN',
  labelStyle,
  inputStyle,
  hintStyle,
}) {
  function handleChange(e) {
    const nextValue = e.target.value;
    onChange(nextValue);
    // Buscar apenas se completan los 17 caracteres, sin esperar a que el
    // usuario haga click afuera -- de lo contrario el buscador parece
    // "colgado" mientras en realidad todavía no arrancó.
    if (nextValue.trim().length === 17 && typeof onLookup === 'function') {
      onLookup(nextValue);
    }
  }

  return (
    <label style={labelStyle}>
      {label}
      <input
        aria-label={label}
        type="text"
        value={value}
        onChange={handleChange}
        style={inputStyle}
      />
      {lookupStatus === 'loading' && <p style={hintStyle}>Buscando en el maestro de VINs…</p>}
      {lookupStatus === 'found' && (
        <p style={{ ...hintStyle, color: '#22c55e' }}>✓ Datos encontrados y completados abajo.</p>
      )}
      {lookupStatus === 'not_found' && <p style={hintStyle}>No está en el maestro — completá manualmente.</p>}
    </label>
  );
}
