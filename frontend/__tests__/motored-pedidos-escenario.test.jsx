/**
 * Motored Fase 4 (F5b): the scenario launcher of /motored/pedidos (ADMIN only,
 * SC-01..SC-06, UX-01). The picker is typed from `/parametros/claves` (bool ->
 * switch, opcion -> select with styled options, entero/decimal -> text field,
 * k_fms -> three fields), shows the value in force of the keys the user picks
 * (one `vigente` call per picked key, never twenty), keeps "Lanzar escenario"
 * disabled until a value really changes, and shows 062 / 010 with their code.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, pagina, setSession, rutasEscenario, SUCURSALES, CLAVES_MOTOR, C_CALCULADA, C_PRUEBA,
} from './helpers/pedidosFetch';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/motored/pedidos',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import PedidosPage from '../app/motored/pedidos/page';

const CREADA = { id: 'e1', codigo: 'ESC-2026-S41-001', estado: 'PENDIENTE', es_escenario: true };

const rutas = (over = {}) => ({
  'GET /corridas': jsonRes(pagina([C_CALCULADA, C_PRUEBA])),
  'GET /maestros/sucursales': jsonRes(SUCURSALES),
  'POST /corridas': jsonRes(CREADA, 202),
  ...rutasEscenario(),
  ...over,
});

const posts = (calls) => calls.filter((c) => c.method === 'POST' && c.path === '/corridas');
const vigentes = (calls) => calls.filter((c) => c.path.endsWith('/vigente'));

async function abrirDialogo() {
  render(<PedidosPage />);
  await screen.findByText('PED-2026-S40-001');
  fireEvent.click(screen.getByRole('button', { name: 'Nuevo escenario' }));
  const dialogo = await screen.findByRole('dialog', { name: 'Nuevo escenario de prueba' });
  const selector = within(dialogo).getByLabelText('Agregar un parámetro a probar');
  await waitFor(() => expect(selector).toBeEnabled());
  return dialogo;
}

async function agregar(dialogo, clave, titulo) {
  fireEvent.change(within(dialogo).getByLabelText('Agregar un parámetro a probar'), { target: { value: clave } });
  const fila = await within(dialogo).findByRole('group', { name: titulo });
  await waitFor(() => expect(within(fila).queryByText('Leyendo el valor actual...')).not.toBeInTheDocument());
  return fila;
}

const fechar = (dialogo, fecha = '2026-10-01') => (
  fireEvent.change(within(dialogo).getByLabelText('Fecha de corte'), { target: { value: fecha } })
);
const lanzar = (dialogo) => within(dialogo).getByRole('button', { name: 'Lanzar escenario' });

const T_SUSTITUIDAS = 'Sumar las ventas de la referencia sustituida';
const T_DIAS = 'Días entre pedidos';
const T_REDONDEO = 'Redondeo al empaque';
const T_ABC = 'Corte de la clase A';
const T_KFMS = 'Factores de cobertura por rotación';

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('ADMIN');
});

describe('who sees the launcher (UX-01)', () => {
  it('shows "Nuevo escenario" to ADMIN', async () => {
    installFetch(rutas());
    render(<PedidosPage />);
    await screen.findByText('PED-2026-S40-001');
    expect(screen.getByRole('button', { name: 'Nuevo escenario' })).toBeInTheDocument();
  });

  it('hides it from COMPRAS, who never even asks for the catalog', async () => {
    setSession('COMPRAS');
    const calls = installFetch(rutas());
    render(<PedidosPage />);
    await screen.findByText('PED-2026-S40-001');
    expect(screen.queryByRole('button', { name: 'Nuevo escenario' })).not.toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'Nueva corrida' })).toBeInTheDocument();
    expect(calls.some((c) => c.path.startsWith('/parametros'))).toBe(false);
  });
});

describe('the catalog of engine keys', () => {
  it('reads the catalog when the dialog opens and offers the 20 keys by their business title', async () => {
    const calls = installFetch(rutas());
    const dialogo = await abrirDialogo();
    expect(calls.filter((c) => c.path === '/parametros/claves')).toHaveLength(1);
    const selector = within(dialogo).getByLabelText('Agregar un parámetro a probar');
    const opciones = within(selector).getAllByRole('option');
    expect(opciones).toHaveLength(CLAVES_MOTOR.length + 1);
    expect(opciones.map((o) => o.textContent)).toEqual(expect.arrayContaining([T_SUSTITUIDAS, T_DIAS, T_REDONDEO, T_KFMS]));
    opciones.forEach((o) => expect(o.textContent).not.toMatch(/_/));
  });

  it('styles every option so the text is readable on the dark theme', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const opciones = within(within(dialogo).getByLabelText('Agregar un parámetro a probar')).getAllByRole('option');
    expect(opciones.length).toBeGreaterThan(1);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });

  it('shows the error with its code when the catalog cannot be read, and offers nothing to pick', async () => {
    installFetch(rutas({ 'GET /parametros/claves': coded(500, 'E-PARAM-500', 'No se pudo leer el catálogo.') }));
    render(<PedidosPage />);
    await screen.findByText('PED-2026-S40-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo escenario' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Nuevo escenario de prueba' });
    expect(await within(dialogo).findByText(/No se pudo leer el catálogo\. \(E-PARAM-500\)/)).toBeInTheDocument();
    expect(within(dialogo).getByLabelText('Agregar un parámetro a probar')).toBeDisabled();
  });
});

describe('a picked key shows its value in force (one call per picked key)', () => {
  it('asks only for the vigente of the key that was picked', async () => {
    const calls = installFetch(rutas());
    const dialogo = await abrirDialogo();
    expect(vigentes(calls)).toHaveLength(0);
    await agregar(dialogo, 'consolidar_sustituidas', T_SUSTITUIDAS);
    expect(vigentes(calls).map((c) => c.path)).toEqual(['/parametros/consolidar_sustituidas/vigente']);
    await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    expect(vigentes(calls)).toHaveLength(2);
  });

  it('shows a switch with the current value for a boolean key', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const fila = await agregar(dialogo, 'consolidar_sustituidas', T_SUSTITUIDAS);
    expect(within(fila).getByText('Valor actual: No')).toBeInTheDocument();
    expect(within(fila).getByRole('checkbox', { name: `${T_SUSTITUIDAS}: valor a probar` })).not.toBeChecked();
  });

  it('prefills the field with the version in force, not with the default', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const fila = await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    expect(within(fila).getByText('Valor actual: 21')).toBeInTheDocument();
    expect(within(fila).getByLabelText(`${T_DIAS}: valor a probar`)).toHaveValue('21');
  });

  it('falls back to the default, and says so, when the key has no version in force', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const fila = await agregar(dialogo, 'umbral_f', 'Meses con venta para rotación frecuente (F)');
    expect(within(fila).getByText('Valor actual: 2')).toBeInTheDocument();
    expect(within(fila).getByText(/valor por defecto/i)).toBeInTheDocument();
    expect(within(fila).getByLabelText('Meses con venta para rotación frecuente (F): valor a probar')).toHaveValue('2');
  });

  it('falls back to the default with a warning when the current value cannot be read', async () => {
    installFetch(rutas({ 'GET /parametros/umbral_m/vigente': jsonRes({ detail: 'boom' }, 500) }));
    const dialogo = await abrirDialogo();
    const fila = await agregar(dialogo, 'umbral_m', 'Meses con venta para rotación media (M)');
    expect(within(fila).getByText(/No se pudo leer el valor actual/)).toBeInTheDocument();
    expect(within(fila).getByLabelText('Meses con venta para rotación media (M): valor a probar')).toHaveValue('1');
  });

  it('shows a select with styled options for an option key, preselected on the current value', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const fila = await agregar(dialogo, 'modo_redondeo_empaque', T_REDONDEO);
    const control = within(fila).getByLabelText(`${T_REDONDEO}: valor a probar`);
    expect(control).toHaveValue('ARRIBA');
    const opciones = within(control).getAllByRole('option');
    expect(opciones.map((o) => o.value)).toEqual(['CERCANO', 'ARRIBA']);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });

  it('shows the three factors of k_fms as three fields', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const fila = await agregar(dialogo, 'k_fms', T_KFMS);
    expect(within(fila).getByText('Valor actual: F 4 · M 2 · S 1')).toBeInTheDocument();
    expect(within(fila).getByLabelText(`${T_KFMS}: factor F`)).toHaveValue('4');
    expect(within(fila).getByLabelText(`${T_KFMS}: factor M`)).toHaveValue('2');
    expect(within(fila).getByLabelText(`${T_KFMS}: factor S`)).toHaveValue('1');
  });

  it('explains each parameter in plain Spanish in a tooltip', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const fila = await agregar(dialogo, 'consolidar_sustituidas', T_SUSTITUIDAS);
    expect(within(fila).getByRole('note')).toHaveAttribute('aria-label', expect.stringMatching(/ventas de una referencia que fue sustituida/));
  });

  it('removes a row and offers the key again', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const selector = within(dialogo).getByLabelText('Agregar un parámetro a probar');
    const fila = await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    expect(within(selector).queryByRole('option', { name: T_DIAS })).not.toBeInTheDocument();
    fireEvent.click(within(fila).getByRole('button', { name: 'Quitar' }));
    expect(within(dialogo).queryByRole('group', { name: T_DIAS })).not.toBeInTheDocument();
    expect(within(selector).getByRole('option', { name: T_DIAS })).toBeInTheDocument();
  });
});

describe('Lanzar escenario stays disabled until a value changes (SC-03)', () => {
  it('is disabled without a fecha de corte, without rows and with an unchanged row', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    expect(lanzar(dialogo)).toBeDisabled();
    fechar(dialogo);
    expect(lanzar(dialogo)).toBeDisabled();
    await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    expect(lanzar(dialogo)).toBeDisabled();
    expect(within(dialogo).getByText('Cambie al menos un valor para lanzar el escenario.')).toBeInTheDocument();
  });

  it('enables when a value changes and disables again when it goes back to the current one', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    fechar(dialogo);
    const fila = await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    const campo = within(fila).getByLabelText(`${T_DIAS}: valor a probar`);
    fireEvent.change(campo, { target: { value: '45' } });
    expect(lanzar(dialogo)).toBeEnabled();
    expect(within(dialogo).getByText('1 cambio para probar')).toBeInTheDocument();
    fireEvent.change(campo, { target: { value: '21' } });
    expect(lanzar(dialogo)).toBeDisabled();
  });

  it('blocks a typed value that is not valid and shows why', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    fechar(dialogo);
    const fila = await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    fireEvent.change(within(fila).getByLabelText(`${T_DIAS}: valor a probar`), { target: { value: '2,5' } });
    expect(within(fila).getByText('Escriba un número entero, sin decimales.')).toBeInTheDocument();
    expect(lanzar(dialogo)).toBeDisabled();
  });

  it('waits for the current value before the row can count as changed', async () => {
    let soltar;
    installFetch(rutas({
      'GET /parametros/dias_entre_pedidos/vigente': () => new Promise((resolver) => {
        soltar = () => resolver(jsonRes({ id: 'v', clave: 'dias_entre_pedidos', valor: 21, vigente_desde: '2026-09-01', sucursal_id: null }));
      }),
    }));
    const dialogo = await abrirDialogo();
    fechar(dialogo);
    fireEvent.change(within(dialogo).getByLabelText('Agregar un parámetro a probar'), { target: { value: 'dias_entre_pedidos' } });
    const fila = await within(dialogo).findByRole('group', { name: T_DIAS });
    expect(within(fila).getByText('Leyendo el valor actual...')).toBeInTheDocument();
    expect(lanzar(dialogo)).toBeDisabled();
    soltar();
    expect(await within(fila).findByText('Valor actual: 21')).toBeInTheDocument();
  });
});

describe('tablet touch targets', () => {
  it('gives the fields and rows of the dialog a 44 px target', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    const fila = await agregar(dialogo, 'consolidar_sustituidas', T_SUSTITUIDAS);
    [
      within(dialogo).getByLabelText('Fecha de corte'), within(dialogo).getByLabelText('Nota (opcional)'),
      within(dialogo).getByLabelText('Agregar un parámetro a probar'), within(fila).getByRole('button', { name: 'Quitar' }),
    ].forEach((campo) => expect(campo.style.minHeight).toBe('44px'));
  });

  it('gives every tienda of the selection a 44 px target', async () => {
    installFetch(rutas());
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('radio', { name: 'Selección de tiendas' }));
    const casilla = await within(dialogo).findByRole('checkbox', { name: 'Pereira' });
    expect(casilla.closest('label').style.minHeight).toBe('44px');
  });
});

describe('a row still reading its current value', () => {
  it('keeps Lanzar escenario disabled even when another row already changed, so no row is left out', async () => {
    let soltar;
    installFetch(rutas({
      'GET /parametros/umbral_f/vigente': () => new Promise((resolver) => { soltar = () => resolver(jsonRes({ valor: 2 })); }),
    }));
    const dialogo = await abrirDialogo();
    fechar(dialogo);
    const sustituidas = await agregar(dialogo, 'consolidar_sustituidas', T_SUSTITUIDAS);
    fireEvent.click(within(sustituidas).getByRole('checkbox', { name: `${T_SUSTITUIDAS}: valor a probar` }));
    expect(lanzar(dialogo)).toBeEnabled();
    fireEvent.change(within(dialogo).getByLabelText('Agregar un parámetro a probar'), { target: { value: 'umbral_f' } });
    await within(dialogo).findByText('Leyendo el valor actual...');
    expect(lanzar(dialogo)).toBeDisabled();
    soltar();
    await within(dialogo).findByText('Valor actual: 2');
    expect(lanzar(dialogo)).toBeEnabled();
  });
});

describe('launching the scenario', () => {
  it('sends the fecha and only the changed keys, with the Spanish decimal comma turned into a dot', async () => {
    const calls = installFetch(rutas());
    const dialogo = await abrirDialogo();
    fechar(dialogo, '2026-10-01');
    const sustituidas = await agregar(dialogo, 'consolidar_sustituidas', T_SUSTITUIDAS);
    fireEvent.click(within(sustituidas).getByRole('checkbox', { name: `${T_SUSTITUIDAS}: valor a probar` }));
    const abc = await agregar(dialogo, 'corte_abc_a', T_ABC);
    fireEvent.change(within(abc).getByLabelText(`${T_ABC}: valor a probar`), { target: { value: '0,85' } });
    await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    expect(within(dialogo).getByText('2 cambios para probar')).toBeInTheDocument();
    fireEvent.click(lanzar(dialogo));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    expect(posts(calls)[0].body).toEqual({
      fecha_corte: '2026-10-01',
      overrides: { consolidar_sustituidas: true, corte_abc_a: '0.85' },
    });
  });

  it('sends an option, an integer and the three k_fms factors in the type the server expects', async () => {
    const calls = installFetch(rutas());
    const dialogo = await abrirDialogo();
    fechar(dialogo);
    const redondeo = await agregar(dialogo, 'modo_redondeo_empaque', T_REDONDEO);
    fireEvent.change(within(redondeo).getByLabelText(`${T_REDONDEO}: valor a probar`), { target: { value: 'CERCANO' } });
    const dias = await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    fireEvent.change(within(dias).getByLabelText(`${T_DIAS}: valor a probar`), { target: { value: '45' } });
    const k = await agregar(dialogo, 'k_fms', T_KFMS);
    fireEvent.change(within(k).getByLabelText(`${T_KFMS}: factor F`), { target: { value: '5' } });
    fireEvent.click(lanzar(dialogo));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    expect(posts(calls)[0].body.overrides).toEqual({
      modo_redondeo_empaque: 'CERCANO', dias_entre_pedidos: 45, k_fms: { F: '5', M: '2', S: '1' },
    });
  });

  it('sends the note and the selected tiendas when the user picks them', async () => {
    const calls = installFetch(rutas());
    const dialogo = await abrirDialogo();
    fechar(dialogo);
    fireEvent.change(within(dialogo).getByLabelText('Nota (opcional)'), { target: { value: 'Probar sustitutas' } });
    fireEvent.click(within(dialogo).getByRole('radio', { name: 'Selección de tiendas' }));
    fireEvent.click(await within(dialogo).findByRole('checkbox', { name: 'Pereira' }));
    const fila = await agregar(dialogo, 'consolidar_sustituidas', T_SUSTITUIDAS);
    fireEvent.click(within(fila).getByRole('checkbox', { name: `${T_SUSTITUIDAS}: valor a probar` }));
    fireEvent.click(lanzar(dialogo));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    expect(posts(calls)[0].body).toEqual({
      fecha_corte: '2026-10-01', sucursal_ids: ['s2'], nota: 'Probar sustitutas',
      overrides: { consolidar_sustituidas: true },
    });
  });

  it('closes, tells the user and reloads the list after a successful launch', async () => {
    const calls = installFetch(rutas());
    const dialogo = await abrirDialogo();
    fechar(dialogo);
    const fila = await agregar(dialogo, 'consolidar_sustituidas', T_SUSTITUIDAS);
    fireEvent.click(within(fila).getByRole('checkbox', { name: `${T_SUSTITUIDAS}: valor a probar` }));
    const antes = calls.filter((c) => c.method === 'GET' && c.path === '/corridas').length;
    fireEvent.click(lanzar(dialogo));
    expect(await screen.findByText(/Escenario ESC-2026-S41-001 creado: se está calculando\./)).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Nuevo escenario de prueba' })).not.toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'GET' && c.path === '/corridas').length).toBe(antes + 1);
    fireEvent.click(screen.getByRole('button', { name: 'Ver escenario' }));
    expect(mockPush).toHaveBeenCalledWith('/motored/pedidos/e1');
  });

  it.each([
    ['E-CORRIDA-062', 403, 'Solo un administrador puede lanzar un escenario.'],
    ['E-CORRIDA-010', 422, 'Parámetro de escenario no válido «dias_entre_pedidos»: se esperaba un entero entre 1 y 60.'],
  ])('keeps the dialog open and shows %s with its message', async (codigo, status, mensaje) => {
    installFetch(rutas({ 'POST /corridas': coded(status, codigo, mensaje) }));
    const dialogo = await abrirDialogo();
    fechar(dialogo);
    const fila = await agregar(dialogo, 'dias_entre_pedidos', T_DIAS);
    fireEvent.change(within(fila).getByLabelText(`${T_DIAS}: valor a probar`), { target: { value: '90' } });
    fireEvent.click(lanzar(dialogo));
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(`${mensaje} (${codigo})`);
    expect(screen.getByRole('dialog', { name: 'Nuevo escenario de prueba' })).toBeInTheDocument();
    expect(within(fila).getByLabelText(`${T_DIAS}: valor a probar`)).toHaveValue('90');
  });

  it('closes without launching when the user cancels', async () => {
    const calls = installFetch(rutas());
    const dialogo = await abrirDialogo();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByRole('dialog', { name: 'Nuevo escenario de prueba' })).not.toBeInTheDocument();
    expect(posts(calls)).toHaveLength(0);
  });
});

describe('the PRUEBA marking on the list (SC-06)', () => {
  it('marks the scenario row with PRUEBA and no other row', async () => {
    installFetch(rutas());
    render(<PedidosPage />);
    await screen.findByText('ESC-2026-S40-001');
    const fila = screen.getByText('ESC-2026-S40-001').closest('tr');
    expect(within(fila).getByText('PRUEBA')).toBeInTheDocument();
    const real = screen.getByText('PED-2026-S40-001').closest('tr');
    expect(within(real).queryByText('PRUEBA')).not.toBeInTheDocument();
  });
});
