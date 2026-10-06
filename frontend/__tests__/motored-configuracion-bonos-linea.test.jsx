/**
 * comision_lineas: per-line sales-mix bonuses of the asesores. Editor rows
 * (pct, bono, activo, remove), the "Agregar línea" select, the live rules,
 * the read-only text, the registry wiring and the Comisiones tab.
 */
import React, { useState } from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import EditorBonosLinea, { opcionesParaAgregar } from '../components/motored/configuracion/EditorBonosLinea';
import { EDITORES } from '../components/motored/configuracion/editores';
import { validarBonosLinea } from '../components/motored/configuracion/validaciones';
import { aBorrador, desdeBorrador, formatearValor } from '../components/motored/configuracion/valor';
import { etiquetaLinea } from '../components/motored/configuracion/etiquetas';
import SeccionPanel from '../components/motored/configuracion/SeccionPanel';

const POR_DEFECTO = [
  { linea: 'LUBRICANTES', pct_meta: '21', bono: '35000', activo: true },
  { linea: 'CASCOS', pct_meta: '6', bono: '30000', activo: true },
  { linea: 'ACCESORIOS', pct_meta: '3', bono: '25000', activo: true },
  { linea: 'LLANTAS', pct_meta: '1', bono: '25000', activo: true },
  { linea: 'BATERIAS', pct_meta: '1', bono: '25000', activo: true },
  { linea: 'TECNIRED', pct_meta: '6', bono: '25000', activo: true },
];

const spec = (clave, tipo, valor, extra = {}) => ({
  clave, seccion: 'comisiones', grupo: 'OPERACION', tipo, dominio: 'dominio',
  ambito: 'GLOBAL', default: valor, opciones: [], minimo: null, maximo: null,
  minimo_exclusivo: false, campos: [], snapshotted: false,
  efectivo_global: { valor, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
  por_sucursal: [], programados: [], ...extra,
});
const SPEC_BONOS = spec('comision_lineas', 'lista_objetos', POR_DEFECTO);

function Envoltorio({ inicial, lineas, onCambio = () => {} }) {
  const [borrador, setBorrador] = useState(inicial);
  const cambiar = (nuevo) => { setBorrador(nuevo); onCambio(nuevo); };
  return <EditorBonosLinea spec={{ ...SPEC_BONOS, lineas }} borrador={borrador} onChange={cambiar} />;
}

function montarEditor(inicial = aBorrador(SPEC_BONOS, POR_DEFECTO), lineas) {
  const onCambio = jest.fn();
  render(<Envoltorio inicial={inicial} lineas={lineas} onCambio={onCambio} />);
  return { onCambio, ultimo: () => onCambio.mock.calls[onCambio.mock.calls.length - 1][0] };
}

describe('EditorBonosLinea', () => {
  it('renders one row per default line with readable labels', () => {
    montarEditor();
    const filas = screen.getAllByRole('listitem');
    expect(filas).toHaveLength(6);
    ['Lubricantes', 'Cascos', 'Otros accesorios', 'Llantas', 'Baterías', 'Tecnired (clientes)'].forEach((t, i) => {
      expect(within(filas[i]).getByText(t)).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Meta de Lubricantes (%)')).toHaveValue('21');
    expect(screen.getByLabelText('Bono de Lubricantes (COP)')).toHaveValue('35000');
    expect(screen.getByLabelText('Pagar bono de Lubricantes')).toBeChecked();
  });

  it('edits pct and bono of one line', () => {
    const { ultimo } = montarEditor();
    fireEvent.change(screen.getByLabelText('Meta de Cascos (%)'), { target: { value: '7,5' } });
    fireEvent.change(screen.getByLabelText('Bono de Cascos (COP)'), { target: { value: '40000' } });
    expect(ultimo()[1]).toEqual({ linea: 'CASCOS', pct_meta: '7,5', bono: '40000', activo: true });
  });

  it('switches a line off', () => {
    const { ultimo } = montarEditor();
    fireEvent.click(screen.getByLabelText('Pagar bono de Llantas'));
    expect(ultimo()[3].activo).toBe(false);
    expect(screen.getByLabelText('Pagar bono de Llantas')).not.toBeChecked();
  });

  it('removes a line and offers it again in Agregar línea', () => {
    const { ultimo } = montarEditor();
    fireEvent.click(screen.getByRole('button', { name: 'Quitar Cascos' }));
    expect(ultimo().map((f) => f.linea)).not.toContain('CASCOS');
    expect(within(screen.getByLabelText('Agregar línea')).getByRole('option', { name: 'Cascos' })).toBeInTheDocument();
  });

  it('adds an unused line from the select, prefilled with its default', () => {
    const { ultimo } = montarEditor([], undefined);
    fireEvent.change(screen.getByLabelText('Agregar línea'), { target: { value: 'LUBRICANTES' } });
    expect(ultimo()).toEqual([{ linea: 'LUBRICANTES', pct_meta: '21', bono: '35000', activo: true }]);
    fireEvent.change(screen.getByLabelText('Agregar línea'), { target: { value: 'GPS' } });
    expect(ultimo()[1]).toEqual({ linea: 'GPS', pct_meta: '', bono: '', activo: true });
  });

  it('lists only unused lines in Agregar línea, each option styled', () => {
    montarEditor();
    const opciones = within(screen.getByLabelText('Agregar línea')).getAllByRole('option');
    const valores = opciones.map((o) => o.value).filter(Boolean);
    expect(valores).toEqual(['REPUESTOS', 'GPS']);
    opciones.forEach((o) => expect(o.getAttribute('style')).toMatch(/color/));
  });

  it('shows the live rule messages', () => {
    montarEditor([{ linea: 'CASCOS', pct_meta: '0', bono: '1.5', activo: true }]);
    expect(screen.getByRole('alert')).toHaveTextContent(/mayor que 0 y hasta 100/);
    expect(screen.getByRole('alert')).toHaveTextContent(/entero en pesos/);
  });
});

describe('opcionesParaAgregar', () => {
  it('uses the configured lineas_comerciales plus TECNIRED, minus used', () => {
    expect(opcionesParaAgregar(['REPUESTOS', 'MOTOS'], [{ linea: 'MOTOS' }])).toEqual(['REPUESTOS', 'TECNIRED']);
  });

  it('falls back to the seven default lines plus TECNIRED', () => {
    expect(opcionesParaAgregar(undefined, [])).toEqual([
      'REPUESTOS', 'ACCESORIOS', 'LLANTAS', 'LUBRICANTES', 'BATERIAS', 'GPS', 'CASCOS', 'TECNIRED',
    ]);
  });
});

describe('validarBonosLinea', () => {
  const fila = (extra) => ({ linea: 'CASCOS', pct_meta: '6', bono: '30000', activo: true, ...extra });

  it('accepts the defaults and an empty list', () => {
    expect(validarBonosLinea(aBorrador(SPEC_BONOS, POR_DEFECTO))).toEqual([]);
    expect(validarBonosLinea([])).toEqual([]);
  });

  it('flags a repeated line', () => {
    expect(validarBonosLinea([fila(), fila()])).toContain('La línea «Cascos» está repetida.');
  });

  it.each(['0', '-1', '100.5', 'abc', ''])('flags the pct %p', (pct) => {
    expect(validarBonosLinea([fila({ pct_meta: pct })])).toEqual(
      ['Cascos: la meta debe ser un porcentaje mayor que 0 y hasta 100.'],
    );
  });

  it('accepts a pct of exactly 100 and a bono of 0', () => {
    expect(validarBonosLinea([fila({ pct_meta: '100', bono: '0' })])).toEqual([]);
  });

  it.each(['-5', '1.5', 'x', ''])('flags the bono %p', (bono) => {
    expect(validarBonosLinea([fila({ bono })])).toEqual(
      ['Cascos: el bono debe ser un valor entero en pesos, 0 o más.'],
    );
  });

  it('flags a line outside the known ones when they are given', () => {
    expect(validarBonosLinea([fila({ linea: 'MOTOS' })], ['CASCOS', 'TECNIRED'])).toEqual(
      ['La línea «MOTOS» no está en las líneas comerciales configuradas.'],
    );
  });
});

describe('valor helpers of comision_lineas', () => {
  it('aBorrador turns numbers into text and keeps activo', () => {
    expect(aBorrador(SPEC_BONOS, [{ linea: 'GPS', pct_meta: 2.5, bono: '25000.00', activo: false }]))
      .toEqual([{ linea: 'GPS', pct_meta: '2.5', bono: '25000', activo: false }]);
  });

  it('desdeBorrador sends decimal strings in the same order', () => {
    const borrador = [{ linea: 'GPS', pct_meta: ' 2,5 ', bono: ' 25000 ', activo: false }, ...POR_DEFECTO.slice(0, 1)];
    expect(desdeBorrador(SPEC_BONOS, borrador)).toEqual({
      valor: [{ linea: 'GPS', pct_meta: '2.5', bono: '25000', activo: false }, POR_DEFECTO[0]],
    });
  });

  it('desdeBorrador rejects a non-number', () => {
    expect(desdeBorrador(SPEC_BONOS, [{ linea: 'GPS', pct_meta: 'x', bono: '1', activo: true }]).error).toMatch(/GPS/);
  });

  it('formatearValor writes each line for a person', () => {
    const valor = [POR_DEFECTO[0], { ...POR_DEFECTO[1], activo: false, pct_meta: '6.5' }];
    expect(formatearValor(SPEC_BONOS, valor)).toBe(
      'Lubricantes ≥21% · $ 35.000 · activo; Cascos ≥6,5% · $ 30.000 · apagado',
    );
    expect(formatearValor(SPEC_BONOS, [])).toBe('(vacía)');
  });

  it('etiquetaLinea keeps an unknown code as is', () => {
    expect(etiquetaLinea('ACCESORIOS')).toBe('Otros accesorios');
    expect(etiquetaLinea('MOTOS')).toBe('MOTOS');
  });
});

describe('registry and Comisiones tab', () => {
  it('registers comision_lineas with its editor and validator', () => {
    expect(EDITORES.comision_lineas.Control).toBe(EditorBonosLinea);
    expect(EDITORES.comision_lineas.validar([{ linea: 'GPS', pct_meta: '0', bono: '1', activo: true }])).toHaveLength(1);
  });

  const datos = (comisiones, indicadores = []) => ({
    secciones: [
      { seccion: 'indicadores', grupos: [{ grupo: 'OPERACION', claves: indicadores }] },
      { seccion: 'comisiones', grupos: [{ grupo: 'OPERACION', claves: comisiones }] },
    ],
  });
  const TRAMOS = spec('comision_tramos', 'tramos', [{ nombre: 'BASE', desde_pct: 0, tasa_pct: 1 }]);

  it('skips the field without crashing when the server does not return the key', () => {
    render(<SeccionPanel seccion={{ id: 'comisiones', label: 'Comisiones' }} data={datos([TRAMOS])} recargar={jest.fn()} />);
    expect(screen.getByText('Tramos de comisión')).toBeInTheDocument();
    expect(screen.queryByText('Bonos por línea')).not.toBeInTheDocument();
  });

  it('shows Bonos por línea, offers the configured lines and saves the value', async () => {
    const onGuardar = jest.fn(async () => ({}));
    const lineas = spec('lineas_comerciales', 'lista', ['Repuestos', 'GPS', 'lubricantes'], { seccion: 'indicadores' });
    const bonos = spec('comision_lineas', 'lista_objetos', POR_DEFECTO.slice(0, 1));
    render(
      <SeccionPanel
        seccion={{ id: 'comisiones', label: 'Comisiones' }} data={datos([TRAMOS, bonos], [lineas])}
        recargar={jest.fn()} onGuardar={onGuardar}
      />,
    );
    const seccion = screen.getByText('Bonos por línea').closest('section');
    expect(within(seccion).getByText(/Valor por defecto: Lubricantes ≥21% · \$ 35.000 · activo/)).toBeInTheDocument();
    const valores = within(within(seccion).getByLabelText('Agregar línea')).getAllByRole('option').map((o) => o.value);
    expect(valores.filter(Boolean)).toEqual(['REPUESTOS', 'GPS', 'TECNIRED']);
    fireEvent.change(within(seccion).getByLabelText('Agregar línea'), { target: { value: 'GPS' } });
    fireEvent.change(within(seccion).getByLabelText('Meta de GPS (%)'), { target: { value: '2' } });
    fireEvent.change(within(seccion).getByLabelText('Bono de GPS (COP)'), { target: { value: '20000' } });
    fireEvent.click(within(seccion).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0].valor).toEqual([
      POR_DEFECTO[0], { linea: 'GPS', pct_meta: '2', bono: '20000', activo: true },
    ]);
  });

  it('no longer says the commission rules are not read yet', () => {
    render(<SeccionPanel seccion={{ id: 'comisiones', label: 'Comisiones' }} data={datos([TRAMOS])} recargar={jest.fn()} />);
    expect(screen.queryByText(/Se aplican cuando estén activos/)).not.toBeInTheDocument();
  });
});
