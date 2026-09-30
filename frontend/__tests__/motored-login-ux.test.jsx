/** Login page UX: notice after automatic logout, password toggle, a11y attributes (T4). */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
const mockLogin = jest.fn();

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: pushMock }) }));
jest.mock('next/image', () => {
  const MockImage = (props) => <span data-testid="img" data-alt={props.alt} />;
  MockImage.displayName = 'MockImage';
  return MockImage;
});
jest.mock('../lib/motored/api', () => ({ login: (...a) => mockLogin(...a) }));

import MotoredLoginPage from '../app/motored/login/page';
import { MOTORED_EXPIRED_KEY } from '../lib/motored/motoredFetch';

const NOTICE = /Tu sesión terminó/;

beforeEach(() => {
  sessionStorage.clear();
  mockLogin.mockReset();
});

describe('session-expired notice', () => {
  it('shows after an automatic logout and is consumed', () => {
    sessionStorage.setItem(MOTORED_EXPIRED_KEY, '1');
    render(<MotoredLoginPage />);
    expect(screen.getByRole('status')).toHaveTextContent(NOTICE);
    expect(sessionStorage.getItem(MOTORED_EXPIRED_KEY)).toBeNull();
  });

  it('does not show after a manual logout (no flag)', () => {
    render(<MotoredLoginPage />);
    expect(screen.queryByText(NOTICE)).toBeNull();
  });
});

describe('form accessibility', () => {
  it('ties labels to inputs with the right autocomplete and autofocus', () => {
    render(<MotoredLoginPage />);
    const email = screen.getByLabelText('Correo electrónico');
    expect(email).toHaveAttribute('autocomplete', 'username');
    expect(email).toHaveFocus();
    const pw = screen.getByLabelText('Contraseña');
    expect(pw).toHaveAttribute('autocomplete', 'current-password');
    expect(pw).toHaveAttribute('type', 'password');
  });

  it('toggles password visibility with an accessible button', () => {
    render(<MotoredLoginPage />);
    const btn = screen.getByRole('button', { name: 'Mostrar contraseña' });
    expect(btn).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(btn);
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute('type', 'text');
    const hide = screen.getByRole('button', { name: 'Ocultar contraseña' });
    expect(hide).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(hide);
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute('type', 'password');
  });

  it('shows the forgot-password hint', () => {
    render(<MotoredLoginPage />);
    expect(screen.getByText(/¿Olvidaste tu contraseña\? Pídele a un administrador que la restablezca\./)).toBeInTheDocument();
  });

  it('renders the server error in a role=alert box', async () => {
    mockLogin.mockRejectedValue(new Error('Demasiados intentos. Espera un minuto e inténtalo de nuevo.'));
    const { container } = render(<MotoredLoginPage />);
    fireEvent.change(screen.getByLabelText('Correo electrónico'), { target: { value: 'a@b.co' } });
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'pw' } });
    fireEvent.submit(container.querySelector('form'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Demasiados intentos'));
  });
});
