/**
 * Test counts (odd/tasks/motored-conteo-prueba.md): ADMIN schedules a count
 * as a test with "Es de prueba", the list hides test counts until
 * "Mostrar pruebas", every test count carries a PRUEBA badge, and ADMIN
 * deletes one with "Borrar conteo de prueba" after a confirmation.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import * as api from '../lib/motored/conteosApi';
import ConteosContainer from '../components/motored/inventarios/ConteosContainer';
import ConteoDetalleContainer from '../components/motored/inventarios/ConteoDetalleContainer';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/inventarios/conteos',
}));
jest.mock('../lib/motored/conteosApi');

const REAL = {
  id: 'c1', tipo: 'TOTAL', estado: 'PROGRAMADO', origen: 'MANUAL', fecha_programada: '2026-10-12',
  sucursal: { id: 's1', nombre: 'Quilichao' }, lider: { id: 'l1', nombre: 'Laura Líder' }, es_prueba: false,
};
const PRUEBA = {
  id: 'c9', tipo: 'TOTAL', estado: 'ANULADO', origen: 'MANUAL', fecha_programada: '2026-10-10',
  sucursal: { id: 's2', nombre: 'Cali Sur' }, lider: { id: 'l1', nombre: 'Laura Líder' }, es_prueba: true,
  anulado_en: '2026-10-10T15:00:00Z', motivo_anulacion: 'Ensayo',
};
const SUCURSALES = [{ id: 's1', nombre: 'Quilichao', vigencia_horas: 6, inventario: null }];
const LIDERES = [{ id: 'l1', nombre: 'Laura Líder', email: 'l@x.co' }];

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

beforeEach(() => {
  sessionStorage.clear();
  jest.resetAllMocks();
  api.listarConteos.mockImplementation(async (filtros = {}) => (filtros.incluir_pruebas ? [REAL, PRUEBA] : [REAL]));
  api.listarSucursalesConteo.mockResolvedValue(SUCURSALES);
  api.listarLideres.mockResolvedValue(LIDERES);
  api.borrarConteoPrueba.mockResolvedValue(undefined);
});

async function programar() {
  fireEvent.click(await screen.findByRole('button', { name: 'Programar conteo' }));
  const dialogo = await screen.findByRole('dialog');
  await within(dialogo).findByRole('option', { name: 'Quilichao' });
  fireEvent.change(within(dialogo).getByLabelText('Tienda'), { target: { value: 's1' } });
  fireEvent.change(within(dialogo).getByLabelText('Líder del conteo'), { target: { value: 'l1' } });
  fireEvent.change(within(dialogo).getByLabelText('Fecha'), { target: { value: '2026-10-12' } });
  return dialogo;
}

describe('Scheduling a test count', () => {
  it('ADMIN marks the count as a test', async () => {
    login('ADMIN');
    render(<ConteosContainer />);
    const dialogo = await programar();

    const casilla = within(dialogo).getByRole('checkbox', { name: 'Es de prueba' });
    expect(casilla).not.toBeChecked();
    fireEvent.click(casilla);
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Programar' }));

    await waitFor(() => expect(api.programarConteo).toHaveBeenCalledWith({
      sucursal_id: 's1', lider_id: 'l1', fecha_programada: '2026-10-12', es_prueba: true,
    }));
  });

  it('rescheduling shows no test checkbox', async () => {
    login('ADMIN');
    render(<ConteosContainer />);

    fireEvent.click(await screen.findByRole('button', { name: 'Reprogramar Quilichao' }));
    const dialogo = await screen.findByRole('dialog');

    expect(within(dialogo).queryByRole('checkbox', { name: 'Es de prueba' })).not.toBeInTheDocument();
  });
});

describe('The list', () => {
  it('ADMIN shows test counts on demand, each with a PRUEBA badge', async () => {
    login('ADMIN');
    render(<ConteosContainer />);

    expect(await screen.findByText('Quilichao')).toBeInTheDocument();
    expect(screen.queryByText('Cali Sur')).not.toBeInTheDocument();
    expect(screen.queryByText('PRUEBA')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Mostrar pruebas' }));

    expect(await screen.findByText('Cali Sur')).toBeInTheDocument();
    expect(api.listarConteos).toHaveBeenLastCalledWith({ incluir_pruebas: true });
    expect(screen.getAllByText('PRUEBA')).toHaveLength(1);
  });

  it.each(['LIDER_INVENTARIOS', 'GERENCIA'])('%s has no test toggle', async (rol) => {
    login(rol);
    render(<ConteosContainer />);

    expect(await screen.findByText('Quilichao')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Mostrar pruebas' })).not.toBeInTheDocument();
  });

  it('ADMIN deletes a test count after confirming, never a real one', async () => {
    login('ADMIN');
    render(<ConteosContainer />);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Mostrar pruebas' }));
    await screen.findByText('Cali Sur');

    expect(screen.queryByRole('button', { name: 'Borrar conteo de prueba Quilichao' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Borrar conteo de prueba Cali Sur' }));
    const dialogo = await screen.findByRole('dialog');
    expect(api.borrarConteoPrueba).not.toHaveBeenCalled();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Borrar conteo de prueba' }));

    await waitFor(() => expect(api.borrarConteoPrueba).toHaveBeenCalledWith('c9'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('One test count', () => {
  it('shows the PRUEBA badge and lets ADMIN delete it', async () => {
    login('ADMIN');
    api.obtenerConteo.mockResolvedValue(PRUEBA);
    render(<ConteoDetalleContainer conteoId="c9" />);

    expect(await screen.findByText('PRUEBA')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Borrar conteo de prueba' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Borrar conteo de prueba' }));

    await waitFor(() => expect(api.borrarConteoPrueba).toHaveBeenCalledWith('c9'));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/inventarios/conteos'));
  });

  it('a real count has no badge and no delete button', async () => {
    login('ADMIN');
    api.obtenerConteo.mockResolvedValue({ ...PRUEBA, es_prueba: false });
    render(<ConteoDetalleContainer conteoId="c9" />);

    expect(await screen.findByText(/Conteo anulado/)).toBeInTheDocument();
    expect(screen.queryByText('PRUEBA')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Borrar conteo de prueba' })).not.toBeInTheDocument();
  });
});
