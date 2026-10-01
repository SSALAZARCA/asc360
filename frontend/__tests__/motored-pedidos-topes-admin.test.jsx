/**
 * Motored Fase 4 (F4): the "Topes por tienda" screen at /motored/pedidos/topes
 * (UX-28, TP-01..TP-05): ADMIN edits the switch and one cap per tienda
 * (search, validation, empty = sin tope); COMPRAS sees the table read-only;
 * every other role is sent away. The list of corridas has the entry button
 * (no sidebar entry).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, pagina, setSession, C_CALCULADA, TOPES_PRESUPUESTO,
} from './helpers/pedidosFetch';
import { hoyBogota } from '../components/motored/pedidos/acciones';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/pedidos/topes',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import TopesPage from '../app/motored/pedidos/topes/page';
import PedidosPage from '../app/motored/pedidos/page';

const LECTURA = 'GET /parametros/topes-presupuesto';
const GUARDAR = 'POST /parametros/topes-presupuesto';
const MODO = 'POST /parametros';

const rutas = (over = {}) => ({
  [LECTURA]: jsonRes(TOPES_PRESUPUESTO),
  [GUARDAR]: jsonRes({ actualizados: ['s1'], sin_cambios: [] }, 201),
  [MODO]: jsonRes({ clave: 'modo_tope_presupuesto' }, 201),
  ...over,
});
const lecturas = (calls) => calls.filter((c) => `${c.method} ${c.path}` === LECTURA);
const posts = (calls, path) => calls.filter((c) => c.method === 'POST' && c.path === path);
const campo = (nombre) => screen.findByRole('textbox', { name: `Tope de ${nombre}` });
const escribir = (input, texto) => fireEvent.change(input, { target: { value: texto } });
const guardar = () => screen.getByRole('button', { name: 'Guardar topes' });

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('ADMIN');
});

describe('Topes por tienda - ADMIN edits', () => {
  it('shows the title, the mode and one field per tienda started on the stored cap', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    expect(await screen.findByRole('heading', { name: 'Topes por tienda' })).toBeInTheDocument();
    expect(await campo('Manizales')).toHaveValue('80000000');
    expect(await campo('Pereira')).toHaveValue('');
    expect(await campo('Cali')).toHaveValue('45000000.5');
    expect(screen.getByRole('checkbox', { name: 'Modo tope de presupuesto' })).not.toBeChecked();
  });

  it('explains the cap column with a tooltip and each empty field says "Sin tope"', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    expect(await screen.findByRole('note', { name: /^Tope de presupuesto: / })).toBeInTheDocument();
    expect(await campo('Pereira')).toHaveAttribute('placeholder', 'Sin tope');
  });

  it('shows the cap as pesos next to the field and when it is valid since', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    const fila = (await campo('Manizales')).closest('tr');
    expect(fila).toHaveTextContent(/80\.000\.000/);
    expect(fila).toHaveTextContent('30/09/2026');
    expect((await campo('Pereira')).closest('tr')).toHaveTextContent('Sin tope');
  });

  it('selects the whole cap when the field gets the focus, so typing replaces it', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    const input = await campo('Manizales');
    fireEvent.focus(input);
    expect([input.selectionStart, input.selectionEnd]).toEqual([0, '80000000'.length]);
  });

  it('keeps Guardar topes disabled until something changes', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    const input = await campo('Manizales');
    expect(guardar()).toBeDisabled();
    escribir(input, '90000000');
    expect(guardar()).toBeEnabled();
    escribir(input, '80000000');
    expect(guardar()).toBeDisabled();
  });

  it('sends only the caps that changed, tells how many and reads the screen again', async () => {
    const calls = installFetch(rutas({ [GUARDAR]: jsonRes({ actualizados: ['s1', 's2'], sin_cambios: [] }, 201) }));
    render(<TopesPage />);
    escribir(await campo('Manizales'), '90000000');
    escribir(await campo('Pereira'), ' 1500000 ');
    fireEvent.click(guardar());
    expect(await screen.findByText('Se guardó el tope de 2 tiendas.')).toBeInTheDocument();
    expect(posts(calls, '/parametros/topes-presupuesto')[0].body).toEqual({
      topes: [{ sucursal_id: 's1', valor: 90000000 }, { sucursal_id: 's2', valor: 1500000 }],
    });
    await waitFor(() => expect(lecturas(calls)).toHaveLength(2));
  });

  it('uses the singular for one tienda', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    escribir(await campo('Manizales'), '90000000');
    fireEvent.click(guardar());
    expect(await screen.findByText('Se guardó el tope de 1 tienda.')).toBeInTheDocument();
  });

  it('removes a cap when the field is emptied (empty = sin tope)', async () => {
    const calls = installFetch(rutas());
    render(<TopesPage />);
    escribir(await campo('Manizales'), '');
    fireEvent.click(guardar());
    await waitFor(() => expect(posts(calls, '/parametros/topes-presupuesto')).toHaveLength(1));
    expect(posts(calls, '/parametros/topes-presupuesto')[0].body).toEqual({ topes: [{ sucursal_id: 's1', valor: null }] });
  });

  it.each([['0', /mayor que cero/], ['abc', /pesos/], ['80.000.000', /pesos/]])(
    'rejects %p on the spot, blocks saving and sends nothing', async (texto, mensaje) => {
      const calls = installFetch(rutas());
      render(<TopesPage />);
      const input = await campo('Manizales');
      escribir(input, texto);
      expect(within(input.closest('tr')).getByRole('alert')).toHaveTextContent(mensaje);
      expect(input).toHaveAttribute('aria-invalid', 'true');
      expect(guardar()).toBeDisabled();
      expect(posts(calls, '/parametros/topes-presupuesto')).toHaveLength(0);
      escribir(input, '95000000');
      expect(within(input.closest('tr')).queryByRole('alert')).not.toBeInTheDocument();
      expect(guardar()).toBeEnabled();
    },
  );

  it('discards the unsaved changes', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    const input = await campo('Manizales');
    escribir(input, '90000000');
    fireEvent.click(screen.getByRole('button', { name: 'Descartar cambios' }));
    expect(input).toHaveValue('80000000');
    expect(guardar()).toBeDisabled();
  });

  it('shows the server message with its code and keeps what the user typed when saving fails', async () => {
    installFetch(rutas({ [GUARDAR]: coded(422, 'E-PARAM-002', 'El tope debe ser mayor que cero.') }));
    render(<TopesPage />);
    const input = await campo('Manizales');
    escribir(input, '90000000');
    fireEvent.click(guardar());
    expect(await screen.findByText('El tope debe ser mayor que cero. (E-PARAM-002)')).toBeInTheDocument();
    expect(input).toHaveValue('90000000');
  });

  it('counts the changes waiting to be saved', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    escribir(await campo('Manizales'), '90000000');
    expect(screen.getByText('1 cambio sin guardar')).toBeInTheDocument();
    escribir(await campo('Pereira'), '1000');
    expect(screen.getByText('2 cambios sin guardar')).toBeInTheDocument();
  });
});

describe('Topes por tienda - search', () => {
  it('filters the tiendas by name and keeps what was typed in a hidden row', async () => {
    const calls = installFetch(rutas());
    render(<TopesPage />);
    escribir(await campo('Manizales'), '90000000');
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar tienda' }), { target: { value: 'cali' } });
    expect(screen.queryByRole('textbox', { name: 'Tope de Manizales' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Tope de Cali' })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar tienda' }), { target: { value: '' } });
    expect(screen.getByRole('textbox', { name: 'Tope de Manizales' })).toHaveValue('90000000');
    fireEvent.click(guardar());
    await waitFor(() => expect(posts(calls, '/parametros/topes-presupuesto')).toHaveLength(1));
  });

  it('says when no tienda matches', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    await campo('Manizales');
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar tienda' }), { target: { value: 'zzz' } });
    expect(screen.getByText('Sin tiendas para mostrar')).toBeInTheDocument();
  });
});

describe('Topes por tienda - the switch (TP-01, TP-02)', () => {
  it('turns the mode on, effective today, and reads the screen again', async () => {
    let lecturasHechas = 0;
    const calls = installFetch(rutas({
      [LECTURA]: () => jsonRes({ ...TOPES_PRESUPUESTO, modo_activo: (lecturasHechas += 1) > 1, modo_vigente_desde: '2026-10-02' }),
    }));
    render(<TopesPage />);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Modo tope de presupuesto' }));
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Modo tope de presupuesto' })).toBeChecked());
    expect(posts(calls, '/parametros')[0].body).toEqual({ clave: 'modo_tope_presupuesto', valor: true, vigente_desde: hoyBogota() });
    expect(screen.getByText('Activado desde 02/10/2026')).toBeInTheDocument();
  });

  it('turns it off again', async () => {
    const calls = installFetch(rutas({ [LECTURA]: jsonRes({ ...TOPES_PRESUPUESTO, modo_activo: true, modo_vigente_desde: '2026-10-02' }) }));
    render(<TopesPage />);
    const interruptor = await screen.findByRole('checkbox', { name: 'Modo tope de presupuesto' });
    expect(interruptor).toBeChecked();
    fireEvent.click(interruptor);
    await waitFor(() => expect(posts(calls, '/parametros')).toHaveLength(1));
    expect(posts(calls, '/parametros')[0].body.valor).toBe(false);
  });

  it('explains what the mode does and that nothing is cut by itself', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    expect(await screen.findByText(/nunca recorta nada solo/i)).toBeInTheDocument();
  });

  it('shows the message with its code and leaves the switch as it was when the change fails', async () => {
    installFetch(rutas({ [MODO]: coded(422, 'E-PARAM-002', 'El valor no es válido.') }));
    render(<TopesPage />);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Modo tope de presupuesto' }));
    expect(await screen.findByText('El valor no es válido. (E-PARAM-002)')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Modo tope de presupuesto' })).not.toBeChecked();
  });
});

describe('Topes por tienda - states', () => {
  it('shows a loading message and then the error with its code', async () => {
    installFetch(rutas({ [LECTURA]: coded(500, 'E-X-001', 'Falló la lectura.') }));
    render(<TopesPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Falló la lectura. (E-X-001)');
    expect(screen.queryByRole('textbox', { name: /Tope de/ })).not.toBeInTheDocument();
  });

  it('says so when there are no tiendas', async () => {
    installFetch(rutas({ [LECTURA]: jsonRes({ ...TOPES_PRESUPUESTO, topes: [] }) }));
    render(<TopesPage />);
    expect(await screen.findByText('Sin tiendas para mostrar')).toBeInTheDocument();
  });
});

describe('Topes por tienda - COMPRAS reads only (UX-28, TP-05)', () => {
  beforeEach(() => setSession('COMPRAS'));

  it('shows the caps as plain text, with no fields, no switch and no save button', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    const fila = (await screen.findByText('Manizales')).closest('tr');
    expect(fila).toHaveTextContent(/80\.000\.000/);
    expect(screen.getByText('Pereira').closest('tr')).toHaveTextContent('Sin tope');
    expect(screen.queryByRole('textbox', { name: /Tope de/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Guardar topes' })).not.toBeInTheDocument();
  });

  it('shows the mode as text and says that only the administrator changes it', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    expect(await screen.findByText('Modo tope: Desactivado')).toBeInTheDocument();
    expect(screen.getByText(/Solo el administrador puede cambiar/)).toBeInTheDocument();
  });

  it('shows the mode as activated when it is', async () => {
    installFetch(rutas({ [LECTURA]: jsonRes({ ...TOPES_PRESUPUESTO, modo_activo: true, modo_vigente_desde: '2026-10-02' }) }));
    render(<TopesPage />);
    expect(await screen.findByText('Modo tope: Activado desde 02/10/2026')).toBeInTheDocument();
  });

  it('still lets COMPRAS search the tiendas', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    await screen.findByText('Manizales');
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar tienda' }), { target: { value: 'pereira' } });
    expect(screen.queryByText('Manizales')).not.toBeInTheDocument();
    expect(screen.getByText('Pereira')).toBeInTheDocument();
  });
});

describe('Topes por tienda - gate', () => {
  it.each(['SUCURSAL', 'CONSULTA'])('sends %s away without fetching any data', async (role) => {
    setSession(role);
    const calls = installFetch(rutas());
    render(<TopesPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(calls).toHaveLength(0);
  });

  it('goes back to the list of pedidos', async () => {
    installFetch(rutas());
    render(<TopesPage />);
    fireEvent.click(await screen.findByRole('button', { name: '← Volver a pedidos' }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos');
  });
});

describe('Entry button on the corridas list', () => {
  it.each(['ADMIN', 'COMPRAS'])('opens the Topes screen for %s', async (role) => {
    setSession(role);
    installFetch({ 'GET /corridas': jsonRes(pagina([C_CALCULADA])) });
    render(<PedidosPage />);
    await screen.findByText('PED-2026-S40-001');
    fireEvent.click(screen.getByRole('button', { name: 'Topes por tienda' }));
    expect(pushMock).toHaveBeenCalledWith('/motored/pedidos/topes');
  });
});
