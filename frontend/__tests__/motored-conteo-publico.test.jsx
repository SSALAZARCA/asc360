/**
 * Public pair counting screen (odd/motored-conteos-inventario WU13/WU14)
 * against a fake public API. Covers the join, session resume, the USB
 * scanner input, location first, unknown codes, the offline queue, reconteo
 * tasks, the mobile layout with camera scanning and the blind-count guard.
 */
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConteoPublicoContainer from '../components/motored/conteo-publico/ConteoPublicoContainer';

const SLUG = 'K7Q2M9XH4P';
const CLAVE_SESION = `motored_conteo_sesion:${SLUG}`;
const INTERVALO = 20;

function respuesta(status, body, headers = {}) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: { get: (h) => headers[h] ?? null },
  });
}

/** A fake of the public API; every handler can be overridden per test. */
function crearServidor(overrides = {}) {
  const s = {
    ubicacion: { id: 'u1', codigo: 'A3', nombre: 'ESTANTE A3' },
    estado: 'EN_CONTEO',
    lecturas: [],
    reconteos: [],
    catalogo: [['90305-KVN-900S', 'TUERCA BRIDA (14MM)'], ['17210-K0R-V00', 'ELEMENTO FILTRO AIRE']],
    llamadas: [],
    ...overrides,
  };
  const manejadores = {
    'POST /unirse': () => respuesta(201, {
      sesion_token: 'tok-123', sesion_id: 'ses-1', etiqueta: 'Pareja 1 · Ana G. y Luis P.',
      integrantes: ['Ana Gómez', 'Luis Pérez'], sucursal: 'Quilichao', estado_conteo: s.estado,
    }),
    'GET /sesion': () => respuesta(200, {
      sesion_id: 'ses-1', etiqueta: 'Pareja 1 · Ana G. y Luis P.', integrantes: ['Ana Gómez', 'Luis Pérez'],
      sucursal: 'Quilichao', estado_conteo: s.estado,
      ubicacion_actual: s.ubicacion ? { id: s.ubicacion.id, nombre: s.ubicacion.nombre } : null,
    }),
    'GET /catalogo': () => respuesta(200, { version: 'v1', referencias: s.catalogo }, { ETag: '"v1"' }),
    'GET /ubicaciones': () => respuesta(200, s.ubicacion ? [s.ubicacion] : []),
    'PUT /ubicacion': (body) => {
      const codigo = body.codigo.replace(/^UBI-/i, '').toUpperCase();
      s.ubicacion = { id: 'u-' + codigo, codigo, nombre: body.nombre || codigo };
      return respuesta(200, { ubicacion: s.ubicacion, creada: false });
    },
    'GET /lecturas/recientes': () => respuesta(200, {
      ubicacion_actual: s.ubicacion, lecturas: [], resumen_ubicacion: [],
    }),
    'POST /lecturas': (body) => {
      s.lecturas.push(...body.lecturas);
      return respuesta(200, {
        aceptadas: body.lecturas.map((l) => l.id), duplicadas: [], desconocidos: [],
        rechazadas: [], referencias: {},
      });
    },
    'GET /reconteos': () => respuesta(200, s.reconteos),
    'POST /salir': () => respuesta(204, null),
    ...s.manejadores,
  };
  global.fetch = jest.fn((url, init = {}) => {
    const ruta = String(url).split(`/publico/conteos/${SLUG}`)[1].split('?')[0];
    const metodo = init.method || 'GET';
    const body = init.body ? JSON.parse(init.body) : undefined;
    s.llamadas.push({ metodo, ruta, body, headers: init.headers || {} });
    let clave = `${metodo} ${ruta}`;
    if (/^\/lecturas\/[^/]+\/anular$/.test(ruta)) clave = 'POST /anular';
    if (/^\/reconteos\/[^/]+\/terminar$/.test(ruta)) clave = 'POST /terminar';
    const manejador = manejadores[clave];
    if (!manejador) return respuesta(404, { detail: { code: 'NO_ENCONTRADO' } });
    return manejador(body, init);
  });
  s.manejadores = manejadores;
  s.envios = () => s.llamadas.filter((l) => l.metodo === 'POST' && l.ruta === '/lecturas');
  return s;
}

function sesionGuardada() {
  localStorage.setItem(CLAVE_SESION, JSON.stringify({
    token: 'tok-123', sesionId: 'ses-1', etiqueta: 'Pareja 1 · Ana G. y Luis P.', sucursal: 'Quilichao',
  }));
}

function montar() {
  return render(<ConteoPublicoContainer slug={SLUG} intervaloEnvioMs={INTERVALO} />);
}

async function escanear(user, codigo) {
  const entrada = await screen.findByLabelText('Escanee con la pistola o escriba el código');
  await user.type(entrada, `${codigo}{Enter}`);
}

let user;
beforeEach(() => {
  localStorage.clear();
  window.innerWidth = 1280;
  delete window.BarcodeDetector;
  user = userEvent.setup();
});

describe('join', () => {
  async function llenarIngreso() {
    await user.type(screen.getByLabelText('Código del conteo'), '482913');
    const nombres = screen.getAllByLabelText('Nombre completo');
    const cedulas = screen.getAllByLabelText('Cédula');
    await user.type(nombres[0], 'Ana Gómez');
    await user.type(cedulas[0], '1.130.124');
    await user.type(nombres[1], 'Luis Pérez');
    await user.type(cedulas[1], '79123193');
  }

  it('shows the join screen with the notice and stores only the token on success', async () => {
    const s = crearServidor();
    montar();
    expect(await screen.findByRole('heading', { name: 'Ingreso de la pareja' })).toBeInTheDocument();
    expect(screen.getByText('Sus datos solo se usan para saber quién contó cada referencia. No se crea un usuario.')).toBeInTheDocument();
    await llenarIngreso();
    expect(screen.getAllByLabelText('Cédula')[0]).toHaveValue('1130124');
    await user.click(screen.getByRole('button', { name: 'Empezar a contar' }));

    expect(await screen.findByText('Pareja 1 · Ana G. y Luis P.')).toBeInTheDocument();
    const unirse = s.llamadas.find((l) => l.ruta === '/unirse');
    expect(unirse.body).toEqual({
      codigo: '482913', dispositivo: 'ESCRITORIO',
      integrantes: [{ nombre: 'Ana Gómez', cedula: '1130124' }, { nombre: 'Luis Pérez', cedula: '79123193' }],
    });
    const guardada = localStorage.getItem(CLAVE_SESION);
    expect(JSON.parse(guardada).token).toBe('tok-123');
    const todo = Object.keys(localStorage).map((k) => localStorage.getItem(k)).join('|');
    expect(todo).not.toContain('1130124');
    expect(todo).not.toContain('79123193');
    expect(document.body.textContent).not.toContain('79123193');
  });

  it('shows the generic message on 401', async () => {
    crearServidor({ manejadores: { 'POST /unirse': () => respuesta(401, { detail: { code: 'ACCESO_INVALIDO' } }) } });
    montar();
    await screen.findByRole('heading', { name: 'Ingreso de la pareja' });
    await llenarIngreso();
    await user.click(screen.getByRole('button', { name: 'Empezar a contar' }));
    expect(await screen.findByText('Código o enlace no válidos.')).toBeInTheDocument();
    expect(localStorage.getItem(CLAVE_SESION)).toBeNull();
  });

  it('shows the lock message on 429', async () => {
    crearServidor({ manejadores: { 'POST /unirse': () => respuesta(429, { detail: { code: 'DEMASIADOS_INTENTOS' } }) } });
    montar();
    await screen.findByRole('heading', { name: 'Ingreso de la pareja' });
    await llenarIngreso();
    await user.click(screen.getByRole('button', { name: 'Empezar a contar' }));
    expect(await screen.findByText('Demasiados intentos. Espere unos minutos e intente de nuevo.')).toBeInTheDocument();
  });
});

describe('session resume', () => {
  it('resumes with the stored token, sending it as Bearer', async () => {
    const s = crearServidor();
    sesionGuardada();
    montar();
    expect(await screen.findByText('ESTANTE A3', { selector: '[data-ubicacion-actual]' })).toBeInTheDocument();
    const sesion = s.llamadas.find((l) => l.ruta === '/sesion');
    expect(sesion.headers.Authorization).toBe('Bearer tok-123');
  });

  it('clears the token and returns to join on a 401', async () => {
    crearServidor({ manejadores: { 'GET /sesion': () => respuesta(401, { detail: { code: 'SESION_INACTIVA' } }) } });
    sesionGuardada();
    montar();
    expect(await screen.findByRole('heading', { name: 'Ingreso de la pareja' })).toBeInTheDocument();
    expect(localStorage.getItem(CLAVE_SESION)).toBeNull();
  });
});

describe('counting on a laptop', () => {
  it('a scanner burst plus Enter queues a reading with metodo ESCANER and sends it', async () => {
    const s = crearServidor();
    sesionGuardada();
    montar();
    await escanear(user, '90305-KVN-900S');
    expect(await screen.findByText(/Última lectura/)).toBeInTheDocument();
    await waitFor(() => expect(s.lecturas).toHaveLength(1));
    expect(s.lecturas[0]).toMatchObject({ codigo_leido: '90305-KVN-900S', cantidad: 1, metodo: 'ESCANER' });
    expect(s.lecturas[0].id).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.getByRole('heading', { name: 'Contado en ESTANTE A3' })).toBeInTheDocument();
    expect(screen.getByText('1 referencia')).toBeInTheDocument();
  });

  it('without a location it asks for one and sends nothing', async () => {
    const s = crearServidor({ ubicacion: null });
    sesionGuardada();
    montar();
    await escanear(user, '90305-KVN-900S');
    expect(await screen.findByText(/Primero indique la ubicación/)).toBeInTheDocument();
    await act(() => new Promise((r) => setTimeout(r, INTERVALO * 4)));
    expect(s.envios()).toHaveLength(0);
  });

  it('a UBI- scan sets the location', async () => {
    const s = crearServidor({ ubicacion: null });
    sesionGuardada();
    montar();
    await escanear(user, 'UBI-B7');
    await waitFor(() => expect(s.llamadas.find((l) => l.metodo === 'PUT')).toBeTruthy());
    expect(s.llamadas.find((l) => l.metodo === 'PUT').body).toEqual({ codigo: 'B7' });
    expect(await screen.findByText('B7', { selector: '[data-ubicacion-actual]' })).toBeInTheDocument();
    expect(s.envios()).toHaveLength(0);
  });

  it('an unknown code is not counted; "Registrar de todas formas" sends forzar_desconocido', async () => {
    const s = crearServidor();
    sesionGuardada();
    montar();
    await screen.findByText('ESTANTE A3', { selector: '[data-ubicacion-actual]' });
    await waitFor(() => expect(s.llamadas.some((l) => l.ruta === '/catalogo')).toBe(true));
    await escanear(user, '9O3O5-KVN');
    expect(await screen.findByText('Código no encontrado: 9O3O5-KVN.')).toBeInTheDocument();
    await act(() => new Promise((r) => setTimeout(r, INTERVALO * 4)));
    expect(s.envios()).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Registrar de todas formas' }));
    await waitFor(() => expect(s.lecturas).toHaveLength(1));
    expect(s.lecturas[0]).toMatchObject({ codigo_leido: '9O3O5-KVN', forzar_desconocido: true });
  });

  it('+ adds one and editing the quantity down voids and re-sends', async () => {
    const s = crearServidor({ manejadores: {
      'POST /anular': () => respuesta(200, { id: 'x', anulada_en: '2026-10-09T10:00:00Z' }),
    } });
    sesionGuardada();
    montar();
    await escanear(user, '90305-KVN-900S');
    await waitFor(() => expect(s.lecturas).toHaveLength(1));
    await user.click(screen.getByRole('button', { name: 'Sumar uno' }));
    await waitFor(() => expect(s.lecturas).toHaveLength(2));
    expect(screen.getByLabelText('Cantidad aquí')).toHaveValue(2);
    await user.click(screen.getByRole('button', { name: 'Restar uno' }));
    await waitFor(() => expect(s.llamadas.filter((l) => l.ruta.endsWith('/anular'))).toHaveLength(1));
    expect(screen.getByLabelText('Cantidad aquí')).toHaveValue(1);
  });
});

describe('offline queue', () => {
  it('keeps readings on a network error, shows the banner, retries and handles duplicadas', async () => {
    let falla = true;
    const s = crearServidor();
    s.manejadores['POST /lecturas'] = (body) => {
      if (falla) return Promise.reject(new TypeError('Failed to fetch'));
      return respuesta(200, {
        aceptadas: [], duplicadas: body.lecturas.map((l) => l.id), desconocidos: [], rechazadas: [], referencias: {},
      });
    };
    sesionGuardada();
    montar();
    await escanear(user, '90305-KVN-900S');
    await escanear(user, '17210-K0R-V00');
    expect(await screen.findByText('Sin conexión · 2 lecturas pendientes de enviar')).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(`motored_conteo_cola:${SLUG}`)).items).toHaveLength(2);
    falla = false;
    await waitFor(() => expect(screen.queryByText(/Sin conexión/)).not.toBeInTheDocument(), { timeout: 3000 });
    expect(localStorage.getItem(`motored_conteo_cola:${SLUG}`)).toBeNull();
    const lista = screen.getByRole('list', { name: 'Contado en ESTANTE A3' });
    expect(within(lista).getAllByRole('listitem')).toHaveLength(2);
    expect(within(lista).getAllByText('1')).toHaveLength(2);
  });

  it('warns before unload while readings are pending', async () => {
    const s = crearServidor();
    s.manejadores['POST /lecturas'] = () => Promise.reject(new TypeError('Failed to fetch'));
    sesionGuardada();
    montar();
    await escanear(user, '90305-KVN-900S');
    await screen.findByText(/pendiente de enviar/);
    const evento = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(evento);
    expect(evento.defaultPrevented).toBe(true);
  });

  it('resumes flushing a queue stored on this device', async () => {
    localStorage.setItem(`motored_conteo_cola:${SLUG}`, JSON.stringify({
      sesionId: 'ses-1',
      items: [{ op: 'lectura', id: '11111111-1111-4111-8111-111111111111', codigo_leido: '90305-KVN-900S',
        cantidad: 1, leida_en: '2026-10-09T10:00:00Z', metodo: 'ESCANER', ubicacion: 'A3' }],
    }));
    const s = crearServidor();
    sesionGuardada();
    montar();
    await waitFor(() => expect(s.lecturas).toHaveLength(1));
    expect(s.lecturas[0]).toEqual({
      id: '11111111-1111-4111-8111-111111111111', codigo_leido: '90305-KVN-900S', cantidad: 1,
      leida_en: '2026-10-09T10:00:00Z', metodo: 'ESCANER',
    });
  });

  it('shows a rejected reading', async () => {
    const s = crearServidor();
    s.manejadores['POST /lecturas'] = (body) => respuesta(200, {
      aceptadas: [], duplicadas: [], desconocidos: [],
      rechazadas: body.lecturas.map((l) => ({ id: l.id, motivo: 'RONDA_CERRADA' })), referencias: {},
    });
    sesionGuardada();
    montar();
    await escanear(user, '90305-KVN-900S');
    expect(await screen.findByText(/La ronda de conteo ya terminó/)).toBeInTheDocument();
  });
});

describe('changing location offline', () => {
  /** POST /lecturas and PUT /ubicacion fail while `red.caida`. */
  function servidorConCorte() {
    const red = { caida: false };
    const s = crearServidor();
    const { 'POST /lecturas': enviar, 'PUT /ubicacion': fijar } = s.manejadores;
    s.manejadores['POST /lecturas'] = (body) => (red.caida
      ? Promise.reject(new TypeError('Failed to fetch')) : enviar(body));
    s.manejadores['PUT /ubicacion'] = (body) => (red.caida
      ? Promise.reject(new TypeError('Failed to fetch')) : fijar(body));
    s.manejadores['GET /lecturas/recientes'] = () => {
      const aqui = s.lecturas.filter((l) => l.ubicacion_codigo === s.ubicacion.codigo);
      const resumen = {};
      aqui.forEach((l) => {
        resumen[l.codigo_leido] = resumen[l.codigo_leido] || { codigo: l.codigo_leido, descripcion: '', cantidad: 0, lecturas: 0 };
        resumen[l.codigo_leido].cantidad += l.cantidad;
        resumen[l.codigo_leido].lecturas += 1;
      });
      return respuesta(200, {
        ubicacion_actual: s.ubicacion, resumen_ubicacion: Object.values(resumen),
        lecturas: aqui.map((l) => ({
          id: l.id, codigo: l.codigo_leido, descripcion: '', cantidad: l.cantidad, metodo: l.metodo,
          ubicacion: { codigo: l.ubicacion_codigo, nombre: l.ubicacion_codigo }, leida_en: l.leida_en, anulada_en: null,
        })),
      });
    };
    return { s, red };
  }

  async function listo(s) {
    await screen.findByText('ESTANTE A3', { selector: '[data-ubicacion-actual]' });
    await waitFor(() => expect(s.llamadas.some((l) => l.ruta === '/catalogo')).toBe(true));
  }

  function lista(nombre) {
    return within(screen.getByRole('list', { name: `Contado en ${nombre}` }));
  }

  it('moves shelves without internet and sends each reading with its own location', async () => {
    const { s, red } = servidorConCorte();
    sesionGuardada();
    montar();
    await listo(s);
    red.caida = true;

    await escanear(user, 'UBI-B7');
    expect(await screen.findByText('B7', { selector: '[data-ubicacion-actual]' })).toBeInTheDocument();
    await escanear(user, '90305-KVN-900S');
    await escanear(user, 'ubi-c1');
    expect(await screen.findByText('C1', { selector: '[data-ubicacion-actual]' })).toBeInTheDocument();
    await escanear(user, '17210-K0R-V00');

    expect(screen.queryByText(/Espere a tener conexión/)).not.toBeInTheDocument();
    expect(screen.queryByText(/no se pudo cambiar la ubicación/)).not.toBeInTheDocument();
    expect(await screen.findByText(/2 lecturas pendientes de enviar/)).toBeInTheDocument();
    expect(s.lecturas).toHaveLength(0);

    red.caida = false;
    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    await waitFor(() => expect(s.lecturas).toHaveLength(2), { timeout: 3000 });
    expect(s.lecturas.map((l) => [l.codigo_leido, l.ubicacion_codigo])).toEqual([
      ['90305-KVN-900S', 'B7'], ['17210-K0R-V00', 'C1'],
    ]);
    await waitFor(() => expect(s.ubicacion.codigo).toBe('C1'));
    const ultimoEnvio = s.llamadas.map((l) => l.ruta).lastIndexOf('/lecturas');
    const ultimoPut = s.llamadas.map((l) => l.metodo).lastIndexOf('PUT');
    expect(ultimoPut).toBeGreaterThan(ultimoEnvio);
    expect(lista('C1').getAllByRole('listitem')).toHaveLength(1);
    expect(lista('C1').getByText('17210-K0R-V00')).toBeInTheDocument();
    expect(lista('C1').getByText('1')).toBeInTheDocument();
  });

  it('lists what was counted per stamped location', async () => {
    const { s, red } = servidorConCorte();
    sesionGuardada();
    montar();
    await listo(s);
    red.caida = true;

    await escanear(user, '90305-KVN-900S');
    await escanear(user, 'UBI-B7');
    await screen.findByText('B7', { selector: '[data-ubicacion-actual]' });
    await escanear(user, '17210-K0R-V00');
    await escanear(user, '17210-K0R-V00');

    expect(lista('B7').getAllByRole('listitem')).toHaveLength(1);
    expect(lista('B7').getByText('2')).toBeInTheDocument();
    expect(lista('B7').queryByText('TUERCA BRIDA (14MM)')).not.toBeInTheDocument();

    await escanear(user, 'UBI-A3');
    await screen.findByText('ESTANTE A3', { selector: '[data-ubicacion-actual]' });
    expect(lista('ESTANTE A3').getAllByRole('listitem')).toHaveLength(1);
    expect(lista('ESTANTE A3').getByText('TUERCA BRIDA (14MM)')).toBeInTheDocument();
  });
});

describe('reconteo tasks', () => {
  const tarea = {
    id: 'rec-1', codigo: '17210-K0R-V00', descripcion: 'ELEMENTO FILTRO AIRE',
    ubicaciones: ['ESTANTE A3', 'BODEGA 2'], estado: 'ASIGNADO',
  };

  it('lists tasks without quantities and tags readings with reconteo_id', async () => {
    const s = crearServidor({ estado: 'EN_RECONTEO', reconteos: [tarea] });
    s.manejadores['POST /terminar'] = () => respuesta(200, { id: 'rec-1', estado: 'TERMINADO', terminado_en: null });
    sesionGuardada();
    montar();
    await user.click(await screen.findByRole('tab', { name: 'Reconteos asignados (1)' }));
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getByText('17210-K0R-V00')).toBeInTheDocument();
    expect(within(panel).getByText('ELEMENTO FILTRO AIRE')).toBeInTheDocument();
    expect(within(panel).getByText(/ESTANTE A3, BODEGA 2/)).toBeInTheDocument();
    await user.click(within(panel).getByRole('button', { name: 'Contar este reconteo' }));
    await escanear(user, '17210-K0R-V00');
    await waitFor(() => expect(s.lecturas).toHaveLength(1));
    expect(s.lecturas[0]).toMatchObject({ codigo_leido: '17210-K0R-V00', reconteo_id: 'rec-1' });

    await user.click(screen.getByRole('button', { name: 'Terminar reconteo' }));
    await user.click(screen.getByRole('button', { name: 'Sí, terminar' }));
    await waitFor(() => expect(s.llamadas.some((l) => l.ruta === '/reconteos/rec-1/terminar')).toBe(true));
  });
});

describe('blind count guard', () => {
  it('never renders expected quantities, stock words or money from API data', async () => {
    const s = crearServidor({
      reconteos: [{ id: 'rec-1', codigo: '17210-K0R-V00', descripcion: 'FILTRO', ubicaciones: ['A3'],
        estado: 'ASIGNADO', cantidad_sistema: 777, existencia: 555, costo: '$ 12.345' }],
    });
    s.manejadores['GET /lecturas/recientes'] = () => respuesta(200, {
      ubicacion_actual: s.ubicacion, sistema: 999, existencia: 555, valor: '$ 9.000',
      lecturas: [], resumen_ubicacion: [{ codigo: '90305-KVN-900S', descripcion: 'TUERCA', cantidad: 4, lecturas: 4, sistema: 777 }],
    });
    sesionGuardada();
    montar();
    await screen.findByText('TUERCA');
    await user.click(screen.getByRole('tab', { name: 'Reconteos asignados (1)' }));
    await screen.findByText('FILTRO');
    const texto = document.body.textContent
      .replace('Conteo a ciegas: no se muestra cuánto dice el sistema.', '');
    expect(texto).not.toMatch(/sistema/i);
    expect(texto).not.toMatch(/existencia/i);
    expect(texto).not.toContain('$');
    expect(texto).not.toContain('777');
    expect(texto).not.toContain('555');
  });
});

describe('mobile', () => {
  beforeEach(() => {
    window.innerWidth = 390;
  });

  it('renders the mobile layout under 600 px, without camera when BarcodeDetector is missing', async () => {
    crearServidor();
    sesionGuardada();
    montar();
    expect(await screen.findByRole('button', { name: 'Escribir código' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Lo contado (0)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reconteos asignados (0)' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Vista de la cámara apuntando al código de barras')).not.toBeInTheDocument();
    expect(screen.getByText(/lector Bluetooth/)).toBeInTheDocument();
    expect(screen.getByLabelText('Escriba el código')).toBeInTheDocument();
  });

  it('a camera detection queues a reading with metodo CAMARA and debounces repeats', async () => {
    const detect = jest.fn().mockResolvedValue([{ rawValue: '90305-KVN-900S' }]);
    window.BarcodeDetector = jest.fn(() => ({ detect }));
    window.BarcodeDetector.getSupportedFormats = jest.fn().mockResolvedValue(['code_128', 'code_39']);
    const pista = { stop: jest.fn() };
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: jest.fn().mockResolvedValue({ getTracks: () => [pista] }) },
    });
    jest.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve());
    navigator.vibrate = jest.fn();
    const s = crearServidor();
    sesionGuardada();
    const { unmount } = montar();
    expect(await screen.findByLabelText('Vista de la cámara apuntando al código de barras')).toBeInTheDocument();
    await waitFor(() => expect(s.lecturas).toHaveLength(1), { timeout: 3000 });
    expect(s.lecturas[0]).toMatchObject({ codigo_leido: '90305-KVN-900S', metodo: 'CAMARA' });
    await act(() => new Promise((r) => setTimeout(r, 700)));
    expect(detect.mock.calls.length).toBeGreaterThan(1);
    expect(s.lecturas).toHaveLength(1);
    expect(navigator.vibrate).toHaveBeenCalled();
    unmount();
    expect(pista.stop).toHaveBeenCalled();
  });

  it('manual entry on the phone sends metodo MANUAL', async () => {
    const s = crearServidor();
    sesionGuardada();
    montar();
    await user.click(await screen.findByRole('button', { name: 'Escribir código' }));
    const entrada = screen.getByLabelText('Escriba el código');
    fireEvent.change(entrada, { target: { value: '90305-KVN-900S' } });
    await user.click(screen.getByRole('button', { name: 'Sumar' }));
    await waitFor(() => expect(s.lecturas).toHaveLength(1));
    expect(s.lecturas[0].metodo).toBe('MANUAL');
  });
});
