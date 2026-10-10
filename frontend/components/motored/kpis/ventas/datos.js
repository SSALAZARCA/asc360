/** View-models of the Ventas tab, derived from `GET /kpis/ventas` (pure, no React). */
import { MESES_CORTOS } from '../periodo';
import { decimales, miles, millones, moneda, pct } from '../format';

const NOMBRES = { REPUESTOS: 'Repuestos', ACCESORIOS: 'Accesorios', LLANTAS: 'Llantas', LUBRICANTES: 'Lubricantes', BATERIAS: 'Baterías', GPS: 'GPS', CASCOS: 'Cascos' };
export const nombreLinea = (linea) => NOMBRES[linea] ?? linea.charAt(0) + linea.slice(1).toLowerCase();
export const mesCorto = (mes) => MESES_CORTOS[Number(mes.slice(5, 7)) - 1];

const indice = (mes) => Number(mes.slice(0, 4)) * 12 + Number(mes.slice(5, 7)) - 1;
const esNumero = (v) => typeof v === 'number' && Number.isFinite(v);

/** Last 3 months vs the 3 before, as a fraction; null unless those 6 calendar months are all there. */
export function crecimiento3m(porMes) {
  const meses = Object.keys(porMes || {}).sort();
  const ultimos = meses.slice(-6);
  const seguidos = ultimos.length === 6 && ultimos.every((m, i) => indice(m) === indice(ultimos[0]) + i && esNumero(porMes[m]));
  if (!seguidos) return null;
  const suma = (lista) => lista.reduce((t, m) => t + porMes[m], 0);
  const previo = suma(ultimos.slice(0, 3));
  return previo > 0 ? suma(ultimos.slice(3)) / previo - 1 : null;
}

const chipCrecimiento = (fraccion) => (fraccion === null ? {} : {
  chip: `${fraccion >= 0 ? '▲' : '▼'} ${pct(Math.abs(fraccion))} 3M`, chipVariant: fraccion >= 0 ? 'up' : 'down',
});

export const hayPresupuesto = (data) => Boolean(data.cumplimiento?.compania?.presupuesto ?? data.cumplimiento?.red?.presupuesto);

/** Tooltip sentence when part of the cost comes from `precio_normal` (the inventory had no cost); '' otherwise. */
export function notaCostoEstimado(costo) {
  return esNumero(costo?.pct_costo_estimado) && costo.pct_costo_estimado > 0
    ? ` ${pct(costo.pct_costo_estimado)} del costo es estimado (Precio normal).`
    : '';
}

/** The six figures next to the gauge. `tip` explains the non-obvious ones. */
export function miniKpis(data) {
  const { venta, costo, facturas, clientes, descuentos } = data.total;
  const n = data.meses.length;
  const conCosto = esNumero(costo.pct_margen) && costo.venta_con_costo > 0;
  return [
    {
      label: `Venta ${n} ${n === 1 ? 'mes' : 'meses'}`, value: millones(venta.total),
      tip: 'Venta neta de la red en los meses elegidos, según el filtro de HMCL.', ...chipCrecimiento(crecimiento3m(venta.por_mes)),
    },
    {
      label: 'Margen', value: conCosto ? pct(costo.pct_margen) : '—',
      tip: conCosto ? `Utilidad bruta sobre la venta que tiene costo en el inventario.${notaCostoEstimado(costo)}` : 'Falta cargar el inventario con costo',
      ...(conCosto ? { chip: millones(costo.utilidad_bruta), chipVariant: 'flat' } : {}),
    },
    { label: 'Ticket', value: moneda(facturas.ticket_promedio), tip: 'Venta promedio por factura.', chip: `${decimales(facturas.items_por_factura, 2)} ítems`, chipVariant: 'flat' },
    { label: 'Facturas', value: miles(facturas.facturas), chip: `${miles(facturas.unidades)} und`, chipVariant: 'flat' },
    {
      label: 'Clientes', value: miles(clientes.clientes_unicos), tip: 'Clientes distintos que compraron en el período.',
      chip: `HMCL ${pct(venta.pct_hmcl)}`, chipVariant: 'flat',
    },
    { label: 'Descuentos', value: millones(descuentos.total), tip: 'Descuento otorgado; el porcentaje es sobre la venta bruta.', chip: pct(descuentos.pct_descuento, 2), chipVariant: 'up' },
  ];
}

/** One row per store: the ones with budget first (highest compliance first), then those without, by name. */
export function filasCumplimiento(data) {
  const presupuestadas = (data.cumplimiento?.tiendas ?? []).filter((t) => esNumero(t.cumplimiento_pct));
  const conId = new Set(presupuestadas.map((t) => t.sucursal_id));
  const con = presupuestadas
    .map((t) => ({ id: t.sucursal_id, nombre: t.nombre, fraccion: t.cumplimiento_pct, venta: t.venta_cumplimiento, presupuesto: t.presupuesto }))
    .sort((a, b) => b.fraccion - a.fraccion || a.nombre.localeCompare(b.nombre, 'es'));
  const sin = (data.tiendas ?? []).filter((t) => !conId.has(t.sucursal_id))
    .map((t) => ({ id: t.sucursal_id, nombre: t.nombre, fraccion: null, venta: null, presupuesto: null }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
  return [...con, ...sin];
}

/** Legend of the three zones from the configured cuts; counts come from the endpoint (`entidad`: tiendas or asesores). */
export function zonasSemaforo(data, entidad = 'tiendas') {
  const { verde_desde: verde = 90, ambar_desde: ambar = 70 } = data.reglas?.semaforo ?? {};
  const conteos = data.cumplimiento?.conteos?.[entidad] ?? {};
  return {
    verde, ambar,
    leyenda: [
      { tone: 'good', label: `≥ ${verde}%`, n: conteos.verde ?? 0 },
      { tone: 'mid', label: `${ambar}–${verde}%`, n: conteos.ambar ?? 0 },
      { tone: 'bad', label: `< ${ambar}%`, n: conteos.violeta ?? 0 },
    ],
  };
}

/** The blocks of the monthly charts: the 12-month window of the payload, or the period's own for an older payload. */
export const bloquesVentana = (data) => ({
  total: data.ventana?.total ?? data.total,
  tecnired: data.ventana?.tecnired ?? data.tecnired,
  meses: data.ventana_meses ?? data.meses,
});

/** Sales by line sorted from the heaviest, plus the months x lines matrix in millions of pesos (12-month window). */
export function ventaPorLinea(data) {
  const { total } = bloquesVentana(data);
  const { por_linea: porLinea, por_mes_linea: porMesLinea } = total.venta;
  const tickets = total.facturas?.ticket_por_linea ?? {};
  const lineas = Object.keys(porLinea).sort((a, b) => porLinea[b] - porLinea[a]);
  const meses = Object.keys(porMesLinea).sort();
  return {
    meses,
    lineas: lineas.map((l) => ({ id: l, name: nombreLinea(l), total: porLinea[l], ticket: esNumero(tickets[l]) ? tickets[l] : null, values: meses.map((m) => (porMesLinea[m][l] ?? 0) / 1e6) })),
  };
}
