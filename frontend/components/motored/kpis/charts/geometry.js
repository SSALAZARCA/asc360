/**
 * Pure geometry of the KPI charts (no React, no DOM): the math each chart draws from, so it can
 * be tested without rendering. Numbers only; colors and labels belong to the components.
 */
import { COLOR } from '../tokens';

const redondear = (valor, cifras = 2) => Number(valor.toFixed(cifras));
const acotar = (valor, minimo, maximo) => Math.min(Math.max(valor, minimo), maximo);
const suma = (valores) => valores.reduce((total, v) => total + v, 0);

// --- Gauge ----------------------------------------------------------------------------------

const GAUGE_RADIO = 80;
const GAUGE_AGUJA = 62;

/** Needle tip and arc dash of the semicircle gauge (viewBox 200 x 120, centre 100,104). */
export function gaugeGeometry(fraccion) {
  const ratio = acotar(Number.isFinite(fraccion) ? fraccion : 0, 0, 1);
  const angulo = Math.PI * (1 - ratio);
  const arc = Math.PI * GAUGE_RADIO;
  return {
    ratio,
    arc,
    dash: ratio * arc,
    needleX: redondear(100 + GAUGE_AGUJA * Math.cos(angulo), 1),
    needleY: redondear(104 - GAUGE_AGUJA * Math.sin(angulo), 1),
  };
}

/** `good | mid | bad | none` for a value in percentage points against the configured cuts. */
export function semaforoTone(puntos, cortes = {}) {
  if (puntos === null || puntos === undefined || !Number.isFinite(Number(puntos))) return 'none';
  const verde = Number.isFinite(cortes.verde_desde) ? cortes.verde_desde : 90;
  const ambar = Number.isFinite(cortes.ambar_desde) ? cortes.ambar_desde : 70;
  if (Number(puntos) >= verde) return 'good';
  return Number(puntos) >= ambar ? 'mid' : 'bad';
}

// --- Donut / shares -------------------------------------------------------------------------

/** Each item with its `fraction` of the positive total (0 when there is nothing to share). */
export function shares(items) {
  const total = suma(items.map((i) => Math.max(Number(i.value) || 0, 0)));
  return items.map((i) => ({ ...i, fraction: total > 0 ? Math.max(Number(i.value) || 0, 0) / total : 0 }));
}

/** Stroke dashes of a donut: one arc per positive item, laid end to end from the top. */
export function donutSegments(items, radio = 66) {
  const circunferencia = 2 * Math.PI * radio;
  let acumulado = 0;
  return shares(items).filter((s) => s.fraction > 0).map((s) => {
    const len = s.fraction * circunferencia;
    const segmento = { ...s, len, gap: circunferencia - len, offset: -acumulado };
    acumulado += len;
    return segmento;
  });
}

// --- Bars -----------------------------------------------------------------------------------

/** Where a bar writes its value: inside from `minimo`% of width, outside (after the bar) below. */
export const barPlacement = (anchoPct, minimo = 20) => (anchoPct >= minimo ? 'inside' : 'outside');

// --- Zone strip -----------------------------------------------------------------------------

const RANURA = 1.4;
const CARRIL = 32;
const SALTO = 14;

/** Stacking level of each dot: dots in the same slot go 0, 1, 2... in input order. */
export function stackLevels(posiciones) {
  const usados = {};
  return posiciones.map((x) => {
    const ranura = Math.round(x / RANURA);
    usados[ranura] = (usados[ranura] || 0) + 1;
    return usados[ranura] - 1;
  });
}

/** Top offset (px) of a stacking level: 0 on the lane, then alternating above and below. */
export const stackTop = (nivel) => (nivel === 0 ? CARRIL : nivel % 2 ? CARRIL - Math.ceil(nivel / 2) * SALTO : CARRIL + (nivel / 2) * SALTO);

const TRANSFORM = (i, total) => (i === 0 ? 'none' : i === total - 1 ? 'translateX(-100%)' : 'translateX(-50%)');

/** Percent positions of the zones, vertical lines, ticks and dots of a "where each one falls" strip. */
export function zoneStripLayout({ dots, min, max, zones, lines = [], ticks = [] }) {
  const pos = (v) => ((acotar(v, min, max) - min) / (max - min)) * 100;
  let previo = min;
  const zonas = zones.map((z) => {
    const hasta = Math.min(z.hasta, max);
    const ancho = ((hasta - previo) / (max - min)) * 100;
    previo = hasta;
    return { widthPct: redondear(ancho), bg: z.bg };
  });
  const posiciones = dots.map((d) => redondear(pos(d.value)));
  const niveles = stackLevels(posiciones);
  return {
    zones: zonas,
    lines: lines.map((v) => redondear(pos(v))),
    ticks: ticks.map((t, i) => ({ ...t, leftPct: redondear(pos(t.value)), transform: TRANSFORM(i, ticks.length) })),
    dots: dots.map((d, i) => ({ ...d, leftPct: posiciones[i], level: niveles[i], top: stackTop(niveles[i]) })),
  };
}

// --- Heatmap --------------------------------------------------------------------------------

const NIVELES_HEAT = [
  { level: 1, desde: 1.15, bg: COLOR.good, fg: '#FFFFFF' },
  { level: 2, desde: 1.05, bg: COLOR.goodSoft, fg: COLOR.goodInk },
  { level: 3, desde: 0.95, bg: COLOR.wash, fg: COLOR.ink2 },
  { level: 4, desde: 0.85, bg: COLOR.midSoft, fg: COLOR.midInk },
  { level: 5, desde: 0.75, bg: COLOR.badSoft, fg: COLOR.badInk },
  { level: 6, desde: -Infinity, bg: COLOR.bad, fg: '#FFFFFF' },
];

export const HEAT_LEYENDA = ['≥ +15%', '+5 a +15%', '± 5%', '−5 a −15%', '−15 a −25%', '≤ −25%'];

export const HEAT_SIN_DATO = { level: null, bg: COLOR.surface, fg: COLOR.gray400 };

/** The heat level (1 strongest above average ... 6 strongest below) of a ratio vs the row average. */
export function heatLevel(ratio) {
  if (!Number.isFinite(ratio)) return { ...HEAT_SIN_DATO };
  const nivel = NIVELES_HEAT.find((n) => ratio >= n.desde);
  return { level: nivel.level, bg: nivel.bg, fg: nivel.fg };
}

/** Cells of each row colored against that row's own average of its active (positive) values. */
export function heatRows(rows) {
  return rows.map((fila) => {
    const activos = fila.values.filter((v) => v > 0);
    const promedio = activos.length ? suma(activos) / activos.length : 0;
    const cells = fila.values.map((v) => (v > 0
      ? { value: v, ...heatLevel(v / promedio) }
      : { value: null, ...HEAT_SIN_DATO }));
    return { ...fila, cells };
  });
}

// --- Treemap --------------------------------------------------------------------------------

function peorProporcion(fila, lado) {
  const area = suma(fila.map((n) => n.area));
  const mayor = Math.max(...fila.map((n) => n.area));
  const menor = Math.min(...fila.map((n) => n.area));
  return Math.max((lado * lado * mayor) / (area * area), (area * area) / (lado * lado * menor));
}

function colocarFila(fila, caja, salida) {
  const area = suma(fila.map((n) => n.area));
  const horizontal = caja.w >= caja.h;
  const grosor = area / (horizontal ? caja.h : caja.w);
  let cursor = horizontal ? caja.y : caja.x;
  fila.forEach((n) => {
    const largo = n.area / grosor;
    salida.push(horizontal
      ? { ...n.item, x: caja.x, y: cursor, w: grosor, h: largo }
      : { ...n.item, x: cursor, y: caja.y, w: largo, h: grosor });
    cursor += largo;
  });
  return horizontal
    ? { x: caja.x + grosor, y: caja.y, w: caja.w - grosor, h: caja.h }
    : { x: caja.x, y: caja.y + grosor, w: caja.w, h: caja.h - grosor };
}

/** Squarified treemap of `items` (by `value`, descending) inside a `ancho` x `alto` box. */
export function squarify(items, ancho, alto) {
  const validos = items.map((item, i) => ({ item, i })).filter((x) => x.item.value > 0);
  validos.sort((a, b) => b.item.value - a.item.value || a.i - b.i);
  const escala = (ancho * alto) / (suma(validos.map((x) => x.item.value)) || 1);
  const nodos = validos.map((x) => ({ item: x.item, area: x.item.value * escala }));
  const salida = [];
  let caja = { x: 0, y: 0, w: ancho, h: alto };
  let i = 0;
  while (i < nodos.length) {
    const lado = Math.min(caja.w, caja.h);
    const fila = [nodos[i]];
    i += 1;
    while (i < nodos.length && peorProporcion([...fila, nodos[i]], lado) <= peorProporcion(fila, lado)) {
      fila.push(nodos[i]);
      i += 1;
    }
    caja = colocarFila(fila, caja, salida);
  }
  return salida;
}

// --- Stacked area ---------------------------------------------------------------------------

const PASOS = [1, 2, 2.5, 5, 10];

/** Rounds `maximo` up so that four equal grid steps are readable numbers (500, 2.5, 20...). */
export function niceMax(maximo) {
  if (!Number.isFinite(maximo) || maximo <= 0) return 4;
  const crudo = maximo / 4;
  const exponente = 10 ** Math.floor(Math.log10(crudo));
  const paso = PASOS.find((p) => p * exponente >= crudo * (1 - 1e-9)) * exponente;
  return redondear(paso * 4, 6);
}

const AREA = { width: 760, height: 270, padL: 80, padR: 30, top: 24, bottom: 240 };

/** Layer paths, month totals and grid lines of a stacked area, as percent overlays of the box. */
export function stackedAreaGeometry(series, cantidad, opciones = {}) {
  const a = { ...AREA, ...opciones };
  const x = (i) => a.padL + (cantidad > 1 ? (i * (a.width - a.padL - a.padR)) / (cantidad - 1) : 0);
  const totales = Array.from({ length: cantidad }, (_, i) => suma(series.map((s) => s.values[i] || 0)));
  const maximo = opciones.yMax || niceMax(Math.max(0, ...totales));
  const y = (v) => a.top + (1 - v / maximo) * (a.bottom - a.top);
  const indices = Array.from({ length: cantidad }, (_, i) => i);
  let base = indices.map(() => 0);
  const layers = series.map((s) => {
    const arriba = base.map((b, i) => b + (s.values[i] || 0));
    const ida = indices.map((i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(arriba[i]).toFixed(1)}`).join(' ');
    const vuelta = [...indices].reverse().map((i) => `L${x(i).toFixed(1)} ${y(base[i]).toFixed(1)}`).join(' ');
    base = arriba;
    return { name: s.name, color: s.color, path: `${ida} ${vuelta} Z` };
  });
  return {
    ...a,
    yMax: maximo,
    layers,
    xs: indices.map((i) => redondear((x(i) / a.width) * 100)),
    totals: indices.map((i) => ({
      value: totales[i], leftPct: redondear((x(i) / a.width) * 100), topPct: redondear(((y(totales[i]) - 4) / a.height) * 100),
    })),
    grid: [0, 1, 2, 3, 4].map((k) => ({ value: (maximo * k) / 4, y: y((maximo * k) / 4), topPct: redondear((y((maximo * k) / 4) / a.height) * 100) })),
  };
}
