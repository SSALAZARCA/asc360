import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { descargarArchivo } from '../lib/motored/descargas';
import InventarioTab from '../components/motored/kpis/inventario/InventarioTab';
import { luzDias } from '../components/motored/kpis/inventario/datos';
import { INVENTARIO, INVENTARIO_VACIO } from './helpers/kpisInventarioFixture';

jest.mock('../lib/motored/descargas', () => ({ descargarArchivo: jest.fn() }));

const FILTROS = { meses: ['2026-09', '2026-07', '2026-08'], sucursales: ['s2', 's1'], hmcl: 'excluir' };
const montar = (data = INVENTARIO, onChange = jest.fn()) => {
  render(<InventarioTab data={data} filtros={FILTROS} onChange={onChange} />);
  return onChange;
};
const seccion = (nombre) => screen.getByRole('region', { name: nombre });
const tarjeta = (rotulo) => screen.getAllByTestId('tarjeta-inv').find((t) => t.firstChild.textContent === rotulo);

beforeEach(() => descargarArchivo.mockReset());

describe('Inventario tab: layout and header', () => {
  it('renders the cards in the design order', () => {
    montar();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Valor del inventario por mes', 'Antigüedad del inventario', 'Inventario por línea', 'Inventario por tienda',
      'Mayor valor sin movimiento', 'Agotadas con demanda',
    ]);
  });

  it('shows the corte chip with the date and the cost months, and no sample-data chip', () => {
    montar();
    expect(screen.getByText('Corte de inventario: 30/09/2026 · costo de ventas jul–sep')).toBeInTheDocument();
    expect(screen.queryByText('Datos de ejemplo')).not.toBeInTheDocument();
  });

  it('shows an empty state when there is no corte', () => {
    montar(INVENTARIO_VACIO);
    expect(screen.getByText('Todavía no hay inventario cargado con costo.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Descargar Excel' })).not.toBeInTheDocument();
  });
});

describe('Inventario tab: KPI cards', () => {
  it('formats values, fractions as percent and the comparison with the previous month', () => {
    montar();
    expect(within(tarjeta('Valor del inventario')).getByText('$ 3.842 M')).toBeInTheDocument();
    expect(within(tarjeta('Valor del inventario')).getByText('▲ 2,1% vs agosto')).toBeInTheDocument();
    expect(within(tarjeta('Días de inventario')).getByText('74 días')).toBeInTheDocument();
    expect(within(tarjeta('Días de inventario')).getByText('Objetivo: 60 días')).toBeInTheDocument();
    expect(within(tarjeta('Rotación')).getByText('4,9 veces')).toBeInTheDocument();
    expect(within(tarjeta('Sin movimiento +180 d')).getByText('$ 412 M')).toBeInTheDocument();
    expect(within(tarjeta('Sin movimiento +180 d')).getByText('10,7% del inventario')).toBeInTheDocument();
    expect(within(tarjeta('Disponibilidad')).getByText('91,4%')).toBeInTheDocument();
    expect(within(tarjeta('Disponibilidad')).getByText('312 referencias agotadas')).toBeInTheDocument();
    expect(within(tarjeta('En tránsito')).getByText('$ 286 M')).toBeInTheDocument();
    expect(within(tarjeta('En tránsito')).getByText('147 facturas sin ingresar')).toBeInTheDocument();
  });

  it('hides the comparison when there is no previous month and shows a dash for null days', () => {
    montar({ ...INVENTARIO, tarjetas: { ...INVENTARIO.tarjetas, valor_mes_anterior: null, dias: null, rotacion: null } });
    expect(screen.queryByText(/vs agosto/)).not.toBeInTheDocument();
    expect(within(tarjeta('Días de inventario')).getByText('—')).toBeInTheDocument();
    expect(within(tarjeta('Rotación')).getByText('—')).toBeInTheDocument();
  });

  it('shows a down arrow when the value fell', () => {
    montar({ ...INVENTARIO, tarjetas: { ...INVENTARIO.tarjetas, valor_mes_anterior: 4100e6 } });
    expect(screen.getByText('▼ 6,3% vs agosto')).toBeInTheDocument();
  });

  it('colors days by the configured cuts', () => {
    const cortes = { verde_hasta: 60, ambar_hasta: 90 };
    expect(luzDias(60, cortes).fg).toContain('--motored-data-good');
    expect(luzDias(61, cortes).fg).toContain('--motored-data-mid');
    expect(luzDias(90, cortes).fg).toContain('--motored-data-mid');
    expect(luzDias(91, cortes).fg).toContain('--motored-data-bad');
    montar();
    expect(within(tarjeta('Días de inventario')).getByText('74 días').style.color).toContain('--motored-data-mid');
  });

  it('explains each card on hover', () => {
    montar();
    expect(tarjeta('Rotación')).toHaveAttribute('title', '365 ÷ días de inventario');
  });
});

describe('Inventario tab: trend, age, lines', () => {
  it('draws a single month with a sensible width and the fill-in note', () => {
    montar();
    const tarjetaMes = seccion('Valor del inventario por mes');
    expect(within(tarjetaMes).getAllByTestId('barra-mes')).toHaveLength(1);
    expect(within(tarjetaMes).getByText('$3,8mm')).toBeInTheDocument();
    expect(within(tarjetaMes).getByText('Sep')).toBeInTheDocument();
    expect(within(tarjetaMes).getByTestId('dias-mes')).toHaveTextContent('74 d');
    expect(within(tarjetaMes).getByRole('img').style.maxWidth).toBe('80px');
    expect(within(tarjetaMes).getByText('La gráfica se va llenando con el cierre de cada mes')).toBeInTheDocument();
    expect(within(tarjetaMes).getByText('61 a 90')).toBeInTheDocument();
  });

  it('has no fill-in note with twelve months', () => {
    const doce = Array.from({ length: 12 }, (_, i) => ({ mes: `2026-${String(i + 1).padStart(2, '0')}`, corte: '2026-01-31', valor: 3e9, dias: 70 }));
    montar({ ...INVENTARIO, tendencia: doce });
    expect(screen.queryByText(/se va llenando/)).not.toBeInTheDocument();
    expect(within(seccion('Valor del inventario por mes')).getAllByTestId('barra-mes')).toHaveLength(12);
  });

  describe('month bars split by days of inventory', () => {
    const BANDAS = [
      { banda: 'verde', valor: 2400 * 1e6, pct: 0.6 }, { banda: 'ambar', valor: 1000 * 1e6, pct: 0.25 },
      { banda: 'violeta', valor: 600 * 1e6, pct: 0.15 },
    ];
    const conBandas = () => ({ ...INVENTARIO, tendencia: [{ ...INVENTARIO.tendencia[0], valor: 4000 * 1e6, bandas: BANDAS }] });

    it('stacks green, amber and violet segments as tall as their share of the bar', () => {
      montar(conBandas());
      const tarjetaMes = seccion('Valor del inventario por mes');
      const segmentos = within(tarjetaMes).getAllByTestId('segmento-banda');
      expect(segmentos.map((x) => x.dataset.banda)).toEqual(['verde', 'ambar', 'violeta']);
      expect(segmentos.map((x) => parseFloat(x.style.height))).toEqual([108, 45, 27]);   // 180 px * 60 / 25 / 15 %
      expect(within(tarjetaMes).getByTestId('barra-apilada').style.height).toBe('180px');
      expect(within(tarjetaMes).getByTestId('barra-apilada').style.flexDirection).toBe('column-reverse');
    });

    it('explains each segment with the configured cuts, its value and its share', () => {
      montar(conBandas());
      const segmentos = within(seccion('Valor del inventario por mes')).getAllByTestId('segmento-banda');
      expect(segmentos[0]).toHaveAttribute('title', '≤60 días: $ 2.400 M · 60%');
      expect(segmentos[1]).toHaveAttribute('title', '61 a 90 días: $ 1.000 M · 25%');
      expect(segmentos[2]).toHaveAttribute('title', '>90 días: $ 600 M · 15%');
    });

    it('follows the cuts configured in Configuración', () => {
      montar({ ...conBandas(), cortes_color: { verde_hasta: 30, ambar_hasta: 45 } });
      const segmentos = within(seccion('Valor del inventario por mes')).getAllByTestId('segmento-banda');
      expect(segmentos.map((x) => x.title.split(':')[0])).toEqual(['≤30 días', '31 a 45 días', '>45 días']);
    });

    it('shows the three shares under the month, above the days chip, and keeps the total on top', () => {
      montar(conBandas());
      const tarjetaMes = seccion('Valor del inventario por mes');
      expect(within(tarjetaMes).getByTestId('pct-bandas')).toHaveTextContent('60%·25%·15%');
      expect(within(tarjetaMes).getByText('$4,0mm')).toBeInTheDocument();
      const pie = within(tarjetaMes).getByTestId('dias-mes').parentElement;
      expect(Array.from(pie.children).map((x) => x.dataset.testid)).toEqual([undefined, 'pct-bandas', 'dias-mes']);
    });

    it('explains in the legend that the colors are the share of inventory by days', () => {
      montar(conBandas());
      expect(within(seccion('Valor del inventario por mes')).getByText(/parte del inventario según sus días/)).toBeInTheDocument();
    });

    it('draws a month without bandas (older payload) as the single bar and no shares', () => {
      montar();
      const tarjetaMes = seccion('Valor del inventario por mes');
      expect(within(tarjetaMes).getAllByTestId('barra-mes')).toHaveLength(1);
      expect(within(tarjetaMes).queryByTestId('segmento-banda')).not.toBeInTheDocument();
      expect(within(tarjetaMes).queryByTestId('pct-bandas')).not.toBeInTheDocument();
    });

    it('draws the single bar when the bands hold no value', () => {
      const vacias = BANDAS.map((b) => ({ ...b, valor: 0, pct: null }));
      montar({ ...INVENTARIO, tendencia: [{ ...INVENTARIO.tendencia[0], bandas: vacias }] });
      expect(within(seccion('Valor del inventario por mes')).queryByTestId('segmento-banda')).not.toBeInTheDocument();
    });
  });

  it('lists the age bands with value and share, and explains the oldest one', () => {
    montar();
    const filas = within(seccion('Antigüedad del inventario')).getAllByTestId('banda-edad');
    expect(filas.map((f) => f.textContent)).toEqual([
      expect.stringContaining('0 a 90 días'), expect.stringContaining('91 a 180 días'),
      expect.stringContaining('181 a 365 días'), expect.stringContaining('Más de 365 días'),
    ]);
    expect(within(filas[0]).getByText('$ 2.614 M')).toBeInTheDocument();
    expect(within(filas[0]).getByText('68,0%')).toBeInTheDocument();
    expect(within(filas[3]).getByRole('note').getAttribute('aria-label')).toContain('enero 2026');
    expect(screen.getByText(/llevan más de 180 días sin venderse/)).toBeInTheDocument();
  });

  it('renders the lines table with chips and dashes for missing days', () => {
    montar();
    const filas = within(seccion('Inventario por línea')).getAllByTestId('fila-linea');
    expect(filas).toHaveLength(3);
    expect(within(filas[0]).getByText('$ 2.391 M')).toBeInTheDocument();
    expect(within(filas[0]).getByText('62,2%')).toBeInTheDocument();
    expect(within(filas[0]).getByText('82 d').style.color).toContain('--motored-data-mid');
    expect(within(filas[1]).getByText('38 d').style.color).toContain('--motored-data-good');
    expect(within(filas[1]).getByText('9,6x')).toBeInTheDocument();
    expect(within(filas[2]).getByText('90,6%')).toBeInTheDocument();
    expect(within(filas[2]).getAllByText('—').length).toBeGreaterThanOrEqual(2);
  });
});

describe('Inventario tab: stores', () => {
  it('shows one row per store with its figures', () => {
    montar();
    const filas = within(seccion('Inventario por tienda')).getAllByTestId('fila-tienda');
    expect(filas).toHaveLength(3);
    expect(within(filas[0]).getByText('118 d')).toBeInTheDocument();
    expect(within(filas[0]).getByText('84,2%')).toBeInTheDocument();
    expect(within(filas[0]).getByText('31')).toBeInTheDocument();
  });

  it('clicking a store narrows the KPI filter to that store', () => {
    const onChange = montar();
    fireEvent.click(screen.getByRole('button', { name: 'Medellín La 33' }));
    expect(onChange).toHaveBeenCalledWith({ sucursales: ['t2'] });
  });
});

describe('Inventario tab: idle references and stockouts', () => {
  it('draws idle bars proportional to value, shaded by days without sale', () => {
    montar();
    const filas = within(seccion('Mayor valor sin movimiento')).getAllByTestId('fila-quieta');
    const barras = within(seccion('Mayor valor sin movimiento')).getAllByTestId('barra-quieta');
    expect(barras[0].style.width).toBe('100%');
    expect(barras[0].style.background).toBe('rgb(91, 30, 147)');
    expect(barras[1].style.background).toBe('rgb(185, 160, 218)');
    expect(barras[2].style.background).toBe('rgb(139, 92, 196)');
    expect(within(filas[0]).getByText('412 d · 42 und')).toBeInTheDocument();
    expect(within(filas[0]).getByText('$ 18,9 M')).toBeInTheDocument();
    expect(screen.getByText('Referencias con más plata quieta (más de 180 días sin venta)')).toBeInTheDocument();
  });

  it('labels stockouts as covered by transit or not ordered, with the demand breakdown', () => {
    montar();
    const filas = within(seccion('Agotadas con demanda')).getAllByTestId('fila-agotada');
    expect(filas).toHaveLength(8);
    expect(within(filas[0]).getByText('86 vendidas + 12 perdidas = 98 und')).toBeInTheDocument();
    expect(within(filas[0]).getByText('60 de 98 und')).toBeInTheDocument();
    expect(within(filas[0]).getByTestId('barra-cubierta').style.width).toBe('61%');
    expect(within(filas[1]).getByText('Sin pedir · 63')).toBeInTheDocument();
    expect(within(filas[1]).getByTestId('barra-cubierta').style.width).toBe('0%');
    expect(screen.getByText('312 agotadas')).toBeInTheDocument();
    expect(screen.getByText('4 en tránsito')).toBeInTheDocument();
    expect(screen.getByText('6 sin pedir')).toBeInTheDocument();
  });

  it('"Ver todas" expands from 8 to every item and collapses back', () => {
    montar();
    const tarjetaAgotadas = seccion('Agotadas con demanda');
    fireEvent.click(within(tarjetaAgotadas).getByRole('button', { name: 'Ver todas (10)' }));
    expect(within(tarjetaAgotadas).getAllByTestId('fila-agotada')).toHaveLength(10);
    fireEvent.click(within(tarjetaAgotadas).getByRole('button', { name: 'Ver menos' }));
    expect(within(tarjetaAgotadas).getAllByTestId('fila-agotada')).toHaveLength(8);
  });
});

describe('Inventario tab: Excel', () => {
  it('downloads the xlsx with the same filters', async () => {
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Descargar Excel' }));
    await waitFor(() => expect(descargarArchivo).toHaveBeenCalledTimes(1));
    const [ruta, nombre] = descargarArchivo.mock.calls[0];
    expect(ruta).toBe('/tablero-asesores/kpis/inventario/excel?meses=2026-07%2C2026-08%2C2026-09&sucursales=s1%2Cs2&hmcl=excluir');
    expect(nombre).toBe('inventario_2026-09-30.xlsx');
  });

  it('shows an error when the download fails', async () => {
    descargarArchivo.mockRejectedValueOnce(new Error('x'));
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Descargar Excel' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos descargar el Excel');
  });
});

describe('Inventario trend without month points', () => {
  it('still renders the tab when there is a corte but no trend point', () => {
    render(<InventarioTab data={{ ...INVENTARIO, tendencia: [] }} filtros={{}} onChange={() => {}} />);
    expect(screen.getByText('Todavía no hay cierres de mes con costo para graficar.')).toBeInTheDocument();
    expect(screen.queryAllByTestId('barra-mes')).toHaveLength(0);
  });
});
