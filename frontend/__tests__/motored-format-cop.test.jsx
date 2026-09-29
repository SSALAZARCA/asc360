/**
 * `formatCOP` -- display-only Colombian peso format for Motored prices,
 * rounded with no decimals (same Intl options as
 * `app/distribuidor/repuestos/page.js`).
 */
import { formatCOP } from '../lib/motored/formatCOP';

// Intl may emit a non-breaking space between "$" and the amount.
const normalize = (text) => text.replace(/\s+/g, ' ');

describe('formatCOP', () => {
  it.each([
    [12746.44, '$ 12.746'],
    ['361815.10', '$ 361.815'],
    ['200.00', '$ 200'],
    [999.5, '$ 1.000'],
    [0, '$ 0'],
  ])('formats %p as %p', (value, expected) => {
    expect(normalize(formatCOP(value))).toBe(expected);
  });

  it.each([null, undefined, '', '   ', 'abc'])('shows a dash for %p', (value) => {
    expect(formatCOP(value)).toBe('—');
  });
});
