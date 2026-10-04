/**
 * CampoConfiguracion: one typed control per registry type, with tooltip,
 * current value, "Rige desde" month and the history drawer. Proven on
 * SYNTHETIC specs (the sections that use it arrive in later tasks).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import CampoConfiguracion from '../components/motored/configuracion/CampoConfiguracion';

const HOY = new Date(2026, 9, 4);

const spec = (tipo, extra = {}) => ({
  clave: 'clave_x', seccion: 'pedido', grupo: 'OPERACION', tipo, dominio: 'un dominio',
  ambito: 'GLOBAL', default: null, opciones: [], minimo: null, maximo: null,
  minimo_exclusivo: false, campos: [], snapshotted: false,
  efectivo_global: { valor: null, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
  por_sucursal: [], programados: [], ...extra,
});
const conValor = (s, valor, desde = '2026-09-01') => ({
  ...s, efectivo_global: { valor, fuente: 'GLOBAL', vigente_desde: desde, parametro_id: 'p1' },
});

const ENTERO = conValor(spec('entero', {
  clave: 'dias_entre_pedidos', minimo: 1, maximo: 60, snapshotted: true, default: 30,
  dominio: 'un entero entre 1 y 60',
}), 45);

function montar(s, props = {}) {
  const onGuardar = props.onGuardar || jest.fn(async () => ({}));
  const cargarHistorial = props.cargarHistorial || jest.fn(async () => []);
  render(
    <CampoConfiguracion
      spec={s} etiqueta="Días entre pedidos" ayuda="Cada cuántos días se pide."
      hoy={HOY} onGuardar={onGuardar} cargarHistorial={cargarHistorial} {...props}
    />,
  );
  return { onGuardar, cargarHistorial };
}

describe('current value and help', () => {
  it('shows the label, the tooltip text and the current value with its month', () => {
    montar(ENTERO);
    expect(screen.getByText('Días entre pedidos')).toBeInTheDocument();
    expect(screen.getByRole('note', { name: 'Cada cuántos días se pide.' })).toBeInTheDocument();
    expect(screen.getByText(/Valor actual:/)).toHaveTextContent('Valor actual: 45');
    expect(screen.getByText(/Rige desde 2026-09/)).toBeInTheDocument();
  });

  it('says so when the value is the registry default', () => {
    montar(spec('entero', {
      default: 30, efectivo_global: { valor: 30, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
    }));
    expect(screen.getByText(/Valor por defecto: 30/)).toBeInTheDocument();
  });

  it('warns that an engine key only changes the new corridas', () => {
    montar(ENTERO);
    expect(screen.getByText(/sólo a las corridas nuevas/i)).toBeInTheDocument();
  });

  it('does not warn for a key outside the engine snapshot', () => {
    montar(spec('entero'));
    expect(screen.queryByText(/sólo a las corridas nuevas/i)).not.toBeInTheDocument();
  });

  it('lists scheduled versions and sucursal overrides', () => {
    const s = {
      ...ENTERO,
      programados: [{ valor: 20, vigente_desde: '2026-11-01', sucursal_id: null }],
      por_sucursal: [{ sucursal_id: 's1', valor: 7, vigente_desde: '2026-09-01', parametro_id: 'q' }],
    };
    montar(s);
    expect(screen.getByText(/Programado: 20 desde 2026-11/)).toBeInTheDocument();
    expect(screen.getByText(/1 tienda con valor propio/)).toBeInTheDocument();
  });
});

describe('saving', () => {
  it('starts with Guardar disabled until the draft changes', () => {
    montar(ENTERO);
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeDisabled();
  });

  it('sends the typed value and the first day of the chosen month', async () => {
    const { onGuardar } = montar(ENTERO);
    fireEvent.change(screen.getByLabelText('Días entre pedidos'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('Rige desde'), { target: { value: '2026-12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledWith({
      clave: 'dias_entre_pedidos', valor: 20, vigente_desde: '2026-12-01', sucursal_id: null,
    }));
    expect(await screen.findByRole('status')).toHaveTextContent('Guardado');
  });

  it('defaults the month to the current one and blocks past months for engine keys', () => {
    montar(ENTERO);
    const mes = screen.getByLabelText('Rige desde');
    expect(mes).toHaveValue('2026-10');
    expect(mes).toHaveAttribute('min', '2026-10');
  });

  it('lets a key outside the snapshot pick a past month', () => {
    montar(spec('entero'));
    expect(screen.getByLabelText('Rige desde')).not.toHaveAttribute('min');
  });

  it('passes the sucursal when the field is scoped to one', async () => {
    const { onGuardar } = montar(ENTERO, { sucursalId: 'suc-1' });
    fireEvent.change(screen.getByLabelText('Días entre pedidos'), { target: { value: '9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledWith(
      expect.objectContaining({ sucursal_id: 'suc-1', valor: 9 }),
    ));
  });

  it('does not call the API with an invalid draft and says why', () => {
    const { onGuardar } = montar(ENTERO);
    fireEvent.change(screen.getByLabelText('Días entre pedidos'), { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(screen.getByRole('alert')).toHaveTextContent(/número entero/);
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it('shows the server message when the save is rejected', async () => {
    const onGuardar = jest.fn(async () => { throw new Error('Valor no válido para «x»: mes ya pasó'); });
    montar(ENTERO, { onGuardar });
    fireEvent.change(screen.getByLabelText('Días entre pedidos'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('mes ya pasó');
  });

  it('calls onGuardado after a successful save', async () => {
    const onGuardado = jest.fn();
    montar(ENTERO, { onGuardado });
    fireEvent.change(screen.getByLabelText('Días entre pedidos'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardado).toHaveBeenCalled());
  });
});

describe('typed controls', () => {
  it('bool is a checkbox', async () => {
    const { onGuardar } = montar(conValor(spec('bool', { clave: 'b' }), false));
    const caja = screen.getByRole('checkbox', { name: 'Días entre pedidos' });
    expect(caja).not.toBeChecked();
    fireEvent.click(caja);
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledWith(expect.objectContaining({ valor: true })));
  });

  it('opcion is a select whose every option has an explicit colour', () => {
    montar(conValor(spec('opcion', { opciones: ['CERCANO', 'ARRIBA'] }), 'CERCANO'));
    const select = screen.getByRole('combobox', { name: 'Días entre pedidos' });
    expect(select).toHaveValue('CERCANO');
    const opciones = within(select).getAllByRole('option');
    expect(opciones).toHaveLength(2);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });

  it('lista is one value per line', async () => {
    const { onGuardar } = montar(conValor(spec('lista_digitos'), ['900', '901']));
    const area = screen.getByRole('textbox', { name: 'Días entre pedidos' });
    expect(area).toHaveValue('900\n901');
    fireEvent.change(area, { target: { value: '900\n902\n' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledWith(
      expect.objectContaining({ valor: ['900', '902'] }),
    ));
  });

  it('objeto_numerico shows one input per field', async () => {
    const s = conValor(spec('objeto_numerico', { campos: ['verde_desde', 'ambar_desde'] }),
      { verde_desde: 90, ambar_desde: 70 });
    const { onGuardar } = montar(s);
    fireEvent.change(screen.getByLabelText('ambar_desde'), { target: { value: '60' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledWith(
      expect.objectContaining({ valor: { verde_desde: '90', ambar_desde: '60' } }),
    ));
  });

  it('mapa_opcion adds and removes rows', async () => {
    const s = conValor(spec('mapa_opcion', { opciones: ['PERSONA', 'OTROS'] }), { GERENTE: 'PERSONA' });
    const { onGuardar } = montar(s);
    fireEvent.click(screen.getByRole('button', { name: 'Agregar fila' }));
    const claves = screen.getAllByLabelText('Nombre de la fila');
    fireEvent.change(claves[1], { target: { value: 'JEFE' } });
    fireEvent.change(screen.getAllByLabelText('Grupo de la fila')[1], { target: { value: 'OTROS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledWith(expect.objectContaining({
      valor: { GERENTE: 'PERSONA', JEFE: 'OTROS' },
    })));
    fireEvent.click(screen.getAllByRole('button', { name: 'Quitar fila' })[0]);
    expect(screen.getAllByLabelText('Nombre de la fila')).toHaveLength(1);
  });

  it('tramos edits an ordered list of rows', async () => {
    const s = conValor(spec('tramos', { campos: ['nombre', 'desde_pct', 'tasa_pct'] }),
      [{ nombre: 'BASE', desde_pct: 0, tasa_pct: 1 }]);
    const { onGuardar } = montar(s);
    fireEvent.click(screen.getByRole('button', { name: 'Agregar fila' }));
    fireEvent.change(screen.getAllByLabelText('Nombre del tramo')[1], { target: { value: 'PRO' } });
    fireEvent.change(screen.getAllByLabelText('Desde (%)')[1], { target: { value: '90' } });
    fireEvent.change(screen.getAllByLabelText('Tasa (%)')[1], { target: { value: '1,5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalledWith(expect.objectContaining({
      valor: [
        { nombre: 'BASE', desde_pct: '0', tasa_pct: '1' },
        { nombre: 'PRO', desde_pct: '90', tasa_pct: '1.5' },
      ],
    })));
  });

  it('every control and button is at least 44 px tall', () => {
    montar(ENTERO);
    ['Días entre pedidos', 'Rige desde'].forEach((nombre) => {
      expect(screen.getByLabelText(nombre).style.minHeight).toBe('44px');
    });
    ['Guardar', 'Ver historial'].forEach((nombre) => {
      expect(screen.getByRole('button', { name: nombre }).style.minHeight).toBe('44px');
    });
  });
});

describe('history drawer', () => {
  const FILAS = [
    { id: 'a', clave: 'clave_x', valor: 45, vigente_desde: '2026-09-01', sucursal_id: null,
      created_by: 'u1', created_by_nombre: 'Ana Admin', created_at: '2026-09-02T14:30:00' },
    { id: 'b', clave: 'clave_x', valor: 30, vigente_desde: '2026-01-01', sucursal_id: 's1',
      created_by: null, created_by_nombre: null, created_at: null },
  ];

  it('opens, asks for the key history and lists newest first with author', async () => {
    const { cargarHistorial } = montar(ENTERO, { cargarHistorial: jest.fn(async () => FILAS) });
    fireEvent.click(screen.getByRole('button', { name: 'Ver historial' }));
    const cajon = await screen.findByRole('dialog', { name: /Historial/ });
    expect(cargarHistorial).toHaveBeenCalledWith('dias_entre_pedidos');
    expect(await within(cajon).findByText('Ana Admin')).toBeInTheDocument();
    const filas = within(cajon).getAllByRole('row').slice(1);
    expect(filas).toHaveLength(2);
    expect(filas[0]).toHaveTextContent('2026-09');
    expect(filas[0]).toHaveTextContent('45');
    expect(filas[0]).toHaveTextContent('Todas las tiendas');
    expect(filas[1]).toHaveTextContent('Una tienda');
    expect(filas[1]).toHaveTextContent('—');
  });

  it('shows an empty state and a load error', async () => {
    const vacio = jest.fn(async () => []);
    const { unmount } = render(
      <CampoConfiguracion spec={ENTERO} etiqueta="E" ayuda="a" hoy={HOY} cargarHistorial={vacio} onGuardar={jest.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Ver historial' }));
    expect(await screen.findByText(/Aún no hay cambios guardados/)).toBeInTheDocument();
    unmount();
    const falla = jest.fn(async () => { throw new Error('No se pudo cargar'); });
    render(
      <CampoConfiguracion spec={ENTERO} etiqueta="E" ayuda="a" hoy={HOY} cargarHistorial={falla} onGuardar={jest.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Ver historial' }));
    expect(await screen.findByText('No se pudo cargar')).toBeInTheDocument();
  });

  it('closes with its button', async () => {
    montar(ENTERO);
    fireEvent.click(screen.getByRole('button', { name: 'Ver historial' }));
    const cajon = await screen.findByRole('dialog');
    fireEvent.click(within(cajon).getByRole('button', { name: 'Cerrar' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
