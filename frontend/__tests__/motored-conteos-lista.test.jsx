/**
 * Conteos list and scheduling (odd/motored-conteos-inventario, WU11): ADMIN
 * schedules, reschedules and annuls; the leader only opens its own conteos;
 * GERENCIA reads with no action buttons. Errors show the backend mensaje.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import * as api from '../lib/motored/conteosApi';
import ConteosContainer from '../components/motored/inventarios/ConteosContainer';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/inventarios/conteos',
}));
jest.mock('../lib/motored/conteosApi');

const CONTEOS = [
  {
    id: 'c1', tipo: 'TOTAL', estado: 'PROGRAMADO', origen: 'MANUAL', fecha_programada: '2026-10-12',
    sucursal: { id: 's1', nombre: 'Quilichao' }, lider: { id: 'l1', nombre: 'Laura Líder' },
  },
  {
    id: 'c2', tipo: 'TOTAL', estado: 'EN_CONTEO', origen: 'MANUAL', fecha_programada: '2026-10-09',
    sucursal: { id: 's2', nombre: 'Cali Sur' }, lider: { id: 'l1', nombre: 'Laura Líder' },
    iniciado_en: '2026-10-09T12:58:00Z', progreso: { refs_universo: 1284, refs_contadas: 796 },
  },
];
const SUCURSALES = [
  { id: 's1', nombre: 'Quilichao', vigencia_horas: 6,
    inventario: { carga_id: 'k1', fecha_corte: '2026-10-09', aplicado_en: '2026-10-09T12:55:00Z', antiguedad_horas: '2.0' } },
  { id: 's2', nombre: 'Cali Sur', vigencia_horas: 6, inventario: null },
];
const LIDERES = [{ id: 'l1', nombre: 'Laura Líder', email: 'l@x.co' }];

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

beforeEach(() => {
  sessionStorage.clear();
  jest.resetAllMocks();
  api.listarConteos.mockResolvedValue(CONTEOS);
  api.listarSucursalesConteo.mockResolvedValue(SUCURSALES);
  api.listarLideres.mockResolvedValue(LIDERES);
});

describe('Progress in the list', () => {
  it('shows how much of an open conteo is counted', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteosContainer />);

    expect(await screen.findByText(/Avance 62 % \(796 de 1\.284\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/^Avance/)).toHaveLength(1);
  });
});

describe('Conteos list per role', () => {
  it('ADMIN sees every conteo and can schedule, reschedule and annul', async () => {
    login('ADMIN');
    render(<ConteosContainer />);

    expect(await screen.findByText('Quilichao')).toBeInTheDocument();
    expect(screen.getByText('Cali Sur')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Programar conteo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reprogramar Quilichao' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^Anular/ })).toHaveLength(2);
  });

  it('the leader opens its conteos but cannot schedule', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteosContainer />);

    expect(await screen.findByText('Quilichao')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Programar conteo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Anular/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Abrir Quilichao' }));
    expect(pushMock).toHaveBeenCalledWith('/motored/inventarios/conteos/c1');
    expect(api.listarLideres).not.toHaveBeenCalled();
  });

  it('GERENCIA reads with no action buttons', async () => {
    login('GERENCIA');
    render(<ConteosContainer />);

    expect(await screen.findByText('Quilichao')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Programar conteo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Reprogramar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Anular/ })).not.toBeInTheDocument();
  });

  it('filters by estado', async () => {
    login('ADMIN');
    render(<ConteosContainer />);
    await screen.findByText('Quilichao');

    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'EN_CONTEO' } });

    await waitFor(() => expect(api.listarConteos).toHaveBeenLastCalledWith({ estado: 'EN_CONTEO' }));
  });

  it('shows the backend mensaje when the list fails', async () => {
    login('ADMIN');
    api.listarConteos.mockRejectedValue(new Error('El servicio no está disponible en este momento.'));
    render(<ConteosContainer />);

    expect(await screen.findByRole('alert')).toHaveTextContent('El servicio no está disponible en este momento.');
  });
});

describe('Programar conteo', () => {
  it('posts store, leader and date, then reloads the list', async () => {
    login('ADMIN');
    api.programarConteo.mockResolvedValue({ id: 'c3' });
    render(<ConteosContainer />);
    fireEvent.click(await screen.findByRole('button', { name: 'Programar conteo' }));

    const dialogo = await screen.findByRole('dialog');
    await within(dialogo).findByRole('option', { name: 'Laura Líder' });
    fireEvent.change(within(dialogo).getByLabelText('Tienda'), { target: { value: 's1' } });
    fireEvent.change(within(dialogo).getByLabelText('Líder del conteo'), { target: { value: 'l1' } });
    fireEvent.change(within(dialogo).getByLabelText('Fecha'), { target: { value: '2026-10-12' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Programar' }));

    await waitFor(() => expect(api.programarConteo).toHaveBeenCalledWith({
      sucursal_id: 's1', lider_id: 'l1', fecha_programada: '2026-10-12', es_prueba: false,
    }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.listarConteos).toHaveBeenCalledTimes(2);
  });

  it('styles every option for the dark theme', async () => {
    login('ADMIN');
    render(<ConteosContainer />);
    fireEvent.click(await screen.findByRole('button', { name: 'Programar conteo' }));
    const dialogo = await screen.findByRole('dialog');
    await within(dialogo).findByRole('option', { name: 'Laura Líder' });

    document.querySelectorAll('option').forEach((opcion) => {
      expect(opcion.style.color).not.toBe('');
    });
  });

  it('shows the inventory age of the chosen store', async () => {
    login('ADMIN');
    render(<ConteosContainer />);
    fireEvent.click(await screen.findByRole('button', { name: 'Programar conteo' }));
    const dialogo = await screen.findByRole('dialog');
    await within(dialogo).findByRole('option', { name: 'Laura Líder' });

    fireEvent.change(within(dialogo).getByLabelText('Tienda'), { target: { value: 's2' } });
    expect(within(dialogo).getByText(/no tiene inventario cargado/i)).toBeInTheDocument();
  });

  it('shows the backend mensaje when scheduling fails', async () => {
    login('ADMIN');
    api.programarConteo.mockRejectedValue(new Error('Esa tienda ya tiene un conteo total abierto.'));
    render(<ConteosContainer />);
    fireEvent.click(await screen.findByRole('button', { name: 'Programar conteo' }));
    const dialogo = await screen.findByRole('dialog');
    await within(dialogo).findByRole('option', { name: 'Laura Líder' });
    fireEvent.change(within(dialogo).getByLabelText('Tienda'), { target: { value: 's1' } });
    fireEvent.change(within(dialogo).getByLabelText('Líder del conteo'), { target: { value: 'l1' } });
    fireEvent.change(within(dialogo).getByLabelText('Fecha'), { target: { value: '2026-10-12' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Programar' }));

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('Esa tienda ya tiene un conteo total abierto.');
  });
});

describe('Reprogramar and anular (ADMIN)', () => {
  it('reschedules the date and the leader', async () => {
    login('ADMIN');
    api.reprogramarConteo.mockResolvedValue({});
    render(<ConteosContainer />);
    fireEvent.click(await screen.findByRole('button', { name: 'Reprogramar Quilichao' }));
    const dialogo = await screen.findByRole('dialog');
    await within(dialogo).findByRole('option', { name: 'Laura Líder' });

    fireEvent.change(within(dialogo).getByLabelText('Fecha'), { target: { value: '2026-10-20' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }));

    await waitFor(() => expect(api.reprogramarConteo).toHaveBeenCalledWith('c1', {
      fecha_programada: '2026-10-20', lider_id: 'l1',
    }));
  });

  it('annuls only with a reason', async () => {
    login('ADMIN');
    api.anularConteo.mockResolvedValue({});
    render(<ConteosContainer />);
    fireEvent.click(await screen.findByRole('button', { name: 'Anular Cali Sur' }));
    const dialogo = await screen.findByRole('dialog');
    const confirmar = within(dialogo).getByRole('button', { name: 'Anular conteo' });
    expect(confirmar).toBeDisabled();

    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'Tienda en obra' } });
    fireEvent.click(confirmar);

    await waitFor(() => expect(api.anularConteo).toHaveBeenCalledWith('c2', 'Tienda en obra'));
  });
});
