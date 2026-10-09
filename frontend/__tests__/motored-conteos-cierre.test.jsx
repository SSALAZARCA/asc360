/**
 * Close and result (odd/motored-conteos-inventario, WU12): the close
 * confirm, the 409 with open reconteos and the forced close that needs a
 * reason, the result view with its KPI, and the Excel downloads.
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

const UMBRALES = { reconteo: '100000', critico: '500000' };
const detalle = (estado) => ({
  id: 'c1', tipo: 'TOTAL', estado, origen: 'MANUAL', fecha_programada: '2026-10-09',
  sucursal: { id: 's1', nombre: 'Quilichao' }, lider: { id: 'l1', nombre: 'Laura' },
  iniciado_en: '2026-10-09T12:58:00Z', cerrado_en: estado === 'CERRADO' ? '2026-10-09T20:00:00Z' : null,
  umbrales: UMBRALES, snapshot: { lineas: 1284 }, acceso: null,
});
const DIFERENCIAS = {
  estado: 'EN_RECONTEO', parcial: false, umbrales: UMBRALES, total: 0, criticas: 0, en_reconteo: 0, items: [],
};
const RESULTADO = {
  conteo_id: 'c1', estado: 'CERRADO', cerrado_en: '2026-10-09T20:00:00Z', motivo_cierre_forzado: 'Fin de jornada',
  bodega: 'BQ011', total: 2,
  kpi: {
    refs_universo: 1280, refs_exactas: 1198, exactitud_pct: '93.59', valor_sistema: '312450000',
    valor_diferencia_neta: '-2140000', valor_diferencia_abs: '4870000',
  },
  items: [
    { codigo: '42601-ACL', descripcion: 'RIM', bodega: 'BQ011', sistema: '6', contado: '2', diferencia: '-4',
      costo_unitario: '330000', costo_fuente: 'SNAPSHOT', valor: '-1320000', ubicaciones: ['B1', 'B4'],
      con_reconteo: true, critico: true, confirmada: true },
    { codigo: 'ZZ-1', descripcion: null, bodega: 'BQ011', sistema: '0', contado: '3', diferencia: '3',
      costo_unitario: null, costo_fuente: 'SIN_COSTO', valor: null, ubicaciones: ['A1'],
      con_reconteo: false, critico: false, confirmada: null },
  ],
};

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

function abiertos() {
  const error = new Error('Todavía hay reconteos sin terminar.');
  error.code = 'RECONTEOS_ABIERTOS';
  error.status = 409;
  error.datos = { code: 'RECONTEOS_ABIERTOS', pendientes: 2, asignados: 3 };
  return error;
}

beforeEach(() => {
  sessionStorage.clear();
  jest.resetAllMocks();
  api.obtenerConteo.mockResolvedValue(detalle('EN_RECONTEO'));
  api.obtenerDiferencias.mockResolvedValue(DIFERENCIAS);
  api.obtenerPanel.mockResolvedValue({
    version: 1, sin_cambios: false, estado: 'EN_RECONTEO', parejas: [], exactitud_parcial: null,
    progreso: { refs_universo: 0, refs_contadas: 0, lecturas_total: 0, ultima_lectura_en: null },
    diferencias_resumen: { criticas: 0, en_reconteo: 0, total: 0 },
  });
  api.listarSesiones.mockResolvedValue([]);
  api.listarConteos.mockResolvedValue([]);
  api.obtenerResultado.mockResolvedValue(RESULTADO);
});

describe('Close', () => {
  it('needs a forced close with a reason when reconteos are open', async () => {
    login('LIDER_INVENTARIOS');
    api.cerrarConteo.mockRejectedValueOnce(abiertos()).mockResolvedValueOnce({ estado: 'CERRADO' });
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar conteo' }));
    let dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar conteo' }));
    await waitFor(() => expect(api.cerrarConteo).toHaveBeenCalledWith('c1', { forzar: false }));

    dialogo = await screen.findByRole('dialog');
    expect(await within(dialogo).findByText(/2 sin asignar y 3 asignados/)).toBeInTheDocument();
    const forzar = within(dialogo).getByRole('button', { name: 'Forzar cierre' });
    expect(forzar).toBeDisabled();

    api.obtenerConteo.mockResolvedValue(detalle('CERRADO'));
    fireEvent.change(within(dialogo).getByLabelText('Motivo del cierre forzado'), { target: { value: 'Fin de jornada' } });
    fireEvent.click(forzar);

    await waitFor(() => expect(api.cerrarConteo).toHaveBeenLastCalledWith('c1', { forzar: true, motivo: 'Fin de jornada' }));
    expect(await screen.findByRole('heading', { name: /Resultado del conteo/ })).toBeInTheDocument();
  });

  it('shows the backend mensaje of a failed close', async () => {
    login('ADMIN');
    const error = new Error('La tienda no tiene una bodega principal registrada.');
    error.code = 'SIN_BODEGA_PRINCIPAL';
    api.cerrarConteo.mockRejectedValue(error);
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar conteo' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar conteo' }));

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('La tienda no tiene una bodega principal registrada.');
  });

  it('downloads the progress Excel while open', async () => {
    login('LIDER_INVENTARIOS');
    api.descargarAvance.mockResolvedValue();
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Descargar avance en Excel' }));

    await waitFor(() => expect(api.descargarAvance).toHaveBeenCalledWith('c1'));
  });
});

describe('Close with idle pairs (owner rule)', () => {
  const haceMin = (min) => new Date(Date.now() - min * 60000).toISOString();
  const sesion = (numero, minutos) => ({
    id: `s${numero}`, numero, etiqueta: `Pareja ${numero} · A. y B.`, estado: 'CONECTADA', dispositivo: 'MOVIL',
    integrantes: ['A', 'B'], ubicacion_actual: null, ultima_actividad_en: haceMin(minutos),
  });

  it('warns about each silent pair and still lets the leader close', async () => {
    login('LIDER_INVENTARIOS');
    api.listarSesiones.mockResolvedValue([sesion(1, 0.2), sesion(2, 5), sesion(4, 12)]);
    api.cerrarConteo.mockResolvedValue({ estado: 'CERRADO' });
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('Sin actividad hace 5 min');

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar conteo' }));
    const dialogo = await screen.findByRole('dialog');

    expect(within(dialogo).getByText('La Pareja 2 lleva 5 minutos sin enviar lecturas.')).toBeInTheDocument();
    expect(within(dialogo).getByText('La Pareja 4 lleva 12 minutos sin enviar lecturas.')).toBeInTheDocument();
    expect(within(dialogo).queryByText(/La Pareja 1 /)).not.toBeInTheDocument();
    expect(within(dialogo).getByText('Puede tener lecturas guardadas sin enviar. ¿Cerrar igual?')).toBeInTheDocument();

    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar conteo' }));
    await waitFor(() => expect(api.cerrarConteo).toHaveBeenCalledWith('c1', { forzar: false }));
  });

  it('shows no warning when every pair is active', async () => {
    login('LIDER_INVENTARIOS');
    api.listarSesiones.mockResolvedValue([sesion(1, 0.5)]);
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar conteo' }));
    const dialogo = await screen.findByRole('dialog');

    expect(within(dialogo).queryByText(/sin enviar lecturas/)).not.toBeInTheDocument();
  });
});

describe('Result', () => {
  it('shows the KPI, the lines and downloads the adjustments', async () => {
    login('GERENCIA');
    api.obtenerConteo.mockResolvedValue(detalle('CERRADO'));
    api.descargarAjustes.mockResolvedValue();
    render(<ConteoDetalleContainer conteoId="c1" />);

    expect(await screen.findByRole('heading', { name: /Resultado del conteo/ })).toBeInTheDocument();
    expect(await screen.findByText('93,6 %')).toBeInTheDocument();
    expect(screen.getByText('1.198 de 1.280 referencias')).toBeInTheDocument();
    expect(screen.getByText(/Fin de jornada/)).toBeInTheDocument();
    expect(screen.getByText('42601-ACL')).toBeInTheDocument();
    expect(screen.getByText('Sin costo')).toBeInTheDocument();
    expect(api.obtenerDiferencias).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Descargar ajustes (Excel)' }));
    await waitFor(() => expect(api.descargarAjustes).toHaveBeenCalledWith('c1'));
  });

  it('shows the download error mensaje', async () => {
    login('ADMIN');
    api.obtenerConteo.mockResolvedValue(detalle('CERRADO'));
    api.descargarAjustes.mockRejectedValue(new Error('No se pudo descargar el archivo.'));
    render(<ConteoDetalleContainer conteoId="c1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Descargar ajustes (Excel)' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo descargar el archivo.');
  });
});
