/**
 * Opening the bare /motored address (a bookmark, the domain, a typed URL)
 * lands on the right place: Inicio with a session, login without one.
 */
import React from 'react';
import { render, waitFor } from '@testing-library/react';

const mockReplace = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockReplace }),
}));

import MotoredRaiz from '../app/motored/page';
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

beforeEach(() => {
  mockReplace.mockReset();
  sessionStorage.clear();
});

function conSesion(user) {
  sessionStorage.setItem(MOTORED_TOKEN_KEY, 't');
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify(user));
}

it.each(['ADMIN', 'COMPRAS', 'GERENCIA', 'SERVICIO_CLIENTE'])(
  '%s goes to Inicio', async (role) => {
    conSesion({ role });
    render(<MotoredRaiz />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/motored/inicio'));
  }
);

it('a pending password change goes to the account page', async () => {
  conSesion({ role: 'ADMIN', must_change_password: true });
  render(<MotoredRaiz />);
  await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/motored/mi-cuenta'));
});

it('without a session goes to login', async () => {
  render(<MotoredRaiz />);
  await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/motored/login'));
});
