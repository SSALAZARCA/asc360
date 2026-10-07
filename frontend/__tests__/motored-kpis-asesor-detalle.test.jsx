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
    expect(c.valor).toBe('$940.000');
    expect(c.desglose).toBe('Comisión $910.000 + bonos $30.000 = $940.000');
    expect(c.chip.texto).toBe('PRO 1,5%');
    expect(c.base).toBe('$60,7 M sin HMCL × 1,5%');
    expect(c.siguiente.titulo).toBe('Le faltan $2,2 M para ELITE');
    expect(c.siguiente.meta).toBe('meta ELITE $63,0 M');
    expect(c.nota).toBe('En ELITE (1,8%) ganaría ≈ $1.134.000. Promedio de comisión de la red: $394.000.');
  });

  it('comision: per-line bonus status, with what is missing for each unmet active line', () => {
    const { bonos } = comisionDe(ASESOR_DETALLE);
    expect(bonos.aviso).toBeNull();
    expect(bonos.lineas.map((l) => [l.texto, l.estado])).toEqual([
      ['Lubricantes · le faltan $3,4 M', 'no-cumple'],
      ['Cascos · +$30.000', 'cumple'],
      ['Tecnired (clientes) · apagado', 'apagado'],
    ]);
    expect(bonos.lineas[0].tip).toBe('Venta mínima de la línea según su presupuesto (presupuesto × 95% × meta). El bono se gana si la línea llega a la meta % de su venta real.');
    expect(bonos.lineas[2].tip).toBe('Bono apagado en Configuración');
  });

  it('comision: the missing sale under 1 M is written in whole pesos, and it shows below the gate too', () => {
    const base = ASESOR_DETALLE.comision;
    const data = {
      ...ASESOR_DETALLE,
      comision: { ...base, gate: { umbral: 95, cumple: false }, bonos: base.bonos.map((b) => (b.linea === 'LUBRICANTES' ? { ...b, falta_venta: 850000 } : b)) },
    };
    const { bonos } = comisionDe(data);
    expect(bonos.aviso).toMatch(/^Necesita/);
    expect(bonos.lineas[0].texto).toBe('Lubricantes · le faltan $850.000');
  });

  it('comision: a line above its budget minimum that still misses its mix says so instead of "$0"', () => {
    const base = ASESOR_DETALLE.comision;
    const data = {
      ...ASESOR_DETALLE,
      comision: {
        ...base,
        bonos: base.bonos.map((b) => (b.linea === 'LUBRICANTES' ? { ...b, cumple: false, falta_venta: 0, pct_real: 0.198, pct_meta: 21 } : b)),
      },
    };
    const linea = comisionDe(data).bonos.lineas[0];
    expect(linea.texto).toBe('Lubricantes · supera el mínimo; le faltan 1,2 pts');
    expect(linea.estado).toBe('no-cumple');
  });

  it('comision: below the gate it asks for the cumplimiento and still shows what is missing per line', () => {
    const c = comisionDe(clonar({ comision: { ...ASESOR_DETALLE.comision, cumplimiento_pct: 0.8, gate: { umbral: 95, cumple: false }, bono_total: 0, total_a_pagar: 910000 } }));
    expect(c.valor).toBe('$910.000');
    expect(c.bonos.aviso).toBe('Necesita ≥95% de cumplimiento para activar bonos (hoy 80,0%)');
    expect(c.bonos.lineas.map((l) => l.texto)).toEqual(['Lubricantes · le faltan $3,4 M', 'Cascos', 'Tecnired (clientes) · apagado']);
  });

  it('comision: an older payload without bonuses still renders the commission alone', () => {
    const vieja = { ...ASESOR_DETALLE.comision };
    ['gate', 'bonos', 'bono_total', 'total_a_pagar', 'cumplimiento_pct'].forEach((k) => delete vieja[k]);
    const c = comisionDe(clonar({ comision: vieja }));
    expect(c.valor).toBe('$910.000');
    expect(c.bonos).toBeNull();
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
    expect(comision.getByText('$940.000')).toBeInTheDocument();
    expect(comision.getByText('Comisión $910.000 + bonos $30.000 = $940.000')).toBeInTheDocument();
    expect(comision.getAllByTestId('chip-bono').map((c) => c.textContent)).toEqual([
      'Lubricantes · le faltan $3,4 M', 'Cascos · +$30.000', 'Tecnired (clientes) · apagado']);
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
