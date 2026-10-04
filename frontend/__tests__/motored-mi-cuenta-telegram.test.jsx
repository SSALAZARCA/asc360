/**
 * Motored "Mi cuenta": ADMIN and COMPRAS link their own Telegram (the early
 * data-age warning reaches COMPRAS through the Lore bot). Other roles never
 * see the panel and never call the endpoints.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/mi-cuenta',
}));

import MiCuentaContainer from '../components/motored/mi-cuenta/MiCuentaContainer';

const CODIGO = { codigo: 'ABCD2345', expira_en: '2026-10-03T20:10:00+00:00' };

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('Telegram link panel', () => {
  it.each(['COMPRAS', 'ADMIN'])('%s can get a one-time code when not linked', async (role) => {
    setSession(role);
    const calls = installFetch({
      'GET /usuarios/me/telegram': jsonRes({ telegram_vinculado: false }),
      'POST /usuarios/me/telegram/codigo': jsonRes(CODIGO),
    });
    render(<MiCuentaContainer />);

    const boton = await screen.findByRole('button', { name: 'Vincular Telegram' });
    expect(boton.style.minHeight).toBe('44px');
    fireEvent.click(boton);

    expect(await screen.findByText('ABCD2345')).toBeInTheDocument();
    expect(screen.getByText(/\/vincular/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST' && c.path === '/usuarios/me/telegram/codigo')).toBe(true);
  });

  it('offers to unlink when already linked, then shows it as not linked', async () => {
    setSession('COMPRAS');
    const calls = installFetch({
      'GET /usuarios/me/telegram': jsonRes({ telegram_vinculado: true }),
      'DELETE /usuarios/me/telegram': jsonRes({ telegram_vinculado: false }),
    });
    render(<MiCuentaContainer />);

    expect(await screen.findByText('Telegram vinculado.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Desvincular Telegram' }));

    expect(await screen.findByRole('button', { name: 'Vincular Telegram' })).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'DELETE')).toBe(true);
  });

  it('shows the server error when the code cannot be generated', async () => {
    setSession('COMPRAS');
    installFetch({
      'GET /usuarios/me/telegram': jsonRes({ telegram_vinculado: false }),
      'POST /usuarios/me/telegram/codigo': jsonRes({ detail: 'No se pudo' }, 500),
    });
    render(<MiCuentaContainer />);

    fireEvent.click(await screen.findByRole('button', { name: 'Vincular Telegram' }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it.each(['SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'])('is hidden for %s and calls nothing', async (role) => {
    setSession(role);
    const calls = installFetch({});
    render(<MiCuentaContainer />);

    await waitFor(() => expect(screen.getByText('Cambiar mi contraseña')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Vincular Telegram' })).toBeNull();
    expect(calls).toHaveLength(0);
  });
});
