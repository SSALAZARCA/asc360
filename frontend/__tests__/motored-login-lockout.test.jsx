/** Login shows the per-account lock message on 429 (T9), not the generic rate-limit text. */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockLogin = jest.fn();
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));
jest.mock('next/image', () => {
  const MockImage = () => <span />;
  MockImage.displayName = 'MockImage';
  return MockImage;
});
jest.mock('../lib/motored/api', () => ({
  ...jest.requireActual('../lib/motored/api'),
  login: (...a) => mockLogin(...a),
}));

import MotoredLoginPage from '../app/motored/login/page';

const { login } = jest.requireActual('../lib/motored/api');

const LOCK = 'Demasiados intentos fallidos. Tu cuenta quedó bloqueada por 15 minutos.';
const RATE = 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.';

function mockFetch(status, body) {
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status, json: () => Promise.resolve(body) });
}

describe('login 429 mapping', () => {
  it('shows the account-lock detail when the backend sends one', async () => {
    mockFetch(429, { detail: LOCK });
    await expect(login('a@b.co', 'pw')).rejects.toThrow(LOCK);
  });

  it('keeps the generic rate-limit text for slowapi (no detail)', async () => {
    mockFetch(429, { error: 'Rate limit exceeded: 10 per 1 minute' });
    await expect(login('a@b.co', 'pw')).rejects.toThrow(RATE);
  });
});

describe('login page', () => {
  it('renders the lock message in the alert box', async () => {
    mockLogin.mockRejectedValue(new Error(LOCK));
    render(<MotoredLoginPage />);
    fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: 'a@b.co' } });
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'x' } });
    fireEvent.submit(screen.getByLabelText('Contraseña').closest('form'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(LOCK));
  });
});
