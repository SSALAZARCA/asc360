/**
 * Test counts on the pair device (odd/tasks/motored-conteo-prueba.md): both
 * the laptop and the phone screens show a PRUEBA badge when the backend says
 * `es_prueba`, and nothing for a real count.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import ConteoPublicoContainer from '../components/motored/conteo-publico/ConteoPublicoContainer';

const SLUG = 'K7Q2M9XH4P';
const CLAVE_SESION = `motored_conteo_sesion:${SLUG}`;

function respuesta(status, body, headers = {}) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: { get: (h) => headers[h] ?? null },
  });
}

function servidor(esPrueba) {
  const sesion = {
    sesion_id: 'ses-1', etiqueta: 'Pareja 1 · Ana G. y Luis P.', integrantes: ['Ana Gómez', 'Luis Pérez'],
    sucursal: 'Quilichao', estado_conteo: 'EN_CONTEO', ubicacion_actual: null, es_prueba: esPrueba,
  };
  const manejadores = {
    'POST /unirse': () => respuesta(201, { ...sesion, sesion_token: 'tok-123' }),
    'GET /sesion': () => respuesta(200, sesion),
    'GET /catalogo': () => respuesta(200, { version: 'v1', referencias: [] }, { ETag: '"v1"' }),
    'GET /ubicaciones': () => respuesta(200, []),
    'GET /lecturas/recientes': () => respuesta(200, { ubicacion_actual: null, lecturas: [], resumen_ubicacion: [] }),
    'GET /reconteos': () => respuesta(200, []),
  };
  global.fetch = jest.fn((url, init = {}) => {
    const ruta = String(url).split(`/publico/conteos/${SLUG}`)[1].split('?')[0];
    const manejador = manejadores[`${init.method || 'GET'} ${ruta}`];
    return manejador ? manejador() : respuesta(404, { detail: { code: 'NO_ENCONTRADO' } });
  });
}

function sesionGuardada() {
  localStorage.setItem(CLAVE_SESION, JSON.stringify({
    token: 'tok-123', sesionId: 'ses-1', etiqueta: 'Pareja 1 · Ana G. y Luis P.', sucursal: 'Quilichao',
  }));
}

function montar() {
  return render(<ConteoPublicoContainer slug={SLUG} intervaloEnvioMs={20} />);
}

beforeEach(() => {
  localStorage.clear();
  delete window.BarcodeDetector;
});

describe.each([['laptop', 1280], ['phone', 390]])('the %s screen', (_, ancho) => {
  beforeEach(() => {
    window.innerWidth = ancho;
  });

  it('shows the PRUEBA badge on a test count', async () => {
    servidor(true);
    sesionGuardada();
    montar();

    expect(await screen.findByText('PRUEBA')).toBeInTheDocument();
  });

  it('shows no badge on a real count', async () => {
    servidor(false);
    sesionGuardada();
    montar();

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/reconteos'), expect.anything()));
    await act(async () => {});
    expect(screen.getByText(/Pareja 1/)).toBeInTheDocument();
    expect(screen.queryByText('PRUEBA')).not.toBeInTheDocument();
  });
});
