/**
 * Referencias: "Descargar Excel" (`odd/tasks/motored-referencias-descarga-
 * excel.md`, T2). The button next to the search box downloads what the
 * table shows filtered (same search, línea and estado), with a busy state
 * and an error message; the API helper hits the export endpoint with the
 * same query parameters as `/buscar`, minus paging.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockBuscarReferencias = jest.fn();
const mockDescargarReferenciasExcel = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: () => Promise.resolve([{ id: 'p1', codigo: 'HMCL', nombre: 'HMCL Colombia' }]),
  listLineasComerciales: () => Promise.resolve(['ACCESORIOS', 'REPUESTOS']),
  buscarReferencias: (...args) => mockBuscarReferencias(...args),
  descargarReferenciasExcel: (...args) => mockDescargarReferenciasExcel(...args),
}));

import ReferenciasTab from '../components/motored/maestros/ReferenciasTab';

const REF = {
  id: 'r1', codigo: 'REF-1', proveedor_id: 'p1', nombre: 'Uno', linea_comercial: 'REPUESTOS',
  unidad_empaque: 1, unidad_empaque_advertencia: false, precio_normal: '1.00', precio_publico: null,
  sustituida_por: null, sustituta_codigo: null, homologados: [], activa: true,
};

beforeEach(() => {
  mockBuscarReferencias.mockReset().mockImplementation(({ page, pageSize }) => (
    Promise.resolve({ items: [REF], total: 1, page, page_size: pageSize })
  ));
  mockDescargarReferenciasExcel.mockReset().mockResolvedValue({ nombre: 'referencias_2026-10-10.xlsx' });
});

function lastQuery() {
  const { calls } = mockBuscarReferencias.mock;
  return calls[calls.length - 1][0];
}

async function renderTab() {
  render(<ReferenciasTab />);
  await within(await screen.findByRole('table')).findByText('REF-1');
}

function boton() {
  return screen.getByRole('button', { name: /Descargar Excel|Descargando/ });
}

describe('ReferenciasTab — Descargar Excel', () => {
  it('sits in the same row as the search box', async () => {
    await renderTab();

    const fila = screen.getByLabelText('Buscar referencia').closest('label').parentElement;
    expect(within(fila).getByRole('button', { name: 'Descargar Excel' })).toBeInTheDocument();
  });

  it('downloads with the filters the table is showing, without paging', async () => {
    await renderTab();
    const linea = screen.getByLabelText('Filtrar por línea comercial');
    await within(linea).findByRole('option', { name: 'REPUESTOS' });
    fireEvent.change(screen.getByLabelText('Buscar referencia'), { target: { value: 'filtro' } });
    fireEvent.change(linea, { target: { value: 'REPUESTOS' } });
    fireEvent.change(screen.getByLabelText('Filtrar por estado'), { target: { value: 'false' } });
    await waitFor(() => expect(lastQuery()).toMatchObject({ q: 'filtro', activa: false }));

    fireEvent.click(boton());

    await waitFor(() => expect(mockDescargarReferenciasExcel).toHaveBeenCalledTimes(1));
    expect(mockDescargarReferenciasExcel).toHaveBeenCalledWith({
      q: 'filtro', lineaComercial: 'REPUESTOS', activa: false,
    });
  });

  it('without filters it asks for the whole master', async () => {
    await renderTab();

    fireEvent.click(boton());

    await waitFor(() => expect(mockDescargarReferenciasExcel).toHaveBeenCalledWith({
      q: '', lineaComercial: '', activa: null,
    }));
  });

  it('shows a busy, disabled button while the file is being built', async () => {
    let terminar;
    mockDescargarReferenciasExcel.mockReturnValue(new Promise((resolve) => { terminar = resolve; }));
    await renderTab();

    fireEvent.click(boton());

    expect(await screen.findByRole('button', { name: 'Descargando…' })).toBeDisabled();
    terminar({});
    expect(await screen.findByRole('button', { name: 'Descargar Excel' })).toBeEnabled();
  });

  it('shows an error message when the download fails', async () => {
    mockDescargarReferenciasExcel.mockRejectedValue(new Error('HTTP 500'));
    await renderTab();

    fireEvent.click(boton());

    expect(await screen.findByText('No se pudo descargar el Excel (HTTP 500).')).toBeInTheDocument();
    expect(boton()).toBeEnabled();
  });
});

describe('descargarReferenciasExcel (API helper)', () => {
  const BASE = 'http://localhost:8000/api/motored';
  const { descargarReferenciasExcel } = jest.requireActual('../lib/motored/api');
  const { MOTORED_TOKEN_KEY } = jest.requireActual('../lib/motored/motoredFetch');

  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem(MOTORED_TOKEN_KEY, 'fake-token');
    global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
    global.URL.revokeObjectURL = jest.fn();
    const realCreateElement = document.createElement.bind(document);
    jest.spyOn(document, 'createElement').mockImplementation((tag) => {
      const el = realCreateElement(tag);
      if (tag === 'a') el.click = jest.fn();
      return el;
    });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: (name) => (name.toLowerCase() === 'content-disposition'
        ? "attachment; filename=\"referencias_2026-10-10.xlsx\"; filename*=UTF-8''referencias_2026-10-10.xlsx"
        : null) },
      blob: async () => ({ fake: 'blob' }),
    });
  });

  afterEach(() => jest.restoreAllMocks());

  it('hits the export endpoint with only the filters that have a value', async () => {
    const res = await descargarReferenciasExcel({ q: ' filtro ', lineaComercial: '', activa: false });

    const url = new URL(global.fetch.mock.calls[0][0]);
    expect(`${url.origin}${url.pathname}`).toBe(`${BASE}/maestros/referencias/exportar.xlsx`);
    expect(url.searchParams.get('q')).toBe('filtro');
    expect(url.searchParams.get('activa')).toBe('false');
    expect(url.searchParams.has('linea_comercial')).toBe(false);
    expect(url.searchParams.has('page')).toBe(false);
    expect(res.nombre).toBe('referencias_2026-10-10.xlsx');
  });

  it('rejects when the server answers an error', async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: 'x' }) });

    await expect(descargarReferenciasExcel({})).rejects.toThrow();
  });
});
