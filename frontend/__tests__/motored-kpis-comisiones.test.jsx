import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { descargarArchivo } from '../lib/motored/descargas';
import ComisionesTab from '../components/motored/kpis/comisiones/ComisionesTab';
import { escalaTramos, colorDeTramo } from '../components/motored/kpis/comisiones/datos';
import { COMISIONES, COMISIONES_SIN_PRESUPUESTO } from './helpers/kpisComisionesFixture';

jest.mock('../lib/motored/descargas', () => ({ descargarArchivo: jest.fn() }));

const FILTROS = { meses: ['2026-07', '2026-05', '2026-06'], sucursales: ['s2', 's1'], hmcl: 'excluir' };
const montar = (data = COMISIONES) => render(<ComisionesTab data={data} filtros={FILTROS} />);
const seccion = (nombre) => screen.getByRole('region', { name: nombre });

describe('Comisiones tab: layout', () => {
  it('shows the liquidated month chip with its tooltip', () => {
    montar();
    const chip = screen.getByText('Mes liquidado: julio 2026');
    expect(chip.closest('[data-testid="chip-mes"]')).toBeInTheDocument();
    expect(screen.getByRole('note', { name: 'Las comisiones se calculan sobre el último mes del período elegido.' })).toBeInTheDocument();
  });

  it('renders every card in the design order', () => {
    montar();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Comisiones · julio',
      'Cómo se calcula la comisión',
      'Dónde cae cada asesor · julio',
      'Comisión por asesor · julio',
      'Cerca de subir de tramo',
      'Bonos por línea · julio',
    ]);
  });

  it('KPI card: the total to pay (commission + bonuses) and the figures', () => {
    montar();
    const tarjeta = seccion('Comisiones del mes');
    expect(within(tarjeta).getByText('Total a pagar')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$5,8 M')).toBeInTheDocument();
    expect(within(tarjeta).getByText('comisión del mes')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$5.700.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('bonos por línea')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$95.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('4')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$1.425.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$2.700.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('1,4%')).toBeInTheDocument();
    expect(within(tarjeta).getByText('de la venta sin HMCL')).toBeInTheDocument();
    expect(within(tarjeta).getAllByRole('note').length).toBeGreaterThanOrEqual(3);
  });

  it('KPI card without bonus lines configured still shows the total to pay and no bonus figure', () => {
    const sinBonos = { ...COMISIONES, reglas: { ...COMISIONES.reglas, comision_lineas: [] }, resumen: { ...COMISIONES.resumen, bonos_total: 0, total_a_pagar: 5.7e6, por_linea: [] } };
    montar(sinBonos);
    const tarjeta = seccion('Comisiones del mes');
    expect(within(tarjeta).getByText('$5,7 M')).toBeInTheDocument();
    expect(within(tarjeta).queryByText('bonos por línea')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Bonos por línea' })).not.toBeInTheDocument();
  });
});

describe('Comisiones tab: how it is calculated', () => {
  it('walks the four steps with the top earner as the example', () => {
    montar();
    const tarjeta = seccion('Cómo se calcula la comisión');
    expect(within(tarjeta).getByText(/Su presupuesto cargado del mes/)).toBeInTheDocument();
    expect(within(tarjeta).queryByText(/Presupuesto de la tienda/)).not.toBeInTheDocument();
    expect(within(tarjeta).getByText('Presupuesto cargado: $200 M')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Venta con HMCL ÷ meta')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$190 M ÷ $200 M = 95,0%')).toBeInTheDocument();
    expect(within(tarjeta).getByText('BASE hasta 90% · PRO 90–105% · ELITE desde 105%')).toBeInTheDocument();
    expect(within(tarjeta).getByText('PRO → 1,5%')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Venta sin HMCL × % del tramo')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$180 M × 1,5% = $2.700.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Bonos por línea')).toBeInTheDocument();
    expect(within(tarjeta).getByText(/Con un cumplimiento de al menos 95%.*cada línea/)).toBeInTheDocument();
    expect(within(tarjeta).getByText('Bonos ganados: $65.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Ejemplo: Jiménez Rangel Yulisa · Bogotá 1 de Mayo · julio')).toBeInTheDocument();
  });

  it('names the bases from the rules in force', () => {
    montar({ ...COMISIONES, reglas: { ...COMISIONES.reglas, cumplimiento_base: 'sin_hmcl', comision_base_pago: 'con_hmcl' } });
    const tarjeta = seccion('Cómo se calcula la comisión');
    expect(within(tarjeta).getByText('Venta sin HMCL ÷ meta')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Venta con HMCL × % del tramo')).toBeInTheDocument();
  });
});

describe('Comisiones tab: bonus step', () => {
  it('says why the example asesor earns no bonus when she is below the gate', () => {
    const debajo = { ...COMISIONES, asesores: [COMISIONES.asesores[2], ...COMISIONES.asesores] };
    montar(debajo);
    expect(within(seccion('Cómo se calcula la comisión')).getByText('85,0% de cumplimiento: sin bonos')).toBeInTheDocument();
  });

  it('has no fifth step when there are no bonus lines', () => {
    montar({ ...COMISIONES, reglas: { ...COMISIONES.reglas, comision_lineas: [] } });
    expect(within(seccion('Cómo se calcula la comisión')).queryByText('Bonos por línea')).not.toBeInTheDocument();
  });
});

describe('Comisiones tab: where each asesor falls', () => {
  it('draws a dot per asesor, the tiers legend from the configured tiers and the non-linear axis', () => {
    montar();
    const tarjeta = seccion('Dónde cae cada asesor');
    expect(within(tarjeta).getByText(/ELITE/)).toHaveTextContent('ELITE desde 105% · 1,8% · 1');
    expect(within(tarjeta).getByText(/PRO/)).toHaveTextContent('PRO 90–105% · 1,5% · 1');
    expect(within(tarjeta).getByText(/BASE/)).toHaveTextContent('BASE hasta 90% · 1% · 2');
    expect(tarjeta.querySelectorAll('[data-level]')).toHaveLength(4);
    expect(tarjeta.querySelector('[title="Jiménez Rangel Yulisa · 95,0%"]')).toHaveStyle({ left: '63.33%' });
    expect(within(tarjeta).getByText('90%')).toBeInTheDocument();
    expect(within(tarjeta).getByText('105%')).toBeInTheDocument();
    expect(within(tarjeta).getByText('150%+')).toBeInTheDocument();
  });

  it('colors the legend and dots by tier', () => {
    expect(colorDeTramo('ELITE', 2, 3)).toBe('#0F766E');
    expect(colorDeTramo('PRO', 1, 3)).toBe('#1D4E89');
    expect(colorDeTramo('BASE', 0, 3)).toBe('#A3A39E');
  });

  it('scale: 0-90 takes 60% of the width, 90-105 takes 10% and 105-150+ takes 30%', () => {
    const { posicion, zonas } = escalaTramos(COMISIONES.tramos);
    expect([0, 45, 90, 97.5, 105, 127.5, 150, 400].map(posicion)).toEqual([0, 30, 60, 65, 70, 85, 100, 100]);
    expect(zonas.map((z) => z.hasta)).toEqual([60, 70, 100]);
  });

  it('scale: adapts to other tiers', () => {
    const { posicion } = escalaTramos([{ nombre: 'A', desde_pct: 0 }, { nombre: 'B', desde_pct: 100 }]);
    expect([50, 100, 175].map(posicion)).toEqual([30, 60, 100]);
  });
});

describe('Comisiones tab: commission by asesor', () => {
  it('ranks the asesores by commission with their tier', () => {
    montar();
    const tarjeta = seccion('Comisión por asesor');
    const nombres = within(tarjeta).getAllByTestId('fila-comision').map((f) => within(f).getByText(/Zapata|Rangel|Romero|Flórez/).textContent);
    expect(nombres).toEqual(['Jiménez Rangel Yulisa', 'Rojas Zapata Alejandra', 'Salgado Romero Andrea', 'Cuenca Flórez Angie']);
    expect(within(tarjeta).getByText('$2.765.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Bogotá 1 de Mayo · cumple 95,0%')).toBeInTheDocument();
    expect(within(tarjeta).getAllByText('BASE')).toHaveLength(2);
  });

  it('draws the thin amber bonus bar only when a bonus was earned, listing the earned lines', () => {
    montar();
    const filas = within(seccion('Comisión por asesor')).getAllByTestId('fila-comision');
    const barra = (fila) => within(fila).queryByTestId('barra-bono');
    expect(barra(filas[0])).toHaveTextContent('+ $65.000 bonos (Lubricantes, Cascos)');
    expect(barra(filas[0]).querySelector('[data-testid="barra-bono-relleno"]')).toHaveStyle({ background: '#B45309' });
    expect(barra(filas[1])).toHaveTextContent('+ $30.000 bonos (Cascos)');
    expect(barra(filas[2])).toBeNull();
    expect(barra(filas[3])).toBeNull();
  });

  it('shows the commission bar and the total payout on the right', () => {
    montar();
    const filas = within(seccion('Comisión por asesor')).getAllByTestId('fila-comision');
    expect(within(filas[0]).getByTestId('barra-comision')).toHaveTextContent('$2.700.000');
    expect(within(filas[0]).getByTestId('total-fila')).toHaveTextContent('$2.765.000');
    expect(within(filas[3]).getByTestId('total-fila')).toHaveTextContent('$400.000');
  });

  it('shows the grey note below the 95% gate and nowhere else', () => {
    montar();
    const filas = within(seccion('Comisión por asesor')).getAllByTestId('fila-comision');
    expect(within(filas[0]).queryByText('No alcanza el 95% para bonos')).toBeNull();
    expect(within(filas[2]).getByText('No alcanza el 95% para bonos')).toBeInTheDocument();
    expect(within(filas[3]).getByText('No alcanza el 95% para bonos')).toBeInTheDocument();
  });

  it('does not show unmet or off lines in the collapsed row', () => {
    montar();
    const tarjeta = seccion('Comisión por asesor');
    expect(within(tarjeta).queryAllByTestId('chip-bono')).toHaveLength(0);
    expect(within(tarjeta).queryByText(/le faltan/)).toBeNull();
    expect(within(tarjeta).queryByText(/apagado/i)).toBeNull();
  });

  it('expands the asesor with a real button: met lines with amount, unmet with what is missing, off lines', () => {
    montar();
    const fila = within(seccion('Comisión por asesor')).getAllByTestId('fila-comision')[1];
    const boton = within(fila).getByRole('button', { name: /Rojas Zapata/ });
    expect(boton).toHaveAttribute('aria-expanded', 'false');
    expect(within(fila).queryByTestId('detalle-bonos')).toBeNull();
    fireEvent.click(boton);
    expect(boton).toHaveAttribute('aria-expanded', 'true');
    const detalle = within(fila).getByTestId('detalle-bonos');
    const items = within(detalle).getAllByRole('listitem').map((li) => li.textContent);
    expect(items[0]).toContain('Lubricantes');
    expect(items[0]).toMatch(/le faltan \$150\.000/);
    expect(items[1]).toContain('✓');
    expect(items[1]).toContain('Cascos');
    expect(items[1]).toContain('$30.000');
    expect(items[2]).toContain('Tecnired (clientes)');
    expect(items[2]).toContain('apagado');
    fireEvent.click(boton);
    expect(within(fila).queryByTestId('detalle-bonos')).toBeNull();
  });

  it('a line met below the gate says it is not paid', () => {
    montar();
    const fila = within(seccion('Comisión por asesor')).getAllByTestId('fila-comision')[2];
    fireEvent.click(within(fila).getByRole('button', { name: /Salgado Romero/ }));
    expect(within(within(fila).getByTestId('detalle-bonos')).getByText(/Lubricantes/).closest('li')).toHaveTextContent('no llega al 95%');
  });

  it('the semaforo view keeps working', () => {
    montar();
    fireEvent.click(within(seccion('Comisión por asesor')).getByRole('button', { name: 'Cumplimiento' }));
    expect(within(seccion('Comisión por asesor')).queryAllByTestId('chip-bono')).toHaveLength(0);
  });

  it('toggles to the cumplimiento semaforo', () => {
    montar();
    const tarjeta = seccion('Comisión por asesor');
    expect(within(tarjeta).getByRole('button', { name: 'Comisión' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(tarjeta).queryAllByTestId('traffic-cell')).toHaveLength(0);
    fireEvent.click(within(tarjeta).getByRole('button', { name: 'Cumplimiento' }));
    const celdas = within(tarjeta).getAllByTestId('traffic-cell');
    expect(celdas.map((c) => c.getAttribute('data-tone'))).toEqual(['good', 'good', 'mid', 'bad']);
    expect(within(celdas[0]).getByText('120,0%')).toBeInTheDocument();
    expect(within(tarjeta).queryAllByTestId('fila-comision')).toHaveLength(0);
  });
});

describe('Comisiones tab: close to the next tier', () => {
  it('lists the asesores near the next tier, smallest gap first, with what they need and gain', () => {
    montar();
    const tarjeta = seccion('Cerca de subir de tramo');
    const filas = within(tarjeta).getAllByTestId('fila-cerca');
    expect(filas).toHaveLength(2);
    expect(within(filas[0]).getByText('Salgado Romero Andrea')).toBeInTheDocument();
    expect(within(filas[0]).getByText('+$475.000')).toBeInTheDocument();
    expect(filas[0]).toHaveTextContent('85,0% → 90% · le faltan $5,0 M para PRO');
    expect(within(filas[1]).getByText('Jiménez Rangel Yulisa')).toBeInTheDocument();
    expect(filas[1]).toHaveTextContent('95,0% → 105% · le faltan $20,0 M para ELITE');
  });

  it('says so when nobody is close', () => {
    montar({ ...COMISIONES, cerca_de_subir: [] });
    expect(within(seccion('Cerca de subir de tramo')).getByText('Nadie está cerca de subir de tramo este mes.')).toBeInTheDocument();
  });
});

describe('Comisiones tab: bonuses by line', () => {
  it('shows the header chips and one mosaic tile per configured line', () => {
    montar();
    const tarjeta = seccion('Bonos por línea');
    expect(within(tarjeta).getByTestId('chip-pagado')).toHaveTextContent(/Pagado en bonos\s*\$95\.000/);
    expect(within(tarjeta).getByTestId('chip-ganados')).toHaveTextContent('3 bonos ganados');
    const tiles = within(tarjeta).getAllByTestId('tile-bono');
    expect(tiles).toHaveLength(3);
    expect(tiles[0]).toHaveTextContent('Lubricantes');
    expect(tiles[0]).toHaveTextContent('≥21% · $35.000 c/u');
    expect(tiles[0]).toHaveTextContent('$35.000');
    expect(tiles[0]).toHaveTextContent('1 asesor');
    expect(tiles[1]).toHaveTextContent('$60.000');
    expect(tiles[1]).toHaveTextContent('2 asesores');
  });

  it('draws one dot per winner and the share of the total paid', () => {
    montar();
    const tiles = within(seccion('Bonos por línea')).getAllByTestId('tile-bono');
    expect(within(tiles[0]).getAllByTestId('punto-ganador')).toHaveLength(1);
    expect(within(tiles[1]).getAllByTestId('punto-ganador')).toHaveLength(2);
    expect(tiles[0]).toHaveTextContent('37% del total pagado');
    expect(tiles[1]).toHaveTextContent('63% del total pagado');
    expect(within(tiles[1]).getByTestId('barra-parte')).toHaveStyle({ width: '63.2%' });
  });

  it('caps the dots at 12 and shows +N', () => {
    const muchos = { ...COMISIONES, resumen: { ...COMISIONES.resumen, por_linea: [{ linea: 'LUBRICANTES', etiqueta: 'Lubricantes', ganadores: 15, monto: 525000 }, ...COMISIONES.resumen.por_linea.slice(1)] } };
    montar(muchos);
    const tile = within(seccion('Bonos por línea')).getAllByTestId('tile-bono')[0];
    expect(within(tile).getAllByTestId('punto-ganador')).toHaveLength(12);
    expect(tile).toHaveTextContent('+3');
  });

  it('mutes an off line: Apagado chip, nothing paid and how many would have won it', () => {
    montar();
    const tile = within(seccion('Bonos por línea')).getAllByTestId('tile-bono')[2];
    expect(tile).toHaveAttribute('data-activo', 'false');
    expect(tile).toHaveTextContent('Apagado');
    expect(tile).toHaveTextContent('$0');
    expect(tile).toHaveTextContent('lo habrían ganado 1');
    expect(within(tile).getAllByTestId('punto-ganador')[0]).toHaveStyle({ background: 'transparent' });
  });
});

describe('Comisiones tab: empty state', () => {
  it('asks for the budgets of the month and shows nothing to compute', () => {
    montar(COMISIONES_SIN_PRESUPUESTO);
    expect(screen.getByText('Mes liquidado: julio 2026')).toBeInTheDocument();
    expect(screen.getByText('Cargá los presupuestos de julio de 2026 para calcular comisiones.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument();
  });
});


describe('Comisiones tab: Excel download', () => {
  beforeEach(() => descargarArchivo.mockReset());

  it('has the button in the header of the commission card, next to the toggle', () => {
    montar();
    const tarjeta = seccion('Comisión por asesor');
    expect(within(tarjeta).getByRole('button', { name: 'Descargar Excel' })).toBeInTheDocument();
    expect(within(tarjeta).getByRole('button', { name: 'Comisión' })).toBeInTheDocument();
  });

  it('downloads the month with the active filters and the month in the file name', async () => {
    descargarArchivo.mockResolvedValue({ nombre: 'x.xlsx' });
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Descargar Excel' }));
    await waitFor(() => expect(descargarArchivo).toHaveBeenCalledTimes(1));
    const [ruta, nombre] = descargarArchivo.mock.calls[0];
    expect(ruta).toBe('/tablero-asesores/kpis/comisiones/excel?meses=2026-05%2C2026-06%2C2026-07&sucursales=s1%2Cs2&hmcl=excluir');
    expect(nombre).toBe('comisiones_2026-07.xlsx');
    expect(await screen.findByRole('button', { name: 'Descargar Excel' })).toBeEnabled();
  });

  it('is busy while it downloads', async () => {
    let terminar;
    descargarArchivo.mockReturnValue(new Promise((resolve) => { terminar = resolve; }));
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Descargar Excel' }));
    const ocupado = await screen.findByRole('button', { name: 'Descargando…' });
    expect(ocupado).toBeDisabled();
    await act(async () => terminar({ nombre: 'x.xlsx' }));
    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeEnabled();
  });

  it('shows the error in Spanish when the download fails', async () => {
    descargarArchivo.mockRejectedValue(new Error('HTTP 500'));
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Descargar Excel' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos descargar el Excel. Intentá de nuevo.');
    expect(screen.getByRole('button', { name: 'Descargar Excel' })).toBeEnabled();
  });
});
