/**
 * Usuarios: the asesor's personal report link
 * (odd/motored-reporte-diario-asesor, T3a). Each row shows "Enlace del
 * informe" (Activo · último acceso, or Sin enlace). The ADMIN can generate
 * a new one (it cancels the old one and Lore sends the new one) or cancel
 * it, both after a confirmation. Without an approved cédula or a linked
 * Telegram the actions are disabled and the row says why.
 */
import React from 'react';
import {
  render, screen, fireEvent, waitFor, within,
} from '@testing-library/react';

const mockListUsuarios = jest.fn();
const mockListSolicitudes = jest.fn();
const mockObtener = jest.fn();
const mockGenerar = jest.fn();
const mockAnular = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listUsuarios: (...a) => mockListUsuarios(...a),
  listSolicitudesPendientes: (...a) => mockListSolicitudes(...a),
  obtenerEnlaceInforme: (...a) => mockObtener(...a),
  generarEnlaceInforme: (...a) => mockGenerar(...a),
  anularEnlaceInforme: (...a) => mockAnular(...a),
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

const TOOLTIP = 'Enlace secreto y permanente que Lore le envía al asesor '
  + 'para ver su informe. Al abrirlo debe escribir su cédula. Generar uno '
  + 'nuevo anula el anterior.';
const base = {
  role: 'ASESOR_MOSTRADOR', activo: true, status: 'approved', email: null,
  phone: '3001234567', telegram_vinculado: true, bloqueado_hasta: null,
  cedula: '79845123', cedula_aprobada: true, cedula_en_maestro: true,
};
const CON_ENLACE = { ...base, id: 'u1', nombre: 'Ana Activa' };
const SIN_ENLACE = { ...base, id: 'u2', nombre: 'Beto Nuevo', cedula: '111' };
const SIN_CEDULA = {
  ...base, id: 'u3', nombre: 'Sara Sin', cedula: null,
  cedula_aprobada: false, cedula_en_maestro: null,
};
const PENDIENTE = {
  ...base, id: 'u4', nombre: 'Pablo Pendiente', cedula_aprobada: false,
};
const SIN_TELEGRAM = {
  ...base, id: 'u5', nombre: 'Tomás Telegram', telegram_vinculado: false,
};
const NUNCA = {
  ...base, id: 'u6', nombre: 'Nora Nunca', cedula: '222',
};

const ESTADOS = {
  u1: {
    activo: true, creado_en: '2026-10-01T14:00:00+00:00',
    ultimo_acceso_en: '2026-10-07T14:30:00+00:00',
  },
  u2: { activo: false, creado_en: null, ultimo_acceso_en: null },
  u6: {
    activo: true, creado_en: '2026-10-01T14:00:00+00:00',
    ultimo_acceso_en: null,
  },
};

function fila(nombre) {
  return screen.getByText(nombre).closest('tr');
}

async function renderPage() {
  render(<UsuariosPage />);
  await waitFor(() => expect(within(fila('Ana Activa'))
    .getByText(/Activo · último acceso/)).toBeInTheDocument());
}

beforeEach(() => {
  jest.clearAllMocks();
  mockListUsuarios.mockResolvedValue([
    CON_ENLACE, SIN_ENLACE, SIN_CEDULA, PENDIENTE, SIN_TELEGRAM, NUNCA,
  ]);
  mockListSolicitudes.mockResolvedValue([]);
  mockObtener.mockImplementation((id) => Promise.resolve(ESTADOS[id]));
  mockGenerar.mockResolvedValue({
    activo: true, creado_en: '2026-10-08T15:00:00+00:00',
    ultimo_acceso_en: null,
  });
  mockAnular.mockResolvedValue({
    activo: false, creado_en: null, ultimo_acceso_en: null,
  });
  sessionStorage.clear();
  sessionStorage.setItem(
    MOTORED_USER_KEY, JSON.stringify({ id: 'admin', role: 'ADMIN' }));
  window.confirm = jest.fn(() => true);
});

describe('Gestión de usuarios: enlace del informe', () => {
  it('shows the column with its tooltip and each row state', async () => {
    await renderPage();
    expect(screen.getAllByRole('note', { name: TOOLTIP }).length)
      .toBeGreaterThan(0);
    expect(within(fila('Ana Activa'))
      .getByText('Activo · último acceso 07/10/2026 09:30'))
      .toBeInTheDocument();
    await waitFor(() => expect(within(fila('Nora Nunca'))
      .getByText('Activo · último acceso nunca')).toBeInTheDocument());
    expect(within(fila('Beto Nuevo')).getByText('Sin enlace'))
      .toBeInTheDocument();
  });

  it('only asks the backend for eligible rows', async () => {
    await renderPage();
    const pedidos = mockObtener.mock.calls.map(([id]) => id).sort();
    expect(pedidos).toEqual(['u1', 'u2', 'u6']);
  });

  it('disables the actions with a hint when not eligible', async () => {
    await renderPage();
    const casos = [
      ['Sara Sin', 'Necesita cédula aprobada'],
      ['Pablo Pendiente', 'Necesita cédula aprobada'],
      ['Tomás Telegram', 'Necesita Telegram vinculado'],
    ];
    casos.forEach(([nombre, pista]) => {
      const row = fila(nombre);
      expect(within(row).getByText(pista)).toBeInTheDocument();
      expect(within(row).getByRole('button', { name: 'Generar enlace nuevo' }))
        .toBeDisabled();
    });
  });

  it('generates a new link after confirming and shows its state', async () => {
    await renderPage();
    fireEvent.click(within(fila('Beto Nuevo'))
      .getByRole('button', { name: 'Generar enlace nuevo' }));

    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(
      /anula el enlace anterior y Lore le envía el nuevo/));
    await waitFor(() => expect(mockGenerar).toHaveBeenCalledWith('u2'));
    await waitFor(() => expect(within(fila('Beto Nuevo'))
      .getByText('Activo · último acceso nunca')).toBeInTheDocument());
  });

  it('does nothing when the confirmation is cancelled', async () => {
    window.confirm = jest.fn(() => false);
    await renderPage();
    fireEvent.click(within(fila('Ana Activa'))
      .getByRole('button', { name: 'Generar enlace nuevo' }));
    fireEvent.click(within(fila('Ana Activa'))
      .getByRole('button', { name: 'Anular enlace' }));

    expect(window.confirm).toHaveBeenCalledTimes(2);
    expect(mockGenerar).not.toHaveBeenCalled();
    expect(mockAnular).not.toHaveBeenCalled();
  });

  it('cancels the link after confirming', async () => {
    await renderPage();
    fireEvent.click(within(fila('Ana Activa'))
      .getByRole('button', { name: 'Anular enlace' }));

    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringMatching(/Anular el enlace del informe de "Ana Activa"/));
    await waitFor(() => expect(mockAnular).toHaveBeenCalledWith('u1'));
    await waitFor(() => expect(within(fila('Ana Activa'))
      .getByText('Sin enlace')).toBeInTheDocument());
  });

  it('offers "Anular enlace" only for an active link', async () => {
    await renderPage();
    expect(within(fila('Beto Nuevo'))
      .queryByRole('button', { name: 'Anular enlace' })).toBeNull();
  });

  it('shows the backend error when the send fails', async () => {
    mockGenerar.mockRejectedValue(new Error(
      'No se pudo enviar el enlace por Lore. El enlace anterior sigue igual.'));
    await renderPage();
    fireEvent.click(within(fila('Ana Activa'))
      .getByRole('button', { name: 'Generar enlace nuevo' }));

    await waitFor(() => expect(within(fila('Ana Activa'))
      .getByText(/El enlace anterior sigue igual/)).toBeInTheDocument());
    expect(within(fila('Ana Activa'))
      .getByText('Activo · último acceso 07/10/2026 09:30'))
      .toBeInTheDocument();
  });
});
