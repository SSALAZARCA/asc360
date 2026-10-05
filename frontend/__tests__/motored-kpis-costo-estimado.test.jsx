import { miniKpis } from '../components/motored/kpis/ventas/datos';
import { miniKpisTiendas } from '../components/motored/kpis/tiendas/datos';
import { miniKpisAsesores } from '../components/motored/kpis/asesores/datos';
import { VENTAS } from './helpers/kpisVentasFixture';
import { TIENDAS } from './helpers/kpisTiendasFixture';
import { ASESORES } from './helpers/kpisAsesoresFixture';

const NOTA = /\d+,\d% del costo es estimado \(Precio normal\)/;
const conEstimado = (costo, pct) => ({
  ...costo, costo_estimado: costo.costo_venta * pct, pct_costo_estimado: pct,
});
const ventasCon = (pct) => ({ ...VENTAS, total: { ...VENTAS.total, costo: conEstimado(VENTAS.total.costo, pct) } });
const tip = (kpis, label) => kpis.find((k) => k.label === label).tip;

describe('KPI margin: share of the cost estimated with the master price', () => {
  it('explains it in the Ventas margin tooltip when part of the cost is estimated', () => {
    expect(tip(miniKpis(ventasCon(0.25)), 'Margen')).toMatch(/25,0% del costo es estimado \(Precio normal\)/);
  });

  it('stays silent when none of the cost is estimated or the field is missing', () => {
    expect(tip(miniKpis(ventasCon(0)), 'Margen')).not.toMatch(NOTA);
    expect(tip(miniKpis(VENTAS), 'Margen')).not.toMatch(NOTA);
  });

  it('keeps the missing-inventory message when there is no cost at all', () => {
    const sinCosto = { ...ventasCon(0.5), total: { ...ventasCon(0.5).total, costo: { ...conEstimado(VENTAS.total.costo, 0.5), venta_con_costo: 0, pct_margen: null } } };
    expect(tip(miniKpis(sinCosto), 'Margen')).toBe('Falta cargar el inventario con costo');
  });

  it('explains it in the Asesores network margin tooltip', () => {
    const data = { ...ASESORES, total: { ...ASESORES.total, costo: conEstimado(ASESORES.total.costo, 0.1) } };
    expect(tip(miniKpisAsesores(data), 'Margen red')).toMatch(/10,0% del costo es estimado \(Precio normal\)/);
    expect(tip(miniKpisAsesores(ASESORES), 'Margen red')).not.toMatch(NOTA);
  });

  it('explains the weighted share of the stores in the Tiendas best-margin tooltip', () => {
    const tiendas = TIENDAS.tiendas.map((t) => ({ ...t, costo: { ...t.costo, costo_venta: 100, costo_estimado: 40, pct_costo_estimado: 0.4 } }));
    expect(tip(miniKpisTiendas({ ...TIENDAS, tiendas }), 'Mejor margen')).toMatch(/40,0% del costo es estimado \(Precio normal\)/);
    expect(tip(miniKpisTiendas(TIENDAS), 'Mejor margen')).not.toMatch(NOTA);
  });
});
