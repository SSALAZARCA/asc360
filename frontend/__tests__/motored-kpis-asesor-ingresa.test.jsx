/**
 * Advisor card and public link: the "Ingrésala al sistema" notice shows only
 * for ASESOR invoices that already arrived; ANALISTA invoices carry a small
 * muted note instead.
 */
import { render, screen, within } from '@testing-library/react';
import AsesorDetalle from '../components/motored/kpis/asesores/AsesorDetalle';
import { ASESOR_DETALLE } from './helpers/kpisAsesorDetalleFixture';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  usePathname: () => '/motored/informe/tok123',
}));

const item = (numero, extra = {}) => ({
  prefijo_rh: 'RH', numero_rh: numero, factura: `RH ${numero}`, sucursal_id: 's-pop', tienda: 'Popayán',
  fecha: '2026-09-28', dias: 12, unidades: 3, valor: 1200000, estado: 'SIN_CONFIRMAR',
  confirmado_por: null, confirmado_en: null, num_referencias: 4, responsable: 'ASESOR',
  puede_descargar_plantilla: false, ...extra,
});
const bloque = (items) => ({ verificable_desde: '2026-09-24', items, resumen: { pendientes: items.length } });
const montar = (items) => render(
  <AsesorDetalle
    data={{ ...ASESOR_DETALLE, pendientes_ingreso: bloque(items) }}
    enlace={{ token: 'tok123', cedula: '123' }}
  />,
);
const fila = (factura) => screen.getByText((_, el) => el.tagName === 'SPAN' && el.textContent.startsWith(factura)).closest('li');

beforeEach(() => { global.fetch = jest.fn(); sessionStorage.clear(); });

it('tells the asesor to enter an arrived ASESOR invoice', async () => {
  montar([item(1, { estado: 'LLEGO' })]);
  await screen.findByRole('region', { name: 'Pedidos por ingresar' });
  expect(within(fila('RH 1')).getByText('Ingrésala al sistema')).toBeInTheDocument();
});

it.each(['SIN_CONFIRMAR', 'NO_HA_LLEGADO'])('shows no notice while the ASESOR invoice is %s', async (estado) => {
  montar([item(1, { estado })]);
  await screen.findByRole('region', { name: 'Pedidos por ingresar' });
  expect(screen.queryByText('Ingrésala al sistema')).not.toBeInTheDocument();
});

it('shows the analista note, never the notice, on an ANALISTA invoice', async () => {
  montar([item(2, { estado: 'LLEGO', responsable: 'ANALISTA', num_referencias: 30 })]);
  await screen.findByRole('region', { name: 'Pedidos por ingresar' });
  expect(within(fila('RH 2')).getByText('La ingresa el analista administrativo')).toBeInTheDocument();
  expect(screen.queryByText('Ingrésala al sistema')).not.toBeInTheDocument();
});

it('shows nothing extra for a row without responsable data', async () => {
  montar([item(3, { estado: 'LLEGO', responsable: undefined })]);
  await screen.findByRole('region', { name: 'Pedidos por ingresar' });
  expect(screen.queryByText('Ingrésala al sistema')).not.toBeInTheDocument();
  expect(screen.queryByText('La ingresa el analista administrativo')).not.toBeInTheDocument();
});
