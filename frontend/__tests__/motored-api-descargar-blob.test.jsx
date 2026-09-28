/**
 * Ad-hoc dedupe (asc360, NOT tracked under any sdd/* change): `descargarPlantilla`
 * and `descargarErroresCargaCsv` in `lib/motored/api.js` share the exact same
 * "fetch -> check ok -> blob -> createObjectURL -> <a download> -> click ->
 * delayed revoke" sequence, differing only in the URL path and the downloaded
 * filename (gga finding, commit `a6a290d`). Neither had a direct unit test
 * before this file -- only indirect coverage through the components that call
 * them (`motored-bulk-upload-template.test.jsx`, `motored-cargas-errores-
 * csv.test.jsx`, both of which mock `lib/motored/api` entirely). This file
 * exercises the real functions (mirrors `motored-demanda-perdida-panel-api.
 * test.jsx`'s convention: mock `global.fetch` directly, not the module under
 * test) as a characterization safety net BEFORE extracting the shared
 * `_descargarBlob` helper, and stays green identically AFTER the extraction --
 * proof of zero behavior change.
 */
import { descargarPlantilla, descargarErroresCargaCsv } from '../lib/motored/api';
import { MOTORED_TOKEN_KEY } from '../lib/motored/motoredFetch';

const BASE = 'http://localhost:8000/api/motored';

let createObjectURLMock;
let revokeObjectURLMock;
let clickMock;
const FAKE_BLOB = { fake: 'blob' };

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_TOKEN_KEY, 'fake-token');
  jest.useFakeTimers();

  createObjectURLMock = jest.fn(() => 'blob:mock-url');
  revokeObjectURLMock = jest.fn();
  global.URL.createObjectURL = createObjectURLMock;
  global.URL.revokeObjectURL = revokeObjectURLMock;

  clickMock = jest.fn();
  const realCreateElement = document.createElement.bind(document);
  jest.spyOn(document, 'createElement').mockImplementation((tag) => {
    const el = realCreateElement(tag);
    if (tag === 'a') el.click = clickMock;
    return el;
  });

  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    blob: async () => FAKE_BLOB,
  });
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
  jest.restoreAllMocks();
});

describe('descargarPlantilla', () => {
  it('fetches the exact plantilla.xlsx URL for the given entidad', async () => {
    await descargarPlantilla('referencia');

    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/maestros/referencia/plantilla.xlsx`);
  });

  it('creates an object URL from the response blob and clicks a download link named plantilla_{entidad}.xlsx', async () => {
    await descargarPlantilla('sucursal');

    expect(createObjectURLMock).toHaveBeenCalledWith(FAKE_BLOB);
    expect(clickMock).toHaveBeenCalledTimes(1);
  });

  it('revokes the object URL after the click (delayed, not in the same tick)', async () => {
    await descargarPlantilla('sucursal');

    expect(revokeObjectURLMock).not.toHaveBeenCalled();
    jest.runOnlyPendingTimers();
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:mock-url');
  });

  it('throws HTTP {status} when the response is not ok', async () => {
    global.fetch.mockResolvedValueOnce({ ok: false, status: 403 });

    await expect(descargarPlantilla('referencia')).rejects.toThrow('HTTP 403');
  });
});

describe('descargarErroresCargaCsv', () => {
  it('fetches the exact errores.csv URL for the given carga id', async () => {
    await descargarErroresCargaCsv('carga-1');

    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/cargas/carga-1/errores.csv`);
  });

  it('creates an object URL from the response blob and clicks a download link named errores_{cargaId}.csv', async () => {
    await descargarErroresCargaCsv('carga-42');

    expect(createObjectURLMock).toHaveBeenCalledWith(FAKE_BLOB);
    expect(clickMock).toHaveBeenCalledTimes(1);
  });

  it('throws HTTP {status} when the response is not ok', async () => {
    global.fetch.mockResolvedValueOnce({ ok: false, status: 502 });

    await expect(descargarErroresCargaCsv('carga-1')).rejects.toThrow('HTTP 502');
  });
});
