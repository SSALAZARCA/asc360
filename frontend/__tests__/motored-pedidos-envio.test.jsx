/**
 * Motored Fase 4 (F3): marking tiendas as sent (F4-5, F4-11, CI-25..CI-36,
 * UX-21, UX-22) and correcting the order number of a sent tienda (F4-15):
 * number and date per tienda, one tienda or a batch, the duplicate-send
 * message and the coded rejections.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, T_BORRADOR, T_CERRADO, T_ENVIADO, otraTienda,
} from './helpers/pedidosFetch';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useParams: () => ({ id: 'c1' }),
  usePathname: () => '/motored/pedidos/c1',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});
// The send date is validated against today in Bogota: pin it so the tests do not depend on the clock.
jest.mock('../components/motored/pedidos/acciones', () => ({
  ...jest.requireActual('../components/motored/pedidos/acciones'),
  hoyBogota: () => '2026-10-05',
}));

import CorridaDetallePage from '../app/motored/pedidos/[id]/page';

const BOGOTA = otraTienda(T_CERRADO, 's6', 'Bogotá', 6);
const DETALLE = { ...D_DETALLE, sucursales: [T_BORRADOR, T_CERRADO, BOGOTA, T_ENVIADO] };
const ENVIADA = (sid) => ({
  corrida_id: 'c1', sucursal_id: sid, estado_pedido: 'ENVIADO', numero_pedido_proveedor: '12345',
  fecha_envio: '2026-10-02', enviada_por: 'u1', enviada_en: '2026-10-02T11:00:00',
});

const rutas = (over = {}) => ({
  'GET /corridas/c1': jsonRes(DETALLE),
  'POST /corridas/c1/sucursales/s2/enviar': jsonRes(ENVIADA('s2')),
  'POST /corridas/c1/enviar': jsonRes({ id: 'c1', codigo: 'PED-2026-S40-001', estado: 'BORRADOR', enviadas: [ENVIADA('s2'), ENVIADA('s6')] }),
  'PATCH /corridas/c1/sucursales/s3/envio': jsonRes(ENVIADA('s3')),
  ...over,
});
const posts = (calls) => calls.filter((c) => c.method === 'POST');
const fila = async (nombre) => (await screen.findByText(nombre)).closest('tr');
const detalleCargas = (calls) => calls.filter((c) => c.method === 'GET' && c.path === '/corridas/c1');
const escribir = (dialogo, etiqueta, valor) => fireEvent.change(within(dialogo).getByLabelText(etiqueta), { target: { value: valor } });

async function abrirEnvio(nombre = 'Pereira') {
  fireEvent.click(within(await fila(nombre)).getByRole('button', { name: 'Marcar como enviado' }));
  return screen.findByRole('dialog', { name: `Marcar como enviado el pedido de ${nombre}` });
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
});

describe('marcar como enviado - una tienda (CI-25, UX-21)', () => {
  it('asks for the HMCL order number and the send date, with today as the default date', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirEnvio();
    expect(within(dialogo).getByLabelText('Número de orden de Pereira')).toHaveValue('');
    const fecha = within(dialogo).getByLabelText('Fecha de envío de Pereira');
    expect(fecha).toHaveValue('2026-10-05');
    expect(fecha).toHaveAttribute('min', '2026-10-01');
    expect(fecha).toHaveAttribute('max', '2026-10-05');
    expect(within(dialogo).getByRole('note', { name: /Orden de pedido/ })).toBeInTheDocument();
  });

  it('keeps the confirm button disabled until the number is filled', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirEnvio();
    const confirmar = within(dialogo).getByRole('button', { name: 'Marcar como enviado' });
    expect(confirmar).toBeDisabled();
    escribir(dialogo, 'Número de orden de Pereira', '   ');
    expect(confirmar).toBeDisabled();
    escribir(dialogo, 'Número de orden de Pereira', '12345');
    expect(confirmar).toBeEnabled();
  });

  it('explains a send date outside the allowed range and blocks the confirmation', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirEnvio();
    escribir(dialogo, 'Número de orden de Pereira', '12345');
    escribir(dialogo, 'Fecha de envío de Pereira', '2026-10-09');
    expect(within(dialogo).getByText('La fecha de envío no puede ser posterior a hoy.')).toBeInTheDocument();
    expect(within(dialogo).getByRole('button', { name: 'Marcar como enviado' })).toBeDisabled();
    escribir(dialogo, 'Fecha de envío de Pereira', '2026-09-20');
    expect(within(dialogo).getByText('La fecha de envío no puede ser anterior al corte.')).toBeInTheDocument();
  });

  it('posts the trimmed number and the date for that tienda and reloads', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirEnvio();
    escribir(dialogo, 'Número de orden de Pereira', ' 12345 ');
    escribir(dialogo, 'Fecha de envío de Pereira', '2026-10-02');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Marcar como enviado' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts(calls)).toHaveLength(1);
    expect(posts(calls)[0]).toMatchObject({
      path: '/corridas/c1/sucursales/s2/enviar',
      body: { numero_pedido_proveedor: '12345', fecha_envio: '2026-10-02' },
    });
    await waitFor(() => expect(detalleCargas(calls)).toHaveLength(2));
  });

  it('shows the duplicate-send message with its code and keeps the dialog (F4-13, UX-22)', async () => {
    const mensaje = 'Pereira ya tiene un pedido enviado para esta semana (corrida PED-2026-S39-001, orden 12345).';
    const calls = installFetch(rutas({ 'POST /corridas/c1/sucursales/s2/enviar': coded(409, 'E-CORRIDA-050', mensaje) }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirEnvio();
    escribir(dialogo, 'Número de orden de Pereira', '777');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Marcar como enviado' }));
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(`${mensaje} (E-CORRIDA-050)`);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(detalleCargas(calls)).toHaveLength(1);
  });

  it.each([
    ['E-CORRIDA-047', 409, 'El pedido de Pereira no está cerrado.'],
    ['E-CORRIDA-048', 422, 'El número de orden debe tener entre 1 y 50 caracteres.'],
    ['E-CORRIDA-049', 409, 'El pedido de Pereira ya está enviado.'],
    ['E-CORRIDA-056', 409, 'Pereira no tiene nada que pedir (todas sus cantidades son 0).'],
  ])('shows %s from the server', async (code, status, mensaje) => {
    installFetch(rutas({ 'POST /corridas/c1/sucursales/s2/enviar': coded(status, code, mensaje) }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirEnvio();
    escribir(dialogo, 'Número de orden de Pereira', '1');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Marcar como enviado' }));
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(`${mensaje} (${code})`);
  });

  it('disables Marcar como enviado, with the reason, for a tienda with nothing to order (A1)', async () => {
    const SIN_NADA = { ...T_CERRADO, unidades_a_pedir: '0.00', valor_a_pedir: '0.00' };
    installFetch(rutas({ 'GET /corridas/c1': jsonRes({ ...DETALLE, sucursales: [SIN_NADA] }) }));
    render(<CorridaDetallePage />);
    const boton = within(await fila('Pereira')).getByRole('button', { name: /Marcar como enviado: .*nada que pedir/ });
    expect(boton).toBeDisabled();
    // Closing and reopening stay available.
    expect(within(await fila('Pereira')).getByRole('button', { name: 'Reabrir' })).toBeEnabled();
  });

  it('is not offered on a draft or on a sent tienda', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    expect(within(await fila('Manizales')).queryByRole('button', { name: 'Marcar como enviado' })).not.toBeInTheDocument();
    expect(within(await fila('Cali')).queryByRole('button', { name: 'Marcar como enviado' })).not.toBeInTheDocument();
  });
});

describe('marcar como enviado - varias tiendas (CI-26, CI-32)', () => {
  async function abrirLote() {
    fireEvent.click(within(await fila('Pereira')).getByRole('checkbox'));
    fireEvent.click(within(await fila('Bogotá')).getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Marcar seleccionadas como enviadas (2)' }));
    return screen.findByRole('dialog', { name: 'Marcar como enviados los pedidos seleccionados' });
  }

  it('asks for an independent number and date for each tienda', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirLote();
    expect(within(dialogo).getByLabelText('Número de orden de Pereira')).toBeInTheDocument();
    expect(within(dialogo).getByLabelText('Número de orden de Bogotá')).toBeInTheDocument();
    expect(within(dialogo).getByLabelText('Fecha de envío de Bogotá')).toHaveValue('2026-10-05');
    expect(within(dialogo).getByRole('button', { name: 'Marcar como enviados' })).toBeDisabled();
  });

  it('posts every tienda with its own number in table order, in one request', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirLote();
    escribir(dialogo, 'Número de orden de Bogotá', '12346');
    escribir(dialogo, 'Número de orden de Pereira', '12345');
    escribir(dialogo, 'Fecha de envío de Bogotá', '2026-10-03');
    expect(within(dialogo).getByRole('button', { name: 'Marcar como enviados' })).toBeEnabled();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Marcar como enviados' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(posts(calls)).toHaveLength(1);
    expect(posts(calls)[0].path).toBe('/corridas/c1/enviar');
    expect(posts(calls)[0].body).toEqual({
      envios: [
        { sucursal_id: 's2', numero_pedido_proveedor: '12345', fecha_envio: '2026-10-05' },
        { sucursal_id: 's6', numero_pedido_proveedor: '12346', fecha_envio: '2026-10-03' },
      ],
    });
    expect(await screen.findByRole('status')).toHaveTextContent('Se marcaron 2 pedidos como enviados.');
  });

  it('shows the error that names the offending tienda and sends nothing else', async () => {
    const calls = installFetch(rutas({
      'POST /corridas/c1/enviar': coded(409, 'E-CORRIDA-050', 'Bogotá ya tiene un pedido enviado para esta semana (corrida PED-2026-S39-001, orden 9).'),
    }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirLote();
    escribir(dialogo, 'Número de orden de Pereira', '1');
    escribir(dialogo, 'Número de orden de Bogotá', '2');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Marcar como enviados' }));
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(/^Bogotá ya tiene un pedido enviado.*\(E-CORRIDA-050\)$/);
    expect(posts(calls)).toHaveLength(1);
    expect(detalleCargas(calls)).toHaveLength(1);
  });

  it('is disabled when the selection includes a tienda that is not closed', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    fireEvent.click(within(await fila('Pereira')).getByRole('checkbox'));
    fireEvent.click(within(await fila('Manizales')).getByRole('checkbox'));
    expect(screen.getByRole('button', { name: 'Marcar seleccionadas como enviadas (2)' })).toBeDisabled();
  });
});

describe('corregir el número de orden (F4-15)', () => {
  async function abrirCorreccion() {
    fireEvent.click(within(await fila('Cali')).getByRole('button', { name: 'Corregir número' }));
    return screen.findByRole('dialog', { name: 'Corregir número de orden de Cali' });
  }

  it('starts from the current number and blocks a blank or unchanged one', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirCorreccion();
    const confirmar = within(dialogo).getByRole('button', { name: 'Corregir número' });
    expect(within(dialogo).getByLabelText('Número de orden de Cali')).toHaveValue('12345');
    expect(confirmar).toBeDisabled();
    escribir(dialogo, 'Número de orden de Cali', '  ');
    expect(confirmar).toBeDisabled();
    escribir(dialogo, 'Número de orden de Cali', '99999');
    expect(confirmar).toBeEnabled();
  });

  it('says the send date does not change', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirCorreccion();
    expect(dialogo).toHaveTextContent('La fecha de envío no cambia');
  });

  it('patches only the number, closes and reloads', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    const dialogo = await abrirCorreccion();
    escribir(dialogo, 'Número de orden de Cali', ' 99999 ');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Corregir número' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const parche = calls.find((c) => c.method === 'PATCH');
    expect(parche).toMatchObject({ path: '/corridas/c1/sucursales/s3/envio', body: { numero_pedido_proveedor: '99999' } });
    await waitFor(() => expect(detalleCargas(calls)).toHaveLength(2));
  });

  it.each([
    ['E-CORRIDA-067', 409, 'Sólo se corrige el número de un pedido enviado.'],
    ['E-CORRIDA-048', 422, 'El número de orden debe tener entre 1 y 50 caracteres.'],
  ])('shows %s from the server', async (code, status, mensaje) => {
    installFetch(rutas({ 'PATCH /corridas/c1/sucursales/s3/envio': coded(status, code, mensaje) }));
    render(<CorridaDetallePage />);
    const dialogo = await abrirCorreccion();
    escribir(dialogo, 'Número de orden de Cali', '99999');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Corregir número' }));
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(`${mensaje} (${code})`);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('is offered only on a sent tienda', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    expect(within(await fila('Pereira')).queryByRole('button', { name: 'Corregir número' })).not.toBeInTheDocument();
    expect(within(await fila('Manizales')).queryByRole('button', { name: 'Corregir número' })).not.toBeInTheDocument();
  });
});
