/** Maestros > Cargas: the TRASLADOS load type (no period, template download, help text, own tab). */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { TIPOS_CARGA, labelTipo, tipoDeclaraPeriodo, tipoUsaFechaDeCorte, textoSinDatos, ayudaTipo } from '../components/motored/cargas/tiposCarga';

jest.mock('../lib/motored/api', () => ({
  listarCargas: jest.fn().mockResolvedValue([]),
  subirCargaMovimiento: jest.fn(),
  getCarga: jest.fn(),
  getCoberturaBot: jest.fn().mockResolvedValue([]),
  listMaestros: jest.fn().mockResolvedValue([]),
}));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));

import MovimientoTab from '../components/motored/cargas/MovimientoTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const AYUDA = 'Traslados entre puntos que siguen vivos en el ERP (archivo Traslados_dd.xlsx). Cada carga reemplaza la foto anterior.';

describe('TRASLADOS load type', () => {
  it('is listed as Traslados without period and without the empty declaration', () => {
    expect(TIPOS_CARGA.map((t) => t.value)).toContain('TRASLADOS');
    expect(labelTipo('TRASLADOS')).toBe('Traslados');
    expect(tipoDeclaraPeriodo('TRASLADOS')).toBe(false);
    expect(tipoUsaFechaDeCorte('TRASLADOS')).toBe(false);
    expect(textoSinDatos('TRASLADOS')).toBeNull();
  });

  it('carries its short help text', () => {
    expect(ayudaTipo('TRASLADOS')).toBe(AYUDA);
    expect(ayudaTipo('VENTAS')).toBeNull();
  });

  it('shows the help under the tab title', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'ADMIN' }));
    render(<MovimientoTab tipo="TRASLADOS" label="Traslados" />);
    expect(await screen.findByText(AYUDA)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Subir archivo' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Declarar sin datos' })).not.toBeInTheDocument();
  });
});
