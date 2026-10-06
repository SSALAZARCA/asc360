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
    ]);
  });

  it('KPI card: total and the four figures', () => {
    montar();
    const tarjeta = seccion('Comisiones del mes');
    expect(within(tarjeta).getByText('$5,7 M')).toBeInTheDocument();
    expect(within(tarjeta).getByText('4')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$1.425.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$2.700.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('1,4%')).toBeInTheDocument();
    expect(within(tarjeta).getByText('de la venta sin HMCL')).toBeInTheDocument();
    expect(within(tarjeta).getAllByRole('note').length).toBeGreaterThanOrEqual(3);
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
    expect(within(tarjeta).getByText('Ejemplo: Jiménez Rangel Yulisa · Bogotá 1 de Mayo · julio')).toBeInTheDocument();
  });

  it('names the bases from the rules in force', () => {
    montar({ ...COMISIONES, reglas: { ...COMISIONES.reglas, cumplimiento_base: 'sin_hmcl', comision_base_pago: 'con_hmcl' } });
    const tarjeta = seccion('Cómo se calcula la comisión');
    expect(within(tarjeta).getByText('Venta sin HMCL ÷ meta')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Venta con HMCL × % del tramo')).toBeInTheDocument();
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
    expect(within(tarjeta).getByText('$2.700.000')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Bogotá 1 de Mayo · cumple 95,0%')).toBeInTheDocument();
    expect(within(tarjeta).getAllByText('BASE')).toHaveLength(2);
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
