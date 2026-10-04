import { fireEvent, render, screen, within } from '@testing-library/react';
import AsesoresTab from '../components/motored/kpis/asesores/AsesoresTab';
import { tecniredAsesores } from '../components/motored/kpis/asesores/datos';
import { ASESORES, ASESORES_SIN_PRESUPUESTO } from './helpers/kpisAsesoresFixture';

const montar = (data = ASESORES) => render(<AsesoresTab data={data} />);
const seccion = (nombre) => screen.getByRole('region', { name: nombre });

describe('Asesores tab: layout', () => {
  it('renders every card in the design order', () => {
    montar();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Asesores que cumplen · may–jul',
      'Dónde cae cada asesor · cumplimiento may–jul',
      'Asesores destacados y a apoyar',
      'Tecnired por asesor · may–jul',
      'Venta por grupo de vendedores',
    ]);
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      'Top 10 · venta may–jul', 'Bottom 10 · cumplimiento may–jul',
    ]);
  });

  it('donut: asesores that meet the goal against the rest, with the "N / M" centre', () => {
    montar();
    const tarjeta = seccion('Asesores que cumplen');
    expect(within(tarjeta).getByRole('img')).toHaveAttribute('aria-label', expect.stringContaining('Cumplen (≥ 90%) 5'));
    expect(within(tarjeta).getByText('5 / 11')).toBeInTheDocument();
    expect(within(tarjeta).getByText('asesores')).toBeInTheDocument();
    expect(within(tarjeta).getByText('No cumplen')).toBeInTheDocument();
    expect(within(tarjeta).getByText('45,5%')).toBeInTheDocument();
  });

  it('shows the six figures', () => {
    montar();
    const mini = seccion('Indicadores de los asesores');
    expect(within(mini).getByText('12')).toBeInTheDocument();
    expect(within(mini).getByText('$700 M')).toBeInTheDocument();
    expect(within(mini).getByText('Jiménez Rangel Yulisa')).toBeInTheDocument();
    expect(within(mini).getByText('36,5%')).toBeInTheDocument();
    expect(within(mini).getByText('▲ vs 27,1% red')).toHaveAttribute('data-variant', 'up');
    expect(within(mini).getByText('$120.000')).toBeInTheDocument();
    expect(within(mini).getByText('▲ 1,4× la red')).toBeInTheDocument();
    expect(within(mini).getByText('2,66 ítems')).toBeInTheDocument();
    expect(within(mini).getAllByText('$85.615')).toHaveLength(1);
    expect(within(mini).getAllByRole('note').length).toBeGreaterThanOrEqual(3);
  });
});

describe('Asesores tab: zone strip', () => {
  it('has a dot per asesor with budget, the semaforo legend counts and the cédula warning', () => {
    montar();
    const tarjeta = seccion('Dónde cae cada asesor');
    expect(within(tarjeta).getByText(/≥ 90%/)).toHaveTextContent('≥ 90% · 5');
    expect(within(tarjeta).getByText(/70–90%/)).toHaveTextContent('70–90% · 2');
    expect(within(tarjeta).getByText(/< 70%/)).toHaveTextContent('< 70% · 4');
    expect(tarjeta.querySelectorAll('[data-level]')).toHaveLength(11);
    expect(tarjeta.querySelector('[title="Jiménez Rangel Yulisa · 116,7%"]')).toBeInTheDocument();
    expect(within(tarjeta).getByText(/2 asesores sin cédula/)).toBeInTheDocument();
  });

  it('shows the budgets link when nobody has a budget', () => {
    montar(ASESORES_SIN_PRESUPUESTO);
    expect(within(seccion('Dónde cae cada asesor')).getByRole('link', { name: /Cargá los presupuestos/ })).toBeInTheDocument();
  });
});

describe('Asesores tab: top and bottom 10', () => {
  it('Top 10 · venta: the ten best sellers with value, store, ticket and margin chip vs the network', () => {
    montar();
    const top = screen.getByRole('region', { name: 'Top 10 · venta' });
    expect(within(top).getAllByTestId('rank-badge')).toHaveLength(10);
    expect(within(top).getByText('Jiménez Rangel Yulisa')).toBeInTheDocument();
    expect(within(top).queryByText('Zambrano Garcés Alam')).not.toBeInTheDocument();
    expect(within(top).getByText('$700 M')).toBeInTheDocument();
    expect(within(top).getByText('Bogotá 1 de Mayo · ticket $120.000')).toBeInTheDocument();
    expect(within(top).getByText('Margen 22,8%')).toHaveAttribute('data-variant', 'down');
    expect(within(top).getByText('Margen 29,8%')).toHaveAttribute('data-variant', 'up');
    expect(within(top).getByText('▲ mayor venta')).toBeInTheDocument();
  });

  it('Bottom 10 · cumplimiento: lowest compliance first, "venta / presupuesto" inside the bar, no asesores without budget', () => {
    montar();
    const bottom = screen.getByRole('region', { name: 'Bottom 10 · cumplimiento' });
    const nombres = within(bottom).getAllByTestId('rank-badge');
    expect(nombres).toHaveLength(10);
    expect(within(bottom).getByText('$60 M / $300 M')).toBeInTheDocument();
    expect(within(bottom).getByText('Bucaramanga · cumple 20,0% · ticket $60.000')).toBeInTheDocument();
    expect(within(bottom).queryByText('Moreno Sánchez Viviana')).not.toBeInTheDocument();
    expect(within(bottom).queryByText('Jiménez Rangel Yulisa')).not.toBeInTheDocument();
    expect(within(bottom).getByText('▼ menor cumplimiento')).toBeInTheDocument();
    expect(within(bottom).getByText(/1 asesor sin presupuesto/)).toBeInTheDocument();
  });

  it('Mezcla: both columns turn into line-share matrices', () => {
    montar();
    const tarjeta = seccion('Asesores destacados y a apoyar');
    fireEvent.click(within(tarjeta).getByRole('button', { name: 'Mezcla' }));
    const top = screen.getByRole('region', { name: 'Top 10 · venta' });
    expect(within(top).queryAllByTestId('rank-badge')).toHaveLength(0);
    expect(within(top).getAllByTestId('mezcla-fila')).toHaveLength(10);
    ['Repuestos', 'Lubric.', 'Acces.', 'Llantas'].forEach((c) => expect(within(top).getByText(c)).toBeInTheDocument());
    const primera = within(top).getAllByTestId('mezcla-fila')[0];
    expect(within(primera).getAllByTestId('mezcla-celda').map((c) => c.textContent)).toEqual(['70,0%', '20,0%', '7,0%', '3,0%']);
    expect(within(screen.getByRole('region', { name: 'Bottom 10 · cumplimiento' })).getAllByTestId('mezcla-fila')).toHaveLength(10);
  });
});

describe('Asesores tab: Tecnired and groups', () => {
  it('Tecnired: chips, treemap and the percentage bars with the network average', () => {
    montar();
    const tarjeta = seccion('Tecnired por asesor');
    expect(within(tarjeta).getByText('$261 M')).toBeInTheDocument();
    expect(within(tarjeta).getByText('asesores le venden').previousSibling).toHaveTextContent('10');
    expect(within(tarjeta).getByText('con más de 15%').previousSibling).toHaveTextContent('1');
    expect(within(tarjeta).getAllByTestId('treemap-tile')).toHaveLength(10);
    const filas = within(tarjeta).getAllByTestId('tecnired-fila');
    expect(within(filas[0]).getByText('Cuenca Flórez Angie')).toBeInTheDocument();
    expect(within(filas[0]).getByText('18,0%')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Promedio de la red 6,3%')).toBeInTheDocument();
    expect(within(tarjeta).getAllByTestId('tecnired-promedio')).toHaveLength(12);
  });

  it('treemap keeps the top 11 and groups the rest in "Otros N asesores"', () => {
    const clon = (i) => ({ ...ASESORES.filas[0], clave: `P:x${i}`, nombre: `Extra ${i}`, clientes: { ...ASESORES.filas[0].clientes, venta_tecnired: (i + 1) * 1e5, pct_tecnired: 0.01 } });
    const filas = [...ASESORES.filas, ...[0, 1, 2, 3].map(clon)];
    const { tiles } = tecniredAsesores({ ...ASESORES, filas });
    expect(tiles).toHaveLength(12);
    expect(tiles[11].label).toBe('Otros 3 asesores');
  });

  it('groups: a 100% bar and a legend with the value of PERSONA, COMERCIALES, OTROS and RESTO', () => {
    montar();
    const tarjeta = seccion('Venta por grupo de vendedores');
    expect(within(tarjeta).getAllByTestId('segment')).toHaveLength(4);
    const leyenda = within(tarjeta).getAllByTestId('grupo-leyenda').map((l) => l.textContent);
    expect(leyenda).toEqual([
      'Asesores de repuestos$4.010 M · 80,8%', 'Comerciales$100 M · 2,0%', 'Otros roles de posventa$50 M · 1,0%', 'Resto de compañía$800 M · 16,1%',
    ]);
  });
});
