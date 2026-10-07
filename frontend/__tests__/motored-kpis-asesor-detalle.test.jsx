import { render, screen, within } from '@testing-library/react';
import AsesorDetalle from '../components/motored/kpis/asesores/AsesorDetalle';
import { comisionDe, explicacionDe } from '../components/motored/kpis/asesores/comision';
import {
  comparacionDe, fichaDe, gaugeDe, lineasDe, stripDe, tendenciaDe, tilesDe,
} from '../components/motored/kpis/asesores/detalle';
import { ASESOR_DETALLE } from './helpers/kpisAsesorDetalleFixture';

const clonar = (cambios = {}) => ({ ...ASESOR_DETALLE, ...cambios });
const montar = (data = ASESOR_DETALLE) => render(<AsesorDetalle data={data} />);
const seccion = (nombre) => screen.getByRole('region', { name: nombre });
const conComision = (cambios) => clonar({ comision: { ...ASESOR_DETALLE.comision, ...cambios } });
const sinCumplir = (cambios = {}) => conComision({ cumplimiento_pct: 0.8, tramo: 'BASE', tasa_pct: 1, ...cambios });

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

  it('gauge: the percentage, the figures and the 90 / 100 / 105 cuts labeled from the configured tiers', () => {
    const g = gaugeDe(ASESOR_DETALLE);
    expect(g.texto).toBe('101,4%');
    expect(g.pie).toBe('$60,8 M de $60,0 M · red 78,0%');
    expect(g.cortes.map((c) => c.label)).toEqual(['90% · PRO', '100% · Meta', '105% · ELITE']);
    expect(g.cortes.map((c) => c.tip)).toEqual([
      'Desde 90% de tu meta: tramo PRO (1,5%)', 'Tu meta: el 100% de tu presupuesto', 'Desde 105% de tu meta: tramo ELITE (1,8%)']);
    expect(g.cortes.map((c) => c.color)).toEqual([expect.stringContaining('#1D4E89'), expect.stringContaining('#1A1A18'), expect.stringContaining('#0F766E')]);
    expect(g.cortes[1].meta).toBe(true);
  });

  it('gauge: the labels follow the tiers of the payload, not hardcoded numbers', () => {
    const tramos = [{ nombre: 'BASE', desde_pct: 0, tasa_pct: 1 }, { nombre: 'MEDIO', desde_pct: 85, tasa_pct: 1.2 }, { nombre: 'TOP', desde_pct: 110, tasa_pct: 2 }];
    const g = gaugeDe(clonar({ strip: { ...ASESOR_DETALLE.strip, tramos }, comision: { ...ASESOR_DETALLE.comision, tramos } }));
    expect(g.cortes.map((c) => c.label)).toEqual(['85% · MEDIO', '100% · Meta', '110% · TOP']);
  });

  it('gauge: the three labels sit apart, the 100% one inside the arc', () => {
    const g = gaugeDe(ASESOR_DETALLE);
    expect(g.cortes.map((c) => c.lado)).toEqual(['fuera', 'dentro', 'fuera']);
    const [pro, , elite] = g.cortes;
    expect(Math.abs(parseFloat(elite.ly) - parseFloat(pro.ly))).toBeGreaterThan(20);
  });

  it('gauge: nothing without a budget for the month', () => {
    expect(gaugeDe(clonar({ cumplimiento_mes: { ...ASESOR_DETALLE.cumplimiento_mes, presupuesto: 0, pct: null, semaforo: null } }))).toBeNull();
  });

  it('comision: total, breakdown, tier chip and the date of the data', () => {
    const c = comisionDe(ASESOR_DETALLE);
    expect(c.titulo).toBe('Comisión estimada · julio');
    expect(c.valor).toBe('$940.000');
    expect(c.desglose).toBe('Comisión $910.000 + bonos $30.000');
    expect(c.chip.texto).toBe('PRO · 1,5%');
    expect(c.datos).toBe('Datos al 18/07/2026 (última venta cargada)');
  });

  it('comision: earned bonuses only, in the card', () => {
    expect(comisionDe(ASESOR_DETALLE).ganados).toEqual([{ linea: 'CASCOS', texto: 'Bono ganado: Cascos', monto: '+ $30.000' }]);
  });

  it('comision: "Para ganar más bonos" lists the active unmet lines by the smallest gap first, with the bonus of each', () => {
    const { paraBonos } = comisionDe(ASESOR_DETALLE);
    expect(paraBonos.mensaje).toBeNull();
    expect(paraBonos.filas).toEqual([
      { linea: 'LLANTAS', etiqueta: 'Llantas', falta: 'te faltan $850.000', bono: '+$25.000' },
      { linea: 'LUBRICANTES', etiqueta: 'Lubricantes', falta: 'te faltan $3,4 M', bono: '+$35.000' },
    ]);
    expect(paraBonos.tip).toMatch(/presupuesto × 95% × meta/);
  });

  it('comision: a line over its budget minimum that still misses its mix says so instead of "$0"', () => {
    const bonos = ASESOR_DETALLE.comision.bonos.map((b) => (b.linea === 'LUBRICANTES' ? { ...b, falta_venta: 0, pct_real: 0.198, pct_meta: 21 } : b));
    const fila = comisionDe(conComision({ bonos })).paraBonos.filas.find((f) => f.linea === 'LUBRICANTES');
    expect(fila.falta).toBe('supera el mínimo; le faltan 1,2 pts');
  });

  it('comision: without the gate the card says how much sale is missing to activate the bonuses, and no line rows', () => {
    const c = comisionDe(sinCumplir({ gate: { umbral: 95, cumple: false }, bono_total: 0, total_a_pagar: 910000, falta_compuerta: 3000000, bonos: ASESOR_DETALLE.comision.bonos.map((b) => ({ ...b, paga: false, bono_pagado: 0 })) }));
    expect(c.ganados).toEqual([]);
    expect(c.paraBonos.filas).toEqual([]);
    expect(c.paraBonos.mensaje).toBe('te faltan $3,0 M de venta para activar los bonos');
  });

  it('comision: when every active line is already earned there is nothing left to ask for', () => {
    const bonos = ASESOR_DETALLE.comision.bonos.map((b) => (b.activo ? { ...b, cumple: true, paga: true, bono_pagado: b.bono } : b));
    expect(comisionDe(conComision({ bonos })).paraBonos.mensaje).toBe('Ya ganaste todos los bonos activos.');
  });

  it('comision: "Para llegar al 100%" celebrates at or above the budget', () => {
    expect(comisionDe(ASESOR_DETALLE).para100).toEqual({ ok: true, texto: '¡Ya superaste tu presupuesto! (101,4%)' });
  });

  it('comision: below the budget it gives what is missing, the working days left and the sale needed per day', () => {
    const c = comisionDe(sinCumplir({ falta_100: 6000000, dias_habiles_restantes: 12, venta_diaria_necesaria: 500000 }));
    expect(c.para100).toEqual({
      ok: false, texto: 'te faltan $6,0 M · quedan 12 días hábiles (lun–sáb, sin festivos) · necesitas $500.000 por día' });
  });

  it('comision: with no working days left there is no daily figure; with one it is singular', () => {
    expect(comisionDe(sinCumplir({ falta_100: 600000, dias_habiles_restantes: 0, venta_diaria_necesaria: null })).para100.texto)
      .toBe('te faltan $600.000 · ya no quedan días hábiles este mes');
    expect(comisionDe(sinCumplir({ falta_100: 600000, dias_habiles_restantes: 1, venta_diaria_necesaria: 600000 })).para100.texto)
      .toBe('te faltan $600.000 · queda 1 día hábil (lun–sáb, sin festivos) · necesitas $600.000 por día');
  });

  it('comision: an older payload without the new fields still renders the card without the extras', () => {
    const vieja = { ...ASESOR_DETALLE.comision };
    ['fecha_datos', 'dias_habiles_restantes', 'falta_100', 'venta_diaria_necesaria', 'falta_compuerta', 'siguiente_tramo', 'venta_hmcl', 'tramos'].forEach((k) => delete vieja[k]);
    const c = comisionDe(clonar({ comision: { ...vieja, cumplimiento_pct: 0.8 } }));
    expect(c.valor).toBe('$940.000');
    expect(c.datos).toBeNull();
    expect(c.para100.texto).not.toMatch(/undefined|NaN/);
    expect(explicacionDe(clonar({ comision: vieja }))).not.toBeNull();
  });

  it('comision: without liquidation there is no card and no explanation', () => {
    expect(comisionDe(clonar({ comision: null }))).toBeNull();
    expect(explicacionDe(clonar({ comision: null }))).toBeNull();
  });

  it('explicacion: the five tiles of the equation, each operator attached to the tile that follows it', () => {
    const e = explicacionDe(ASESOR_DETALLE);
    expect(e.pasos.map((p) => [p.operador, p.label, p.valor])).toEqual([
      [null, 'Venta que cuenta', '$60,7 M'], ['×', 'PRO', '1,5%'], ['=', 'Comisión', '$910.000'], ['+', 'Bonos', '$30.000'], ['=', 'Total', '$940.000']]);
    expect(e.pasos.map((p) => p.caption)).toEqual(['sin HMCL', '101,4% de tu meta', '$60,7 M × 1,5%', 'Cascos', 'comisión + bonos']);
  });

  it('explicacion: each tile carries the full math in its tooltip', () => {
    const [venta, tramo, comision, bonos, total] = explicacionDe(ASESOR_DETALLE).pasos.map((p) => p.tip);
    expect(venta).toBe('Venta total $60,8 M − venta a HMCL $0,1 M = $60,7 M');
    expect(tramo).toBe('Cumplimiento: $60,8 M ÷ $60,0 M = 101,4% ≥ 90% → PRO (1,5%)');
    expect(comision).toBe('Comisión: $60.700.000 × 1,5% = $910.000');
    expect(bonos).toBe('Bonos activos: 101,4% ≥ 95%. Cascos 7,1% de tu venta ≥ 6% → $30.000');
    expect(total).toBe('$910.000 + $30.000 = $940.000');
  });

  it('explicacion: bonuses are off below the gate and the tooltip says why', () => {
    const e = explicacionDe(sinCumplir({ gate: { umbral: 95, cumple: false }, bono_total: 0, total_a_pagar: 910000, bonos: ASESOR_DETALLE.comision.bonos.map((b) => ({ ...b, paga: false, bono_pagado: 0 })) }));
    expect(e.pasos[3].tip).toBe('Bonos apagados: 80,0% < 95%. Con el 95% de tu presupuesto se activan.');
    expect(e.pasos[3].valor).toBe('$0');
  });

  it('explicacion: the tier ladder marks where she is and tells what the next tier gives', () => {
    const e = explicacionDe(ASESOR_DETALLE);
    expect(e.tramos.map((t) => [t.nombre, t.tasa, t.desde, t.actual])).toEqual([
      ['BASE', '1,0%', 'desde 0%', false], ['PRO', '1,5%', 'desde 90%', true], ['ELITE', '1,8%', 'desde 105%', false]]);
    expect(e.marcador).toBe('▲ Estás aquí · 101,4%');
    expect(e.siguiente).toBe('Te faltan $2,2 M para ELITE; tu comisión pasaría a $1.134.000.');
    expect(e.nota).toBe('El % se aplica a toda tu venta.');
  });

  it('explicacion: at the top tier there is no next one', () => {
    const e = explicacionDe(conComision({ tramo: 'ELITE', tasa_pct: 1.8, sig: null, siguiente_tramo: null, cumplimiento_pct: 1.132 }));
    expect(e.siguiente).toBe('Estás en el tramo más alto.');
    expect(e.tramos.find((t) => t.actual).nombre).toBe('ELITE');
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
    expect(comision.getByText('Comisión $910.000 + bonos $30.000')).toBeInTheDocument();
    expect(comision.getByText('Bono ganado: Cascos')).toBeInTheDocument();
    expect(comision.getByText('Para ganar más bonos')).toBeInTheDocument();
    expect(comision.getByText('te faltan $850.000')).toBeInTheDocument();
    expect(comision.getByText('Para llegar al 100%')).toBeInTheDocument();
    expect(comision.getByText('¡Ya superaste tu presupuesto! (101,4%)')).toBeInTheDocument();
    expect(comision.getByText('Datos al 18/07/2026 (última venta cargada)')).toBeInTheDocument();
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

  it('draws the gauge cuts with their labels and tooltips', () => {
    montar();
    const gauge = within(seccion('Cumplimiento de su meta'));
    ['90% · PRO', '100% · Meta', '105% · ELITE'].forEach((t) => expect(gauge.getByText(t)).toBeInTheDocument());
    expect(gauge.getByText('90% · PRO')).toHaveAttribute('title', 'Desde 90% de tu meta: tramo PRO (1,5%)');
    expect(gauge.getByText('100% · Meta')).toHaveAttribute('title', 'Tu meta: el 100% de tu presupuesto');
    expect(gauge.getByText('105% · ELITE')).toHaveAttribute('title', 'Desde 105% de tu meta: tramo ELITE (1,8%)');
  });

  it('draws the section "Así se calcula tu comisión" with the equation, the hint and the ladder', () => {
    montar();
    const sec = within(seccion('Así se calcula tu comisión'));
    expect(sec.getByText('Julio · datos al 18/07/2026')).toBeInTheDocument();
    expect(sec.getByText('Pasa el mouse o toca un dato para ver cómo se calculó.')).toBeInTheDocument();
    ['Venta que cuenta', 'Comisión', 'Bonos', 'Total'].forEach((t) => expect(sec.getByText(t)).toBeInTheDocument());
    expect(sec.getByText('$60,7 M')).toBeInTheDocument();
    expect(sec.getAllByText(/^[×=+]$/).map((o) => o.textContent)).toEqual(['×', '=', '+', '=']);
    expect(sec.getByTitle('Comisión: $60.700.000 × 1,5% = $910.000')).toBeInTheDocument();
    expect(sec.getByTitle('$910.000 + $30.000 = $940.000')).toBeInTheDocument();
    expect(sec.getAllByTestId('info-paso')).toHaveLength(5);
    expect(sec.getByText('BASE · 1,0%')).toBeInTheDocument();
    expect(sec.getByText('ELITE · 1,8%')).toBeInTheDocument();
    expect(sec.getByText('▲ Estás aquí · 101,4%')).toBeInTheDocument();
    expect(sec.getByText('Te faltan $2,2 M para ELITE; tu comisión pasaría a $1.134.000.')).toBeInTheDocument();
  });

  it('shows only the state that applies: below the gate and below the budget', () => {
    montar(sinCumplir({ gate: { umbral: 95, cumple: false }, falta_compuerta: 3000000, falta_100: 6000000, dias_habiles_restantes: 12, venta_diaria_necesaria: 500000 }));
    const comision = within(seccion('Comisión estimada'));
    expect(comision.getByText('te faltan $3,0 M de venta para activar los bonos')).toBeInTheDocument();
    expect(comision.queryByText('te faltan $850.000')).not.toBeInTheDocument();
    expect(comision.getByText(/te faltan \$6,0 M · quedan 12 días hábiles/)).toBeInTheDocument();
    expect(comision.queryByText(/Ya superaste/)).not.toBeInTheDocument();
    expect(comision.queryByText(/Si aún no llegaras|Si no llegaras|Si no estuviera/)).not.toBeInTheDocument();
  });

  it('has no Tecnired top when she sold nothing to Tecnired', () => {
    montar(clonar({ tecnired: { ...ASESOR_DETALLE.tecnired, venta: 0, clientes: 0, top: [] } }));
    expect(within(seccion('Clientes Tecnired atendidos')).getByText(/no le vendió a clientes Tecnired/i)).toBeInTheDocument();
  });
});
