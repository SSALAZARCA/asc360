import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InformeContainer from '../components/motored/informe/InformeContainer';
import InformePage, { metadata } from '../app/motored/informe/[token]/page';
import { verInforme } from '../lib/motored/informeApi';
import { ASESOR_DETALLE } from './helpers/kpisAsesorDetalleFixture';

const push = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: push }),
  usePathname: () => '/motored/informe/tok123',
}));

const respuesta = (status, body = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const montar = () => render(<InformeContainer token="tok123" />);
const escribir = async (user, valor) => { await user.type(screen.getByLabelText('Tu cédula'), valor); };

beforeEach(() => {
  push.mockClear();
  global.fetch = jest.fn();
  document.cookie = '';
});
afterEach(() => jest.restoreAllMocks());

describe('informeApi.verInforme', () => {
  it('POSTs the cédula to the public endpoint with no auth header', async () => {
    global.fetch.mockResolvedValue(respuesta(200, ASESOR_DETALLE));
    const data = await verInforme('tok 1', '123');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toMatch(/\/api\/motored\/publico\/informe\/tok%201$/);
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ cedula: '123' });
    expect(JSON.stringify(opts.headers)).not.toMatch(/authorization/i);
    expect(data).toEqual(ASESOR_DETALLE);
  });

  it('401 and 429 and other failures map to their Spanish messages', async () => {
    global.fetch.mockResolvedValueOnce(respuesta(401));
    await expect(verInforme('t', '1')).rejects.toThrow('Enlace o cédula no válidos.');
    global.fetch.mockResolvedValueOnce(respuesta(429));
    await expect(verInforme('t', '1')).rejects.toThrow('Demasiados intentos. Intenta de nuevo en unos minutos.');
    global.fetch.mockResolvedValueOnce(respuesta(500));
    await expect(verInforme('t', '1')).rejects.toThrow('No pudimos cargar tu informe. Intenta de nuevo.');
    global.fetch.mockRejectedValueOnce(new TypeError('network'));
    await expect(verInforme('t', '1')).rejects.toThrow('No pudimos cargar tu informe. Intenta de nuevo.');
  });
});

describe('informe page', () => {
  it('shows the cédula form with the security note and a numeric input', () => {
    montar();
    const input = screen.getByLabelText('Tu cédula');
    expect(input).toHaveAttribute('inputmode', 'numeric');
    expect(input).toHaveAttribute('autocomplete', 'off');
    expect(screen.getByRole('button', { name: 'Ver mi informe' })).toBeInTheDocument();
    expect(screen.getByText('Por seguridad te pediremos tu cédula cada vez que abras este enlace.')).toBeInTheDocument();
  });

  it('rejects an empty cédula without calling the API', async () => {
    const user = userEvent.setup();
    montar();
    await user.click(screen.getByRole('button', { name: 'Ver mi informe' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Escribe tu cédula.');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('rejects a cédula with non-digits without calling the API', async () => {
    const user = userEvent.setup();
    montar();
    await escribir(user, '12a45');
    await user.click(screen.getByRole('button', { name: 'Ver mi informe' }));
    expect(screen.getByRole('alert')).toHaveTextContent('La cédula solo lleva números.');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('shows the invalid message on 401 and the rate-limit message on 429', async () => {
    const user = userEvent.setup();
    montar();
    await escribir(user, '123456');
    global.fetch.mockResolvedValueOnce(respuesta(401));
    await user.click(screen.getByRole('button', { name: 'Ver mi informe' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Enlace o cédula no válidos.');
    global.fetch.mockResolvedValueOnce(respuesta(429));
    await user.click(screen.getByRole('button', { name: 'Ver mi informe' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Demasiados intentos. Intenta de nuevo en unos minutos.'));
  });

  it('renders the asesor detail read-only on success and writes nothing to storage or cookies', async () => {
    const user = userEvent.setup();
    const local = jest.spyOn(Storage.prototype, 'setItem');
    montar();
    await escribir(user, '123456');
    global.fetch.mockResolvedValueOnce(respuesta(200, ASESOR_DETALLE));
    await user.click(screen.getByRole('button', { name: 'Ver mi informe' }));
    expect(await screen.findByRole('region', { name: 'Detalle del asesor' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Ficha del asesor' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Indicadores del asesor' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Tu cédula')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /recalcular/i })).not.toBeInTheDocument();
    expect(local).not.toHaveBeenCalled();
    expect(document.cookie).toBe('');
    const opts = global.fetch.mock.calls[0][1];
    expect(JSON.stringify(opts.headers)).not.toMatch(/authorization/i);
  });

  it('renders without a Motored session: no redirect to the login, noindex metadata', async () => {
    sessionStorage.clear();
    localStorage.clear();
    const element = await InformePage({ params: Promise.resolve({ token: 'tok123' }) });
    render(element);
    expect(screen.getByLabelText('Tu cédula')).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    expect(metadata.robots).toEqual({ index: false, follow: false });
  });
});
