/**
 * Maestros health warnings refresh after a write: a save or an upload
 * announces the change and the tabs fetch `/maestros/salud` again, so a
 * fixed warning disappears without reloading the page.
 */
import React from 'react';
import { render, screen, act, waitFor } from '@testing-library/react';

const mockGetSalud = jest.fn();
jest.mock('../lib/motored/api', () => ({
  getSalud: (...args) => mockGetSalud(...args),
}));

import MaestrosTabs from '../components/motored/maestros/MaestrosTabs';
import { avisarMaestrosCambiaron } from '../lib/motored/maestrosEventos';

const TABS = [
  { id: 'suc', label: 'Sucursales', entidadSalud: 'sucursal', render: () => <p>contenido</p> },
];

const SIN_CO = {
  tipo: 'sucursal_sin_codigo_co', entidad: 'sucursal',
  mensaje: "La sucursal 'ARMENIA' no tiene Código C.O.", bloqueante: false,
};

it('fetches the warnings again when maestros change', async () => {
  mockGetSalud.mockResolvedValueOnce({ estado: 'advertencia', hallazgos: [SIN_CO] });
  render(<MaestrosTabs tabs={TABS} />);
  await screen.findByRole('button', { name: /1 advertencia/ });

  mockGetSalud.mockResolvedValueOnce({ estado: 'ok', hallazgos: [] });
  act(() => avisarMaestrosCambiaron());

  await waitFor(() => expect(screen.queryByRole('button', { name: /advertencia/ })).toBeNull());
  expect(mockGetSalud).toHaveBeenCalledTimes(2);
});
