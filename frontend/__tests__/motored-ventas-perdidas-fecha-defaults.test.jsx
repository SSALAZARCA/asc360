/**
 * Tests for `components/motored/ventas-perdidas/fechaDefaults.js`
 * (sdd/motored-ventas-perdidas-panel, Phase 7, task 7.1). Pure date math --
 * no mocks needed (Extract-Before-Mock rule). The owner decision made AFTER
 * the design doc (folded into `tasks.md` as authoritative) is "last 30
 * days" on load, frontend-only -- NOT the design doc's stale "last 7 days"
 * text.
 */
import { calcularRangoUltimos30Dias, formatFechaISO } from '../components/motored/ventas-perdidas/fechaDefaults';

describe('formatFechaISO', () => {
  it('formats a Date as YYYY-MM-DD, zero-padding month and day', () => {
    expect(formatFechaISO(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});

describe('calcularRangoUltimos30Dias', () => {
  it('returns hasta = today and desde = today minus 30 days', () => {
    const hoy = new Date(2026, 8, 26); // 2026-09-26
    const { desde, hasta } = calcularRangoUltimos30Dias(hoy);
    expect(hasta).toBe('2026-09-26');
    expect(desde).toBe('2026-08-27');
  });

  it('rolls back across a month/year boundary correctly', () => {
    const hoy = new Date(2026, 0, 10); // 2026-01-10
    const { desde, hasta } = calcularRangoUltimos30Dias(hoy);
    expect(hasta).toBe('2026-01-10');
    expect(desde).toBe('2025-12-11');
  });
});
