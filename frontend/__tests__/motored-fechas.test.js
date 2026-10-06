import {
  fechaBogota, fechaHoraBogota, horaBogota, parseInstante,
} from '../lib/motored/fechas';

describe('Motored dates in Colombia time', () => {
  test.each([
    ['2026-10-05T12:43:00Z'],
    ['2026-10-05T12:43:00'],
    ['2026-10-05T12:43:00+00:00'],
    ['2026-10-05T12:43:00.123456'],
    ['2026-10-05T07:43:00-05:00'],
  ])('%s is 07:43 in Bogota', (valor) => {
    expect(horaBogota(valor)).toBe('07:43');
    expect(fechaHoraBogota(valor)).toBe('05/10/2026 07:43');
    expect(fechaBogota(valor)).toBe('05/10/2026');
  });

  test('a Date instance is accepted', () => {
    expect(fechaHoraBogota(new Date(Date.UTC(2026, 9, 5, 12, 43)))).toBe('05/10/2026 07:43');
  });

  test('00:30 UTC is the previous day at 19:30', () => {
    expect(fechaHoraBogota('2026-10-06T00:30:00+00:00')).toBe('05/10/2026 19:30');
    expect(fechaBogota('2026-10-06T00:30:00')).toBe('05/10/2026');
  });

  test('a date-only value stays the same calendar date', () => {
    expect(fechaBogota('2026-10-05')).toBe('05/10/2026');
    expect(fechaHoraBogota('2026-10-05')).toBe('05/10/2026');
    expect(horaBogota('2026-10-05')).toBe('—');
    expect(fechaBogota('2026-01-01')).toBe('01/01/2026');
  });

  test('uses 24h time', () => {
    expect(horaBogota('2026-10-05T20:05:00Z')).toBe('15:05');
  });

  test.each([[null], [undefined], [''], ['not a date'], [{}]])('%p is a dash', (valor) => {
    expect(parseInstante(valor)).toBeNull();
    expect(fechaHoraBogota(valor)).toBe('—');
    expect(fechaBogota(valor)).toBe('—');
    expect(horaBogota(valor)).toBe('—');
  });
});

describe('every screen formatter shows Colombia time', () => {
  const { formatFecha, formatFechaHora } = require('../components/motored/detractores/labels');
  const { formatFechaHoraCo, formatHoraCo } = require('../components/motored/ingresos/labels');
  const { fechaLegible } = require('../components/motored/maestros/presupuestos/formato');
  const { fechaCorta } = require('../components/motored/pedidos/reglas');
  const { fechaHora } = require('../components/motored/pedidos/formato');
  const { momentoActualizacion, textoActualizado } = require('../components/motored/kpis/frescura');
  const AHORA = new Date('2026-10-05T18:00:00Z');

  test('detractores', () => {
    expect(formatFechaHora('2026-10-05T12:43:00')).toBe('05/10/2026 07:43');
    expect(formatFecha('2026-10-06T00:30:00+00:00')).toBe('05/10/2026');
  });

  test('ingresos', () => {
    expect(formatFechaHoraCo('2026-10-05T12:43:00+00:00')).toBe('05/10/2026 07:43');
    expect(formatHoraCo('2026-10-05T12:43:00Z')).toBe('07:43');
  });

  test('presupuestos and pedidos', () => {
    expect(fechaLegible('2026-10-06T00:30:00')).toBe('05/10/2026');
    expect(fechaLegible('garbage')).toBe('garbage');
    expect(fechaCorta('2026-10-05')).toBe('05/10/2026');
    expect(fechaCorta('2026-10-06T00:30:00+00:00')).toBe('05/10/2026');
    expect(fechaHora('2026-10-05T12:43:00')).toBe('05/10/2026 07:43');
  });

  test('KPI freshness reads a naive string as UTC', () => {
    expect(momentoActualizacion('2026-10-05T12:43:00', AHORA)).toBe('a las 07:43');
    expect(momentoActualizacion('2026-10-05T12:43:00+00:00', AHORA)).toBe('a las 07:43');
    expect(textoActualizado('2026-10-04T12:43:00Z', AHORA)).toBe('Datos actualizados el 04/10 a las 07:43');
  });
});
