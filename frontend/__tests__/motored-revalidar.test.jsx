/**
 * "Volver a validar": shown to writers only while the carga is VALIDADO or
 * CON_ERRORES, asks for confirmation, calls the endpoint and follows the
 * carga until the new validation ends.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockRevalidar = jest.fn();
const mockGetInforme = jest.fn();
jest.mock('../lib/motored/api', () => ({
  revalidarCarga: (...args) => mockRevalidar(...args),
  getInformeCarga: (...args) => mockGetInforme(...args),
  aplicarCarga: jest.fn(),
  anularCarga: jest.fn(),
}));

import BotonRevalidar, { CONFIRMAR_REVALIDAR } from '../components/motored/cargas/BotonRevalidar';
import ResumenTab from '../components/motored/cargas/ResumenTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const BOTON = { name: 'Volver a validar' };

beforeEach(() => {
  mockRevalidar.mockReset().mockResolvedValue({ id: 'c1', estado: 'PENDIENTE' });
  mockGetInforme.mockReset().mockResolvedValue({
    id: 'c1', estado: 'VALIDADO', filas_leidas: 4, filas_validas: 4,
    filas_rechazadas: 0, periodo_desde: null, periodo_hasta: null, log: {},
    variacion_pct_vs_carga_anterior: null,
  });
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});

afterEach(() => {
  window.confirm.mockRestore();
});

it.each(['VALIDADO', 'CON_ERRORES'])('is shown for a carga in %s', (estado) => {
  render(<BotonRevalidar carga={{ id: 'c1', estado }} onChanged={jest.fn()} />);

  expect(screen.getByRole('button', BOTON)).toBeInTheDocument();
});

it.each(['APLICADO', 'ANULADO', 'PROCESANDO', 'PENDIENTE'])('is hidden for a carga in %s', (estado) => {
  render(<BotonRevalidar carga={{ id: 'c1', estado }} onChanged={jest.fn()} />);

  expect(screen.queryByRole('button', BOTON)).toBeNull();
});

it('does nothing when the confirmation is cancelled', () => {
  window.confirm.mockReturnValue(false);
  render(<BotonRevalidar carga={{ id: 'c1', estado: 'VALIDADO' }} onChanged={jest.fn()} />);

  fireEvent.click(screen.getByRole('button', BOTON));

  expect(window.confirm).toHaveBeenCalledWith(CONFIRMAR_REVALIDAR);
  expect(mockRevalidar).not.toHaveBeenCalled();
});

it('calls the API after confirming and follows the carga until it is validated', async () => {
  const onChanged = jest.fn()
    .mockResolvedValueOnce({ id: 'c1', estado: 'PENDIENTE' })
    .mockResolvedValueOnce({ id: 'c1', estado: 'PROCESANDO' })
    .mockResolvedValue({ id: 'c1', estado: 'VALIDADO' });
  const onTerminado = jest.fn();
  render(
    <BotonRevalidar
      carga={{ id: 'c1', estado: 'VALIDADO' }} onChanged={onChanged}
      onTerminado={onTerminado} intervaloMs={1}
    />,
  );

  fireEvent.click(screen.getByRole('button', BOTON));

  expect(CONFIRMAR_REVALIDAR).toBe(
    'Se volverá a validar el archivo con las correcciones hechas. ¿Continuar?',
  );
  await waitFor(() => expect(onTerminado).toHaveBeenCalledTimes(1));
  expect(mockRevalidar).toHaveBeenCalledWith('c1');
  expect(onChanged).toHaveBeenCalledTimes(3);
});

it('shows the server message when the revalidation is refused', async () => {
  mockRevalidar.mockRejectedValue(new Error('No se puede volver a validar una carga en estado APLICADO'));
  render(<BotonRevalidar carga={{ id: 'c1', estado: 'VALIDADO' }} onChanged={jest.fn()} />);

  fireEvent.click(screen.getByRole('button', BOTON));

  expect(await screen.findByRole('alert')).toHaveTextContent(/estado APLICADO/);
});

it('appears in the Resumen tab for a writer, not for a reader', async () => {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'ADMIN' }));
  const { unmount } = render(<ResumenTab carga={{ id: 'c1', estado: 'VALIDADO', tipo: 'FACTURAS_PEDIDOS' }} />);
  expect(await screen.findByRole('button', BOTON)).toBeInTheDocument();
  unmount();

  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'CONSULTA' }));
  render(<ResumenTab carga={{ id: 'c1', estado: 'VALIDADO', tipo: 'FACTURAS_PEDIDOS' }} />);
  await screen.findByText('Filas leídas');
  expect(screen.queryByRole('button', BOTON)).toBeNull();
});
