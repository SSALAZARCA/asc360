/**
 * Live panel (odd/motored-conteos-inventario, WU12/WU12b): polling 15 s
 * visible / 60 s hidden (owner change) that stops on CERRADO and sends the
 * last panel version (the differences reload only when it moved), the KPIs
 * with the real progress, the differences filters, the
 * reconteo request / assign / same-pair override, the pairs, the end of the
 * first round, and GERENCIA read-only.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import * as api from '../lib/motored/conteosApi';
import ConteoDetalleContainer from '../components/motored/inventarios/ConteoDetalleContainer';
import { INTERVALO_OCULTO_MS, INTERVALO_VISIBLE_MS } from '../components/motored/inventarios/usePollingConteo';
import { MINUTOS_SIN_ACTIVIDAD } from '../components/motored/inventarios/conteosFormato';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/inventarios/conteos/c1',
}));
jest.mock('../lib/motored/conteosApi');

const UMBRALES = { reconteo: '100000', critico: '500000' };
const detalle = (estado) => ({
  id: 'c1', tipo: 'TOTAL', estado, origen: 'MANUAL', fecha_programada: '2026-10-09',
  sucursal: { id: 's1', nombre: 'Quilichao' }, lider: { id: 'l1', nombre: 'Laura' },
  iniciado_en: '2026-10-09T12:58:00Z', umbrales: UMBRALES,
  snapshot: { lineas: 1284, valor_sistema: '312450000', tomado_en: '2026-10-09T12:58:00Z', aplicado_en: '2026-10-09T12:55:00Z' },
  acceso: { slug: 'K7', url: 'https://x/motored/c/K7', qr_url: '/q' },
});
const fila = (codigo, extra = {}) => ({
  codigo, descripcion: `Desc ${codigo}`, ubicaciones: ['A1'], sistema: '6', contado_ronda1: '2', contado: '2',
  diferencia: '-4', costo_unitario: '330000', sin_costo: false, valor: '-1320000', critico: false, reconteo: null,
  ...extra,
});
const ITEMS = [
  fila('42601-ACL', { critico: true }),
  fila('BTX4L', { valor: '-740000', critico: true, reconteo: { id: 'r1', estado: 'ASIGNADO', origen: 'UMBRAL', sesion: { id: 's3', etiqueta: 'Pareja 3 · Sofía L. y Diego M.' } } }),
  fila('90305-KVN', { valor: '182000', diferencia: '14', reconteo: { id: 'r2', estado: 'PENDIENTE', origen: 'UMBRAL', sesion: null } }),
  fila('17210-K0R', { valor: '-64000', diferencia: '-1' }),
];
const diferencias = (estado) => ({
  estado, parcial: estado === 'EN_CONTEO', umbrales: UMBRALES, total: 4, criticas: 2, en_reconteo: 2, items: ITEMS,
});
const SESIONES = [
  { id: 's1', numero: 1, etiqueta: 'Pareja 1 · Ana G. y Luis P.', estado: 'CONECTADA', dispositivo: 'ESCRITORIO',
    integrantes: ['Ana', 'Luis'], ubicacion_actual: { id: 'u1', nombre: 'Estante A3' }, ultima_actividad_en: new Date().toISOString() },
  { id: 's3', numero: 3, etiqueta: 'Pareja 3 · Sofía L. y Diego M.', estado: 'CONECTADA', dispositivo: 'MOVIL',
    integrantes: ['Sofía', 'Diego'], ubicacion_actual: null, ultima_actividad_en: new Date().toISOString() },
];

const pareja = (id, numero, lecturas, extra = {}) => ({
  sesion_id: id, numero, etiqueta: `Pareja ${numero}`, ubicacion_actual: null, lecturas,
  ultima_lectura_en: null, ultima_actividad_en: null, estado: 'CONECTADA', ...extra,
});
const vivo = (estado, version = 7, extra = {}) => ({
  version, sin_cambios: false, estado,
  progreso: { refs_universo: 1284, refs_contadas: 796, lecturas_total: 2310, ultima_lectura_en: new Date().toISOString() },
  exactitud_parcial: {
    refs_evaluadas: 800, refs_exactas: 749, exactitud_pct: '93.63', valor_diferencia_neta: '-2140000', valor_diferencia_abs: '3100000',
  },
  parejas: [pareja('s1', 1, 241), pareja('s3', 3, 198)],
  diferencias_resumen: { criticas: 2, en_reconteo: 2, total: 4 },
  ...extra,
});
/** The server's short-circuit: the same version answers `sin_cambios`. */
function panelConVersion(respuesta) {
  return (id, version) => Promise.resolve(
    version === respuesta.version ? { version, sin_cambios: true } : respuesta,
  );
}

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

function coded(code, mensaje) {
  const error = new Error(mensaje);
  error.code = code;
  error.status = 409;
  return error;
}

function setVisibility(valor) {
  Object.defineProperty(document, 'visibilityState', { value: valor, configurable: true });
  document.dispatchEvent(new Event('visibilitychange'));
}

beforeEach(() => {
  sessionStorage.clear();
  jest.resetAllMocks();
  setVisibility('visible');
  api.obtenerConteo.mockResolvedValue(detalle('EN_RECONTEO'));
  api.obtenerDiferencias.mockResolvedValue(diferencias('EN_RECONTEO'));
  api.obtenerPanel.mockImplementation(panelConVersion(vivo('EN_RECONTEO')));
  api.listarSesiones.mockResolvedValue(SESIONES);
  api.listarConteos.mockResolvedValue([]);
  api.listarUbicaciones.mockResolvedValue([]);
});

afterEach(() => {
  jest.useRealTimers();
});

describe('Polling', () => {
  it('polls the panel every 15 s while visible, every 60 s when hidden, and stops on CERRADO', async () => {
    expect(INTERVALO_VISIBLE_MS).toBe(15000);
    expect(INTERVALO_OCULTO_MS).toBe(60000);
    jest.useFakeTimers();
    login('LIDER_INVENTARIOS');
    api.obtenerResultado.mockResolvedValue({ kpi: { refs_universo: 0, refs_exactas: 0, valor_sistema: '0', valor_diferencia_neta: '0', valor_diferencia_abs: '0' }, items: [], total: 0 });
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');
    expect(api.obtenerPanel).toHaveBeenCalledTimes(1);

    await act(async () => { jest.advanceTimersByTime(14000); });
    expect(api.obtenerPanel).toHaveBeenCalledTimes(1);
    await act(async () => { jest.advanceTimersByTime(1000); });
    expect(api.obtenerPanel).toHaveBeenCalledTimes(2);

    act(() => setVisibility('hidden'));
    await act(async () => { jest.advanceTimersByTime(15000); });
    expect(api.obtenerPanel).toHaveBeenCalledTimes(2);
    await act(async () => { jest.advanceTimersByTime(45000); });
    expect(api.obtenerPanel).toHaveBeenCalledTimes(3);

    act(() => setVisibility('visible'));
    await waitFor(() => expect(api.obtenerPanel).toHaveBeenCalledTimes(4));

    api.obtenerPanel.mockImplementation(panelConVersion(vivo('CERRADO', 9)));
    api.obtenerConteo.mockResolvedValue(detalle('CERRADO'));
    await act(async () => { jest.advanceTimersByTime(15000); });
    await screen.findByRole('heading', { name: /Resultado del conteo/ });
    const llamadas = api.obtenerPanel.mock.calls.length;
    await act(async () => { jest.advanceTimersByTime(120000); });
    expect(api.obtenerPanel).toHaveBeenCalledTimes(llamadas);
  });

  it('sends the last version and refetches the differences only when it moved', async () => {
    jest.useFakeTimers();
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');
    expect(api.obtenerDiferencias).toHaveBeenCalledTimes(1);
    expect(api.listarSesiones).toHaveBeenCalledTimes(1);

    await act(async () => { jest.advanceTimersByTime(INTERVALO_VISIBLE_MS); });
    expect(api.obtenerPanel).toHaveBeenLastCalledWith('c1', 7);
    expect(api.obtenerDiferencias).toHaveBeenCalledTimes(1);
    expect(api.listarSesiones).toHaveBeenCalledTimes(1);

    api.obtenerPanel.mockImplementation(panelConVersion(vivo('EN_RECONTEO', 8)));
    await act(async () => { jest.advanceTimersByTime(INTERVALO_VISIBLE_MS); });
    await waitFor(() => expect(api.obtenerDiferencias).toHaveBeenCalledTimes(2));
    expect(api.listarSesiones).toHaveBeenCalledTimes(2);

    await act(async () => { jest.advanceTimersByTime(INTERVALO_VISIBLE_MS); });
    expect(api.obtenerPanel).toHaveBeenLastCalledWith('c1', 8);
    expect(api.obtenerDiferencias).toHaveBeenCalledTimes(2);
  });

  it('refreshes by hand', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    fireEvent.click(screen.getByRole('button', { name: 'Actualizar ahora' }));

    await waitFor(() => expect(api.obtenerDiferencias).toHaveBeenCalledTimes(2));
    expect(api.obtenerPanel).toHaveBeenLastCalledWith('c1', undefined);
  });
});

describe('KPIs and differences', () => {
  it('shows the counts the API gives', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    expect(screen.getByRole('button', { name: 'Todas (4)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Críticas (2)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'En reconteo (2)' })).toBeInTheDocument();
    expect(screen.getByText('1 asignadas · 0 recontadas')).toBeInTheDocument();
    expect(screen.getByText('2 conectadas')).toBeInTheDocument();
  });

  it('shows the real progress, the partial accuracy and the last reading', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    expect(screen.getByText('796 / 1.284')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Avance del conteo' })).toHaveAttribute('aria-valuenow', '62');
    expect(screen.getByText('referencias contadas')).toBeInTheDocument();
    expect(screen.getByText('93,6 %')).toBeInTheDocument();
    expect(screen.getByText('Diferencia neta parcial: −$2.140.000')).toBeInTheDocument();
    expect(screen.getByText(/^última lectura hace \d+ s$/)).toBeInTheDocument();
  });

  it('shows dashes until something is counted', async () => {
    login('LIDER_INVENTARIOS');
    api.obtenerPanel.mockImplementation(panelConVersion(vivo('EN_CONTEO', 7, {
      progreso: { refs_universo: 1284, refs_contadas: 0, lecturas_total: 0, ultima_lectura_en: null },
      exactitud_parcial: null,
    })));
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    expect(screen.getByText('0 / 1.284')).toBeInTheDocument();
    expect(screen.getByText('Sin referencias contadas todavía')).toBeInTheDocument();
    expect(screen.getByText('sin lecturas todavía')).toBeInTheDocument();
  });

  it('shows the readings of each pair', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    expect(screen.getByText(/^Estante A3 · 241 lecturas · hace/)).toBeInTheDocument();
    expect(screen.getByText(/^Sin ubicación · 198 lecturas · hace/)).toBeInTheDocument();
  });

  it('filters critical rows and rows in reconteo', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    fireEvent.click(screen.getByRole('button', { name: 'Críticas (2)' }));
    expect(screen.getByText('BTX4L')).toBeInTheDocument();
    expect(screen.queryByText('17210-K0R')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'En reconteo (2)' }));
    expect(screen.getByText('90305-KVN')).toBeInTheDocument();
    expect(screen.queryByText('42601-ACL')).not.toBeInTheDocument();
  });

  it('marks critical rows and pair assignments', async () => {
    login('LIDER_INVENTARIOS');
    render(<ConteoDetalleContainer conteoId="c1" />);
    const filaCritica = (await screen.findByText('42601-ACL')).closest('tr');

    expect(within(filaCritica).getByText('Crítica')).toBeInTheDocument();
    expect(screen.getByText('Recontando · Pareja 3')).toBeInTheDocument();
  });
});

describe('Reconteo control', () => {
  it('asks for a manual reconteo', async () => {
    login('LIDER_INVENTARIOS');
    api.pedirReconteo.mockResolvedValue({});
    render(<ConteoDetalleContainer conteoId="c1" />);
    const filaRef = (await screen.findByText('17210-K0R')).closest('tr');

    fireEvent.click(within(filaRef).getByRole('button', { name: 'Pedir reconteo' }));

    await waitFor(() => expect(api.pedirReconteo).toHaveBeenCalledWith('c1', '17210-K0R'));
  });

  it('assigns to a pair and offers the same-pair override only when one pair is connected', async () => {
    login('LIDER_INVENTARIOS');
    api.listarSesiones.mockResolvedValue([SESIONES[0]]);
    api.asignarReconteo
      .mockRejectedValueOnce(coded('MISMA_PAREJA', 'Esa pareja comparte una persona con quien contó.'))
      .mockResolvedValueOnce({});
    render(<ConteoDetalleContainer conteoId="c1" />);
    const filaRef = (await screen.findByText('90305-KVN')).closest('tr');

    fireEvent.click(within(filaRef).getByRole('button', { name: 'Asignar' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText('Pareja'), { target: { value: 's1' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Asignar' }));

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('Esa pareja comparte una persona');
    fireEvent.click(within(dialogo).getByRole('checkbox', { name: /Autorizar misma pareja/ }));
    const confirmar = within(dialogo).getByRole('button', { name: 'Asignar' });
    expect(confirmar).toBeDisabled();
    fireEvent.change(within(dialogo).getByLabelText('Motivo de la autorización'), { target: { value: 'Solo hay una pareja' } });
    fireEvent.click(confirmar);

    await waitFor(() => expect(api.asignarReconteo).toHaveBeenLastCalledWith('c1', 'r2', {
      sesion_id: 's1', autorizar_misma_pareja: true, motivo: 'Solo hay una pareja',
    }));
  });

  it('does not offer the override when another pair is connected', async () => {
    login('LIDER_INVENTARIOS');
    api.asignarReconteo.mockRejectedValue(coded('MISMA_PAREJA', 'Esa pareja comparte una persona con quien contó.'));
    render(<ConteoDetalleContainer conteoId="c1" />);
    const filaRef = (await screen.findByText('90305-KVN')).closest('tr');

    fireEvent.click(within(filaRef).getByRole('button', { name: 'Asignar' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText('Pareja'), { target: { value: 's1' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Asignar' }));

    await within(dialogo).findByRole('alert');
    expect(within(dialogo).queryByRole('checkbox', { name: /Autorizar misma pareja/ })).not.toBeInTheDocument();
  });

  it('spreads and cancels reconteos', async () => {
    login('LIDER_INVENTARIOS');
    api.repartirReconteos.mockResolvedValue({ asignados: [{ id: 'r2' }], sin_pareja: [] });
    api.cancelarReconteo.mockResolvedValue({});
    render(<ConteoDetalleContainer conteoId="c1" />);
    const filaRef = (await screen.findByText('90305-KVN')).closest('tr');

    fireEvent.click(screen.getByRole('button', { name: 'Repartir automático' }));
    await waitFor(() => expect(api.repartirReconteos).toHaveBeenCalledWith('c1'));
    expect(await screen.findByText(/1 reconteos asignados/)).toBeInTheDocument();

    fireEvent.click(within(filaRef).getByRole('button', { name: 'Cancelar reconteo' }));
    await waitFor(() => expect(api.cancelarReconteo).toHaveBeenCalledWith('c1', 'r2'));
  });

  it('disconnects a pair after a confirm', async () => {
    login('LIDER_INVENTARIOS');
    api.desconectarSesion.mockResolvedValue({});
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    fireEvent.click(screen.getByRole('button', { name: 'Desconectar Pareja 1' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Desconectar' }));

    await waitFor(() => expect(api.desconectarSesion).toHaveBeenCalledWith('c1', 's1'));
  });
});

describe('First round', () => {
  it('ends the first round after a confirm', async () => {
    login('LIDER_INVENTARIOS');
    api.obtenerConteo.mockResolvedValue(detalle('EN_CONTEO'));
    api.obtenerDiferencias.mockResolvedValue(diferencias('EN_CONTEO'));
    api.terminarRonda.mockResolvedValue({ estado: 'EN_RECONTEO', diferencias: 4, reconteos_creados: 2 });
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');
    expect(screen.queryByRole('button', { name: 'Pedir reconteo' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Terminar primera vuelta' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/calcula las diferencias/)).toBeInTheDocument();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Terminar primera vuelta' }));

    await waitFor(() => expect(api.terminarRonda).toHaveBeenCalledWith('c1'));
  });
});

describe('GERENCIA', () => {
  it('sees the panel with no action buttons and no access card', async () => {
    login('GERENCIA');
    api.obtenerConteo.mockResolvedValue({ ...detalle('EN_RECONTEO'), acceso: null });
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    expect(screen.queryByRole('button', { name: 'Pedir reconteo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Asignar' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Repartir automático' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Desconectar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cerrar conteo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Acceso para parejas' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Descargar avance en Excel' })).toBeInTheDocument();
  });
});

describe('Idle pairs (owner rule)', () => {
  const AHORA = new Date('2026-10-09T15:00:00Z');
  const haceMin = (min) => new Date(AHORA.getTime() - min * 60000).toISOString();
  const sesion = (numero, minutos, estado = 'CONECTADA') => ({
    id: `s${numero}`, numero, etiqueta: `Pareja ${numero} · A. y B.`, estado, dispositivo: 'ESCRITORIO',
    integrantes: ['A', 'B'], ubicacion_actual: null, ultima_actividad_en: haceMin(minutos),
  });

  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(AHORA);
  });

  it('highlights a connected pair silent for more than 2 minutes', async () => {
    expect(MINUTOS_SIN_ACTIVIDAD).toBe(2);
    login('LIDER_INVENTARIOS');
    api.listarSesiones.mockResolvedValue([sesion(1, 1), sesion(2, 1.9), sesion(3, 5), sesion(4, 30, 'DESCONECTADA')]);
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    expect(screen.getByText('Sin actividad hace 5 min')).toBeInTheDocument();
    expect(screen.getAllByText(/^Sin actividad hace/)).toHaveLength(1);
    const tarjeta = screen.getByText('Pareja 3 · A. y B.').parentElement.parentElement;
    expect(tarjeta).toHaveAttribute('data-inactiva', 'si');
    expect(tarjeta.style.background).toBe('var(--motored-warning-bg, #fef3e2)');
  });

  it('counts a recent reading as activity', async () => {
    login('LIDER_INVENTARIOS');
    api.listarSesiones.mockResolvedValue([sesion(3, 5)]);
    api.obtenerPanel.mockImplementation(panelConVersion(vivo('EN_RECONTEO', 7, {
      parejas: [pareja('s3', 3, 12, { ultima_lectura_en: haceMin(0.5) })],
    })));
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    expect(screen.queryByText(/^Sin actividad hace/)).not.toBeInTheDocument();
  });

  it('flags a pair once it crosses the threshold', async () => {
    login('LIDER_INVENTARIOS');
    api.listarSesiones.mockResolvedValue([sesion(1, 1.9)]);
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');
    expect(screen.queryByText(/^Sin actividad hace/)).not.toBeInTheDocument();

    await act(async () => { jest.advanceTimersByTime(INTERVALO_VISIBLE_MS); });

    expect(await screen.findByText('Sin actividad hace 2 min')).toBeInTheDocument();
  });

  it('is shown to the leader only, not to GERENCIA', async () => {
    login('GERENCIA');
    api.obtenerConteo.mockResolvedValue({ ...detalle('EN_RECONTEO'), acceso: null });
    api.listarSesiones.mockResolvedValue([sesion(3, 5)]);
    render(<ConteoDetalleContainer conteoId="c1" />);
    await screen.findByText('42601-ACL');

    expect(screen.queryByText(/^Sin actividad hace/)).not.toBeInTheDocument();
  });
});
