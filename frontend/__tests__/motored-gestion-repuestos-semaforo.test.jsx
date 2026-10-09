/**
 * Urgency traffic light of the pending invoices: the pure rule (7 / 15 day thresholds), and where the panel and the
 * asesor card paint it (KPI cards, store dot, pills, state chip, legend, "N días" segment).
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';

const mockDetalle = jest.fn();

jest.mock('../lib/motored/gestionRepuestosApi', () => ({
  getIngresosDetalle: (...a) => mockDetalle(...a),
  getIngresosHistorial: jest.fn().mockResolvedValue({ historial: [] }),
  confirmarIngreso: jest.fn(),
}));

import IngresosFacturasPanel from '../components/motored/gestion-repuestos/IngresosFacturasPanel';
import PendientesIngreso from '../components/motored/kpis/asesores/PendientesIngreso';
import {
  nivelPorDias, nivelEstado, nivelTienda, NORMAL, ATENCION, CRITICO,
} from '../components/motored/gestion-repuestos/semaforo';

describe('semaforo rule', () => {
  test.each([[0, NORMAL], [7, NORMAL], [8, ATENCION], [15, ATENCION], [16, CRITICO], [31, CRITICO]])(
    '%i days is %s', (dias, nivel) => expect(nivelPorDias(dias)).toBe(nivel));

  test('no usable number has no level', () => {
    expect(nivelPorDias(null)).toBeNull();
    expect(nivelPorDias(undefined)).toBeNull();
  });

  test('LLEGO is always critical, NO_HA_LLEGADO follows the age, SIN_CONFIRMAR is neutral', () => {
    expect(nivelEstado('LLEGO', 1)).toBe(CRITICO);
    expect(nivelEstado('NO_HA_LLEGADO', 3)).toBe(NORMAL);
    expect(nivelEstado('NO_HA_LLEGADO', 10)).toBe(ATENCION);
    expect(nivelEstado('SIN_CONFIRMAR', 30)).toBeNull();
  });

  test('a store takes its worst state', () => {
    expect(nivelTienda({ llegaron_sin_ingresar: 1, mas_antigua: 2 })).toBe(CRITICO);
    expect(nivelTienda({ llegaron_sin_ingresar: 0, mas_antigua: 16 })).toBe(CRITICO);
    expect(nivelTienda({ llegaron_sin_ingresar: 0, mas_antigua: 8 })).toBe(ATENCION);
    expect(nivelTienda({ llegaron_sin_ingresar: 0, mas_antigua: 7 })).toBe(NORMAL);
    expect(nivelTienda({ llegaron_sin_ingresar: 0, mas_antigua: null })).toBe(NORMAL);
  });
});

const it = (n, estado, dias, id = 'a', tienda = 'Tienda') => ({
  prefijo_rh: 'RH', numero_rh: n, factura: `RH ${n}`, sucursal_id: id, tienda, fecha: '2026-09-07',
  dias, unidades: 1, valor: 1000, estado, confirmado_por: null, confirmado_en: null,
});
const montar = async (items) => {
  mockDetalle.mockResolvedValue({ verificable_desde: '2026-09-07', items });
  render(<IngresosFacturasPanel />);
  await screen.findByText(items[0].factura);
};
const kpi = (nombre) => screen.getByText(nombre, { selector: 'p' }).closest('div');

describe('panel colors', () => {
  test('"Llegaron sin ingresar" card is critical when above zero, good at zero; "Más antigua" follows the age', async () => {
    await montar([it(1, 'LLEGO', 10)]);
    expect(kpi('Llegaron sin ingresar')).toHaveAttribute('data-nivel', CRITICO);
    expect(kpi('Más antigua')).toHaveAttribute('data-nivel', ATENCION);
    expect(kpi('Pendientes')).not.toHaveAttribute('data-nivel');
  });

  test('"Llegaron sin ingresar" is good at zero and an old invoice is critical', async () => {
    await montar([it(1, 'SIN_CONFIRMAR', 20)]);
    expect(kpi('Llegaron sin ingresar')).toHaveAttribute('data-nivel', NORMAL);
    expect(kpi('Más antigua')).toHaveAttribute('data-nivel', CRITICO);
  });

  test('each store gets a dot with its worst state and a pill on its oldest invoice', async () => {
    await montar([
      it(1, 'LLEGO', 3, 'a', 'Cali'), it(2, 'SIN_CONFIRMAR', 9, 'b', 'Pasto'), it(3, 'SIN_CONFIRMAR', 2, 'c', 'Tuluá')]);
    const fila = (n) => within(screen.getByRole('table', { name: 'Por tienda' })).getByText(n).closest('tr');
    expect(fila('Cali').querySelector('[aria-hidden="true"][data-nivel]')).toHaveAttribute('data-nivel', CRITICO);
    expect(fila('Pasto').querySelector('[aria-hidden="true"][data-nivel]')).toHaveAttribute('data-nivel', ATENCION);
    expect(fila('Tuluá').querySelector('[aria-hidden="true"][data-nivel]')).toHaveAttribute('data-nivel', NORMAL);
    expect(within(fila('Pasto')).getByText('9')).toHaveAttribute('data-nivel', ATENCION);
    expect(within(fila('Cali')).getAllByRole('cell')[2]).toHaveStyle({ fontWeight: 700 });
  });

  test('detalle paints the days and the state chip', async () => {
    await montar(
      [it(1, 'LLEGO', 2), it(2, 'NO_HA_LLEGADO', 12), it(3, 'SIN_CONFIRMAR', 20)]);
    const fila = (f) => screen.getByText(f).closest('tr');
    expect(within(fila('RH 1')).getByText('2', { selector: 'span' })).toHaveAttribute('data-nivel', NORMAL);
    expect(within(fila('RH 1')).getByText('Ya llegó sin ingresar')).toHaveAttribute('data-nivel', CRITICO);
    expect(within(fila('RH 2')).getByText('Aún no llega')).toHaveAttribute('data-nivel', ATENCION);
    expect(within(fila('RH 3')).getByText('20', { selector: 'span' })).toHaveAttribute('data-nivel', CRITICO);
    expect(within(fila('RH 3')).getByText('Sin confirmar')).not.toHaveAttribute('data-nivel');
  });

  test('legend explains the three colors and the thresholds', async () => {
    await montar([it(1, 'SIN_CONFIRMAR', 1)]);
    const leyenda = screen.getByLabelText('Leyenda de colores');
    expect(leyenda).toHaveTextContent('≤7 días normal');
    expect(leyenda).toHaveTextContent('8–15 días atención');
    expect(leyenda).toHaveTextContent('>15 días o llegó sin ingresar: crítico');
    expect(leyenda.querySelectorAll('[data-nivel]')).toHaveLength(3);
    expect(leyenda).toHaveAttribute('title', expect.stringMatching(/7 y 15 días/));
  });
});

test('asesor card colors the "N días" segment by age', async () => {
  const bloque = { verificable_desde: '2026-09-24', items: [{ ...it(1, 'SIN_CONFIRMAR', 12), fecha: '2026-09-28' }] };
  render(<PendientesIngreso enlace={{ token: 't', cedula: '1' }} data={{ asesor: {}, pendientes_ingreso: bloque }} />);
  const card = await screen.findByRole('region', { name: 'Pedidos por ingresar' });
  expect(within(card).getByText('12 días')).toHaveAttribute('data-nivel', ATENCION);
});
