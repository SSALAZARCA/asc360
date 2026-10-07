/** View-models of the Comisiones tab, derived from `GET /kpis/comisiones` (pure, no React). */
import { decimales, millones, miles, moneda, pct } from '../format';
import { periodoCorto } from '../periodo';

const esNumero = (v) => typeof v === 'number' && Number.isFinite(v);

export const COLOR_TRAMO = { ELITE: '#0F766E', PRO: '#1D4E89', BASE: '#A3A39E' };
const ZONA_BG = { primera: '#E4E4E1', media: '#D3DDEA', ultima: '#CFE6E3' };

/** Tier color: by name (ELITE teal, PRO blue, BASE gray); a tier with another name by position (last, first, middle). */
export function colorDeTramo(nombre, indice, total) {
  if (COLOR_TRAMO[nombre]) return COLOR_TRAMO[nombre];
  if (indice === total - 1) return COLOR_TRAMO.ELITE;
  return indice === 0 ? COLOR_TRAMO.BASE : COLOR_TRAMO.PRO;
}

/** `1.5` -> `1,5`, `90` -> `90`. */
export const numero = (v) => decimales(v, Number.isInteger(v) ? 0 : 1);

/** `$190 M`, `$5,0 M`: millions with a decimal only when needed (always one under `fijo`). */
export const enMillones = (v, fijo = false) => millones(v, !fijo && Number.isInteger(v / 1e6) ? 0 : 1);

/** Month words of the settled month: `{ largo: 'julio', anio: '2026', completo: 'julio 2026' }`. */
export function mesLiquidado(data) {
  const mes = data.mes_liquidado;
  const largo = periodoCorto([mes]);
  return { largo, anio: mes.slice(0, 4), completo: `${largo} ${mes.slice(0, 4)}` };
}

/** The configured bonus lines in config order ([] when none, or when the payload predates the bonuses). */
export const lineasBono = (data) => data.reglas?.comision_lineas ?? [];

export const umbralBono = (data) => data.reglas?.comision_bono_umbral_pct;

/** What is paid: commission + bonuses (the commission alone for a payload without bonuses). */
export const totalAPagar = (data) => data.resumen.total_a_pagar ?? data.resumen.comision_total;

export const sinPresupuestos = (data) => Boolean(data.advertencias?.sin_presupuestos) || data.asesores.length === 0;

const baseTexto = (base) => (base === 'sin_hmcl' ? 'sin HMCL' : 'con HMCL');

/** Range label of each tier from the configured tiers: `BASE hasta 90%`, `PRO 90–105%`, `ELITE desde 105%`. */
export function rangosDeTramos(tramos) {
  return tramos.map((x, i) => {
    if (tramos.length === 1) return `${x.nombre} todos`;
    if (i === 0) return `${x.nombre} hasta ${numero(tramos[1].desde_pct)}%`;
    if (i === tramos.length - 1) return `${x.nombre} desde ${numero(x.desde_pct)}%`;
    return `${x.nombre} ${numero(x.desde_pct)}–${numero(tramos[i + 1].desde_pct)}%`;
  });
}

/** Legend of the strip: one entry per tier with its range, rate and number of asesores. */
export function leyendaTramos(data) {
  const rangos = rangosDeTramos(data.tramos);
  return data.tramos.map((x, i) => ({
    nombre: x.nombre, texto: `${rangos[i]} · ${numero(x.tasa_pct)}% · `, n: x.asesores, color: colorDeTramo(x.nombre, i, data.tramos.length),
  }));
}

// Widths of the non-linear axis: the first tier takes 60%, the last one 30% and the middle ones share 10%.
const anchos = (n) => {
  if (n === 1) return [100];
  if (n === 2) return [60, 40];
  return [60, ...Array(n - 2).fill(10 / (n - 2)), 30];
};

/**
 * The non-linear axis of the strip (0-90 % takes 60% of the width with the default tiers): `posicion(pct)` -> 0..100,
 * `zonas` for `ZoneStrip` (`hasta` in axis units) and the `lineas` and `ticks` at each tier start.
 */
export function escalaTramos(tramos) {
  const desdes = tramos.map((x) => x.desde_pct);
  const fin = Math.max(150, desdes[desdes.length - 1] + 45);
  const ancho = anchos(tramos.length);
  const inicio = ancho.map((_, i) => ancho.slice(0, i).reduce((t, a) => t + a, 0));
  const posicion = (porcentaje) => {
    if (!esNumero(porcentaje) || porcentaje <= 0) return 0;
    if (porcentaje >= fin) return 100;
    let i = desdes.length - 1;
    while (desdes[i] > porcentaje) i -= 1;
    const hasta = i + 1 < desdes.length ? desdes[i + 1] : fin;
    return inicio[i] + ((porcentaje - desdes[i]) / (hasta - desdes[i])) * ancho[i];
  };
  const bg = (i) => (i === 0 ? ZONA_BG.primera : i === tramos.length - 1 ? ZONA_BG.ultima : ZONA_BG.media);
  const inicios = desdes.filter((d) => d > 0);
  return {
    posicion,
    zonas: ancho.map((a, i) => ({ hasta: inicio[i] + a, bg: bg(i) })),
    lineas: inicios.map(posicion),
    ticks: [
      { value: 0, label: '0%' },
      ...inicios.map((d) => ({ value: posicion(d), label: `${numero(d)}%`, strong: true })),
      { value: 100, label: `${numero(fin)}%+` },
    ],
  };
}

/** One dot per asesor with budget, placed on the non-linear axis. */
export function puntosAsesores(data, escala) {
  const total = data.tramos.length;
  const indiceDe = (nombre) => Math.max(0, data.tramos.findIndex((x) => x.nombre === nombre));
  return data.asesores.map((a) => ({
    value: escala.posicion((a.cumplimiento_pct ?? 0) * 100),
    color: colorDeTramo(a.tramo, indiceDe(a.tramo), total),
    tip: `${a.nombre ?? a.cedula} · ${pct(a.cumplimiento_pct)}`,
  }));
}

/** The KPI card: figures under the total to pay (`tip` explains each one); the bonus ones only with bonus lines. */
export function miniKpis(data) {
  const r = data.resumen;
  const base = baseTexto(data.reglas.comision_base_pago);
  const bonos = lineasBono(data).length === 0 ? [] : [
    { label: 'comisión del mes', value: moneda(r.comision_total), tip: 'La comisión por tramo de todos los asesores liquidados, sin los bonos.' },
    { label: 'bonos por línea', value: moneda(r.bonos_total), tip: 'Los bonos fijos ganados por línea: solo cuentan los asesores que llegan a la compuerta de cumplimiento y las líneas encendidas.' },
  ];
  return [
    ...bonos,
    { label: 'asesores', value: miles(r.asesores), tip: 'Asesores con presupuesto cargado en el mes y un cargo que gana comisión.' },
    { label: 'comisión promedio', value: moneda(r.comision_promedio), tip: 'Comisión total del mes dividida entre los asesores liquidados.' },
    {
      label: 'mayor comisión', value: moneda(r.comision_mayor?.comision), chip: r.comision_mayor?.nombre, chipVariant: 'flat',
      tip: 'La comisión más alta del mes y quién la ganó.',
    },
    { label: `de la venta ${base}`, value: pct(r.comision_pct_venta), tip: `Comisión total sobre la venta ${base} de los asesores liquidados (la base de pago).` },
  ];
}

const pesosTexto = (v) => moneda(v);

export const COLOR_BONO = '#B45309';
const MAX_PUNTOS = 12;

/** Detail of one bonus line of an asesor, shown when her row is expanded: met and paid, met below the gate, unmet or off. */
export function detalleBono(a, b) {
  const base = { linea: b.linea, etiqueta: b.etiqueta };
  if (!b.activo) return { ...base, estado: 'apagado', marca: '○', texto: 'apagado' };
  if (b.cumple && b.paga) return { ...base, estado: 'cumple', marca: '✓', texto: moneda(b.bono_pagado) };
  if (b.cumple) return { ...base, estado: 'sin-compuerta', marca: '○', texto: `cumple, pero no llega al ${numero(a.gate.umbral)}%: no se paga` };
  return { ...base, estado: 'no-cumple', marca: '○', texto: `le faltan ${moneda(b.falta_venta)}` };
}

/** Rows of "Comisión por asesor" (the API already sorts them by commission): commission bar, thin bonus bar, total and detail. */
export function filasComision(data) {
  const pagado = (a) => a.total_a_pagar ?? a.comision;
  const maximo = Math.max(1, ...data.asesores.map((a) => a.comision));
  const total = data.tramos.length;
  const conBonos = lineasBono(data).length > 0;
  return data.asesores.map((a) => {
    const ganados = (a.bonos ?? []).filter((b) => b.paga);
    const bono = a.bono_total ?? 0;
    const tramo = a.tramo ?? '—';
    return {
      id: a.cedula, nombre: a.nombre ?? a.cedula, sub: `${a.tienda ?? '—'} · cumple ${pct(a.cumplimiento_pct)}`,
      ancho: Math.max((a.comision / maximo) * 100, 0.5), valor: moneda(a.comision), total: moneda(pagado(a)), tramo,
      color: colorDeTramo(a.tramo, Math.max(0, data.tramos.findIndex((x) => x.nombre === a.tramo)), total),
      textoSobreBase: tramo === 'BASE',
      bono: bono > 0 ? {
        ancho: Math.min(Math.max((bono / maximo) * 100, 0.5), 100),
        etiqueta: `+ ${moneda(bono)} bonos (${ganados.map((b) => b.etiqueta).join(', ')})`,
      } : null,
      bajoCompuerta: conBonos && a.gate?.cumple === false,
      umbral: a.gate ? numero(a.gate.umbral) : numero(umbralBono(data)),
      detalle: (a.bonos ?? []).map((b) => detalleBono(a, b)),
    };
  });
}

/** The semaforo view: by cumplimiento, best first. */
export function celdasCumplimiento(data) {
  return [...data.asesores]
    .sort((x, y) => (y.cumplimiento_pct ?? 0) - (x.cumplimiento_pct ?? 0))
    .map((a) => ({ id: a.cedula, name: a.nombre ?? a.cedula, pct: a.cumplimiento_pct, detail: `${a.tramo ?? '—'} · ${a.tienda ?? '—'}` }));
}

/** "Cerca de subir de tramo" cards: progress towards the next tier start, what is missing and what it would add. */
export function tarjetasCerca(data) {
  const total = data.tramos.length;
  const indiceDe = (nombre) => Math.max(0, data.tramos.findIndex((x) => x.nombre === nombre));
  return data.cerca_de_subir.map((c) => {
    const meta = data.tramos.find((x) => x.nombre === c.siguiente)?.desde_pct;
    return {
      id: c.cedula, nombre: c.nombre ?? c.cedula, gana: `+${moneda(c.gana)}`, actual: pct(c.cumplimiento_pct),
      meta: `${numero(meta)}%`, siguiente: c.siguiente, falta: c.falta < 1e6 ? moneda(c.falta) : enMillones(c.falta, true),
      ancho: Math.min(100, (c.cumplimiento_pct * 10000) / meta), color: colorDeTramo(c.tramo, indiceDe(c.tramo), total),
    };
  });
}

const asesoresTexto = (n) => `${n} ${n === 1 ? 'asesor' : 'asesores'}`;

/** Asesores that met an off line while past the gate: they would have earned it were it on. */
const habriaGanado = (data, linea) => data.asesores.filter((a) => a.gate?.cumple && (a.bonos ?? []).some((b) => b.linea === linea && b.cumple)).length;

/** The "Bonos por línea" mosaic: header figures and one tile per configured line (target, amount, winners, share of the total). */
export function mosaicoBonos(data) {
  const resumen = new Map((data.resumen.por_linea ?? []).map((x) => [x.linea, x]));
  const lineas = lineasBono(data);
  const montoDe = (l) => (l.activo ? resumen.get(l.linea)?.monto ?? 0 : 0);
  const ganadoresDe = (l) => resumen.get(l.linea)?.ganadores ?? 0;
  const pagado = lineas.reduce((t, l) => t + montoDe(l), 0);
  const ganados = lineas.reduce((t, l) => t + (l.activo ? ganadoresDe(l) : 0), 0);
  return {
    pagado: moneda(pagado), ganados: `${ganados} ${ganados === 1 ? 'bono ganado' : 'bonos ganados'}`,
    tiles: lineas.map((l) => {
      const n = l.activo ? ganadoresDe(l) : habriaGanado(data, l.linea);
      const monto = montoDe(l);
      const parte = pagado > 0 ? (monto / pagado) * 100 : 0;
      return {
        id: l.linea, etiqueta: l.etiqueta, activo: l.activo, regla: `≥${numero(l.pct_meta)}% · ${moneda(l.bono)} c/u`, monto: moneda(monto),
        quienes: l.activo ? asesoresTexto(n) : `lo habrían ganado ${n}`,
        puntos: Math.min(n, MAX_PUNTOS), mas: n > MAX_PUNTOS ? `+${n - MAX_PUNTOS}` : '',
        ancho: Number(parte.toFixed(1)),
        parteTexto: l.activo ? `${Math.round(parte)}% del total pagado` : 'Apagado en Configuración · no suma al total',
      };
    }),
  };
}
