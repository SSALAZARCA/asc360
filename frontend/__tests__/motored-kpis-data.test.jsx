import { act, renderHook, waitFor } from '@testing-library/react';
import { claveKpis } from '../components/motored/kpis/useKpis';
import useKpis from '../components/motored/kpis/useKpis';
import { rutaKpis } from '../lib/motored/kpisApi';

const FILTROS = { meses: ['2026-06', '2026-07'], sucursales: ['b', 'a'], hmcl: 'incluir' };

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe('kpisApi routes', () => {
  it('builds the per-tab path with months, stores and hmcl', () => {
    const ruta = decodeURIComponent(rutaKpis('ventas', FILTROS));
    expect(ruta).toBe('/tablero-asesores/kpis/ventas?meses=2026-06,2026-07&sucursales=a,b&hmcl=incluir');
  });

  it('omits the stores when there is no store filter', () => {
    expect(decodeURIComponent(rutaKpis('tiendas', { ...FILTROS, sucursales: [] }))).toBe(
      '/tablero-asesores/kpis/tiendas?meses=2026-06,2026-07&hmcl=incluir',
    );
  });
});

describe('claveKpis', () => {
  it('is the same whatever the order of stores and months', () => {
    expect(claveKpis('ventas', FILTROS)).toBe(claveKpis('ventas', { ...FILTROS, sucursales: ['a', 'b'], meses: ['2026-07', '2026-06'] }));
    expect(claveKpis('ventas', FILTROS)).not.toBe(claveKpis('tiendas', FILTROS));
    expect(claveKpis('ventas', FILTROS)).not.toBe(claveKpis('ventas', { ...FILTROS, hmcl: 'solo' }));
  });
});

describe('claveKpis of the inventory tab', () => {
  it('ignores the months (the tab does not depend on the Período) but not stores or HMCL', () => {
    expect(claveKpis('inventario', FILTROS)).toBe(claveKpis('inventario', { ...FILTROS, meses: ['2026-01'] }));
    expect(claveKpis('inventario', FILTROS)).not.toBe(claveKpis('inventario', { ...FILTROS, sucursales: ['a'] }));
    expect(claveKpis('inventario', FILTROS)).not.toBe(claveKpis('inventario', { ...FILTROS, hmcl: 'solo' }));
  });
});

describe('useKpis', () => {
  it('fetches only the active tab and reuses the cache when coming back', async () => {
    const api = { ventas: jest.fn().mockResolvedValue({ v: 1 }), tiendas: jest.fn().mockResolvedValue({ t: 1 }), asesores: jest.fn() };
    const { result, rerender } = renderHook(({ tab }) => useKpis(tab, FILTROS, api), { initialProps: { tab: 'ventas' } });
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual({ v: 1 }));
    rerender({ tab: 'tiendas' });
    await waitFor(() => expect(result.current.data).toEqual({ t: 1 }));
    rerender({ tab: 'ventas' });
    expect(result.current.data).toEqual({ v: 1 });
    expect(api.ventas).toHaveBeenCalledTimes(1);
    expect(api.tiendas).toHaveBeenCalledTimes(1);
    expect(api.asesores).not.toHaveBeenCalled();
  });

  it('ignores a stale response that arrives after a newer request', async () => {
    const lenta = deferred();
    const api = { ventas: jest.fn().mockReturnValueOnce(lenta.promise).mockResolvedValueOnce({ mes: 'nuevo' }) };
    const { result, rerender } = renderHook(({ f }) => useKpis('ventas', f, api), { initialProps: { f: FILTROS } });
    rerender({ f: { ...FILTROS, hmcl: 'solo' } });
    await waitFor(() => expect(result.current.data).toEqual({ mes: 'nuevo' }));
    await act(async () => { lenta.resolve({ mes: 'viejo' }); });
    expect(result.current.data).toEqual({ mes: 'nuevo' });
  });

  it('shares one pending request between identical keys', async () => {
    const lenta = deferred();
    const api = { ventas: jest.fn().mockReturnValue(lenta.promise) };
    const { result, rerender } = renderHook(({ f }) => useKpis('ventas', f, api), { initialProps: { f: FILTROS } });
    rerender({ f: { ...FILTROS, hmcl: 'solo' } });
    rerender({ f: FILTROS });
    expect(api.ventas).toHaveBeenCalledTimes(2);
    await act(async () => { lenta.resolve({ ok: 1 }); });
    await waitFor(() => expect(result.current.data).toEqual({ ok: 1 }));
  });

  it('reports a Spanish error and does not cache failures', async () => {
    const api = { ventas: jest.fn().mockRejectedValueOnce(new Error('boom')).mockResolvedValue({ ok: true }) };
    const { result, rerender } = renderHook(({ f }) => useKpis('ventas', f, api), { initialProps: { f: FILTROS } });
    await waitFor(() => expect(result.current.error).toMatch(/No pudimos cargar/));
    expect(result.current.data).toBeNull();
    rerender({ f: { ...FILTROS, hmcl: 'excluir' } });
    await waitFor(() => expect(result.current.data).toEqual({ ok: true }));
    expect(result.current.error).toBeNull();
    rerender({ f: FILTROS });
    await waitFor(() => expect(result.current.data).toEqual({ ok: true }));
    expect(api.ventas).toHaveBeenCalledTimes(3);
  });

  it('does not fetch while there are no months or the tab has no fetcher', () => {
    const api = { ventas: jest.fn() };
    renderHook(() => useKpis('ventas', { ...FILTROS, meses: null }, api));
    renderHook(() => useKpis('asesores', FILTROS, api));
    expect(api.ventas).not.toHaveBeenCalled();
  });
});
