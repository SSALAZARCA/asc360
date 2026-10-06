/**
 * T6 Indicadores and T7 Comisiones tabs: the notice, every field with its
 * tooltip, and the editors (chips, cargo map, semáforo, tramos table).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import SeccionPanel from '../components/motored/configuracion/SeccionPanel';

const spec = (clave, tipo, extra = {}, valor = null) => ({
  clave, seccion: 'indicadores', grupo: 'OPERACION', tipo, dominio: 'dominio',
  ambito: 'GLOBAL', default: valor, opciones: [], minimo: null, maximo: null,
  minimo_exclusivo: false, campos: [], snapshotted: false,
  efectivo_global: { valor, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
  por_sucursal: [], programados: [], ...extra,
});

const CARGOS = {
  'ASESOR DE REPUESTOS': 'PERSONA',
  'ASESOR COMERCIAL DE SERVICIO POSVENTA': 'COMERCIALES',
};
const INDICADORES = [
  spec('hmcl_nits', 'lista_digitos', {}, ['900723988', '900883086']),
  spec('grupo_por_cargo', 'mapa_opcion', { opciones: ['PERSONA', 'COMERCIALES', 'OTROS'] }, CARGOS),
  spec('lineas_comerciales', 'lista', {}, ['REPUESTOS', 'GPS']),
  spec('kpi_semaforo_cortes', 'objeto_numerico', {
    campos: ['verde_desde', 'ambar_desde'], minimo: 0, maximo: 200,
  }, { verde_desde: 90, ambar_desde: 70 }),
];
const COMISIONES = [
  spec('comision_tramos', 'tramos', { seccion: 'comisiones', campos: ['nombre', 'desde_pct', 'tasa_pct'] }, [
    { nombre: 'BASE', desde_pct: 0, tasa_pct: 1 },
    { nombre: 'PRO', desde_pct: 90, tasa_pct: 1.5 },
  ]),
  spec('comision_base_pago', 'opcion', { seccion: 'comisiones', opciones: ['sin_hmcl', 'con_hmcl'] }, 'sin_hmcl'),
  spec('cumplimiento_base', 'opcion', { seccion: 'comisiones', opciones: ['con_hmcl', 'sin_hmcl'] }, 'con_hmcl'),
  spec('comision_cargos_asesor', 'lista', { seccion: 'comisiones' }, ['ASESOR DE REPUESTOS']),
];
const datos = (seccion, claves) => ({
  secciones: [{ seccion, grupos: [{ grupo: 'OPERACION', claves }] }],
});

function montar(id, label, claves) {
  const onGuardar = jest.fn(async () => ({}));
  render(<SeccionPanel seccion={{ id, label }} data={datos(id, claves)} recargar={jest.fn()} onGuardar={onGuardar} />);
  return { onGuardar };
}
const campo = (nombre) => screen.getByText(nombre).closest('section');

describe('Indicadores tab', () => {
  it('shows the notice and the four fields, each with a tooltip', () => {
    montar('indicadores', 'Indicadores', INDICADORES);
    expect(screen.getByText(/Se aplican cuando estén activos los indicadores de comisiones/)).toBeInTheDocument();
    expect(screen.getAllByRole('note').length).toBeGreaterThanOrEqual(4);
    ['NIT de HMCL', 'Grupo de cada cargo', 'Líneas comerciales', 'Colores del semáforo'].forEach((t) => {
      expect(screen.getByText(t)).toBeInTheDocument();
    });
  });

  it('saves hmcl_nits after adding a NIT chip and removing another', async () => {
    const { onGuardar } = montar('indicadores', 'Indicadores', INDICADORES);
    const nits = campo('NIT de HMCL');
    fireEvent.click(within(nits).getByRole('button', { name: 'Quitar 900883086' }));
    fireEvent.change(within(nits).getByLabelText('Nuevo valor'), { target: { value: '800111222' } });
    fireEvent.click(within(nits).getByRole('button', { name: 'Agregar' }));
    fireEvent.click(within(nits).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'hmcl_nits', valor: ['900723988', '800111222'] });
  });

  it('refuses a non-digit or repeated NIT with a message', () => {
    montar('indicadores', 'Indicadores', INDICADORES);
    const nits = campo('NIT de HMCL');
    fireEvent.change(within(nits).getByLabelText('Nuevo valor'), { target: { value: '90a' } });
    fireEvent.click(within(nits).getByRole('button', { name: 'Agregar' }));
    expect(within(nits).getByRole('alert')).toHaveTextContent('sólo dígitos');
    fireEvent.change(within(nits).getByLabelText('Nuevo valor'), { target: { value: '900723988' } });
    fireEvent.click(within(nits).getByRole('button', { name: 'Agregar' }));
    expect(within(nits).getByRole('alert')).toHaveTextContent('ya está');
  });

  it('adds a cargo in capitals with a group and saves the map', async () => {
    const { onGuardar } = montar('indicadores', 'Indicadores', INDICADORES);
    const mapa = campo('Grupo de cada cargo');
    fireEvent.click(within(mapa).getByRole('button', { name: /Agregar cargo/ }));
    const nombres = within(mapa).getAllByLabelText('Nombre del cargo');
    fireEvent.change(nombres[nombres.length - 1], { target: { value: 'jefe de taller' } });
    const grupos = within(mapa).getAllByLabelText('Grupo del cargo');
    fireEvent.change(grupos[grupos.length - 1], { target: { value: 'OTROS' } });
    fireEvent.click(within(mapa).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0].valor).toEqual({ ...CARGOS, 'JEFE DE TALLER': 'OTROS' });
  });

  it('gives every cargo group option an explicit colour', () => {
    montar('indicadores', 'Indicadores', INDICADORES);
    const mapa = campo('Grupo de cada cargo');
    within(mapa).getAllByRole('option').forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });

  it('previews the three bands of the semáforo live and validates the order', () => {
    montar('indicadores', 'Indicadores', INDICADORES);
    const sem = campo('Colores del semáforo');
    expect(sem).toHaveTextContent('Verde: 90 % o más');
    expect(sem).toHaveTextContent('Ámbar: de 70 % a menos de 90 %');
    expect(sem).toHaveTextContent('Rojo: menos de 70 %');
    fireEvent.change(within(sem).getByLabelText('Ámbar desde (%)'), { target: { value: '95' } });
    expect(within(sem).getByRole('alert')).toHaveTextContent('«Ámbar desde» debe ser menor que «Verde desde».');
    fireEvent.change(within(sem).getByLabelText('Ámbar desde (%)'), { target: { value: '60' } });
    fireEvent.change(within(sem).getByLabelText('Verde desde (%)'), { target: { value: '100' } });
    expect(sem).toHaveTextContent('Verde: 100 % o más');
    expect(sem).toHaveTextContent('Ámbar: de 60 % a menos de 100 %');
    expect(within(sem).queryByRole('alert')).toBeNull();
  });

  it('does not call the API when the semáforo is invalid', async () => {
    const { onGuardar } = montar('indicadores', 'Indicadores', INDICADORES);
    const sem = campo('Colores del semáforo');
    fireEvent.change(within(sem).getByLabelText('Verde desde (%)'), { target: { value: '250' } });
    fireEvent.click(within(sem).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(within(sem).getAllByRole('alert').length).toBeGreaterThan(0));
    expect(onGuardar).not.toHaveBeenCalled();
  });
});

describe('Comisiones tab', () => {
  it('shows the notice, the four fields and the readable base options', () => {
    montar('comisiones', 'Comisiones', COMISIONES);
    expect(screen.getByText(/El tablero de KPI usa estas reglas/)).toBeInTheDocument();
    ['Tramos de comisión', 'Base para pagar la comisión', 'Base del cumplimiento', 'Cargos que comisionan'].forEach((t) => {
      expect(screen.getByText(t)).toBeInTheDocument();
    });
    const base = campo('Base para pagar la comisión');
    expect(within(base).getByRole('option', { name: 'Sin HMCL' }).value).toBe('sin_hmcl');
    expect(within(base).getByRole('option', { name: 'Con HMCL' }).value).toBe('con_hmcl');
  });

  it('adds, edits and reorders tramos and saves them in that order', async () => {
    const { onGuardar } = montar('comisiones', 'Comisiones', COMISIONES);
    const t = campo('Tramos de comisión');
    fireEvent.click(within(t).getByRole('button', { name: /Agregar tramo/ }));
    const nombres = within(t).getAllByLabelText('Nombre del tramo');
    fireEvent.change(nombres[2], { target: { value: 'ELITE' } });
    fireEvent.change(within(t).getAllByLabelText('Desde (%)')[2], { target: { value: '105' } });
    fireEvent.change(within(t).getAllByLabelText('Tasa (%)')[2], { target: { value: '1,8' } });
    fireEvent.click(within(t).getAllByRole('button', { name: 'Subir tramo' })[2]);
    expect(within(t).getAllByRole('alert')[0]).toHaveTextContent('debe ser mayor que el del tramo anterior');
    fireEvent.click(within(t).getAllByRole('button', { name: 'Bajar tramo' })[1]);
    expect(within(t).queryByRole('alert')).toBeNull();
    fireEvent.click(within(t).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0].valor).toEqual([
      { nombre: 'BASE', desde_pct: '0', tasa_pct: '1' },
      { nombre: 'PRO', desde_pct: '90', tasa_pct: '1.5' },
      { nombre: 'ELITE', desde_pct: '105', tasa_pct: '1.8' },
    ]);
  });

  it('shows the rule message and blocks the save when the first tramo is not 0', async () => {
    const { onGuardar } = montar('comisiones', 'Comisiones', COMISIONES);
    const t = campo('Tramos de comisión');
    fireEvent.change(within(t).getAllByLabelText('Desde (%)')[0], { target: { value: '5' } });
    expect(within(t).getByRole('alert')).toHaveTextContent('El primer tramo debe empezar en 0 %.');
    fireEvent.click(within(t).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).not.toHaveBeenCalled());
  });

  it('removes a tramo and keeps controls at 44 px', () => {
    montar('comisiones', 'Comisiones', COMISIONES);
    const t = campo('Tramos de comisión');
    fireEvent.click(within(t).getAllByRole('button', { name: 'Quitar fila' })[1]);
    expect(within(t).getAllByLabelText('Nombre del tramo')).toHaveLength(1);
    within(t).getAllByRole('button').forEach((b) => expect(b.style.minHeight).toBe('44px'));
  });

  it('edits the advisor cargos as chips', async () => {
    const { onGuardar } = montar('comisiones', 'Comisiones', COMISIONES);
    const c = campo('Cargos que comisionan');
    fireEvent.change(within(c).getByLabelText('Nuevo valor'), { target: { value: 'asesor supernumerario' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Agregar' }));
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0].valor).toEqual(['ASESOR DE REPUESTOS', 'ASESOR SUPERNUMERARIO']);
  });
});
