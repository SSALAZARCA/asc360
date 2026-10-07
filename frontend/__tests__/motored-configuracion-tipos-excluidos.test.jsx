/**
 * ventas_tipos_excluidos: the ERP "Tipo inventario" codes whose rows are
 * discarded when a VENTAS file loads. Editor rows (código + modo + remove,
 * add row), the live rules, the value helpers, the registry wiring and the
 * Cargas tab (shown when the server returns the key, skipped otherwise).
 */
import React, { useState } from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import EditorTiposExcluidos from '../components/motored/configuracion/EditorTiposExcluidos';
import { EDITORES } from '../components/motored/configuracion/editores';
import { validarTiposExcluidos } from '../components/motored/configuracion/validaciones';
import { aBorrador, desdeBorrador, formatearValor } from '../components/motored/configuracion/valor';
import SeccionPanel from '../components/motored/configuracion/SeccionPanel';

const POR_DEFECTO = [
  { codigo: 'IM19', modo: 'prefijo' },
  { codigo: 'VS12', modo: 'exacto' },
  { codigo: 'G01', modo: 'exacto' },
];

const spec = (clave, tipo, valor) => ({
  clave, seccion: 'cargas', grupo: 'OPERACION', tipo, dominio: 'dominio',
  ambito: 'GLOBAL', default: valor, opciones: [], minimo: null, maximo: null,
  minimo_exclusivo: false, campos: [], snapshotted: false,
  efectivo_global: { valor, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
  por_sucursal: [], programados: [],
});
const SPEC = spec('ventas_tipos_excluidos', 'lista_objetos', POR_DEFECTO);

function Envoltorio({ inicial, onCambio }) {
  const [borrador, setBorrador] = useState(inicial);
  const cambiar = (nuevo) => { setBorrador(nuevo); onCambio(nuevo); };
  return <EditorTiposExcluidos spec={SPEC} borrador={borrador} onChange={cambiar} />;
}

function montar(inicial = aBorrador(SPEC, POR_DEFECTO)) {
  const onCambio = jest.fn();
  render(<Envoltorio inicial={inicial} onCambio={onCambio} />);
  return { ultimo: () => onCambio.mock.calls[onCambio.mock.calls.length - 1][0] };
}

describe('EditorTiposExcluidos', () => {
  it('renders one row per code with its mode, every option styled', () => {
    montar();
    expect(screen.getByLabelText('Código 1')).toHaveValue('IM19');
    expect(screen.getByLabelText('Modo del código 1')).toHaveValue('prefijo');
    expect(screen.getByLabelText('Modo del código 2')).toHaveValue('exacto');
    const opciones = within(screen.getByLabelText('Modo del código 1')).getAllByRole('option');
    expect(opciones.map((o) => o.textContent)).toEqual(['Empieza por', 'Exacto']);
    opciones.forEach((o) => expect(o.getAttribute('style')).toMatch(/color/));
  });

  it('writes the code in capitals and changes the mode', () => {
    const { ultimo } = montar();
    fireEvent.change(screen.getByLabelText('Código 2'), { target: { value: 'vs13' } });
    expect(ultimo()[1]).toEqual({ codigo: 'VS13', modo: 'exacto' });
    fireEvent.change(screen.getByLabelText('Modo del código 2'), { target: { value: 'prefijo' } });
    expect(ultimo()[1]).toEqual({ codigo: 'VS13', modo: 'prefijo' });
  });

  it('adds an empty exact row and removes a row', () => {
    const { ultimo } = montar();
    fireEvent.click(screen.getByRole('button', { name: /Agregar código/ }));
    expect(ultimo()).toHaveLength(4);
    expect(ultimo()[3]).toEqual({ codigo: '', modo: 'exacto' });
    fireEvent.click(screen.getByRole('button', { name: 'Quitar código 1' }));
    expect(ultimo().map((f) => f.codigo)).toEqual(['VS12', 'G01', '']);
  });

  it('shows the live rule messages', () => {
    montar([{ codigo: '', modo: 'exacto' }, { codigo: 'G01', modo: 'exacto' }, { codigo: 'G01', modo: 'exacto' }]);
    expect(screen.getByRole('alert')).toHaveTextContent('Fila 1: escriba un código.');
    expect(screen.getByRole('alert')).toHaveTextContent('«G01» (Exacto) está repetido.');
  });

  it('says so when the list is empty', () => {
    montar([]);
    expect(screen.getByText(/Sin códigos/)).toBeInTheDocument();
  });
});

describe('validarTiposExcluidos', () => {
  it('accepts the defaults and an empty list', () => {
    expect(validarTiposExcluidos(POR_DEFECTO)).toEqual([]);
    expect(validarTiposExcluidos([])).toEqual([]);
  });

  it('flags characters outside letters, digits, dot, dash and underscore', () => {
    expect(validarTiposExcluidos([{ codigo: 'IM 19', modo: 'prefijo' }])).toEqual(
      ['«IM 19» tiene caracteres no permitidos (use letras, números, punto, guion o guion bajo).'],
    );
  });

  it('allows the same code once as prefix and once as exact', () => {
    expect(validarTiposExcluidos([{ codigo: 'G01', modo: 'prefijo' }, { codigo: 'g01', modo: 'exacto' }])).toEqual([]);
  });

  it('flags a duplicate ignoring case and spaces', () => {
    expect(validarTiposExcluidos([{ codigo: 'G01', modo: 'exacto' }, { codigo: ' g01 ', modo: 'exacto' }]))
      .toEqual(['«G01» (Exacto) está repetido.']);
  });
});

describe('valor helpers of ventas_tipos_excluidos', () => {
  it('aBorrador copies the rows and defaults an unknown mode to exacto', () => {
    expect(aBorrador(SPEC, [{ codigo: 'IM19', modo: 'prefijo' }, { codigo: 'X1' }]))
      .toEqual([{ codigo: 'IM19', modo: 'prefijo' }, { codigo: 'X1', modo: 'exacto' }]);
    expect(aBorrador(SPEC, null)).toEqual([]);
  });

  it('desdeBorrador trims and uppercases the codes', () => {
    expect(desdeBorrador(SPEC, [{ codigo: ' im19 ', modo: 'prefijo' }])).toEqual({
      valor: [{ codigo: 'IM19', modo: 'prefijo' }],
    });
  });

  it('desdeBorrador rejects an empty code', () => {
    expect(desdeBorrador(SPEC, [{ codigo: ' ', modo: 'exacto' }]).error).toMatch(/Fila 1/);
  });

  it('formatearValor writes each code with its mode', () => {
    expect(formatearValor(SPEC, POR_DEFECTO)).toBe('IM19 (empieza por), VS12 (exacto), G01 (exacto)');
    expect(formatearValor(SPEC, [])).toBe('(vacía)');
  });
});

describe('registry and Cargas tab', () => {
  it('registers the key with its editor and validator', () => {
    expect(EDITORES.ventas_tipos_excluidos.Control).toBe(EditorTiposExcluidos);
    expect(EDITORES.ventas_tipos_excluidos.validar([{ codigo: '', modo: 'exacto' }])).toHaveLength(1);
  });

  const datos = (claves) => ({ secciones: [{ seccion: 'cargas', grupos: [{ grupo: 'OPERACION', claves }] }] });
  const DIAS = spec('dias_ventana_ingresos', 'entero', 90);

  it('skips the field when the server does not return the key', () => {
    render(<SeccionPanel seccion={{ id: 'cargas', label: 'Cargas' }} data={datos([DIAS])} recargar={jest.fn()} />);
    expect(screen.getByText('Ventana de ingresos (días)')).toBeInTheDocument();
    expect(screen.queryByText('Tipos de inventario que se descartan')).not.toBeInTheDocument();
  });

  it('shows the field and saves the edited list', async () => {
    const onGuardar = jest.fn(async () => ({}));
    render(
      <SeccionPanel
        seccion={{ id: 'cargas', label: 'Cargas' }} data={datos([DIAS, SPEC])}
        recargar={jest.fn()} onGuardar={onGuardar}
      />,
    );
    const seccion = screen.getByText('Tipos de inventario que se descartan').closest('section');
    expect(within(seccion).getByText(/Valor por defecto: IM19 \(empieza por\)/)).toBeInTheDocument();
    fireEvent.click(within(seccion).getByRole('button', { name: /Agregar código/ }));
    fireEvent.change(within(seccion).getByLabelText('Código 4'), { target: { value: 'obs2' } });
    fireEvent.click(within(seccion).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0].valor).toEqual([...POR_DEFECTO, { codigo: 'OBS2', modo: 'exacto' }]);
  });
});
