/**
 * Leader panel: the "Contadas (N)" chip, the reference search (debounced,
 * server-side, combined with the active chip) and the per-reference detail
 * (odd/tasks/motored-conteo-panel-busqueda.md).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import * as api from '../lib/motored/conteosApi';
import ConteoDetalleContainer from '../components/motored/inventarios/ConteoDetalleContainer';
import { DEMORA_BUSQUEDA_MS } from '../components/motored/inventarios/useBusquedaDiferencias';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/inventarios/conteos/c1',
}));
jest.mock('../lib/motored/conteosApi');

const UMBRALES = { reconteo: '100000', critico: '500000' };
const detalle = {
  id: 'c1', tipo: 'TOTAL', estado: 'EN_CONTEO', origen: 'MANUAL', fecha_programada: '2026-10-10',
  sucursal: { id: 's1', nombre: 'Quilichao' }, lider: { id: 'l1', nombre: 'Laura' },
  iniciado_en: '2026-10-10T12:58:00Z', umbrales: UMBRALES,
  snapshot: { lineas: 10, valor_sistema: '1000', tomado_en: '2026-10-10T12:58:00Z', aplicado_en: '2026-10-10T12:55:00Z' },
  acceso: { slug: 'K7', url: 'https://x/motored/c/K7', qr_url: '/q' },
};
const fila = (codigo, extra = {}) => ({
  codigo, descripcion: `Desc ${codigo}`, ubicaciones: ['Estante A3'], sistema: '6', contado_ronda1: '2', contado: '2',
  diferencia: '-4', costo_unitario: '1000', sin_costo: false, valor: '-4000', critico: false, reconteo: null,
  ultima_lectura_en: '2026-10-10T13:05:00Z', ...extra,
});
const respuesta = (items, extra = {}) => ({
  estado: 'EN_CONTEO', parcial: true, umbrales: UMBRALES, total: 2, criticas: 1, en_reconteo: 0, items, ...extra,
});
const BASE = respuesta([fila('42601-ACL', { critico: true, valor: '-900000' }), fila('17210-K0R')]);
const vivo = {
  version: 7, sin_cambios: false, estado: 'EN_CONTEO',
  progreso: { refs_universo: 10, refs_contadas: 5, lecturas_total: 9, ultima_lectura_en: '2026-10-10T13:05:00Z' },
  exactitud_parcial: null, parejas: [],
  unidades: { total_contado: '9', dentro_esperado: '9', sobrantes: '0', sistema_total: '20' },
  diferencias_resumen: { criticas: 1, en_reconteo: 0, total: 2, contadas: 5 },
};

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

/** Answers the polled `todas` read with BASE and any on-demand read with `remoto`. */
function diferenciasCon(remoto) {
  api.obtenerDiferencias.mockImplementation((id, filtro, q) => Promise.resolve(
    filtro === 'todas' && !q ? BASE : remoto,
  ));
}

async function abrir(role = 'LIDER_INVENTARIOS') {
  login(role);
  render(<ConteoDetalleContainer conteoId="c1" />);
  await screen.findByText('42601-ACL');
}

beforeEach(() => {
  sessionStorage.clear();
  jest.resetAllMocks();
  api.obtenerConteo.mockResolvedValue(detalle);
  diferenciasCon(respuesta([]));
  api.obtenerPanel.mockResolvedValue(vivo);
  api.listarSesiones.mockResolvedValue([]);
  api.listarConteos.mockResolvedValue([]);
  api.listarUbicaciones.mockResolvedValue([]);
});

afterEach(() => {
  jest.useRealTimers();
});

describe('Contadas chip', () => {
  it('shows N from the panel and lists the counted references from the server', async () => {
    diferenciasCon(respuesta([fila('EXACTA-1', { sistema: '2', diferencia: '0', valor: '0' }), fila('17210-K0R')]));
    await abrir();

    fireEvent.click(screen.getByRole('button', { name: 'Contadas (5)' }));

    expect(await screen.findByText('EXACTA-1')).toBeInTheDocument();
    expect(api.obtenerDiferencias).toHaveBeenLastCalledWith('c1', 'contadas', undefined);
    expect(screen.queryByText('42601-ACL')).not.toBeInTheDocument();
    const filas = screen.getAllByRole('row').slice(1).map((r) => within(r).queryByText(/^(EXACTA-1|17210-K0R)$/)?.textContent);
    expect(filas.filter(Boolean)).toEqual(['EXACTA-1', '17210-K0R']);
  });

  it('says when nothing is counted yet', async () => {
    await abrir();

    fireEvent.click(screen.getByRole('button', { name: 'Contadas (5)' }));

    expect(await screen.findByText('Todavía no hay referencias contadas.')).toBeInTheDocument();
  });

  it('keeps the polled table on the client for the other chips', async () => {
    await abrir();

    fireEvent.click(screen.getByRole('button', { name: 'Críticas (1)' }));

    expect(screen.getByText('42601-ACL')).toBeInTheDocument();
    expect(screen.queryByText('17210-K0R')).not.toBeInTheDocument();
    expect(api.obtenerDiferencias).toHaveBeenCalledTimes(1);
  });
});

describe('Search', () => {
  it('asks the server with q after the debounce, combined with the active chip', async () => {
    jest.useFakeTimers();
    diferenciasCon(respuesta([fila('94109-12000S', { descripcion: 'Pastilla de freno' })]));
    await abrir();
    fireEvent.click(screen.getByRole('button', { name: 'Críticas (1)' }));

    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar referencia' }), { target: { value: 'pas' } });
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar referencia' }), { target: { value: 'pastilla' } });
    await act(async () => { jest.advanceTimersByTime(DEMORA_BUSQUEDA_MS - 50); });
    expect(api.obtenerDiferencias).toHaveBeenCalledTimes(1);
    await act(async () => { jest.advanceTimersByTime(50); });

    expect(api.obtenerDiferencias).toHaveBeenCalledTimes(2);
    expect(api.obtenerDiferencias).toHaveBeenLastCalledWith('c1', 'criticas', 'pastilla');
    expect(await screen.findByText('94109-12000S')).toBeInTheDocument();
    expect(screen.queryByText('42601-ACL')).not.toBeInTheDocument();
  });

  it('says when nothing matches, and clearing the box brings the table back', async () => {
    jest.useFakeTimers();
    await abrir();
    const caja = screen.getByRole('searchbox', { name: 'Buscar referencia' });

    fireEvent.change(caja, { target: { value: 'zzz' } });
    await act(async () => { jest.advanceTimersByTime(DEMORA_BUSQUEDA_MS); });
    expect(await screen.findByText('Ninguna referencia coincide con la búsqueda.')).toBeInTheDocument();

    fireEvent.change(caja, { target: { value: '' } });
    expect(await screen.findByText('42601-ACL')).toBeInTheDocument();
  });
});

describe('Detail', () => {
  it('opens the per-location, per-pair detail of a reference', async () => {
    api.obtenerDetalleDiferencia.mockResolvedValue({
      codigo: '42601-ACL', ultima_lectura_en: '2026-10-10T13:05:00Z',
      lineas: [
        { ubicacion: 'Estante A3', ronda: 1, sesion: { id: 's1', etiqueta: 'Pareja 1 · Ana G. y Luis P.' }, cantidad: '5.00', ultima_lectura_en: '2026-10-10T13:05:00Z' },
        { ubicacion: 'Estante B1', ronda: 2, sesion: { id: 's3', etiqueta: 'Pareja 3 · Sofía L. y Diego M.' }, cantidad: '3.00', ultima_lectura_en: '2026-10-10T13:01:00Z' },
      ],
    });
    await abrir('GERENCIA');
    const filaRef = screen.getByText('42601-ACL').closest('tr');

    fireEvent.click(within(filaRef).getByRole('button', { name: 'Ver detalle de 42601-ACL' }));

    const tabla = await screen.findByRole('table', { name: 'Detalle de 42601-ACL' });
    expect(api.obtenerDetalleDiferencia).toHaveBeenCalledWith('c1', '42601-ACL');
    expect(within(tabla).getByText('Estante A3')).toBeInTheDocument();
    expect(within(tabla).getByText('Pareja 1 · Ana G. y Luis P.')).toBeInTheDocument();
    expect(within(tabla).getByText('Primera vuelta')).toBeInTheDocument();
    expect(within(tabla).getByText('Reconteo')).toBeInTheDocument();
    expect(within(tabla).getByText('5')).toBeInTheDocument();

    fireEvent.click(within(filaRef).getByRole('button', { name: 'Ocultar detalle de 42601-ACL' }));
    await waitFor(() => expect(screen.queryByRole('table', { name: 'Detalle de 42601-ACL' })).not.toBeInTheDocument());
  });

  it('says when a reference has no readings', async () => {
    api.obtenerDetalleDiferencia.mockResolvedValue({ codigo: '17210-K0R', lineas: [], ultima_lectura_en: null });
    await abrir();

    fireEvent.click(screen.getByRole('button', { name: 'Ver detalle de 17210-K0R' }));

    expect(await screen.findByText('Nadie ha contado esta referencia todavía.')).toBeInTheDocument();
  });
});
