/**
 * The pair screen after a reload (odd/tasks/motored-conteo-recarga-pareja.md):
 * when `/lecturas/recientes` fails on mount, the screen warns instead of
 * showing a silent 0 and retries the seed on the 30 s timer and on `online`
 * until it succeeds. The saved session also keeps `esPrueba`, so the PRUEBA
 * badge shows before `/sesion` answers.
 */
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConteoPublicoContainer from '../components/motored/conteo-publico/ConteoPublicoContainer';
import { guardarSesion } from '../lib/motored/conteoPublicoApi';

const SLUG = 'K7Q2M9XH4P';
const CLAVE_SESION = `motored_conteo_sesion:${SLUG}`;
const AVISO = 'No se pudo cargar lo contado. Reintentando… No vuelva a escanear lo que ya contó.';
const UBICACION = { id: 'u1', codigo: 'A1', nombre: 'ESTANTE A1' };
const TUERCA = '90305-KVN-900S';

function respuesta(status, body) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: { get: () => null },
  });
}

/**
 * A fake of the public API whose server already holds 3 TUERCA in A1.
 * `s.fallaRecientes` (a status) makes `/lecturas/recientes` fail.
 */
function crearServidor({ fallaRecientes = 503, esPrueba = false, sesionColgada = false } = {}) {
  const previas = [1, 2, 3].map((n) => ({
    id: `srv-${n}`, codigo: TUERCA, descripcion: 'TUERCA BRIDA', cantidad: 1, ubicacion: { codigo: 'A1' },
  }));
  const s = { fallaRecientes, lecturas: [], llamadas: [] };
  const todas = () => [...previas, ...s.lecturas.map((l) => ({
    id: l.id, codigo: l.codigo_leido, descripcion: 'TUERCA BRIDA', cantidad: l.cantidad,
    ubicacion: { codigo: l.ubicacion_codigo },
  }))];
  const manejadores = {
    'GET /sesion': () => (sesionColgada ? new Promise(() => {}) : respuesta(200, {
      sesion_id: 'ses-1', etiqueta: 'Pareja 1 · Ana G. y Luis P.', sucursal: 'Quilichao',
      estado_conteo: 'EN_CONTEO', ubicacion_actual: UBICACION, es_prueba: esPrueba,
    })),
    'GET /catalogo': () => respuesta(200, { version: 'v1', referencias: [[TUERCA, 'TUERCA BRIDA']] }),
    'GET /ubicaciones': () => respuesta(200, [UBICACION]),
    'GET /reconteos': () => respuesta(200, []),
    'GET /lecturas/recientes': () => {
      if (s.fallaRecientes) return respuesta(s.fallaRecientes, { detail: { code: 'FALLO' } });
      const lecturas = todas();
      const cantidad = lecturas.filter((l) => l.ubicacion.codigo === 'A1').reduce((t, l) => t + l.cantidad, 0);
      return respuesta(200, {
        ubicacion_actual: UBICACION,
        lecturas,
        resumen_ubicacion: [{ codigo: TUERCA, descripcion: 'TUERCA BRIDA', cantidad: String(cantidad) }],
      });
    },
    'POST /lecturas': (body) => {
      s.lecturas.push(...body.lecturas);
      return respuesta(200, {
        aceptadas: body.lecturas.map((l) => l.id), duplicadas: [], desconocidos: [], rechazadas: [], referencias: {},
      });
    },
  };
  global.fetch = jest.fn((url, init = {}) => {
    const ruta = String(url).split(`/publico/conteos/${SLUG}`)[1].split('?')[0];
    const metodo = init.method || 'GET';
    const body = init.body ? JSON.parse(init.body) : undefined;
    s.llamadas.push({ metodo, ruta });
    const manejador = manejadores[`${metodo} ${ruta}`];
    return manejador ? manejador(body) : respuesta(404, { detail: { code: 'NO_ENCONTRADO' } });
  });
  s.recientesPedidas = () => s.llamadas.filter((l) => l.ruta === '/lecturas/recientes').length;
  return s;
}

/** A saved session WITH a location, as after counting a while. */
function sesionGuardada() {
  localStorage.setItem(CLAVE_SESION, JSON.stringify({
    token: 'tok-123', sesionId: 'ses-1', etiqueta: 'Pareja 1 · Ana G. y Luis P.', sucursal: 'Quilichao',
    ubicacion: { codigo: 'A1', nombre: 'ESTANTE A1' },
  }));
}

function montar() {
  return render(<ConteoPublicoContainer slug={SLUG} intervaloEnvioMs={20} />);
}

function lista() {
  return within(screen.getByRole('list', { name: 'Contado en ESTANTE A1' }));
}

/** Runs the 30 s refresh of the screen once, without waiting 30 s. */
function refrescoDe30s(espia) {
  const llamada = espia.mock.calls.filter(([, ms]) => ms === 30000).pop();
  return act(async () => {
    llamada[0]();
  });
}

let user;
let espiaIntervalo;
beforeEach(() => {
  localStorage.clear();
  window.innerWidth = 1280;
  delete window.BarcodeDetector;
  user = userEvent.setup();
  espiaIntervalo = jest.spyOn(window, 'setInterval');
});

afterEach(() => {
  espiaIntervalo.mockRestore();
});

describe('a failed seed on reload', () => {
  it('warns instead of a silent 0 and restores the list on the next online event', async () => {
    const s = crearServidor({ fallaRecientes: 503 });
    sesionGuardada();
    montar();

    expect(await screen.findByText(AVISO)).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Contado en ESTANTE A1' })).not.toBeInTheDocument();

    s.fallaRecientes = null;
    act(() => {
      window.dispatchEvent(new Event('online'));
    });

    await waitFor(() => expect(screen.queryByText(AVISO)).not.toBeInTheDocument());
    expect(lista().getByText(TUERCA)).toBeInTheDocument();
    expect(lista().getByText('3')).toBeInTheDocument();
  });

  it('warns on a non-network error too and retries on the 30 s refresh', async () => {
    const s = crearServidor({ fallaRecientes: 409 });
    sesionGuardada();
    montar();

    expect(await screen.findByText(AVISO)).toBeInTheDocument();
    const antes = s.recientesPedidas();
    await refrescoDe30s(espiaIntervalo);
    expect(s.recientesPedidas()).toBe(antes + 1);
    expect(screen.getByText(AVISO)).toBeInTheDocument();

    s.fallaRecientes = null;
    await refrescoDe30s(espiaIntervalo);

    await waitFor(() => expect(screen.queryByText(AVISO)).not.toBeInTheDocument());
    expect(lista().getByText('3')).toBeInTheDocument();
    // Once seeded, the refresh stops asking for the list.
    const despues = s.recientesPedidas();
    await refrescoDe30s(espiaIntervalo);
    expect(s.recientesPedidas()).toBe(despues);
  });

  it('keeps readings scanned while the notice shows, without counting them twice', async () => {
    const s = crearServidor({ fallaRecientes: 503 });
    sesionGuardada();
    montar();
    expect(await screen.findByText(AVISO)).toBeInTheDocument();
    await waitFor(() => expect(s.llamadas.some((l) => l.ruta === '/catalogo')).toBe(true));

    const entrada = screen.getByLabelText('Escanee con la pistola o escriba el código');
    await user.type(entrada, `${TUERCA}{Enter}`);
    await user.type(entrada, `${TUERCA}{Enter}`);
    await waitFor(() => expect(s.lecturas).toHaveLength(2));
    expect(lista().getByText('2')).toBeInTheDocument();

    s.fallaRecientes = null;
    act(() => {
      window.dispatchEvent(new Event('online'));
    });

    await waitFor(() => expect(screen.queryByText(AVISO)).not.toBeInTheDocument());
    expect(lista().getAllByRole('listitem')).toHaveLength(1);
    expect(lista().getByText('5')).toBeInTheDocument();
    expect(s.lecturas).toHaveLength(2);
  });

  it('shows the notice on the phone screen too', async () => {
    window.innerWidth = 390;
    const s = crearServidor({ fallaRecientes: 503 });
    sesionGuardada();
    montar();

    expect(await screen.findByText(AVISO)).toBeInTheDocument();
    s.fallaRecientes = null;
    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    await waitFor(() => expect(screen.queryByText(AVISO)).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Lo contado (1)' })).toBeInTheDocument();
  });
});

describe('the saved session', () => {
  it('keeps esPrueba, so the PRUEBA badge shows before /sesion answers', async () => {
    crearServidor({ fallaRecientes: null, esPrueba: true, sesionColgada: true });
    guardarSesion(SLUG, {
      token: 'tok-123', sesionId: 'ses-1', etiqueta: 'Pareja 1 · Ana G. y Luis P.', sucursal: 'Quilichao',
      esPrueba: true,
    });
    expect(JSON.parse(localStorage.getItem(CLAVE_SESION)).esPrueba).toBe(true);

    montar();
    expect(await screen.findByText('PRUEBA')).toBeInTheDocument();
  });
});
