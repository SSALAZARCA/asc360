/**
 * frontend/lib/motored/formatCOP.js
 *
 * Display-only Colombian peso format, rounded with no decimals (same Intl
 * options as `app/distribuidor/repuestos/page.js`). The backend sends
 * Decimal prices as strings ("12746.44"), so the value is converted with
 * `Number` first. Missing or non-numeric values render as "—".
 */
const COP = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });

export function formatCOP(value) {
  if (value == null || String(value).trim() === '') return '—';
  const amount = Number(value);
  return Number.isFinite(amount) ? COP.format(amount) : '—';
}
