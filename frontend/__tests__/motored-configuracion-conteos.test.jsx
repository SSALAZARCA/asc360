/**
 * Configuración tab "Conteos de inventario" (odd/motored-conteos-inventario,
 * WU4): the three fields with their tooltips, saving through the API and
 * the "reconteo below crítico" rule checked before saving.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

jest.mock('../lib/motored/configuracionApi', () => ({
  guardarParametro: jest.fn(async () => ({})),
  getHistorialParametro: jest.fn(async () => []),
}));

import { guardarParametro } from '../lib/motored/configuracionApi';
import SeccionConteos from '../components/motored/configuracion/SeccionConteos';
import SeccionPanel from '../components/motored/configuracion/SeccionPanel';
import { SECCIONES } from '../components/motored/configuracion/secciones';

const spec = (clave, valor) => ({
  clave, seccion: 'conteos', grupo: 'OPERACION', tipo: 'entero', dominio: 'dominio',
  ambito: 'GLOBAL', default: valor, opciones: [], minimo: 1, maximo: null,
  minimo_exclusivo: false, campos: [], snapshotted: false,
  efectivo_global: { valor, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
  por_sucursal: [], programados: [],
});

const DATOS = {
  secciones: [{
    seccion: 'conteos',
    grupos: [{
      grupo: 'OPERACION',
      claves: [
        spec('conteo_umbral_reconteo_pesos', 100000),
        spec('conteo_umbral_critico_pesos', 500000),
        spec('conteo_inventario_vigencia_horas', 6),
      ],
    }],
  }],
};

const ETIQUETAS = [
  'Diferencia que pide reconteo',
  'Diferencia crítica',
  'Antigüedad máxima del inventario',
];

const campo = (nombre) => screen.getByText(nombre).closest('section');

function cambiarYGuardar(etiqueta, valor) {
  const caja = campo(etiqueta);
  fireEvent.change(within(caja).getByLabelText(etiqueta), { target: { value: valor } });
  fireEvent.click(within(caja).getByRole('button', { name: 'Guardar' }));
  return caja;
}

beforeEach(() => jest.clearAllMocks());

describe('Conteos de inventario tab', () => {
  it('is a Configuración tab placed before Topes', () => {
    const ids = SECCIONES.map((s) => s.id);
    expect(SECCIONES.find((s) => s.id === 'conteos')).toEqual({ id: 'conteos', label: 'Conteos de inventario' });
    expect(ids.indexOf('conteos')).toBe(ids.indexOf('topes') - 1);
  });

  it('shows the notice and the three fields, each with a tooltip', () => {
    render(<SeccionConteos data={DATOS} recargar={jest.fn()} />);
    expect(screen.getByText(/se copian en cada conteo al iniciarlo/)).toBeInTheDocument();
    ETIQUETAS.forEach((t) => {
      const caja = campo(t);
      expect(within(caja).getByRole('note')).toBeInTheDocument();
    });
  });

  it('saves a new reconteo amount through the API', async () => {
    const recargar = jest.fn();
    render(<SeccionConteos data={DATOS} recargar={recargar} />);
    cambiarYGuardar('Diferencia que pide reconteo', '150000');
    await waitFor(() => expect(guardarParametro).toHaveBeenCalled());
    expect(guardarParametro.mock.calls[0][0]).toMatchObject({
      clave: 'conteo_umbral_reconteo_pesos', valor: 150000, sucursal_id: null,
    });
    await waitFor(() => expect(recargar).toHaveBeenCalled());
  });

  it('saves the inventory age in hours', async () => {
    render(<SeccionConteos data={DATOS} recargar={jest.fn()} />);
    cambiarYGuardar('Antigüedad máxima del inventario', '12');
    await waitFor(() => expect(guardarParametro).toHaveBeenCalled());
    expect(guardarParametro.mock.calls[0][0]).toMatchObject({
      clave: 'conteo_inventario_vigencia_horas', valor: 12,
    });
  });

  it('refuses a reconteo amount not below the critical one, without calling the API', async () => {
    render(<SeccionConteos data={DATOS} recargar={jest.fn()} />);
    const caja = cambiarYGuardar('Diferencia que pide reconteo', '500000');
    await waitFor(() => expect(within(caja).getByRole('alert')).toHaveTextContent('debe ser menor que'));
    expect(guardarParametro).not.toHaveBeenCalled();
  });

  it('refuses a critical amount not above the reconteo one', async () => {
    render(<SeccionConteos data={DATOS} recargar={jest.fn()} />);
    const caja = cambiarYGuardar('Diferencia crítica', '90000');
    await waitFor(() => expect(within(caja).getByRole('alert')).toHaveTextContent('debe ser menor que'));
    expect(guardarParametro).not.toHaveBeenCalled();
  });

  it('uses the save handler it is given (as SeccionPanel passes it)', async () => {
    const onGuardar = jest.fn(async () => ({}));
    render(<SeccionConteos data={DATOS} recargar={jest.fn()} onGuardar={onGuardar} />);
    cambiarYGuardar('Diferencia crítica', '800000');
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'conteo_umbral_critico_pesos', valor: 800000 });
    expect(guardarParametro).not.toHaveBeenCalled();
  });
});

describe('SeccionPanel', () => {
  it('renders the Conteos de inventario panel for its tab', () => {
    render(<SeccionPanel seccion={{ id: 'conteos', label: 'Conteos de inventario' }} data={DATOS} recargar={jest.fn()} />);
    expect(screen.getByRole('tabpanel', { name: 'Conteos de inventario' })).toHaveTextContent('Diferencia crítica');
  });
});
