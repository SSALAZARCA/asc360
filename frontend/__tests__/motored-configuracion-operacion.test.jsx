/**
 * T2 Pedido, T3 Avisos, T4 Cargas and T5 Limpieza tabs: grouped fields with
 * a tooltip each, the per-tienda value of dias_entre_pedidos, the hour and
 * role controls, and the notices of each tab.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

jest.mock('../lib/motored/api', () => ({ listMaestros: jest.fn() }));

import { listMaestros } from '../lib/motored/api';
import SeccionPanel from '../components/motored/configuracion/SeccionPanel';

const spec = (clave, tipo, extra = {}, valor = null) => ({
  clave, seccion: 'pedido', grupo: 'MOTOR', tipo, dominio: 'dominio',
  ambito: 'GLOBAL', default: valor, opciones: [], minimo: null, maximo: null,
  minimo_exclusivo: false, campos: [], snapshotted: false,
  efectivo_global: { valor, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
  por_sucursal: [], programados: [], ...extra,
});
const motor = (clave, tipo, extra, valor) => spec(clave, tipo, { snapshotted: true, ...extra }, valor);

const PEDIDO = [
  motor('dias_entre_pedidos', 'entero', { ambito: 'GLOBAL_Y_SUCURSAL', minimo: 1, maximo: 60 }, 30),
  motor('modo_mes_en_curso', 'opcion', { opciones: ['EXCLUIDO', 'PONDERADO'] }, 'EXCLUIDO'),
  motor('tope_proyeccion_mes_actual', 'decimal', {}, '3.0'),
  motor('min_dias_mes_actual', 'entero', {}, 5),
  motor('modo_redondeo_empaque', 'opcion', { opciones: ['CERCANO', 'ARRIBA'] }, 'CERCANO'),
  motor('corte_abc_a', 'decimal', {}, '0.80'),
  motor('corte_abc_b', 'decimal', {}, '0.95'),
  motor('umbral_f', 'entero', {}, 2),
  motor('umbral_m', 'entero', {}, 1),
  motor('k_fms', 'k_fms', { campos: ['F', 'M', 'S'] }, { F: '3', M: '1.5', S: '1' }),
  motor('incluir_demanda_perdida_en_ponderada', 'bool', {}, false),
  motor('factor_demanda_perdida', 'decimal', {}, '1'),
  motor('consolidar_sustituidas', 'bool', {}, false),
  motor('excluir_transito_vencido', 'bool', {}, false),
  motor('tolerancia_sobrestock', 'decimal', {}, '0.25'),
  motor('meses_inventario_muerto', 'entero', {}, 6),
  motor('max_dias_antiguedad_inventario', 'entero', {}, 7),
  motor('max_dias_antiguedad_backorder', 'entero', {}, 7),
  motor('max_dias_antiguedad_facturas', 'entero', {}, 7),
  motor('max_dias_antiguedad_ingresos', 'entero', {}, 7),
];
const AVISOS = [
  spec('aviso_hora_vispera', 'hora', { seccion: 'avisos', grupo: 'OPERACION' }, '16:30'),
  spec('aviso_hora_dia', 'hora', { seccion: 'avisos', grupo: 'OPERACION' }, '08:30'),
  spec('aviso_roles_destino', 'lista_opciones', { seccion: 'avisos', grupo: 'OPERACION', opciones: ['ADMIN', 'COMPRAS'] }, ['COMPRAS']),
];
const CARGAS = [
  spec('tipos_inventario_incluidos', 'lista', { seccion: 'cargas', grupo: 'INGESTA' }, ['REPUESTOS', 'GPS']),
  spec('estados_backorder_vigentes', 'lista', { seccion: 'cargas', grupo: 'INGESTA' }, ['BACKORDER']),
  spec('dias_ventana_ingresos', 'entero', { seccion: 'cargas', grupo: 'INGESTA' }, 45),
  spec('tolerancia_ingreso_pct', 'decimal', { seccion: 'cargas', grupo: 'INGESTA' }, '2.0'),
  spec('periodo_tolerancia_pct', 'decimal', { seccion: 'cargas', grupo: 'INGESTA' }, '0.5'),
  spec('bodegas_excluidas', 'lista', { seccion: 'cargas', grupo: 'OPERACION' }, ['99999', 'PYM01']),
];
const LIMPIEZA = [
  spec('retencion_inventario_habilitada', 'bool', { seccion: 'limpieza', grupo: 'OPERACION' }, false),
  spec('retencion_inventario_dias', 'entero', { seccion: 'limpieza', grupo: 'OPERACION', minimo: 30, maximo: 3650 }, 90),
  spec('retencion_corridas_habilitada', 'bool', { seccion: 'limpieza', grupo: 'OPERACION' }, false),
  spec('retencion_corridas_dias', 'entero', { seccion: 'limpieza', grupo: 'OPERACION', minimo: 7, maximo: 3650 }, 45),
];

const datos = (seccion, claves) => ({
  secciones: [{ seccion, grupos: [{ grupo: 'X', claves }] }],
});

function montar(id, label, claves) {
  const onGuardar = jest.fn(async () => ({}));
  const recargar = jest.fn();
  render(<SeccionPanel seccion={{ id, label }} data={datos(id, claves)} recargar={recargar} onGuardar={onGuardar} />);
  return { onGuardar, recargar };
}
const campo = (nombre) => screen.getByText(nombre).closest('section');

beforeEach(() => {
  jest.clearAllMocks();
  listMaestros.mockResolvedValue([
    { id: 's1', nombre: 'Bogotá Norte' },
    { id: 's2', nombre: 'Medellín' },
    { id: 's3', nombre: 'Cali' },
  ]);
});

describe('Pedido tab', () => {
  it('shows the banner and the five groups in order', () => {
    montar('pedido', 'Pedido', PEDIDO);
    expect(screen.getByText('Los cambios aplican a los pedidos nuevos; los ya calculados no cambian.')).toBeInTheDocument();
    const titulos = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(titulos).toEqual([
      'Cobertura y frecuencia', 'Clasificación ABC/FMS', 'Mejoras opcionales', 'Alertas', 'Antigüedad de datos',
    ]);
  });

  it('gives every field a plain-Spanish tooltip', () => {
    montar('pedido', 'Pedido', PEDIDO);
    const notas = screen.getAllByRole('note');
    expect(notas.length).toBeGreaterThanOrEqual(PEDIDO.length);
    notas.forEach((n) => expect(n.getAttribute('aria-label').length).toBeGreaterThan(20));
  });

  it('shows the optional improvements off by default', () => {
    montar('pedido', 'Pedido', PEDIDO);
    const grupo = screen.getByRole('heading', { name: 'Mejoras opcionales' }).closest('div');
    within(grupo).getAllByRole('checkbox').forEach((c) => expect(c).not.toBeChecked());
    expect(within(grupo).getAllByRole('checkbox').length).toBeGreaterThanOrEqual(3);
  });

  it('saves an engine key through the generic control', async () => {
    const { onGuardar } = montar('pedido', 'Pedido', PEDIDO);
    const c = campo('Umbral de frecuencia alta (F)');
    fireEvent.change(within(c).getByRole('textbox'), { target: { value: '3' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'umbral_f', valor: 3, sucursal_id: null });
  });

  it('gives every select option an explicit colour', () => {
    montar('pedido', 'Pedido', PEDIDO);
    screen.getAllByRole('option').forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });
});

describe('Pedido: dias_entre_pedidos per tienda', () => {
  const conExcepciones = () => PEDIDO.map((s) => (s.clave === 'dias_entre_pedidos'
    ? { ...s, por_sucursal: [{ sucursal_id: 's1', valor: 20, vigente_desde: '2026-10-01', parametro_id: 'p1' }] }
    : s));

  it('lists the tiendas with their own value by name', async () => {
    montar('pedido', 'Pedido', conExcepciones());
    const fila = await screen.findByText('Bogotá Norte');
    expect(within(fila.closest('section')).getByText(/Valor actual: 20/)).toBeInTheDocument();
  });

  it('saves a new value for a tienda that has none, with its sucursal_id', async () => {
    const { onGuardar, recargar } = montar('pedido', 'Pedido', conExcepciones());
    await screen.findByText('Bogotá Norte');
    const selector = screen.getByLabelText('Tienda');
    const nombres = within(selector).getAllByRole('option').map((o) => o.textContent);
    expect(nombres).toEqual(['Elegir tienda…', 'Medellín', 'Cali']);
    fireEvent.change(selector, { target: { value: 's2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar tienda' }));
    const fila = screen.getByText('Medellín').closest('section');
    fireEvent.change(within(fila).getByRole('textbox'), { target: { value: '14' } });
    fireEvent.click(within(fila).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'dias_entre_pedidos', valor: 14, sucursal_id: 's2' });
    await waitFor(() => expect(recargar).toHaveBeenCalled());
  });

  it('edits the value of a tienda that already has one', async () => {
    const { onGuardar } = montar('pedido', 'Pedido', conExcepciones());
    const fila = (await screen.findByText('Bogotá Norte')).closest('section');
    fireEvent.change(within(fila).getByRole('textbox'), { target: { value: '25' } });
    fireEvent.click(within(fila).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ valor: 25, sucursal_id: 's1' });
  });

  it('still works when the tiendas cannot be loaded', async () => {
    listMaestros.mockRejectedValue(new Error('boom'));
    montar('pedido', 'Pedido', PEDIDO);
    await waitFor(() => expect(screen.getByLabelText('Tienda')).toBeInTheDocument());
    expect(within(screen.getByLabelText('Tienda')).getAllByRole('option')).toHaveLength(1);
  });

  it('keeps the touch targets at 44 px', async () => {
    montar('pedido', 'Pedido', conExcepciones());
    await screen.findByText('Bogotá Norte');
    const selector = screen.getByLabelText('Tienda');
    expect(selector.style.minHeight).toBe('44px');
    expect(screen.getByRole('button', { name: 'Agregar tienda' }).style.minHeight).toBe('44px');
  });
});

describe('Avisos tab', () => {
  it('shows the three fields with tooltips', () => {
    montar('avisos', 'Avisos', AVISOS);
    ['Hora del aviso de víspera', 'Hora del aviso del día del vencimiento', 'A quién se avisa'].forEach((t) => {
      expect(screen.getByText(t)).toBeInTheDocument();
    });
    expect(screen.getAllByRole('note').length).toBeGreaterThanOrEqual(3);
  });

  it('edits an hour with a time control and saves HH:MM', async () => {
    const { onGuardar } = montar('avisos', 'Avisos', AVISOS);
    const c = campo('Hora del aviso del día del vencimiento');
    const hora = within(c).getByLabelText('Hora del aviso del día del vencimiento');
    expect(hora).toHaveAttribute('type', 'time');
    expect(hora).toHaveValue('08:30');
    fireEvent.change(hora, { target: { value: '07:15' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'aviso_hora_dia', valor: '07:15' });
  });

  it('chooses the roles with readable names and saves them in order', async () => {
    const { onGuardar } = montar('avisos', 'Avisos', AVISOS);
    const c = campo('A quién se avisa');
    expect(within(c).getByLabelText('Compras')).toBeChecked();
    expect(within(c).getByLabelText('Administración')).not.toBeChecked();
    fireEvent.click(within(c).getByLabelText('Administración'));
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0].valor).toEqual(['ADMIN', 'COMPRAS']);
  });

  it('blocks saving with no role chosen', async () => {
    const { onGuardar } = montar('avisos', 'Avisos', AVISOS);
    const c = campo('A quién se avisa');
    fireEvent.click(within(c).getByLabelText('Compras'));
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    expect(await within(c).findByRole('alert')).toHaveTextContent('Elija al menos');
    expect(onGuardar).not.toHaveBeenCalled();
  });
});

describe('Cargas tab', () => {
  it('shows the five keys, the period tolerance included, with tooltips', () => {
    montar('cargas', 'Cargas', CARGAS);
    ['Estados de backorder vigentes', 'Ventana de ingresos (días)', 'Tolerancia de ingresos (%)', 'Tolerancia del período declarado (%)', 'Bodegas que no son tiendas']
      .forEach((t) => expect(screen.getByText(t)).toBeInTheDocument());
    expect(screen.getAllByRole('note').length).toBeGreaterThanOrEqual(5);
    expect(campo('Tolerancia del período declarado (%)')).toHaveTextContent('Porcentaje máximo de líneas de otro mes que se acepta al declarar el período de un archivo.');
  });

  it('saves the period tolerance as typed (the API accepts numeric text)', async () => {
    const { onGuardar } = montar('cargas', 'Cargas', CARGAS);
    const c = campo('Tolerancia del período declarado (%)');
    fireEvent.change(within(c).getByRole('textbox'), { target: { value: '5' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'periodo_tolerancia_pct', valor: '5' });
  });

  it('no longer offers the inventory lines (VENTAS keeps the catalog lines)', () => {
    montar('cargas', 'Cargas', CARGAS);
    expect(screen.queryByText('Líneas de inventario que cuentan')).toBeNull();
  });

  it('explains the excluded bodegas and shows them as chips', () => {
    montar('cargas', 'Cargas', CARGAS);
    const c = campo('Bodegas que no son tiendas');
    expect(within(c).getByText('99999')).toBeInTheDocument();
    expect(within(c).getByText('PYM01')).toBeInTheDocument();
    const nota = within(c).getByRole('note');
    expect(nota.getAttribute('aria-label')).toBe(
      'Códigos de bodega que no son tiendas (p. ej. bodega central o producto terminado). '
      + 'Sus líneas se ignoran al cargar ventas e inventario, sin marcar error. '
      + 'Una bodega que no esté aquí ni tenga tienda asignada sigue dando error.',
    );
  });

  it('adds an excluded bodega in capitals and saves the whole list', async () => {
    const { onGuardar } = montar('cargas', 'Cargas', CARGAS);
    const c = campo('Bodegas que no son tiendas');
    fireEvent.change(within(c).getByLabelText('Nuevo valor'), { target: { value: ' ba099 ' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Agregar' }));
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'bodegas_excluidas' });
    expect(onGuardar.mock.calls[0][0].valor).toEqual(['99999', 'PYM01', 'BA099']);
  });

  it('refuses a repeated code and an empty list before saving', async () => {
    const { onGuardar } = montar('cargas', 'Cargas', CARGAS);
    const c = campo('Bodegas que no son tiendas');
    fireEvent.change(within(c).getByLabelText('Nuevo valor'), { target: { value: 'pym01' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Agregar' }));
    expect(within(c).getByRole('alert')).toHaveTextContent('ya está en la lista');
    fireEvent.click(within(c).getByRole('button', { name: 'Quitar 99999' }));
    fireEvent.click(within(c).getByRole('button', { name: 'Quitar PYM01' }));
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    expect(await within(c).findByText('Agregue al menos un valor.')).toBeInTheDocument();
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it('saves the ingresos window as a number', async () => {
    const { onGuardar } = montar('cargas', 'Cargas', CARGAS);
    const c = campo('Ventana de ingresos (días)');
    fireEvent.change(within(c).getByRole('textbox'), { target: { value: '60' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'dias_ventana_ingresos', valor: 60 });
  });
});

describe('Limpieza tab', () => {
  it('says that closed or sent pedidos are never deleted', () => {
    montar('limpieza', 'Limpieza', LIMPIEZA);
    expect(screen.getByText('Nunca borra pedidos cerrados o enviados.')).toBeInTheDocument();
  });

  it('shows the switches and the days with tooltips', () => {
    montar('limpieza', 'Limpieza', LIMPIEZA);
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
    expect(screen.getAllByRole('note').length).toBeGreaterThanOrEqual(4);
    expect(campo('Días de inventario que se conservan')).toHaveTextContent('Valor por defecto: 90');
  });

  it('turns the inventory purge on and saves it', async () => {
    const { onGuardar } = montar('limpieza', 'Limpieza', LIMPIEZA);
    const c = campo('Borrar inventario viejo automáticamente');
    fireEvent.click(within(c).getByRole('checkbox'));
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'retencion_inventario_habilitada', valor: true });
  });

  it('shows the server explanation when the days are below the minimum', async () => {
    const onGuardar = jest.fn(async () => { throw new Error('Valor no válido: menos de 30 días borraría inventario que todavía se consulta.'); });
    render(<SeccionPanel seccion={{ id: 'limpieza', label: 'Limpieza' }} data={datos('limpieza', LIMPIEZA)} recargar={jest.fn()} onGuardar={onGuardar} />);
    const c = campo('Días de inventario que se conservan');
    fireEvent.change(within(c).getByRole('textbox'), { target: { value: '10' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    expect(await within(c).findByRole('alert')).toHaveTextContent('menos de 30 días');
  });
});
