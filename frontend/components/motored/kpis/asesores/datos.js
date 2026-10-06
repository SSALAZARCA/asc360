/** View-models of the Asesores tab, derived from `GET /kpis/asesores` (pure, no React). */
import { decimales, miles, millones, moneda, pct } from '../format';
import { CATEGORIA, COLOR, TONO } from '../tokens';
import { notaCostoEstimado } from '../ventas/datos';

const esNumero = (v) => typeof v === 'number' && Number.isFinite(v);
const suma = (valores) => valores.reduce((t, v) => t + v, 0);

export const personas = (data) => data.filas.filter((f) => f.tipo === 'PERSONA');
const margenDe = (f) => (esNumero(f.costo?.pct_margen) && f.costo.venta_con_costo > 0 ? f.costo.pct_margen : null);
const margenRed = (data) => margenDe(data.total);
const TONO_DE = { verde: 'good', ambar: 'mid', violeta: 'bad' };

/** Cédula of the tablero row `clave` (`P:...`): the one of its cumplimiento row, else the digits of the key; null if it has none. */
function cedulaDe(data, clave) {
  const fila = data.cumplimiento?.asesores?.find((a) => a.clave === clave);
  if (fila?.cedula) return fila.cedula;
  const limpia = String(clave).replace(/^P:/, '').replace(/\.0$/, '').replace(/[\s.]+/g, '');
  return /^\d+$/.test(limpia) ? limpia : null;
}

/** Items of a ranking whose name selects the asesor (`onSelect`); without a cédula or a handler the name stays text. */
export const conSeleccion = (items, onAsesor) => items.map((i) => (onAsesor && i.cedula ? { ...i, onSelect: () => onAsesor(i.cedula) } : i));

/** Asesores with a budget: those that meet the goal (green) against the rest. */
export function cumplen(data) {
  const c = data.cumplimiento.conteos.asesores;
  const verde = data.reglas?.semaforo?.verde_desde ?? 90;
  const si = c.verde ?? 0;
  const no = (c.ambar ?? 0) + (c.violeta ?? 0);
  return {
    segmentos: [{ label: `Cumplen (≥ ${verde}%)`, value: si, color: COLOR.good }, { label: 'No cumplen', value: no, color: COLOR.bad }],
    cumplen: si, evaluados: si + no,
  };
}

function extremo(lista, valor) {
  const validas = lista.filter((f) => valor(f) !== null);
  return validas.length ? validas.reduce((a, b) => (valor(b) > valor(a) ? b : a)) : null;
}

const ficha = (label, tip, fila, texto, chip, variante) => (fila
  ? { label, tip, value: texto(fila), chip: chip(fila), chipVariant: variante }
  : { label, tip, value: '—' });

/** The six figures next to the donut. Best margin and ticket skip asesores with very few sales. */
export function miniKpisAsesores(data) {
  const todas = personas(data).filter((f) => f.venta.total > 0);
  const promedio = todas.length ? suma(todas.map((f) => f.venta.total)) / todas.length : 0;
  const candidatas = todas.filter((f) => f.venta.total >= 0.1 * promedio);
  const red = margenRed(data);
  const ticketRed = data.total.facturas.ticket_promedio;
  const ticketDe = (f) => (esNumero(f.facturas?.ticket_promedio) ? f.facturas.ticket_promedio : null);
  const lider = extremo(todas, (f) => f.venta.total);
  const periodo = data.meses.length;
  return [
    { label: 'Asesores', value: miles(todas.length), chip: 'con venta', chipVariant: 'flat', tip: 'Asesores con venta en los meses elegidos.' },
    ficha('Líder', 'El asesor que más vendió en los meses elegidos.', lider, (f) => millones(f.venta.total), (f) => f.nombre, 'flat'),
    ficha('Mejor margen', 'Utilidad bruta sobre la venta con costo; solo asesores con al menos el 10% de la venta de un asesor promedio.', extremo(candidatas, margenDe), (f) => pct(margenDe(f)),
      (f) => (red === null ? f.nombre : `${margenDe(f) >= red ? '▲' : '▼'} vs ${pct(red)} red`), 'up'),
    ficha('Mayor ticket', 'Venta promedio por factura.', extremo(candidatas, ticketDe), (f) => moneda(ticketDe(f)),
      (f) => (esNumero(ticketRed) && ticketRed > 0 ? `▲ ${decimales(ticketDe(f) / ticketRed, 1)}× la red` : f.nombre), 'up'),
    { label: 'Margen red', value: red === null ? '—' : pct(red), chip: `${periodo} ${periodo === 1 ? 'mes' : 'meses'}`, chipVariant: 'flat', tip: `Margen de toda la red en los meses elegidos.${notaCostoEstimado(data.total.costo)}` },
    { label: 'Ticket red', value: moneda(ticketRed), chip: `${decimales(data.total.facturas.items_por_factura, 2)} ítems`, chipVariant: 'flat', tip: 'Venta promedio por factura de toda la red.' },
  ];
}

/** Dots of the zone strip: one per asesor with a budget, colored by their semaforo. */
export function puntosAsesores(data) {
  return data.cumplimiento.asesores.filter((a) => esNumero(a.cumplimiento_pct)).map((a) => ({
    value: a.cumplimiento_pct * 100, color: TONO[TONO_DE[a.semaforo] ?? 'none'].color, tip: `${a.nombre ?? 'Sin nombre'} · ${pct(a.cumplimiento_pct)}`,
  }));
}

const chipMargen = (f, red) => {
  const m = margenDe(f);
  if (m === null) return { text: 'Margen —', variant: 'flat' };
  return { text: `Margen ${pct(m)}`, variant: red !== null && m < red ? 'down' : 'up' };
};

const MEDALLA_BAJA = { bg: COLOR.badSoft, fg: COLOR.badInk };

/** Top 10 by sales (BarList items). */
export function topVenta(data) {
  const red = margenRed(data);
  return personas(data).filter((f) => f.venta.total > 0).sort((a, b) => b.venta.total - a.venta.total).slice(0, 10).map((f) => ({
    id: f.clave, cedula: cedulaDe(data, f.clave), name: f.nombre, value: f.venta.total, valueText: millones(f.venta.total),
    sub: [f.punto_venta, `ticket ${moneda(f.facturas.ticket_promedio)}`].filter(Boolean).join(' · '), chips: [chipMargen(f, red)],
    fila: f,
  }));
}

const textoPesos = (v) => millones(v, v >= 1e7 ? 0 : v >= 1e6 ? 1 : 2);

/** Bottom 10 by compliance among the asesores with a budget, and how many were left out for not having one. */
export function bottomCumplimiento(data) {
  const red = margenRed(data);
  const filas = new Map(personas(data).map((f) => [f.clave, f]));
  const evaluadas = data.cumplimiento.asesores.filter((a) => esNumero(a.cumplimiento_pct))
    .sort((a, b) => a.cumplimiento_pct - b.cumplimiento_pct || (a.nombre ?? '').localeCompare(b.nombre ?? '', 'es'));
  const items = evaluadas.slice(0, 10).map((a) => {
    const f = filas.get(a.clave);
    const ticket = f && esNumero(f.facturas?.ticket_promedio) ? `ticket ${moneda(f.facturas.ticket_promedio)}` : null;
    return {
      id: a.clave, cedula: a.cedula ?? cedulaDe(data, a.clave), name: a.nombre ?? 'Sin nombre', value: a.cumplimiento_pct, valueText: `${textoPesos(a.venta_cumplimiento)} / ${textoPesos(a.presupuesto)}`,
      color: TONO[TONO_DE[a.semaforo] ?? 'none'].color, badge: MEDALLA_BAJA,
      sub: [f?.punto_venta, `cumple ${pct(a.cumplimiento_pct)}`, ticket].filter(Boolean).join(' · '), chips: f ? [chipMargen(f, red)] : [],
      fila: f,
    };
  });
  return { items, sinPresupuesto: data.cumplimiento.conteos.asesores.sin_presupuesto ?? 0 };
}

export const COLUMNAS_MEZCLA = [['REPUESTOS', 'Repuestos'], ['LUBRICANTES', 'Lubric.'], ['ACCESORIOS', 'Acces.'], ['LLANTAS', 'Llantas']];

/** Share of each line in the asesor's sales, with the blue intensity of the cell (`alpha`). */
export function filaMezcla(item) {
  const f = item.fila;
  const total = f?.venta?.total ?? 0;
  return {
    id: item.id, name: item.name, onSelect: item.onSelect,
    cells: COLUMNAS_MEZCLA.map(([linea]) => {
      const share = total > 0 ? (f.venta.por_linea[linea] ?? 0) / total : null;
      const alpha = share === null ? 0.08 : Math.max(0.08, Math.min(1, share * 1.25));
      return { share, text: pct(share), alpha, dark: alpha > 0.55 };
    }),
  };
}

const ESCALA_TECNIRED = [
  { desde: 0.25, color: CATEGORIA[0], ink: '#FFFFFF' }, { desde: 0.15, color: CATEGORIA[1], ink: '#FFFFFF' },
  { desde: 0.1, color: CATEGORIA[2], ink: '#FFFFFF' }, { desde: 0.063, color: CATEGORIA[4], ink: '#0E2A4D' },
  { desde: -Infinity, color: CATEGORIA[6], ink: '#0E2A4D' },
];

/** Blue shade of a share of sales that goes to Tecnired; null (the "Otros" tile) is gray. */
export function tonoTecnired(fraccion) {
  if (!esNumero(fraccion)) return { bg: COLOR.track, fg: COLOR.ink2 };
  const n = ESCALA_TECNIRED.find((e) => fraccion >= e.desde);
  return { bg: n.color, fg: n.ink };
}

/** Tecnired by asesor: chips, treemap tiles (top 11 + "Otros N asesores") and the sorted share bars. */
export function tecniredAsesores(data) {
  const todas = personas(data).filter((f) => f.venta.total > 0);
  const conTecnired = todas.filter((f) => f.clientes.venta_tecnired > 0).sort((a, b) => b.clientes.venta_tecnired - a.clientes.venta_tecnired);
  const total = suma(conTecnired.map((f) => f.clientes.venta_tecnired));
  const resto = conTecnired.slice(11);
  const tiles = conTecnired.slice(0, 11).map((f) => ({
    id: f.clave, label: f.nombre, value: f.clientes.venta_tecnired, colorValue: f.clientes.pct_tecnired, valueText: millones(f.clientes.venta_tecnired, 1),
    sub: `${pct(f.clientes.pct_tecnired)} de su venta`, tip: [f.nombre, f.punto_venta].filter(Boolean).join(' · '),
  }));
  if (resto.length) {
    const venta = suma(resto.map((f) => f.clientes.venta_tecnired));
    tiles.push({
      id: 'otros', label: `Otros ${resto.length} asesores`, value: venta, colorValue: null, valueText: millones(venta, 1),
      sub: `${decimales((venta / total) * 100, 0)}% del total`, tip: `Otros ${resto.length} asesores`,
    });
  }
  const filas = todas.map((f) => ({ id: f.clave, cedula: cedulaDe(data, f.clave), name: f.nombre, pct: f.clientes.pct_tecnired ?? 0 })).sort((a, b) => b.pct - a.pct);
  const promedio = data.total.clientes.pct_tecnired;
  return {
    kpis: [
      { value: millones(total), label: 'venta a Tecnired' },
      { value: String(conTecnired.length), label: 'asesores le venden' },
      { value: String(todas.filter((f) => f.clientes.pct_tecnired > 0.15).length), label: 'con más de 15%' },
    ],
    tiles, filas, promedio: esNumero(promedio) ? promedio : null,
    maximo: Math.max(0.1, ...filas.map((f) => f.pct), (esNumero(promedio) ? promedio : 0) * 1.5),
  };
}

const GRUPOS = [
  { clave: 'PERSONA', name: 'Asesores de repuestos', color: COLOR.info },
  { clave: 'COMERCIALES', name: 'Comerciales', color: CATEGORIA[3] },
  { clave: 'OTROS', name: 'Otros roles de posventa', color: CATEGORIA[5] },
  { clave: 'RESTO', name: 'Resto de compañía', color: COLOR.line },
];

/** Sales of the asesores (PERSONA) and of each group row, as 100%-bar segments. */
export function ventaPorGrupo(data) {
  return GRUPOS.map((g) => ({
    label: g.name, color: g.color,
    value: g.clave === 'PERSONA' ? suma(personas(data).map((f) => f.venta.total)) : suma(data.filas.filter((f) => f.clave === g.clave).map((f) => f.venta.total)),
  })).filter((g) => g.value > 0 || g.label === GRUPOS[0].name);
}
