/**
 * Detractors panel (T8): case detail — warning banner, cards, timeline,
 * add action and state changes.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockFetch = jest.fn();
const pushMock = jest.fn();

jest.mock('../lib/motored/motoredFetch', () => ({
  ...jest.requireActual('../lib/motored/motoredFetch'),
  motoredFetch: (...a) => mockFetch(...a),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/detractores/c1',
  useParams: () => ({ id: 'c1' }),
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import DetractorDetailPage from '../app/motored/detractores/[id]/page';

const res = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

const MATRIX_TEXTS = [
  'La explicación y asesoría técnica que le dieron en el taller de los problemas que tenía la moto',
  'La confianza en la reparación de la motocicleta realizada por el taller o centro de servicio',
  'Servicio que le prestaron en el taller o centro de servicio',
  'La calidad del trabajo realizado por los mecánicos',
  'La claridad en la explicación recibida de los cobros realizados antes y después del servicio',
  'La confianza en la procedencia y originalidad de los repuestos',
];

function caso(over = {}) {
  return {
    id: 'c1', numero: 12, estado: 'ABIERTO', resultado: null,
    created_at: '2026-09-20T15:30:00', cerrado_at: null, asignado_a: null,
    cliente: { nombre: 'Ana Pérez' }, satisfaccion_general: 2, autoriza_datos: true,
    registro: {
      nombre: 'Ana Pérez', cedula: '1012345678', celular: '3001234567', linea: 'Xpeed 125',
      placa: 'ABC12D', sic: 'SIC-77', centro_servicio: 'Taller Norte', tipo: 'SERVICIO_TALLER',
      carga: { nombre_archivo: 'base_sep.xlsx', fecha: '2026-09-10T09:00:00' },
    },
    respuesta: {
      satisfaccion_general: 2,
      p_explicacion_tecnica: 4, p_confianza_reparacion: null, p_servicio_taller: 1,
      p_calidad_mecanicos: 3, p_claridad_cobros: 5, p_originalidad_repuestos: 2,
      observaciones: 'Demoraron mucho', autoriza_datos: true, created_at: '2026-09-20T15:30:00',
    },
    acciones: [
      { id: 'a1', tipo: 'APERTURA', descripcion: 'Caso abierto por encuesta', estado_anterior: null, estado_nuevo: null, created_at: '2026-09-20T15:30:00', usuario: null },
      { id: 'a2', tipo: 'CAMBIO_ESTADO', descripcion: 'Lo tomo yo', estado_anterior: 'ABIERTO', estado_nuevo: 'EN_GESTION', created_at: '2026-09-21T10:00:00', usuario: { id: 'u1', nombre: 'Marta Ruiz' } },
    ],
    ...over,
  };
}

let current;
function route(handlers = {}) {
  mockFetch.mockImplementation(async (path, opts = {}) => {
    if (opts.method === 'POST' && handlers.post) return handlers.post(path, JSON.parse(opts.body));
    return res(current);
  });
}

async function renderDetail(role = 'SERVICIO_CLIENTE') {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 't');
  render(<DetractorDetailPage />);
  await screen.findByText('Caso No. 12');
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  current = caso();
  route();
});

describe('Detractor detail — header and consent warning', () => {
  it('shows header data', async () => {
    await renderDetail();
    expect(screen.getByText('Abierto')).toBeInTheDocument();
    expect(mockFetch.mock.calls[0][0]).toBe('/detractores/c1');
  });

  it('shows a prominent warning when the customer did not authorize data', async () => {
    current = caso({ autoriza_datos: false, respuesta: { ...caso().respuesta, autoriza_datos: false } });
    await renderDetail();
    const banner = screen.getByRole('alert');
    expect(banner).toHaveTextContent('Cliente NO autorizó tratamiento de datos');
    expect(banner).toHaveTextContent('Respondió «No» a la autorización de datos en la encuesta. Tenlo en cuenta antes de contactarlo.');
  });

  it('shows no warning when the customer authorized', async () => {
    await renderDetail();
    expect(screen.queryByText(/NO autorizó tratamiento de datos/)).not.toBeInTheDocument();
  });

  it('shows the result when closed', async () => {
    current = caso({ estado: 'CERRADO', resultado: 'RECUPERADO' });
    await renderDetail();
    expect(screen.getByText('Recuperado')).toBeInTheDocument();
  });
});

describe('Detractor detail — cliente and respuesta', () => {
  it('shows contact links and the SIC tooltip', async () => {
    await renderDetail();
    expect(screen.getByRole('link', { name: '3001234567' })).toHaveAttribute('href', 'tel:3001234567');
    expect(screen.getByRole('link', { name: /WhatsApp/ })).toHaveAttribute('href', 'https://wa.me/573001234567');
    expect(screen.getByText('SIC-77')).toBeInTheDocument();
    expect(screen.getAllByRole('note').length).toBeGreaterThan(0);
    expect(screen.getByText('base_sep.xlsx', { exact: false })).toBeInTheDocument();
  });

  it('omits the WhatsApp link when the number is not a Colombian mobile', async () => {
    current = caso({ registro: { ...caso().registro, celular: '6011234567' } });
    await renderDetail();
    expect(screen.queryByRole('link', { name: /WhatsApp/ })).not.toBeInTheDocument();
  });

  it('shows the general score with label and the six verbatim matrix rows with NS/NR', async () => {
    await renderDetail();
    expect(screen.getByText('2/5')).toBeInTheDocument();
    expect(screen.getByText('Insatisfecho')).toBeInTheDocument();
    MATRIX_TEXTS.forEach((t) => expect(screen.getByText(t)).toBeInTheDocument());
    const nsRow = screen.getByText(MATRIX_TEXTS[1]).closest('li');
    expect(within(nsRow).getByText('NS/NR')).toBeInTheDocument();
    expect(within(screen.getByText(MATRIX_TEXTS[0]).closest('li')).getByText('4')).toBeInTheDocument();
    expect(screen.getByText('Demoraron mucho')).toBeInTheDocument();
  });

  it('shows Sin observaciones when empty', async () => {
    current = caso({ respuesta: { ...caso().respuesta, observaciones: null } });
    await renderDetail();
    expect(screen.getByText('Sin observaciones')).toBeInTheDocument();
  });
});

describe('Detractor detail — timeline', () => {
  it('shows Sistema actor, user names and the transition arrow', async () => {
    await renderDetail();
    const items = screen.getAllByRole('listitem').filter((li) => li.dataset.testid === 'accion');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Sistema');
    expect(items[0]).toHaveTextContent('Apertura');
    expect(items[1]).toHaveTextContent('Marta Ruiz');
    expect(items[1]).toHaveTextContent('Cambio de estado');
    expect(items[1]).toHaveTextContent('Abierto → En gestión');
  });
});

describe('Detractor detail — registrar acción', () => {
  it('offers the five types with styled options on an open case', async () => {
    await renderDetail();
    const select = screen.getByLabelText('Tipo de acción');
    const opts = within(select).getAllByRole('option').map((o) => o.textContent);
    expect(opts).toEqual(['Llamada', 'WhatsApp', 'Nota', 'Compensación', 'Corrección']);
    within(select).getAllByRole('option').forEach((o) => expect(o.style.color).not.toBe(''));
  });

  it('offers only Nota and Corrección on a closed case', async () => {
    current = caso({ estado: 'CERRADO', resultado: 'NO_RECUPERADO' });
    await renderDetail();
    const opts = within(screen.getByLabelText('Tipo de acción')).getAllByRole('option').map((o) => o.textContent);
    expect(opts).toEqual(['Nota', 'Corrección']);
  });

  it('validates the minimum length and shows a counter', async () => {
    await renderDetail();
    fireEvent.change(screen.getByLabelText('Descripción'), { target: { value: 'abc' } });
    expect(screen.getByText('3/4000')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Registrar acción' })).toBeDisabled();
  });

  it('posts the action, clears the form and reloads', async () => {
    const post = jest.fn(async () => res({ id: 'a3' }, 201));
    route({ post });
    await renderDetail();
    fireEvent.change(screen.getByLabelText('Tipo de acción'), { target: { value: 'LLAMADA' } });
    fireEvent.change(screen.getByLabelText('Descripción'), { target: { value: 'Llamé y no contestó' } });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar acción' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/detractores/c1/acciones', { tipo: 'LLAMADA', descripcion: 'Llamé y no contestó' }));
    await waitFor(() => expect(screen.getByLabelText('Descripción').value).toBe(''));
    expect(mockFetch.mock.calls.filter(([, o]) => !o).length).toBeGreaterThanOrEqual(2);
  });

  it('shows the backend error', async () => {
    route({ post: async () => res({ detail: 'El caso está cerrado' }, 409) });
    await renderDetail();
    fireEvent.change(screen.getByLabelText('Descripción'), { target: { value: 'Una nota válida' } });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar acción' }));
    expect(await screen.findByText('El caso está cerrado')).toBeInTheDocument();
  });
});

describe('Detractor detail — cambiar estado', () => {
  it('Tomar caso sends EN_GESTION and reloads', async () => {
    const post = jest.fn(async () => res(current));
    route({ post });
    await renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Tomar caso' }));
    fireEvent.change(screen.getByLabelText('Comentario'), { target: { value: 'Lo atiendo hoy' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/detractores/c1/estado', { estado: 'EN_GESTION', comentario: 'Lo atiendo hoy' }));
  });

  it('Cerrar caso requires a resultado and a comentario of at least 5 chars', async () => {
    const post = jest.fn(async () => res(current));
    route({ post });
    await renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar caso' }));
    const confirm = screen.getByRole('button', { name: 'Confirmar' });
    expect(confirm).toBeDisabled();
    const sel = screen.getByLabelText('Resultado');
    const opts = within(sel).getAllByRole('option').map((o) => o.textContent);
    expect(opts).toEqual(expect.arrayContaining(['Recuperado', 'No recuperado', 'No se pudo contactar']));
    within(sel).getAllByRole('option').forEach((o) => expect(o.style.color).not.toBe(''));
    fireEvent.change(screen.getByLabelText('Comentario'), { target: { value: 'Cliente conforme' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(sel, { target: { value: 'RECUPERADO' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(post).toHaveBeenCalledWith('/detractores/c1/estado', { estado: 'CERRADO', resultado: 'RECUPERADO', comentario: 'Cliente conforme' }));
  });

  it('EN_GESTION offers only Cerrar caso', async () => {
    current = caso({ estado: 'EN_GESTION' });
    await renderDetail();
    expect(screen.queryByRole('button', { name: 'Tomar caso' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cerrar caso' })).toBeInTheDocument();
  });

  it('CERRADO offers only Reabrir caso', async () => {
    current = caso({ estado: 'CERRADO', resultado: 'RECUPERADO' });
    await renderDetail();
    expect(screen.queryByRole('button', { name: 'Tomar caso' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cerrar caso' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reabrir caso' })).toBeInTheDocument();
  });

  it('Reabrir caso requires a comentario and sends EN_GESTION without resultado', async () => {
    current = caso({ estado: 'CERRADO', resultado: 'RECUPERADO' });
    const post = jest.fn(async () => res(current));
    route({ post });
    await renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Reabrir caso' }));
    expect(screen.queryByLabelText('Resultado')).not.toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'Confirmar' });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Comentario'), { target: { value: 'Volvió a llamar' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(post).toHaveBeenCalledWith('/detractores/c1/estado', { estado: 'EN_GESTION', comentario: 'Volvió a llamar' }));
  });

  it('after reopening, the action form offers every tipo again', async () => {
    current = caso({ estado: 'CERRADO', resultado: 'RECUPERADO' });
    route({ post: async () => { current = caso({ estado: 'EN_GESTION' }); return res(current); } });
    await renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Reabrir caso' }));
    fireEvent.change(screen.getByLabelText('Comentario'), { target: { value: 'Volvió a llamar' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    await screen.findByRole('button', { name: 'Cerrar caso' });
    expect(screen.getByRole('option', { name: 'Llamada' })).toBeInTheDocument();
  });

  it('on 409 shows the message and reloads the case', async () => {
    route({ post: async () => res({ detail: 'El caso ya está cerrado y no se puede reabrir ni modificar su estado.' }, 409) });
    await renderDetail();
    const before = mockFetch.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Tomar caso' }));
    fireEvent.change(screen.getByLabelText('Comentario'), { target: { value: 'Lo atiendo hoy' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText(/ya está cerrado y no se puede reabrir/)).toBeInTheDocument();
    await waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThan(before + 1));
  });
});

describe('Detractor detail — navigation', () => {
  it('goes back to the list', async () => {
    await renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /Volver/ }));
    expect(pushMock).toHaveBeenCalledWith('/motored/detractores');
  });
});
