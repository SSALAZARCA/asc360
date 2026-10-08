/**
 * Cargas > Errores: "Crear referencia" opens a small form with the línea
 * comercial (required, from the configured lines) and the proveedor
 * (HMCL by default), says how many rows of the carga it resolves, and
 * posts both fields to the resolver.
 */
import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';

const mockGetErrores = jest.fn();
const mockResolver = jest.fn();
const mockLineas = jest.fn();
const mockListMaestros = jest.fn();
jest.mock('../lib/motored/api', () => ({
  getErroresCarga: (...args) => mockGetErrores(...args),
  resolverErroresCarga: (...args) => mockResolver(...args),
  getLineasComercialesCarga: (...args) => mockLineas(...args),
  descargarErroresCargaCsv: jest.fn(),
  listMaestros: (...args) => mockListMaestros(...args),
}));

import ErroresTab from '../components/motored/cargas/ErroresTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

function errorRef(id, fila, valor = 'BTX4L/BTZ5S-BS') {
  return {
    id, fila, columna: 'Parte', valor,
    codigo_error: 'REFERENCIA_NO_ENCONTRADA', mensaje: 'No se encontró.',
  };
}

const PROVEEDORES = [
  { id: 'p-otros', codigo: 'OTROS', nombre: 'Otros', es_principal: false, activa: true },
  { id: 'p-hmcl', codigo: 'HMCL', nombre: 'Honda HMCL', es_principal: true, activa: true },
  { id: 'p-viejo', codigo: 'VIEJO', nombre: 'Viejo', es_principal: false, activa: false },
];

beforeEach(() => {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'COMPRAS' }));
  mockGetErrores.mockReset().mockResolvedValue([
    errorRef('e1', 10), errorRef('e2', 11), errorRef('e3', 12, 'OTRO-1'),
  ]);
  mockResolver.mockReset().mockResolvedValue({ acciones_aplicadas: 1, acciones_ignoradas: 0 });
  mockLineas.mockReset().mockResolvedValue([
    { valor: 'Repuestos', etiqueta: 'Repuestos' },
    { valor: 'Accesorios', etiqueta: 'Accesorios' },
  ]);
  mockListMaestros.mockReset().mockImplementation(
    (entidad) => Promise.resolve(entidad === 'proveedores' ? PROVEEDORES : []),
  );
});

async function abrirFormulario() {
  render(<ErroresTab carga={{ id: 'c1', estado: 'VALIDADO' }} />);
  const [fila] = await screen.findAllByTestId('error-row');
  fireEvent.click(within(fila).getByRole('button', { name: 'Crear referencia' }));
  return screen.findByRole('dialog', { name: /Crear referencia/ });
}

it('requires a línea, defaults the proveedor to HMCL and posts both', async () => {
  const dialogo = await abrirFormulario();
  const linea = await within(dialogo).findByLabelText(/Línea comercial/);
  const proveedor = within(dialogo).getByLabelText(/Proveedor/);
  await within(dialogo).findByRole('option', { name: 'Repuestos' });
  await within(dialogo).findByRole('option', { name: 'Honda HMCL' });

  expect(proveedor).toHaveValue('p-hmcl');
  expect(within(proveedor).queryByRole('option', { name: 'Viejo' })).toBeNull();
  const crear = within(dialogo).getByRole('button', { name: 'Crear referencia' });
  expect(crear).toBeDisabled();

  fireEvent.change(linea, { target: { value: 'Repuestos' } });
  fireEvent.click(crear);

  expect(await screen.findByRole('status')).toHaveTextContent(
    "Referencia BTX4L/BTZ5S-BS creada (línea Repuestos). Use 'Volver a validar' para incluir estas filas.",
  );
  expect(mockResolver).toHaveBeenCalledWith('c1', [{
    codigo_error: 'REFERENCIA_NO_ENCONTRADA',
    valor: 'BTX4L/BTZ5S-BS',
    accion: 'crear_referencia',
    linea_comercial: 'Repuestos',
    proveedor_id: 'p-hmcl',
  }]);
});

it('says how many rows of the carga the code resolves', async () => {
  const dialogo = await abrirFormulario();

  expect(within(dialogo).getByText(
    'Se resuelven 2 filas de esta carga con este código',
  )).toBeInTheDocument();
});

it('styles every option so it stays readable in the dark theme', async () => {
  const dialogo = await abrirFormulario();
  await within(dialogo).findByRole('option', { name: 'Repuestos' });
  await within(dialogo).findByRole('option', { name: 'Honda HMCL' });

  within(dialogo).getAllByRole('option').forEach((opcion) => {
    expect(opcion.getAttribute('style')).toMatch(/color/);
  });
});

it('closes without posting on Cancelar', async () => {
  const dialogo = await abrirFormulario();

  fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }));

  expect(screen.queryByRole('dialog')).toBeNull();
  expect(mockResolver).not.toHaveBeenCalled();
});
