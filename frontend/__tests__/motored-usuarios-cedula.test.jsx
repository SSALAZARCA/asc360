/**
 * Usuarios: the cédula that links a usuario to the vendedor master
 * (odd/motored-reporte-diario-asesor, T1). Gestión de usuarios shows its
 * state (Aprobada / Pendiente / Sin cédula); the ADMIN adds, edits, clears,
 * approves or rejects it. Lore registrations show the cédula the asesor
 * typed, and approving the registration never approves the cédula.
 */
import React from 'react';
import {
  render, screen, fireEvent, waitFor, within,
} from '@testing-library/react';

const mockListUsuarios = jest.fn();
const mockListSolicitudes = jest.fn();
const mockFijar = jest.fn();
const mockAprobarCedula = jest.fn();
const mockRechazarCedula = jest.fn();
const mockQuitar = jest.fn();
const mockAprobarUsuario = jest.fn();
const mockCreateUsuario = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listUsuarios: (...a) => mockListUsuarios(...a),
  listSolicitudesPendientes: (...a) => mockListSolicitudes(...a),
  fijarCedulaUsuario: (...a) => mockFijar(...a),
  aprobarCedulaUsuario: (...a) => mockAprobarCedula(...a),
  rechazarCedulaUsuario: (...a) => mockRechazarCedula(...a),
  quitarCedulaUsuario: (...a) => mockQuitar(...a),
  aprobarUsuario: (...a) => mockAprobarUsuario(...a),
  createUsuario: (...a) => mockCreateUsuario(...a),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/usuarios',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div />;
  M.displayName = 'M';
  return M;
});

import UsuariosPage from '../app/motored/usuarios/page';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const TOOLTIP = 'La cédula vincula al usuario con el maestro de Vendedores '
  + 'para enviarle su reporte diario por Lore. Solo se usa cuando está '
  + 'aprobada.';
const base = {
  role: 'ASESOR_MOSTRADOR', activo: true, status: 'approved', email: null,
  phone: '3001234567', telegram_vinculado: true, bloqueado_hasta: null,
};
const APROBADA = {
  ...base, id: 'u1', nombre: 'Ana Aprobada', cedula: '79845123',
  cedula_aprobada: true, cedula_en_maestro: true,
};
const PENDIENTE = {
  ...base, id: 'u2', nombre: 'Pablo Pendiente', cedula: '555666',
  cedula_aprobada: false, cedula_en_maestro: false,
};
const SIN = {
  ...base, id: 'u3', nombre: 'Sara Sin', cedula: null,
  cedula_aprobada: false, cedula_en_maestro: null,
};
const SOLICITUD = {
  ...base, id: 's1', nombre: 'Nuevo Lore', status: 'pending',
  cedula: '1130123456', cedula_aprobada: false, cedula_en_maestro: true,
};

function fila(nombre) {
  return screen.getByText(nombre).closest('tr');
}

async function renderPage() {
  render(<UsuariosPage />);
  await waitFor(() => expect(screen.getByText('Ana Aprobada'))
    .toBeInTheDocument());
}

beforeEach(() => {
  jest.clearAllMocks();
  mockListUsuarios.mockResolvedValue([APROBADA, PENDIENTE, SIN]);
  mockListSolicitudes.mockResolvedValue([SOLICITUD]);
  [mockFijar, mockAprobarCedula, mockRechazarCedula, mockQuitar,
    mockAprobarUsuario, mockCreateUsuario].forEach((m) => m.mockResolvedValue({}));
  sessionStorage.clear();
  sessionStorage.setItem(
    MOTORED_USER_KEY, JSON.stringify({ id: 'admin', role: 'ADMIN' }));
  window.confirm = jest.fn(() => true);
});

describe('Gestión de usuarios: cédula', () => {
  it('shows the column with its tooltip and each state', async () => {
    await renderPage();
    expect(screen.getAllByRole('note', { name: TOOLTIP }).length)
      .toBeGreaterThan(0);
    expect(within(fila('Ana Aprobada')).getByText('Aprobada'))
      .toBeInTheDocument();
    expect(within(fila('Ana Aprobada')).getByText('79845123'))
      .toBeInTheDocument();
    expect(within(fila('Pablo Pendiente')).getByText('Pendiente'))
      .toBeInTheDocument();
    expect(within(fila('Sara Sin')).getByText('Sin cédula'))
      .toBeInTheDocument();
  });

  it('flags a pending cédula outside the vendedor master', async () => {
    await renderPage();
    expect(within(fila('Pablo Pendiente'))
      .getByText(/No está en el maestro de Vendedores/)).toBeInTheDocument();
    expect(within(fila('Ana Aprobada'))
      .queryByText(/No está en el maestro/)).toBeNull();
  });

  it('adds a cédula from the row editor and reloads', async () => {
    await renderPage();
    const row = fila('Sara Sin');
    fireEvent.click(within(row).getByRole('button', { name: 'Agregar cédula' }));
    fireEvent.change(within(row).getByLabelText('Cédula de Sara Sin'), {
      target: { value: '1.130.123.456' },
    });
    fireEvent.click(within(row).getByRole('button', { name: 'Guardar cédula' }));

    await waitFor(() => expect(mockFijar)
      .toHaveBeenCalledWith('u3', '1.130.123.456'));
    await waitFor(() => expect(mockListUsuarios).toHaveBeenCalledTimes(2));
  });

  it('edits an existing cédula starting from its value', async () => {
    await renderPage();
    const row = fila('Ana Aprobada');
    fireEvent.click(within(row).getByRole('button', { name: 'Editar cédula' }));
    const input = within(row).getByLabelText('Cédula de Ana Aprobada');
    expect(input).toHaveValue('79845123');
    fireEvent.change(input, { target: { value: '79845124' } });
    fireEvent.click(within(row).getByRole('button', { name: 'Guardar cédula' }));

    await waitFor(() => expect(mockFijar)
      .toHaveBeenCalledWith('u1', '79845124'));
  });

  it('shows the API message when saving fails', async () => {
    mockFijar.mockRejectedValueOnce(
      new Error('La cédula ya está aprobada para el usuario Ana Aprobada.'));
    await renderPage();
    const row = fila('Sara Sin');
    fireEvent.click(within(row).getByRole('button', { name: 'Agregar cédula' }));
    fireEvent.change(within(row).getByLabelText('Cédula de Sara Sin'), {
      target: { value: '79845123' },
    });
    fireEvent.click(within(row).getByRole('button', { name: 'Guardar cédula' }));

    expect(await screen.findByText(
      'La cédula ya está aprobada para el usuario Ana Aprobada.'))
      .toBeInTheDocument();
  });

  it('approves and rejects a pending cédula', async () => {
    await renderPage();
    const row = fila('Pablo Pendiente');
    fireEvent.click(within(row).getByRole('button', { name: 'Aprobar cédula' }));
    await waitFor(() => expect(mockAprobarCedula).toHaveBeenCalledWith('u2'));

    fireEvent.click(
      within(fila('Pablo Pendiente'))
        .getByRole('button', { name: 'Rechazar cédula' }));
    await waitFor(() => expect(mockRechazarCedula)
      .toHaveBeenCalledWith('u2'));
  });

  it('offers approve/reject only on a pending cédula', async () => {
    await renderPage();
    expect(within(fila('Ana Aprobada'))
      .queryByRole('button', { name: 'Aprobar cédula' })).toBeNull();
    expect(within(fila('Sara Sin'))
      .queryByRole('button', { name: 'Rechazar cédula' })).toBeNull();
  });

  it('clears an approved cédula after confirming', async () => {
    await renderPage();
    fireEvent.click(within(fila('Ana Aprobada'))
      .getByRole('button', { name: 'Quitar cédula' }));

    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(mockQuitar).toHaveBeenCalledWith('u1'));
  });

  it('does not clear when the confirm is cancelled', async () => {
    window.confirm = jest.fn(() => false);
    await renderPage();
    fireEvent.click(within(fila('Ana Aprobada'))
      .getByRole('button', { name: 'Quitar cédula' }));

    expect(mockQuitar).not.toHaveBeenCalled();
  });
});

describe('Solicitudes pendientes: cédula from Lore', () => {
  it('shows the cédula the asesor typed with its state', async () => {
    await renderPage();
    const row = fila('Nuevo Lore');
    expect(within(row).getByText('1130123456')).toBeInTheDocument();
    expect(within(row).getByText('Pendiente')).toBeInTheDocument();
  });

  it('approving the registration does not approve the cédula', async () => {
    await renderPage();
    fireEvent.click(within(fila('Nuevo Lore'))
      .getByRole('button', { name: 'Aprobar' }));

    await waitFor(() => expect(mockAprobarUsuario).toHaveBeenCalledWith('s1'));
    expect(mockAprobarCedula).not.toHaveBeenCalled();
  });

  it('has its own explicit Aprobar cédula action', async () => {
    await renderPage();
    fireEvent.click(within(fila('Nuevo Lore'))
      .getByRole('button', { name: 'Aprobar cédula' }));

    await waitFor(() => expect(mockAprobarCedula).toHaveBeenCalledWith('s1'));
    await waitFor(() => expect(mockListSolicitudes).toHaveBeenCalledTimes(2));
  });
});

describe('Crear usuario: optional cédula', () => {
  function llenarFormulario() {
    fireEvent.change(screen.getByLabelText('Nombre'), {
      target: { value: 'Nuevo Usuario' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'nuevo@test.co' },
    });
    fireEvent.change(screen.getByLabelText('Contraseña'), {
      target: { value: 'clave-segura-123' },
    });
    fireEvent.change(
      screen.getByLabelText('Confirmar contraseña del usuario'),
      { target: { value: 'clave-segura-123' } });
  }

  it('has a Cédula field with the tooltip', async () => {
    await renderPage();
    const form = screen.getByRole('button', { name: 'Crear usuario' })
      .closest('form');
    expect(within(form).getByLabelText('Cédula (opcional)'))
      .toBeInTheDocument();
    expect(within(form).getByRole('note', { name: TOOLTIP }))
      .toBeInTheDocument();
  });

  it('sends the cédula when filled', async () => {
    await renderPage();
    llenarFormulario();
    fireEvent.change(screen.getByLabelText('Cédula (opcional)'), {
      target: { value: ' 79.845.123 ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Crear usuario' }));

    await waitFor(() => expect(mockCreateUsuario).toHaveBeenCalledWith(
      expect.objectContaining({ cedula: '79.845.123' })));
  });

  it('omits the cédula when left empty', async () => {
    await renderPage();
    llenarFormulario();
    fireEvent.click(screen.getByRole('button', { name: 'Crear usuario' }));

    await waitFor(() => expect(mockCreateUsuario).toHaveBeenCalled());
    expect(mockCreateUsuario.mock.calls[0][0]).not.toHaveProperty('cedula');
  });
});
