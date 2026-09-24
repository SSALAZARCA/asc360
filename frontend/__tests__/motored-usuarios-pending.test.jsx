/**
 * Tests for the Usuarios screen's new surface (sdd/motored-ventas-perdidas-
 * bot, Phase 4, tasks 4.6/4.7; design D5):
 *   - Pending-requests list (`status='pending'` advisors) with
 *     Aprobar/Rechazar actions calling `resolver_solicitud` via
 *     `aprobarUsuario`/`rechazarUsuario`.
 *   - "Vincular Telegram para notificaciones" action on the authenticated
 *     ADMIN's OWN row (matched by id against `motored_user` in
 *     sessionStorage) -- never on another user's row. Generates and
 *     displays a one-time code (`generarCodigoTelegram`), and offers
 *     "Desvincular" once already linked (`desvincularTelegram`).
 *
 * Mirrors this project's established Motored mocking convention: mock
 * `lib/motored/api`, import the component after the mock is registered.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListUsuarios = jest.fn();
const mockListSolicitudesPendientes = jest.fn();
const mockAprobarUsuario = jest.fn();
const mockRechazarUsuario = jest.fn();
const mockGenerarCodigoTelegram = jest.fn();
const mockDesvincularTelegram = jest.fn();
const mockCreateUsuario = jest.fn();
const mockDeactivateUsuario = jest.fn();
const pushMock = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listUsuarios: (...args) => mockListUsuarios(...args),
  listSolicitudesPendientes: (...args) => mockListSolicitudesPendientes(...args),
  aprobarUsuario: (...args) => mockAprobarUsuario(...args),
  rechazarUsuario: (...args) => mockRechazarUsuario(...args),
  generarCodigoTelegram: (...args) => mockGenerarCodigoTelegram(...args),
  desvincularTelegram: (...args) => mockDesvincularTelegram(...args),
  createUsuario: (...args) => mockCreateUsuario(...args),
  deactivateUsuario: (...args) => mockDeactivateUsuario(...args),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/usuarios',
}));

jest.mock('../components/motored/MotoredSidebar', () => {
  const MockMotoredSidebar = () => <div data-testid="mock-motored-sidebar" />;
  MockMotoredSidebar.displayName = 'MockMotoredSidebar';
  return MockMotoredSidebar;
});

import UsuariosPage from '../app/motored/usuarios/page';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const ADMIN_ID = 'admin-1';
const OTHER_ADMIN_ID = 'admin-2';

const ADMIN_SELF = {
  id: ADMIN_ID, nombre: 'Ana Admin', email: 'ana@x.com', role: 'ADMIN',
  activo: true, status: 'approved', phone: null, telegram_vinculado: false,
};

const ADMIN_OTHER = {
  id: OTHER_ADMIN_ID, nombre: 'Beto Admin', email: 'beto@x.com', role: 'ADMIN',
  activo: true, status: 'approved', phone: null, telegram_vinculado: false,
};

const PENDING_ADVISOR = {
  id: 'asesor-1', nombre: 'Juan Asesor', email: null, role: 'ASESOR_MOSTRADOR',
  activo: true, status: 'pending', phone: '3001234567', telegram_vinculado: true,
};

beforeEach(() => {
  mockListUsuarios.mockReset().mockResolvedValue([ADMIN_SELF, ADMIN_OTHER]);
  mockListSolicitudesPendientes.mockReset().mockResolvedValue([PENDING_ADVISOR]);
  mockAprobarUsuario.mockReset().mockResolvedValue({ ...PENDING_ADVISOR, status: 'approved' });
  mockRechazarUsuario.mockReset().mockResolvedValue({ ...PENDING_ADVISOR, status: 'rejected' });
  mockGenerarCodigoTelegram.mockReset().mockResolvedValue({
    codigo: 'ABC23456', expira_en: '2026-09-24T15:10:00+00:00',
  });
  mockDesvincularTelegram.mockReset().mockResolvedValue({ ...ADMIN_SELF, telegram_vinculado: false });
  pushMock.mockClear();
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ id: ADMIN_ID, nombre: 'Ana Admin', role: 'ADMIN' }));
});

describe('UsuariosPage — solicitudes pendientes', () => {
  it('renders the pending advisor with Aprobar/Rechazar actions', async () => {
    render(<UsuariosPage />);

    await waitFor(() => expect(screen.getByText('Juan Asesor')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Aprobar' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rechazar' })).toBeInTheDocument();
  });

  it('Aprobar calls aprobarUsuario with the row id and reloads the pending list', async () => {
    render(<UsuariosPage />);
    await waitFor(() => expect(screen.getByText('Juan Asesor')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Aprobar' }));

    await waitFor(() => expect(mockAprobarUsuario).toHaveBeenCalledWith('asesor-1'));
    await waitFor(() => expect(mockListSolicitudesPendientes).toHaveBeenCalledTimes(2));
  });

  it('Rechazar calls rechazarUsuario with the row id', async () => {
    render(<UsuariosPage />);
    await waitFor(() => expect(screen.getByText('Juan Asesor')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Rechazar' }));

    await waitFor(() => expect(mockRechazarUsuario).toHaveBeenCalledWith('asesor-1'));
  });

  it('shows an honest empty state when there are no pending requests', async () => {
    mockListSolicitudesPendientes.mockResolvedValue([]);
    render(<UsuariosPage />);

    await waitFor(() => expect(screen.getByText('No hay solicitudes pendientes.')).toBeInTheDocument());
  });
});

describe('UsuariosPage — vinculación de Telegram', () => {
  it('shows "Vincular Telegram" only on the authenticated ADMIN\'s own row', async () => {
    render(<UsuariosPage />);
    await waitFor(() => expect(screen.getByText('Ana Admin')).toBeInTheDocument());

    const filaPropia = screen.getByText('Ana Admin').closest('tr');
    const filaAjena = screen.getByText('Beto Admin').closest('tr');

    expect(within(filaPropia).getByRole('button', { name: 'Vincular Telegram' })).toBeInTheDocument();
    expect(within(filaAjena).queryByRole('button', { name: 'Vincular Telegram' })).not.toBeInTheDocument();
    expect(within(filaAjena).queryByRole('button', { name: 'Desvincular Telegram' })).not.toBeInTheDocument();
  });

  it('generates and displays a one-time code on click', async () => {
    render(<UsuariosPage />);
    await waitFor(() => expect(screen.getByText('Ana Admin')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Vincular Telegram' }));

    await waitFor(() => expect(mockGenerarCodigoTelegram).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText(/ABC23456/)).toBeInTheDocument());
  });

  it('shows "Desvincular Telegram" for a row already linked, and calls desvincularTelegram on click', async () => {
    mockListUsuarios.mockResolvedValue([{ ...ADMIN_SELF, telegram_vinculado: true }, ADMIN_OTHER]);
    render(<UsuariosPage />);
    await waitFor(() => expect(screen.getByText('Ana Admin')).toBeInTheDocument());

    const boton = screen.getByRole('button', { name: 'Desvincular Telegram' });
    fireEvent.click(boton);

    await waitFor(() => expect(mockDesvincularTelegram).toHaveBeenCalledTimes(1));
  });
});
