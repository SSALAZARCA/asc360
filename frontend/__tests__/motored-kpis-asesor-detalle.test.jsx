import { render, screen, within } from '@testing-library/react';
import AsesorDetalle from '../components/motored/kpis/asesores/AsesorDetalle';
import {
  comisionDe, comparacionDe, fichaDe, gaugeDe, lineasDe, stripDe, tendenciaDe, tilesDe,
} from '../components/motored/kpis/asesores/detalle';
import { ASESOR_DETALLE } from './helpers/kpisAsesorDetalleFixture';

const clonar = (cambios = {}) => ({ ...ASESOR_DETALLE, ...cambios });
const montar = (data = ASESOR_DETALLE) => render(<AsesorDetalle data={data} />);
const seccion = (nombre) => screen.getByRole('region', { name: nombre });

describe('single-asesor view-model', () => {
  it('ficha: name, role, store, cédula, tier chip and the three puestos', () => {
    const f = fichaDe(ASESOR_DETALLE);
    expect(f.nombre).toBe('Gómez Muñoz Paula');
    expect(f.iniciales).toBe('GM');
    expect(f.partes).toEqual(['Asesor de repuestos', 'Popayán', 'C.C. a8']);
    expect(f.tramo).toEqual(expect.objectContaining({ texto: 'PRO · julio' }));
    expect(f.puestos).toEqual([
      { label: 'Cumplimiento', val: 'Puesto 7 de 43' }, { label: 'Venta may–jul', val: 'Puesto 8 de 45' }, { label: 'Tecnired', val: 'Puesto 5 de 45' },
    ]);
  });

  it('ficha leaves out a puesto she does not have and parts that are missing', () => {
    const sin = fichaDe(clonar({
      asesor: { ...ASESOR_DETALLE.asesor, tienda: null, cargo: null },
      puestos: { ...ASESOR_DETALLE.puestos, cumplimiento: { puesto: null, de: 43 } },
    }));
    expect(sin.puestos.map((p) => p.label)).toEqual(['Venta may–jul', 'Tecnired']);
    expect(sin.partes).toEqual(['C.C. a8']);
  });

  it('tiles: values, change chips and the reference, volume against the asesores and ratios against the network', () => {
    const tiles = tilesDe(ASESOR_DETALLE);
    expect(tiles.map((t) => t.label)).toEqual(['Venta · may–jul', 'Ticket promedio', 'Facturas', 'Clientes únicos', 'Margen', '% Tecnired']);
    expect(tiles[0]).toEqual(expect.objectContaining({ valor: '$421,2 M', ref: 'vs promedio asesores $209,2 M', chip: { text: '▲ 101,0%', variant: 'up' } }));
    expect(tiles[1]).toEqual(expect.objectContaining({ valor: '$76.696', ref: 'vs red $85.615', chip: { text: '▼ 10,4%', variant: 'down' } }));
    expect(tiles[2]).toEqual(expect.objectContaining({ valor: '5.492', ref: 'vs promedio asesores 2.443' }));
    expect(tiles[4]).toEqual(expect.objectContaining({ valor: '28,1%', ref: 'vs red 27,1%', chip: { text: '▲ 1,0 pts', variant: 'up' } }));
    expect(tiles[5].chip).toEqual({ text: '▲ 5,8 pts', variant: 'up' });
  });

  it('tiles: a value without data is a dash with no change chip', () => {
    const tiles = tilesDe(clonar({ tiles: [{ id: 'ticket', valor: null, ref: 85615, ref_de: 'red', dif_tipo: 'pct', dif: null }] }));
    expect(tiles[0]).toEqual(expect.objectContaining({ valor: '—', chip: null, ref: 'vs red $85.615' }));
  });

  it('gauge: the percentage, the figures and the 90 / 105 cuts', () => {
    const g = gaugeDe(ASESOR_DETALLE);
    expect(g.texto).toBe('101,4%');
    expect(g.pie).toBe('$60,8 M de $60,0 M · red 78,0%');
    expect(g.cortes.map((c) => c.label)).toEqual(['90', '105']);
  });

  it('gauge: nothing without a budget for the month', () => {
    expect(gaugeDe(clonar({ cumplimiento_mes: { ...ASESOR_DETALLE.cumplimiento_mes, presupuesto: 0, pct: null, semaforo: null } }))).toBeNull();
  });

  it('comision: amount, tier chip, what is missing for the next tier and the network average', () => {
    const c = comisionDe(ASESOR_DETALLE);
    expect(c.valor).toBe('$910.000');
    expect(c.chip.texto).toBe('PRO 1,5%');
    expect(c.base).toBe('$60,7 M sin HMCL × 1,5%');
    expect(c.siguiente.titulo).toBe('Le faltan $2,2 M para ELITE');
    expect(c.siguiente.meta).toBe('meta ELITE $63,0 M');
    expect(c.nota).toBe('En ELITE (1,8%) ganaría ≈ $1.134.000. Promedio de comisión de la red: $394.000.');
  });

  it('comision: at the top tier there is no next one; without liquidation there is no card', () => {
    const arriba = comisionDe(clonar({ comision: { ...ASESOR_DETALLE.comision, tramo: 'ELITE', sig: null } }));
    expect(arriba.siguiente).toBeNull();
    expect(arriba.nota).toBe('Está en el tramo más alto. Promedio de comisión de la red: $394.000.');
    expect(comisionDe(clonar({ comision: null }))).toBeNull();
  });

  it('tendencia: one point per month, a gap where she has no budget, and how many months she met the goal', () => {
    const t = tendenciaDe(ASESOR_DETALLE);
    expect(t.puntos.map((p) => p.m)).toEqual(['May', 'Jun', 'Jul']);
    expect(t.puntos.map((p) => p.val)).toEqual(['93', null, '101']);
    expect(t.nota).toMatch(/Cumplió \(≥ 90%\) en 2 de 2 meses con presupuesto/);
    expect(t.linea.match(/M/g)).toHaveLength(2); // the null month breaks the line in two segments
  });

  it('lineas: biggest share first, the network tick and the difference in points', () => {
    const l = lineasDe(ASESOR_DETALLE);
    expect(l.filas.map((f) => f.name)).toEqual(['Repuestos', 'Lubricantes', 'Accesorios', 'Llantas']);
    expect(l.filas[0]).toEqual(expect.objectContaining({ pct: '55,0%', diff: '▼ 5,4 pts', variant: 'down', tip: 'Red 60,4%' }));
    expect(l.filas[1]).toEqual(expect.objectContaining({ diff: '▲ 2,7 pts', variant: 'up' }));
    expect(l.nota).toBe('Vende más lubricantes y accesorios que la red; repuestos es su línea con más espacio.');
  });

  it('strip: her position among the others', () => {
    const s = stripDe(ASESOR_DETALLE);
    expect(s.otros).toHaveLength(7);
    expect(s.yo.label).toBe('101,4%');
    expect(s.texto).toBe('Está por encima de 5 compañeros; 2 asesores superan su cumplimiento.');
    expect(s.total).toBe(8);
  });

  it('comparacion: her figures, her store average and the network average', () => {
    const c = comparacionDe(ASESOR_DETALLE);
    expect(c.sub).toBe('Popayán tiene 2 asesores · julio, salvo margen y ticket (may–jul)');
    expect(c.filas.map((f) => f.label)).toEqual(['Venta julio', 'Cumplimiento julio', 'Ticket promedio', 'Margen', '% Tecnired']);
    expect(c.filas[0]).toEqual(expect.objectContaining({ yo: '$60,8 M', tienda: '$52,4 M', red: '$35,6 M' }));
    expect(c.filas[1]).toEqual(expect.objectContaining({ yo: '101,4%', tienda: '94,0%', red: '78,0%' }));
  });
});

describe('single-asesor view', () => {
  it('renders every section of the proposal', () => {
    montar();
    expect(seccion('Ficha del asesor')).toBeInTheDocument();
    const ficha = within(seccion('Ficha del asesor'));
    expect(ficha.getByRole('heading', { name: 'Gómez Muñoz Paula' })).toBeInTheDocument();
    expect(ficha.getByText('PRO · julio')).toBeInTheDocument();
    expect(ficha.getByText(/Asesor de repuestos · Popayán · C\.C\. a8/)).toBeInTheDocument();
    expect(ficha.getByText('Puesto 7 de 43')).toBeInTheDocument();
    expect(within(seccion('Cumplimiento de su meta')).getByText('101,4%')).toBeInTheDocument();
    expect(within(seccion('Cumplimiento de su meta')).getByText('$60,8 M de $60,0 M · red 78,0%')).toBeInTheDocument();
    const comision = within(seccion('Comisión estimada'));
    expect(comision.getByText('$910.000')).toBeInTheDocument();
    expect(comision.getByText('Le faltan $2,2 M para ELITE')).toBeInTheDocument();
    expect(within(seccion('Indicadores del asesor')).getAllByText(/^vs /)).toHaveLength(6);
    expect(within(seccion('Tendencia de cumplimiento')).getByRole('img')).toBeInTheDocument();
    expect(within(seccion('Venta por línea vs la red')).getByText('Repuestos')).toBeInTheDocument();
    expect(within(seccion('Dónde está frente a sus compañeros')).getByText('Este asesor · 101,4%')).toBeInTheDocument();
    expect(within(seccion('Comparación con su tienda')).getByRole('table')).toBeInTheDocument();
    const tec = within(seccion('Clientes Tecnired atendidos'));
    expect(tec.getByText('Taller Uno SAS')).toBeInTheDocument();
    expect(tec.getByText('900123456')).toBeInTheDocument();
    expect(tec.getByText('14')).toBeInTheDocument();
  });

  it('compares her against her store in a table with her name in the header', () => {
    montar();
    const tabla = within(seccion('Comparación con su tienda')).getByRole('table');
    expect(within(tabla).getAllByRole('row')).toHaveLength(6);
    expect(within(tabla).getByRole('columnheader', { name: 'Prom. su tienda' })).toBeInTheDocument();
    expect(within(tabla).getByRole('columnheader', { name: 'Prom. red' })).toBeInTheDocument();
  });

  it('shows tooltips on the figures whose name is not obvious', () => {
    montar();
    expect(within(seccion('Indicadores del asesor')).getAllByRole('note').length).toBeGreaterThanOrEqual(4);
  });

  it('never shows a placeholder or a field without a data source', () => {
    const { container } = montar();
    expect(container.textContent).not.toMatch(/\[|\]|Ingresó|antigüedad|pendiente|undefined|NaN|null/i);
  });

  it('leaves out the Clientes únicos tile when the payload does not carry it', () => {
    montar(clonar({ tiles: ASESOR_DETALLE.tiles.filter((t) => t.id !== 'clientes_unicos') }));
    const tiles = seccion('Indicadores del asesor');
    expect(within(tiles).queryByText(/Clientes únicos/)).not.toBeInTheDocument();
    expect(within(tiles).getAllByText(/^vs /)).toHaveLength(5);
  });

  it('has no commission card for an asesor that is not liquidated, and no gauge without a budget', () => {
    montar(clonar({
      comision: null, cumplimiento_mes: { ...ASESOR_DETALLE.cumplimiento_mes, presupuesto: 0, pct: null, semaforo: null },
    }));
    expect(screen.queryByRole('region', { name: 'Comisión estimada' })).not.toBeInTheDocument();
    expect(within(seccion('Cumplimiento de su meta')).getByText(/Sin presupuesto cargado para julio/)).toBeInTheDocument();
  });

  it('has no Tecnired top when she sold nothing to Tecnired', () => {
    montar(clonar({ tecnired: { ...ASESOR_DETALLE.tecnired, venta: 0, clientes: 0, top: [] } }));
    expect(within(seccion('Clientes Tecnired atendidos')).getByText(/no le vendió a clientes Tecnired/i)).toBeInTheDocument();
  });
});
