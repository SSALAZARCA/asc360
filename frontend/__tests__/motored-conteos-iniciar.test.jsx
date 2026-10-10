/**
 * Start screen and pair access (odd/motored-conteos-inventario, WU11):
 * the inventory age, the stale 409 -> confirm -> retry, the code shown only
 * right after start or rotation, the QR fetched with auth, the link copy,
 * printing, and the store's locations.
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
    lineas: 1284, valor_sistema: '312450000', sin_costo: 3,
  },
  acceso: { slug: 'K7Q2', url: 'https://asc360.online/motored/c/K7Q2', qr_url: '/x', codigo_rotado_en: null },
};
const SUCURSALES = [{
  id: 's1', nombre: 'Quilichao', vigencia_horas: 6,
  inventario: { carga_id: 'k1', fecha_corte: '2026-10-08', aplicado_en: '2026-10-08T12:55:00Z', antiguedad_horas: '30.0' },
}];
const UBICACIONES = [
  { id: 'u1', codigo: 'A3', nombre: 'Estante A3', activa: true, origen: 'LIDER' },
  { id: 'u2', codigo: 'B1', nombre: 'Estante B1', activa: false, origen: 'PAREJA' },
];
const DIFERENCIAS = {
  estado: 'EN_CONTEO', parcial: true, umbrales: BASE.umbrales, total: 0, criticas: 0, en_reconteo: 0, items: [],
};

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

function antiguo() {
  const error = new Error('El inventario de la tienda se cargó hace 30.0 horas; el límite es 6 horas.');
  error.status = 409;
  error.code = 'INVENTARIO_ANTIGUO';
  error.datos = { antiguedad_horas: '30.0', vigencia_horas: 6 };
  return error;
}

beforeEach(() => {
  sessionStorage.clear();
  jest.resetAllMocks();
  api.obtenerConteo.mockResolvedValue(PROGRAMADO);
  api.listarSucursalesConteo.mockResolvedValue(SUCURSALES);
  api.listarUbicaciones.mockResolvedValue(UBICACIONES);
  api.obtenerPendientesConteo.mockResolvedValue({
    facturas: [], traslados: [], por_sanear: { facturas: 0, traslados: 0 },
    cargas: { facturas_pedidos: null, ingresos_facturas: null, traslados: null }, verificable_desde: null,
  });
  api.listarConteos.mockResolvedValue([]);
  api.obtenerDiferencias.mockResolvedValue(DIFERENCIAS);
  api.listarSesiones.mockResolvedValue([]);
  api.obtenerQrObjectUrl.mockResolvedValue('blob:qr');
});

describe('Start screen', () => {
  it('shows the store inventory age and warns when it is stale', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);

    expect(await screen.findByRole('heading', { name: '2. Foto del inventario' })).toBeInTheDocument();
    expect(await screen.findByText(/hace 30 horas/)).toBeInTheDocument();
    expect(screen.getByText(/más de 6 horas/)).toBeInTheDocument();
  });

  it('confirms a stale inventory and retries with confirmar_antiguedad', async () => {
    login('LIDER_INVENTARIOS');
    api.iniciarConteo
      .mockRejectedValueOnce(antiguo())
      .mockResolvedValueOnce({ conteo: ABIERTO, codigo: '482913', advertencia: null });
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar conteo de Quilichao' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/se cargó hace 30.0 horas/)).toBeInTheDocument();
    expect(api.iniciarConteo).toHaveBeenCalledWith('c1', { confirmarAntiguedad: false, confirmarPendientes: false });

    fireEvent.click(within(dialogo).getByRole('button', { name: 'Iniciar de todos modos' }));

    await waitFor(() => expect(api.iniciarConteo).toHaveBeenLastCalledWith('c1', { confirmarAntiguedad: true, confirmarPendientes: false }));
    expect(await screen.findByText('482 913')).toBeInTheDocument();
    expect(screen.getByText('https://asc360.online/motored/c/K7Q2')).toBeInTheDocument();
    expect(await screen.findByAltText('Código QR del conteo')).toHaveAttribute('src', 'blob:qr');
  });

  it('shows the backend mensaje of any other start error', async () => {
    login('ADMIN');
    const error = new Error('La tienda no tiene inventario cargado.');
    error.code = 'SIN_INVENTARIO';
    api.iniciarConteo.mockRejectedValue(error);
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar conteo de Quilichao' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('La tienda no tiene inventario cargado.');
  });

  it('GERENCIA cannot start', async () => {
    login('GERENCIA');
    render(<ConteoDetalleContainer conteoId="c1" />);

    await screen.findByRole('heading', { name: '2. Foto del inventario' });
    expect(screen.queryByRole('button', { name: /Iniciar conteo/ })).not.toBeInTheDocument();
  });
});

describe('Pair access', () => {
  it('hides the code after a reload and shows the new one after rotating', async () => {
    login('LIDER_INVENTARIOS');
    api.obtenerConteo.mockResolvedValue(ABIERTO);
    api.rotarCodigo.mockResolvedValue({ codigo: '093117', rotado_en: '2026-10-09T13:10:00Z' });
    render(<ConteoDetalleContainer conteoId="c1" />);

    expect(await screen.findByText('Código oculto')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cambiar código' }));

    expect(await screen.findByText('093 117')).toBeInTheDocument();
    expect(api.rotarCodigo).toHaveBeenCalledWith('c1');
  });

  it('copies the link and prints the QR', async () => {
    login('LIDER_INVENTARIOS');
    api.obtenerConteo.mockResolvedValue(ABIERTO);
    const writeText = jest.fn().mockResolvedValue();
    Object.assign(navigator, { clipboard: { writeText } });
    const ventana = { document: { write: jest.fn(), close: jest.fn() }, focus: jest.fn(), print: jest.fn() };
    window.open = jest.fn(() => ventana);
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Ver QR y enlace' }));
    await screen.findByAltText('Código QR del conteo');
    fireEvent.click(screen.getByRole('button', { name: 'Copiar enlace' }));
    expect(writeText).toHaveBeenCalledWith('https://asc360.online/motored/c/K7Q2');

    fireEvent.click(screen.getByRole('button', { name: 'Imprimir QR' }));
    expect(window.open).toHaveBeenCalled();
    expect(ventana.document.write.mock.calls[0][0]).toContain('blob:qr');
  });

  it('prints the location labels with their scan codes', async () => {
    login('LIDER_INVENTARIOS');
    api.obtenerConteo.mockResolvedValue(ABIERTO);
    const ventana = { document: { write: jest.fn(), close: jest.fn() }, focus: jest.fn(), print: jest.fn() };
    window.open = jest.fn(() => ventana);
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Ver QR y enlace' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Imprimir etiquetas de ubicación' }));

    const html = ventana.document.write.mock.calls[0][0];
    expect(html).toContain('UBI-A3');
    expect(html).not.toContain('UBI-B1');
  });
});

describe('Locations', () => {
  it('is optional and collapsed by default: pairs create locations while counting', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);
    const seccion = (await screen.findByRole('heading', { name: 'Ubicaciones (opcional)' })).closest('section');

    expect(within(seccion).getByText(/las crean las parejas al contar/i)).toBeInTheDocument();
    expect(within(seccion).queryByRole('button', { name: 'Agregar' })).not.toBeInTheDocument();
    const mostrar = within(seccion).getByRole('button', { name: /Mostrar ubicaciones/ });
    expect(mostrar).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(mostrar);
    expect(within(seccion).getByRole('button', { name: /Ocultar ubicaciones/ })).toHaveAttribute('aria-expanded', 'true');
    expect(within(seccion).getByRole('button', { name: 'Agregar' })).toBeInTheDocument();
  });

  it('adds, renames and deactivates a location', async () => {
    login('LIDER_INVENTARIOS');
    api.crearUbicacion.mockResolvedValue({});
    api.editarUbicacion.mockResolvedValue({});
    render(<ConteoDetalleContainer conteoId="c1" />);
    const seccion = (await screen.findByRole('heading', { name: 'Ubicaciones (opcional)' })).closest('section');
    fireEvent.click(within(seccion).getByRole('button', { name: /Mostrar ubicaciones/ }));
    await within(seccion).findByText('Estante A3');

    fireEvent.change(within(seccion).getByLabelText('Código'), { target: { value: 'C2' } });
    fireEvent.change(within(seccion).getByLabelText('Nombre'), { target: { value: 'Estante C2' } });
    fireEvent.click(within(seccion).getByRole('button', { name: 'Agregar' }));
    await waitFor(() => expect(api.crearUbicacion).toHaveBeenCalledWith('c1', { codigo: 'C2', nombre: 'Estante C2' }));

    fireEvent.click(within(seccion).getByRole('button', { name: 'Renombrar A3' }));
    fireEvent.change(within(seccion).getByLabelText('Nuevo nombre de A3'), { target: { value: 'Vitrina A3' } });
    fireEvent.click(within(seccion).getByRole('button', { name: 'Guardar nombre' }));
    await waitFor(() => expect(api.editarUbicacion).toHaveBeenCalledWith('c1', 'u1', { nombre: 'Vitrina A3' }));

    fireEvent.click(within(seccion).getByRole('button', { name: 'Desactivar A3' }));
    await waitFor(() => expect(api.editarUbicacion).toHaveBeenCalledWith('c1', 'u1', { activa: false }));
  });

  it('GERENCIA only reads the locations', async () => {
    login('GERENCIA');
    render(<ConteoDetalleContainer conteoId="c1" />);
    const seccion = (await screen.findByRole('heading', { name: 'Ubicaciones (opcional)' })).closest('section');
    fireEvent.click(within(seccion).getByRole('button', { name: /Mostrar ubicaciones/ }));
    await within(seccion).findByText('Estante A3');

    expect(within(seccion).queryByRole('button', { name: 'Agregar' })).not.toBeInTheDocument();
    expect(within(seccion).queryByRole('button', { name: /Desactivar/ })).not.toBeInTheDocument();
  });
});
