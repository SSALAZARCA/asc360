/**
 * Tests for `useVentasPerdidas` (sdd/motored-ventas-perdidas-panel, Phase 7,
 * task 7.3). Mirrors this project's established Motored mocking convention:
 * mock `lib/motored/api`, import the hook after the mock is registered.
 *
 * What's under test:
 * 1. Initial load uses the 30-day default range (`calcularRangoUltimos30Dias`)
 *    as the `desde`/`hasta` sent to `listarBotLineas` -- this is the
 *    end-to-end proof of task 7.1's "pre-filled on mount" requirement, not
 *    just the pure-function math (covered separately) or the dumb
 *    controlled-component render (covered separately).
 * 2. `editar` calls `editarBotLinea` with the right args and reloads.
 * 3. `anular` calls `anularBotLinea` and reloads; when the response's
 *    `agregado_consistente` is `false`, the hook surfaces `inconsistencia`.
 * 4. A `listarBotLineas` rejection surfaces `error`, not a crash.
 * 5. Nothing loads while `enabled` is false (ADMIN gate not yet resolved).
 */
import { renderHook, waitFor, act } from '@testing-library/react';

const mockListarBotLineas = jest.fn();
const mockEditarBotLinea = jest.fn();
const mockAnularBotLinea = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listarBotLineas: (...args) => mockListarBotLineas(...args),
  editarBotLinea: (...args) => mockEditarBotLinea(...args),
  anularBotLinea: (...args) => mockAnularBotLinea(...args),
}));

import useVentasPerdidas from '../components/motored/ventas-perdidas/useVentasPerdidas';
import { calcularRangoUltimos30Dias } from '../components/motored/ventas-perdidas/fechaDefaults';

const LINEA = {
  linea_id: 'l1', carga_id: 'c1', fecha: '2026-09-01', cantidad: 3, estado: 'ACTIVA',
  metodo: 'manual', asesor: { id: 'a1', nombre: 'Juan', activo: true },
  sucursal: { id: 's1', nombre: 'Bogotá', activa: true },
  referencia: { id: 'r1', codigo: 'X1', nombre: 'Filtro' },
  editado_por: null, editado_en: null, anulado_por: null, anulado_en: null,
};

beforeEach(() => {
  mockListarBotLineas.mockReset().mockResolvedValue([LINEA]);
  mockEditarBotLinea.mockReset().mockResolvedValue({ ...LINEA, cantidad: 5 });
  mockAnularBotLinea.mockReset().mockResolvedValue({ ...LINEA, estado: 'ANULADA', agregado_consistente: true });
});

describe('useVentasPerdidas — initial load uses the 30-day default', () => {
  it('calls listarBotLineas with the exact 30-day default range on first render', async () => {
    const esperado = calcularRangoUltimos30Dias();
    renderHook(() => useVentasPerdidas(true));

    await waitFor(() => expect(mockListarBotLineas).toHaveBeenCalledWith(
      expect.objectContaining({ desde: esperado.desde, hasta: esperado.hasta })
    ));
  });

  it('does not fetch at all while enabled=false', async () => {
    renderHook(() => useVentasPerdidas(false));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mockListarBotLineas).not.toHaveBeenCalled();
  });
});

describe('useVentasPerdidas — editar', () => {
  it('calls editarBotLinea with the line id and new quantity, then reloads', async () => {
    const { result } = renderHook(() => useVentasPerdidas(true));
    await waitFor(() => expect(result.current.lineas).toHaveLength(1));
    mockListarBotLineas.mockClear();

    await act(async () => {
      await result.current.editar('l1', 5);
    });

    expect(mockEditarBotLinea).toHaveBeenCalledWith('l1', 5);
    expect(mockListarBotLineas).toHaveBeenCalledTimes(1);
  });
});

describe('useVentasPerdidas — anular', () => {
  it('calls anularBotLinea with the line id and reloads', async () => {
    const { result } = renderHook(() => useVentasPerdidas(true));
    await waitFor(() => expect(result.current.lineas).toHaveLength(1));
    mockListarBotLineas.mockClear();

    await act(async () => {
      await result.current.anular('l1');
    });

    expect(mockAnularBotLinea).toHaveBeenCalledWith('l1');
    expect(mockListarBotLineas).toHaveBeenCalledTimes(1);
    expect(result.current.inconsistencia).toBe(false);
  });

  it('surfaces inconsistencia=true when the response has agregado_consistente=false', async () => {
    mockAnularBotLinea.mockResolvedValue({ ...LINEA, estado: 'ANULADA', agregado_consistente: false });
    const { result } = renderHook(() => useVentasPerdidas(true));
    await waitFor(() => expect(result.current.lineas).toHaveLength(1));

    await act(async () => {
      await result.current.anular('l1');
    });

    expect(result.current.inconsistencia).toBe(true);
  });
});

describe('useVentasPerdidas — error handling', () => {
  it('surfaces an error state instead of throwing when listarBotLineas rejects', async () => {
    mockListarBotLineas.mockReset().mockRejectedValue(new Error('Rango inválido'));
    const { result } = renderHook(() => useVentasPerdidas(true));

    await waitFor(() => expect(result.current.error).toBe('Rango inválido'));
    expect(result.current.lineas).toEqual([]);
  });
});
