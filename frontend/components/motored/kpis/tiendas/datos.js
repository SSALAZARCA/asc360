/** View-models of the Tiendas tab, derived from `GET /kpis/tiendas` (pure, no React). */
import { fechaCorta, miles, millones, moneda, pct, pctSigned } from '../format';
import { niceMax } from '../charts/geometry';
import { CATEGORIA, COLOR } from '../tokens';
import { mesCorto, nombreLinea, notaCostoEstimado } from '../ventas/datos';

const esNumero = (v) => typeof v === 'number' && Number.isFinite(v);
const suma = (valores) => valores.reduce((t, v) => t + v, 0);
const esNueva = (t) => t.crecimiento?.clasificacion === 'nueva';
const margenDe = (t) => (esNumero(t.costo?.pct_margen) && t.costo.venta_con_costo > 0 ? t.costo.pct_margen : null);

export const SIN_INVENTARIO = 'Falta cargar el inventario con costo';

/** Stores with sales, biggest first (the endpoint already sorts them; kept explicit for safety). */
export const tiendasConVenta = (data) => data.tiendas.filter((t) => t.venta.total > 0).sort((a, b) => b.venta.total - a.venta.total);

/** Weighted margin of the network over the stores that have cost data; null when none has. */
export function margenRed(tiendas) {
  const base = suma(tiendas.filter((t) => margenDe(t) !== null).map((t) => t.costo.venta_con_costo));
  return base > 0 ? suma(tiendas.filter((t) => margenDe(t) !== null).map((t) => t.costo.utilidad_bruta)) / base : null;
}

/** Estimated share of the cost over the stores with a margin (same base as `margenRed`). */
function costoEstimadoRed(tiendas) {
  const con = tiendas.filter((t) => margenDe(t) !== null);
  const costo = suma(con.map((t) => t.costo.costo_venta ?? 0));
  return { pct_costo_estimado: costo > 0 ? suma(con.map((t) => t.costo.costo_estimado ?? 0)) / costo : 0 };
}

/** Donut segments: stores that grow, fall or are new, from the endpoint's own classification. */
export function tendencia(data) {
  const r = data.resumen_crecimiento ?? {};
  const segmentos = [
    { label: 'Crecen', value: r.crece ?? 0, color: COLOR.good },
    { label: 'Caen', value: r.cae ?? 0, color: COLOR.bad },
    { label: 'Nuevas', value: r.nueva ?? 0, color: COLOR.gray500 },
  ];
  return { segmentos, total: suma(segmentos.map((s) => s.value)) };
}

const diasDe = (t) => (esNumero(t.dias_inventario?.dias) ? t.dias_inventario.dias : null);

/** Best/worst store by `valor`, among the stores with enough sales (at least 10% of the average store). */
function extremo(candidatas, valor, mayor) {
  const validas = candidatas.filter((t) => valor(t) !== null);
  if (!validas.length) return null;
  return validas.reduce((a, b) => ((valor(b) > valor(a)) === mayor && valor(b) !== valor(a) ? b : a));
}

const ficha = (label, tip, tienda, texto, variante) => (
  tienda ? { label, tip, value: texto(tienda), chip: tienda.nombre, chipVariant: variante } : { label, tip, value: '—' }
);

/** The six figures next to the donut; each one names the store that owns it. */
export function miniKpisTiendas(data) {
  const todas = tiendasConVenta(data);
  const promedio = todas.length ? suma(todas.map((t) => t.venta.total)) / todas.length : null;
  const candidatas = todas.filter((t) => !esNueva(t) && t.venta.total >= 0.1 * promedio);
  const crecimiento = (t) => (esNumero(t.crecimiento?.pct) ? t.crecimiento.pct : null);
  const caida = extremo(candidatas, crecimiento, false);
  const n = data.meses.length;
  return [
    {
      label: 'Venta promedio por tienda', value: promedio === null ? '—' : millones(promedio), chip: `${n} ${n === 1 ? 'mes' : 'meses'}`, chipVariant: 'flat',
      tip: 'Venta de la red en los meses elegidos dividida por las tiendas que vendieron.',
    },
    ficha('Mejor margen', `Utilidad bruta sobre la venta con costo. Solo tiendas que no son nuevas y venden al menos el 10% de una tienda promedio.${notaCostoEstimado(costoEstimadoRed(todas))}`, extremo(candidatas, margenDe, true), (t) => pct(margenDe(t)), 'up'),
    ficha('Mayor crecimiento', 'Últimos 3 meses contra los 3 anteriores. Las tiendas nuevas no cuentan.', extremo(candidatas, crecimiento, true), (t) => pctSigned(crecimiento(t)), 'up'),
    caida && crecimiento(caida) < 0
      ? ficha('Mayor caída', 'Últimos 3 meses contra los 3 anteriores. Las tiendas nuevas no cuentan.', caida, (t) => pctSigned(crecimiento(t)), 'down')
      : { label: 'Mayor caída', tip: 'Últimos 3 meses contra los 3 anteriores. Las tiendas nuevas no cuentan.', value: '—', chip: 'Ninguna cae', chipVariant: 'flat' },
    ficha('Mayor ticket', 'Venta promedio por factura.', extremo(candidatas, (t) => (esNumero(t.facturas?.ticket_promedio) ? t.facturas.ticket_promedio : null), true), (t) => moneda(t.facturas.ticket_promedio), 'flat'),
    {
      ...ficha('Más días de inventario', 'Inventario a costo dividido por el costo diario de venta de los últimos 3 meses.', extremo(candidatas, diasDe, true), (t) => `${miles(diasDe(t))} días`, 'down'),
      ...(extremo(candidatas, diasDe, true) ? {} : { tip: SIN_INVENTARIO }),
    },
  ];
}

const chipMargen = (tienda, red) => {
  const m = margenDe(tienda);
  if (m === null) return { text: 'Margen —', variant: 'flat' };
  return { text: `Margen ${pct(m)}`, variant: red !== null && m < red ? 'down' : 'up' };
};

const chipCrecimiento = (t) => {
  if (esNueva(t)) return { text: 'Nueva', variant: 'flat' };
  const p = t.crecimiento?.pct;
  return esNumero(p) ? { text: `${p >= 0 ? '▲' : '▼'} ${pct(Math.abs(p))}`, variant: p >= 0 ? 'up' : 'down' } : null;
};

const subDeTienda = (t) => {
  const dias = diasDe(t);
  const inventario = dias === null ? '— días de inv.' : `${miles(dias)} días de inv.`;
  const base = `${miles(t.facturas.facturas)} facturas · ticket ${moneda(t.facturas.ticket_promedio)}`;
  return {
    sub: `${base} · ${inventario}`,
    tip: dias === null ? SIN_INVENTARIO : `Inventario al ${fechaCorta(t.dias_inventario.fecha_corte)}`,
  };
};

/** BarList items of the "Venta" view. */
export function rankingVenta(data) {
  const tiendas = tiendasConVenta(data);
  const red = margenRed(tiendas);
  return tiendas.map((t) => ({
    id: t.sucursal_id, name: t.nombre, value: t.venta.total, valueText: millones(t.venta.total), ...subDeTienda(t),
    chips: [chipMargen(t, red), chipCrecimiento(t)].filter(Boolean),
  }));
}

/** DivergingBars items of the "Crecimiento" view: new stores and stores without a base are left out. */
export function rankingCrecimiento(data) {
  return tiendasConVenta(data)
    .filter((t) => !esNueva(t) && esNumero(t.crecimiento?.pct))
    .sort((a, b) => b.crecimiento.pct - a.crecimiento.pct)
    .map((t) => ({ id: t.sucursal_id, name: t.nombre, value: t.crecimiento.pct, valueText: pctSigned(t.crecimiento.pct) }));
}

/** Lines of the mix view, heaviest first over the whole selection, with their blue category color. */
export function lineasMezcla(data) {
  const total = {};
  data.tiendas.forEach((t) => Object.entries(t.venta.por_linea).forEach(([l, v]) => { total[l] = (total[l] ?? 0) + v; }));
  return Object.keys(total).sort((a, b) => total[b] - total[a]).map((l, i) => ({ id: l, name: nombreLinea(l), color: CATEGORIA[i % CATEGORIA.length] }));
}

/** One row per store: the 100% bar segments and the share of repuestos. */
export function filasMezcla(data) {
  const lineas = lineasMezcla(data);
  return tiendasConVenta(data).map((t) => {
    const total = suma(Object.values(t.venta.por_linea));
    const repuestos = total > 0 ? (t.venta.por_linea.REPUESTOS ?? 0) / total : null;
    return {
      id: t.sucursal_id, name: t.nombre, rep: repuestos === null ? '—' : `${Math.round(repuestos * 100)}%`,
      segments: lineas.map((l) => ({ label: l.name, value: t.venta.por_linea[l.id] ?? 0, color: l.color })),
    };
  });
}

/** Heatmap input: sales per month in millions of pesos. */
export function matrizMensual(data) {
  return {
    columns: data.meses.map(mesCorto),
    rows: tiendasConVenta(data).map((t) => ({ id: t.sucursal_id, name: t.nombre, values: data.meses.map((m) => (t.venta.por_mes[m] ?? 0) / 1e6) })),
  };
}

const colorTendencia = (t) => (esNueva(t) ? COLOR.gray500 : t.crecimiento?.clasificacion === 'cae' ? COLOR.bad : COLOR.good);

/** Scatter input: sales (millions) vs margin (%) with the network averages as the quadrant lines. */
export function dispersionVentaMargen(data) {
  const tiendas = tiendasConVenta(data);
  const dibujadas = tiendas.filter((t) => margenDe(t) !== null);
  const puntos = dibujadas.map((t) => ({
    id: t.sucursal_id, x: t.venta.total / 1e6, y: margenDe(t) * 100, r: 4 + Math.sqrt((t.facturas.ticket_promedio ?? 0) / 1000) * 0.6,
    color: colorTendencia(t), label: t.nombre, tip: `${t.nombre} · ${millones(t.venta.total)} · margen ${pct(margenDe(t))}`,
  }));
  const margenes = puntos.map((p) => p.y);
  const piso = Math.floor((Math.min(...margenes, 100) - 1) / 5) * 5;
  const techo = Math.ceil((Math.max(...margenes, 0) + 1) / 5) * 5;
  const red = margenRed(tiendas);
  const mejor = extremo(dibujadas, margenDe, true);
  const xMax = niceMax(Math.max(1, ...puntos.map((p) => p.x)));
  return {
    puntos,
    xDomain: [0, xMax],
    yDomain: puntos.length ? [piso, techo] : undefined,
    quadrant: { x: tiendas.length ? suma(tiendas.map((t) => t.venta.total)) / tiendas.length / 1e6 : undefined, y: red === null ? undefined : red * 100 },
    xTicks: [{ value: 0, label: '$0' }, { value: xMax, label: `$${miles(xMax)} M` }],
    yTicks: puntos.length ? Array.from({ length: (techo - piso) / 5 + 1 }, (_, i) => ({ value: piso + i * 5, label: `${piso + i * 5}%` })) : [],
    destacados: [...new Set([...dibujadas.slice(0, 4).map((t) => t.sucursal_id), ...(mejor ? [mejor.sucursal_id] : [])])],
    sinCosto: tiendas.length - dibujadas.length,
  };
}
