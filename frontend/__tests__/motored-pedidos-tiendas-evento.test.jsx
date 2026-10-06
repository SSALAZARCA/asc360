/**
 * Motored Fase 4 (F4): the "Último evento" cell of the Tiendas table. At
 * tablet widths the text used to be cut by the sticky "Acción" column
 * ("Cerrado po…"); it now wraps, and the whole sentence is also the tooltip
 * (title) of the cell. The overlap itself is checked in a real browser.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { T_BORRADOR, T_CERRADO, T_ENVIADO, otraTienda } from './helpers/pedidosFetch';
import TiendasTable from '../components/motored/pedidos/TiendasTable';

const filaDe = (nombre) => screen.getByText(nombre).closest('tr');
const celdaEvento = (nombre) => {
  const columna = [...document.querySelectorAll('thead th')].findIndex((th) => th.textContent.startsWith('Último evento'));
  return filaDe(nombre).querySelectorAll('td')[columna];
};

describe('Último evento tooltip', () => {
  it('carries the whole sentence (event, who, when) as a tooltip, whatever the width', () => {
    render(<TiendasTable tiendas={[T_CERRADO, T_ENVIADO]} onOpen={() => {}} />);
    expect(within(celdaEvento('Pereira')).getByTitle('Cerrado por Compras Uno · 02/10/2026 04:15')).toBeInTheDocument();
    expect(within(celdaEvento('Cali')).getByTitle('Enviado por Ana Gómez · 02/10/2026 06:00')).toBeInTheDocument();
  });

  it('leaves out the "por" part when the user is unknown', () => {
    const sinUsuario = otraTienda({ ...T_CERRADO, ultimo_evento: { evento: 'CERRADO', usuario: null, creado_en: '2026-10-02T09:15:00' } }, 's9', 'Neiva', 9);
    render(<TiendasTable tiendas={[sinUsuario]} onOpen={() => {}} />);
    expect(within(celdaEvento('Neiva')).getByTitle('Cerrado · 02/10/2026 04:15')).toBeInTheDocument();
  });

  it('has no tooltip for a tienda without movements', () => {
    render(<TiendasTable tiendas={[T_BORRADOR]} onOpen={() => {}} />);
    expect(within(celdaEvento('Manizales')).getByText('Sin movimientos')).toBeInTheDocument();
    expect(celdaEvento('Manizales').querySelector('[title]')).toBeNull();
  });
});
