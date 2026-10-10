/**
 * "4. Pendientes por sanear" on the start screen (odd/motored-conteos-inventario,
 * WU15): the store's invoices pending ingreso and transfers pending reception,
 * the load dates, the empty state, the "Verificado en el ERP" mark and its undo,
 * and the Iniciar warning (409 PENDIENTES_POR_SANEAR -> confirm -> retry with
 * the flag, also combined with the stale-inventory confirmation).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import * as api from '../lib/motored/conteosApi';
import ConteoDetalleContainer from '../components/motored/inventarios/ConteoDetalleContainer';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/inventarios/conteos/c1',
}));
jest.mock('../lib/motored/conteosApi');

const BASE = {
  id: 'c1', tipo: 'TOTAL', origen: 'MANUAL', fecha_programada: '2026-10-09',
  sucursal: { id: 's1', nombre: 'Quilichao' }, lider: { id: 'l1', nombre: 'Laura Líder' },
  umbrales: { reconteo: '100000', critico: '500000' },
};
const PROGRAMADO = { ...BASE, estado: 'PROGRAMADO', snapshot: null, acceso: null };
const ABIERTO = {
  ...BASE, estado: 'EN_CONTEO', iniciado_en: '2026-10-09T12:58:00Z',
  snapshot: {
    carga_id: 'k1', nombre_archivo: 'inventario.xlsx', fecha_corte: '2026-10-09',
    aplicado_en: '2026-10-09T12:55:00Z', tomado_en: '2026-10-09T12:58:00Z',
    lineas: 10, valor_sistema: '1000', sin_costo: 0,
  },
  acceso: { slug: 'K7Q2', url: 'https://asc360.online/motored/c/K7Q2', qr_url: '/x', codigo_rotado_en: null },
};
const SUCURSALES = [{
  id: 's1', nombre: 'Quilichao', vigencia_horas: 6,
  inventario: { carga_id: 'k1', fecha_corte: '2026-10-09', aplicado_en: '2026-10-09T12:55:00Z', antiguedad_horas: '1.0' },
}];
const FACTURA = {
  factura: 'RH 482915', fecha: '2026-10-03', dias: 7, unidades: 4, valor: 125000, num_referencias: 3,
  estado_confirmacion: 'LLEGO', confirmado_por: 'Ana', clave: 'RH 482915', verificado: null,
};
const TRASLADO = {
  documento: '79-00000067', fecha: '2026-10-05', dias: 5, bodega_salida: 'B07', bodega_entrada: 'B01',
  sale: 'Popayán', llega: 'Quilichao', refs: 2, unidades: 6, num_lineas: 3,
  estado_confirmacion: 'NO_HA_LLEGADO', confirmado_por: null, clave: '79-00000067|B07|B01', verificado: null,
};
const CARGAS = {
  facturas_pedidos: { fecha_carga: '2026-10-09T13:00:00Z', periodo_hasta: null },
  ingresos_facturas: { fecha_carga: '2026-10-08T13:00:00Z', periodo_hasta: null },
  traslados: null,
};
const CON_PENDIENTES = {
  facturas: [FACTURA], traslados: [TRASLADO], por_sanear: { facturas: 1, traslados: 1 },
  cargas: CARGAS, verificable_desde: '2026-09-01',
};
const VACIO = {
  facturas: [], traslados: [], por_sanear: { facturas: 0, traslados: 0 }, cargas: CARGAS, verificable_desde: null,
};

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

function codificado(code, message, datos = {}) {
  const error = new Error(message);
  error.status = 409;
  error.code = code;
  error.datos = { code, mensaje: message, ...datos };
  return error;
}

const pendientes = (n, m) => codificado('PENDIENTES_POR_SANEAR', 'Hay pendientes.', { facturas: n, traslados: m });
const antiguo = () => codificado('INVENTARIO_ANTIGUO', 'El inventario se cargó hace 30.0 horas.');

beforeEach(() => {
  sessionStorage.clear();
  jest.resetAllMocks();
  api.obtenerConteo.mockResolvedValue(PROGRAMADO);
  api.listarSucursalesConteo.mockResolvedValue(SUCURSALES);
  api.listarUbicaciones.mockResolvedValue([]);
  api.obtenerPendientesConteo.mockResolvedValue(CON_PENDIENTES);
  api.listarSesiones.mockResolvedValue([]);
  api.obtenerQrObjectUrl.mockResolvedValue('blob:qr');
});

async function tarjeta() {
  const titulo = await screen.findByRole('heading', { name: '4. Pendientes por sanear' });
  return titulo.closest('section');
}

describe('Pendientes por sanear card', () => {
  it('lists the invoices and transfers with their counts and the load dates', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);

    const card = await tarjeta();
    expect(await within(card).findByText('RH 482915')).toBeInTheDocument();
    expect(within(card).getByText('79-00000067')).toBeInTheDocument();
    expect(within(card).getByText('Popayán → Quilichao')).toBeInTheDocument();
    expect(within(card).getByText('Ya llegó')).toBeInTheDocument();
    expect(within(card).getByText('No ha llegado')).toBeInTheDocument();
    expect(within(card).getByRole('heading', { name: 'Facturas por ingresar · 1' })).toBeInTheDocument();
    expect(within(card).getByRole('heading', { name: 'Traslados por recibir · 1' })).toBeInTheDocument();
    expect(within(card).getByText(/Facturas de pedidos: 09\/10\/2026/)).toBeInTheDocument();
    expect(within(card).getByText(/Traslados: sin cargar/)).toBeInTheDocument();
    expect(within(card).getByText(/Conviene ingresar en el ERP estas facturas/)).toBeInTheDocument();
    expect(api.obtenerPendientesConteo).toHaveBeenCalledWith('c1');
  });

  it('shows the green empty state when the store has nothing pending', async () => {
    login('LIDER_INVENTARIOS');
    api.obtenerPendientesConteo.mockResolvedValue(VACIO);
    render(<ConteoDetalleContainer conteoId="c1" />);

    const card = await tarjeta();
    expect(await within(card).findByText('Sin pendientes para esta tienda')).toBeInTheDocument();
    expect(within(card).queryByRole('table')).not.toBeInTheDocument();
  });

  it('is not shown on the access screen once the count started', async () => {
    login('LIDER_INVENTARIOS');
    api.obtenerPendientesConteo.mockResolvedValue(VACIO);
    api.iniciarConteo.mockResolvedValue({ conteo: ABIERTO, codigo: '482913', advertencia: null });
    render(<ConteoDetalleContainer conteoId="c1" />);
    await tarjeta();

    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar conteo de Quilichao' }));

    expect(await screen.findByText('482 913')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '4. Pendientes por sanear' })).not.toBeInTheDocument();
  });

  it('marks an item verified in the ERP, greys it out and undoes it', async () => {
    login('LIDER_INVENTARIOS');
    const verificada = {
      ...CON_PENDIENTES,
      facturas: [{ ...FACTURA, verificado: { por: 'Laura Líder', en: '2026-10-10T14:30:00Z' } }],
      por_sanear: { facturas: 0, traslados: 1 },
    };
    api.verificarPendiente.mockResolvedValue(verificada);
    api.desverificarPendiente.mockResolvedValue(CON_PENDIENTES);
    render(<ConteoDetalleContainer conteoId="c1" />);
    const card = await tarjeta();

    fireEvent.click(await within(card).findByRole('button', { name: 'Marcar RH 482915 como verificado en el ERP' }));

    expect(await within(card).findByText(/Verificado en el ERP por Laura Líder/)).toBeInTheDocument();
    expect(api.verificarPendiente).toHaveBeenCalledWith('c1', 'FACTURA', 'RH 482915');
    expect(within(card).getByText('RH 482915').closest('tr')).toHaveStyle({ opacity: '0.55' });
    expect(within(card).getByRole('heading', { name: 'Facturas por ingresar · 0' })).toBeInTheDocument();

    fireEvent.click(within(card).getByRole('button', { name: 'Deshacer verificación de RH 482915' }));

    await waitFor(() => expect(api.desverificarPendiente).toHaveBeenCalledWith('c1', 'FACTURA', 'RH 482915'));
    expect(await within(card).findByRole('button', { name: 'Marcar RH 482915 como verificado en el ERP' }))
      .toBeInTheDocument();
  });

  it('GERENCIA reads the lists but cannot mark', async () => {
    login('GERENCIA');
    render(<ConteoDetalleContainer conteoId="c1" />);
    const card = await tarjeta();

    expect(await within(card).findByText('RH 482915')).toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: /verificado en el ERP/ })).not.toBeInTheDocument();
  });
});

describe('Iniciar with pending items', () => {
  it('confirms the pending items and retries with confirmar_pendientes', async () => {
    login('LIDER_INVENTARIOS');
    api.iniciarConteo
      .mockRejectedValueOnce(pendientes(3, 2))
      .mockResolvedValueOnce({ conteo: ABIERTO, codigo: '482913', advertencia: null });
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar conteo de Quilichao' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText('Esta tienda tiene 3 facturas y 2 traslados pendientes. ¿Iniciar igual?'))
      .toBeInTheDocument();

    fireEvent.click(within(dialogo).getByRole('button', { name: 'Iniciar de todos modos' }));

    await waitFor(() => expect(api.iniciarConteo).toHaveBeenLastCalledWith(
      'c1', { confirmarAntiguedad: false, confirmarPendientes: true },
    ));
    expect(await screen.findByText('482 913')).toBeInTheDocument();
  });

  it('chains the stale-inventory and the pending confirmations, keeping both flags', async () => {
    login('LIDER_INVENTARIOS');
    api.iniciarConteo
      .mockRejectedValueOnce(antiguo())
      .mockRejectedValueOnce(pendientes(1, 0))
      .mockResolvedValueOnce({ conteo: ABIERTO, codigo: '482913', advertencia: null });
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar conteo de Quilichao' }));
    let dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/se cargó hace 30.0 horas/)).toBeInTheDocument();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Iniciar de todos modos' }));

    dialogo = await screen.findByText('Esta tienda tiene 1 factura y 0 traslados pendientes. ¿Iniciar igual?');
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Iniciar de todos modos' }));

    await waitFor(() => expect(api.iniciarConteo).toHaveBeenCalledTimes(3));
    expect(api.iniciarConteo.mock.calls.map((c) => c[1])).toEqual([
      { confirmarAntiguedad: false, confirmarPendientes: false },
      { confirmarAntiguedad: true, confirmarPendientes: false },
      { confirmarAntiguedad: true, confirmarPendientes: true },
    ]);
  });

  it('chains the other order too', async () => {
    login('LIDER_INVENTARIOS');
    api.iniciarConteo
      .mockRejectedValueOnce(pendientes(2, 1))
      .mockRejectedValueOnce(antiguo())
      .mockResolvedValueOnce({ conteo: ABIERTO, codigo: '482913', advertencia: null });
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar conteo de Quilichao' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Iniciar de todos modos' }));
    await screen.findByText(/se cargó hace 30.0 horas/);
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Iniciar de todos modos' }));

    await waitFor(() => expect(api.iniciarConteo).toHaveBeenCalledTimes(3));
    expect(api.iniciarConteo.mock.calls[2][1]).toEqual({ confirmarAntiguedad: true, confirmarPendientes: true });
  });
});
