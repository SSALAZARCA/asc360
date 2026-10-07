/** View-models of the single-asesor view, derived from `GET /kpis/asesores/detalle` (pure, no React). */
import { decimales, miles, millones, moneda, pct, VACIO } from '../format';
import { MESES_CORTOS, periodoCorto } from '../periodo';
import { COLOR } from '../tokens';
import { nombreLinea } from '../ventas/datos';

const esNumero = (v) => typeof v === 'number' && Number.isFinite(v);
const MESES_LARGOS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const mesLargo = (mes) => MESES_LARGOS[Number(mes.slice(5, 7)) - 1];
const TRAMOS_DEFECTO = [{ nombre: 'BASE', desde_pct: 0 }, { nombre: 'PRO', desde_pct: 90 }, { nombre: 'ELITE', desde_pct: 105 }];
const COLOR_TRAMO = { ELITE: COLOR.good, PRO: COLOR.info, BASE: COLOR.gray400 };
const SOFT_TRAMO = { ELITE: COLOR.goodSoft, PRO: COLOR.infoSoft };

export const tramosDe = (data) => {
  const tramos = data.strip?.tramos;
  return [...(tramos?.length ? tramos : TRAMOS_DEFECTO)].sort((a, b) => a.desde_pct - b.desde_pct);
};
export const colorDeTramo = (nombre, tramos) => {
  if (COLOR_TRAMO[nombre]) return COLOR_TRAMO[nombre];
  const i = tramos.findIndex((t) => t.nombre === nombre);
  return i <= 0 ? COLOR.gray400 : i === tramos.length - 1 ? COLOR.good : COLOR.info;
};
export const softDeTramo = (nombre) => SOFT_TRAMO[nombre] ?? null;

/** The tier of her month: the liquidated one, else the highest cut her compliance reaches. */
export function tramoActual(data) {
  if (data.comision?.tramo) return data.comision.tramo;
  const pctMes = data.cumplimiento_mes?.pct;
  if (!esNumero(pctMes)) return null;
  return tramosDe(data).filter((t) => pctMes * 100 >= t.desde_pct).pop()?.nombre ?? null;
}

const capitalizar = (texto) => (texto ? texto.charAt(0).toUpperCase() + texto.slice(1).toLowerCase() : null);
const periodoDe = (data) => periodoCorto(data.meses);
const mesDe = (data) => mesLargo(data.cumplimiento_mes.mes);
/** Name of the month of her compliance (`julio`). */
export const mesNombre = mesDe;

/** Header card: name, role · store · cédula, tier chip and the positions she holds (a missing one is left out). */
export function fichaDe(data) {
  const { asesor, puestos } = data;
  const tramo = tramoActual(data);
  const puesto = (label, p) => (p && esNumero(p.puesto) ? { label, val: `Puesto ${p.puesto} de ${p.de}` } : null);
  return {
    nombre: asesor.nombre ?? 'Sin nombre',
    iniciales: (asesor.nombre ?? '?').split(/\s+/).slice(0, 2).map((p) => p.charAt(0).toUpperCase()).join(''),
    partes: [capitalizar(asesor.cargo), asesor.tienda, `C.C. ${asesor.cedula}`].filter(Boolean),
    tramo: tramo ? { texto: `${tramo} · ${mesDe(data)}`, color: colorDeTramo(tramo, tramosDe(data)) } : null,
    puestos: [
      puesto('Cumplimiento', puestos.cumplimiento), puesto(`Venta ${periodoDe(data)}`, puestos.venta), puesto('Tecnired', puestos.tecnired),
    ].filter(Boolean),
  };
}

const ROTULOS = {
  venta: { label: (d) => `Venta · ${periodoDe(d)}`, formato: (v) => millones(v, 1) },
  ticket: { label: () => 'Ticket promedio', formato: moneda, tip: 'Venta promedio por factura.' },
  facturas: { label: () => 'Facturas', formato: miles },
  clientes_unicos: { label: () => 'Clientes únicos', formato: miles, tip: 'Clientes distintos a los que facturó en los meses elegidos.' },
  margen: { label: () => 'Margen', formato: pct, tip: 'Utilidad bruta sobre la venta con costo.' },
  pct_tecnired: { label: () => '% Tecnired', formato: pct, tip: 'Parte de su venta que va a talleres de la lista Tecnired.' },
};
const DE = { asesores: 'promedio asesores', red: 'red' };

function chipDe(t) {
  if (!esNumero(t.dif)) return null;
  const arriba = t.dif >= 0;
  const cifra = t.dif_tipo === 'pts' ? `${decimales(Math.abs(t.dif) * 100, 1)} pts` : pct(Math.abs(t.dif));
  return { text: `${arriba ? '▲' : '▼'} ${cifra}`, variant: arriba ? 'up' : 'down' };
}

/** The tiles that came in the payload (one without a data source is not sent, so it is not drawn). */
export function tilesDe(data) {
  return data.tiles.filter((t) => ROTULOS[t.id]).map((t) => {
    const r = ROTULOS[t.id];
    return {
      id: t.id, label: r.label(data), tip: r.tip, valor: esNumero(t.valor) ? r.formato(t.valor) : VACIO,
      chip: esNumero(t.valor) ? chipDe(t) : null, ref: `vs ${DE[t.ref_de]} ${esNumero(t.ref) ? r.formato(t.ref) : VACIO}`,
    };
  });
}

const GAUGE_L = Math.PI * 80;
const GAUGE_MAX = 120;
const sobreArco = (v, r) => {
  const a = Math.PI - (Math.min(v, GAUGE_MAX) / GAUGE_MAX) * Math.PI;
  return [100 + r * Math.cos(a), 104 - r * Math.sin(a)];
};

/** Gauge of her month (arc to 120 %, cuts of the tiers); null without budget for the month. */
export function gaugeDe(data) {
  const m = data.cumplimiento_mes;
  if (!m.presupuesto || !esNumero(m.pct)) return null;
  const tramos = tramosDe(data);
  const tramo = tramoActual(data);
  const cortes = tramos.filter((t) => t.desde_pct > 0).map((t) => {
    const [x1, y1] = sobreArco(t.desde_pct, 68);
    const [x2, y2] = sobreArco(t.desde_pct, 92);
    const [tx, ty] = sobreArco(t.desde_pct, 104);
    return { x1: x1.toFixed(1), y1: y1.toFixed(1), x2: x2.toFixed(1), y2: y2.toFixed(1), tx: tx.toFixed(1), ty: (ty + 3).toFixed(1), label: String(t.desde_pct) };
  });
  const texto = pct(m.pct);
  const pie = [`${millones(m.venta, 1)} de ${millones(m.presupuesto, 1)}`, esNumero(m.red_pct) ? `red ${pct(m.red_pct)}` : null].filter(Boolean).join(' · ');
  return {
    texto, pie, cortes, color: tramo ? colorDeTramo(tramo, tramos) : COLOR.info, titulo: `Cumplimiento de su meta · ${mesDe(data)}`,
    arco: `${((Math.min(m.pct * 100, GAUGE_MAX) / GAUGE_MAX) * GAUGE_L).toFixed(1)} ${GAUGE_L.toFixed(1)}`, aria: `Cumplimiento ${texto} de su meta`,
  };
}

const TIP_APAGADO = 'Bono apagado en Configuración';
const sinDecimalInutil = (v) => decimales(v, Number.isInteger(v) ? 0 : 1);

/** Missing sale of an unmet line in pesos: from 1 M on one decimal in millions (`$3,4 M`), below it whole pesos (`$850.000`). */
const pesosFalta = (v) => (v >= 1e6 ? millones(v, 1) : moneda(v));
const textoFalta = (b) => (b.falta_venta == null ? b.etiqueta : `${b.etiqueta} · le faltan ${pesosFalta(b.falta_venta)}`);

/** Bonus status of her month: a notice when she is below the gate, and one entry per bonus line. Null for a payload without bonuses. */
function bonosDe(c) {
  if (!c.gate || !c.bonos) return null;
  const { cumple: pasa, umbral } = c.gate;
  const lineas = c.bonos.map((b) => {
    const base = { linea: b.linea };
    if (!b.activo) return { ...base, texto: `${b.etiqueta} · apagado`, estado: 'apagado', tip: TIP_APAGADO };
    if (b.cumple && pasa) return { ...base, texto: `${b.etiqueta} · +${moneda(b.bono_pagado)}`, estado: 'cumple', tip: `Gana ${moneda(b.bono_pagado)}` };
    if (b.cumple) {
      return { ...base, texto: b.etiqueta, estado: 'sin-compuerta', tip: `Cumple la línea, pero no llega al ${sinDecimalInutil(umbral)}% de cumplimiento: no se paga` };
    }
    const meta = `Venta mínima de la línea según su presupuesto (presupuesto × ${sinDecimalInutil(umbral)}% × meta). El bono se gana si la línea llega a la meta % de su venta real.`;
    return { ...base, texto: textoFalta(b), estado: 'no-cumple', tip: meta };
  });
  return {
    aviso: pasa ? null : `Necesita ≥${sinDecimalInutil(umbral)}% de cumplimiento para activar bonos (hoy ${pct(c.cumplimiento_pct)})`,
    lineas,
  };
}

/** Commission card: amount, tier chip, the gap to the next tier and the network average; null if not liquidated. */
export function comisionDe(data) {
  const c = data.comision;
  if (!c) return null;
  const tramos = tramosDe(data);
  const promedio = `Promedio de comisión de la red: ${moneda(c.promedio_red)}.`;
  const base = c.base_pago === 'sin_hmcl' ? 'sin HMCL' : 'con HMCL';
  const sig = c.sig;
  const avance = sig && sig.meta > 0 ? Math.min(Math.max(data.cumplimiento_mes.venta / sig.meta, 0), 1) : 0;
  const bonos = bonosDe(c);
  const total = c.total_a_pagar ?? c.comision;
  return {
    titulo: `Comisión estimada · ${mesLargo(c.mes)}`, valor: moneda(total), bonos,
    desglose: bonos ? `Comisión ${moneda(c.comision)} + bonos ${moneda(c.bono_total)} = ${moneda(total)}` : null,
    chip: { texto: `${c.tramo ?? 'Sin tramo'} ${decimales(c.tasa_pct, 1)}%`, color: colorDeTramo(c.tramo, tramos) },
    base: `${millones(c.venta_base, 1)} ${base} × ${decimales(c.tasa_pct, 1)}%`,
    siguiente: sig ? {
      titulo: `Le faltan ${millones(sig.falta, 1)} para ${sig.tramo}`, meta: `meta ${sig.tramo} ${millones(sig.meta, 1)}`,
      avance: Number((avance * 100).toFixed(1)), color: colorDeTramo(c.tramo, tramos), colorMeta: colorDeTramo(sig.tramo, tramos),
    } : null,
    nota: sig
      ? `En ${sig.tramo} (${decimales(sig.tasa_pct, 1)}%) ganaría ≈ ${moneda(c.comision + sig.gana)}. ${promedio}`
      : `Está en el tramo más alto. ${promedio}`,
  };
}

const X0 = 74;
const ANCHO = 440;
const SUPERIOR = 16;
const INFERIOR = 216;
const PASO = 15;

/** Monthly compliance (hers and the network's) as SVG paths, the tier bands and the grid. */
export function tendenciaDe(data) {
  const { tendencia } = data;
  const valores = tendencia.flatMap((p) => [p.pct, p.red_pct]).filter(esNumero).map((v) => v * 100);
  const tramos = tramosDe(data);
  const lo = Math.min(60, Math.floor(Math.min(...valores, 60) / PASO) * PASO);
  const hi = Math.max(120, Math.ceil(Math.max(...valores, 120) / PASO) * PASO);
  const y = (v) => SUPERIOR + (1 - (Math.min(Math.max(v, lo), hi) - lo) / (hi - lo)) * (INFERIOR - SUPERIOR);
  const x = (i) => (tendencia.length === 1 ? X0 + ANCHO / 2 : X0 + i * (ANCHO / (tendencia.length - 1)));
  const trazo = (clave) => tendencia.reduce((d, p, i) => {
    if (!esNumero(p[clave])) return d;
    const previo = i > 0 && esNumero(tendencia[i - 1][clave]);
    return `${d}${d ? ' ' : ''}${previo ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p[clave] * 100).toFixed(1)}`;
  }, '');
  const cortes = tramos.filter((t) => t.desde_pct > 0).map((t) => t.desde_pct);
  const grid = [];
  for (let v = lo; v <= hi; v += PASO) {
    const corte = cortes.includes(v);
    grid.push({ y: y(v).toFixed(1), ty: (y(v) + 4).toFixed(1), label: `${v}%`, corte });
  }
  const bandas = tramos.filter((t) => softDeTramo(t.nombre)).map((t) => {
    const siguiente = tramos.find((o) => o.desde_pct > t.desde_pct)?.desde_pct ?? hi;
    return { nombre: t.nombre, y: y(Math.min(siguiente, hi)).toFixed(1), alto: (y(t.desde_pct) - y(Math.min(siguiente, hi))).toFixed(1), fill: softDeTramo(t.nombre), yEtiqueta: (y(t.desde_pct) - 8).toFixed(1), color: colorDeTramo(t.nombre, tramos) };
  });
  const verde = data.reglas?.semaforo?.verde_desde ?? 90;
  const conPresupuesto = tendencia.filter((p) => esNumero(p.pct));
  const cumplio = conPresupuesto.filter((p) => p.pct * 100 >= verde).length;
  const pro = tramos.length > 2 ? tramos[1] : null;
  const elite = tramos.length > 2 ? tramos[tramos.length - 1] : null;
  return {
    puntos: tendencia.map((p, i) => ({
      x: x(i).toFixed(1), y: esNumero(p.pct) ? y(p.pct * 100).toFixed(1) : null, ly: esNumero(p.pct) ? (y(p.pct * 100) - 11).toFixed(1) : null,
      val: esNumero(p.pct) ? String(Math.round(p.pct * 100)) : null, m: MESES_CORTOS[Number(p.mes.slice(5, 7)) - 1],
    })),
    linea: trazo('pct'), rojo: trazo('red_pct'), grid, bandas, cortes,
    nota: `${conPresupuesto.length ? `Cumplió (≥ ${verde}%) en ${cumplio} de ${conPresupuesto.length} ${conPresupuesto.length === 1 ? 'mes' : 'meses'} con presupuesto.` : 'Sin presupuesto en los meses elegidos.'}${pro && elite ? ` Bandas: ${pro.nombre} desde ${pro.desde_pct}%, ${elite.nombre} sobre ${elite.desde_pct}%.` : ''}`,
    aria: `Cumplimiento mensual entre ${Math.round(Math.min(...valores, 100))}% y ${Math.round(Math.max(...valores, 0))}% frente al promedio de la red`,
  };
}

const listar = (items) => (items.length > 1 ? `${items.slice(0, -1).join(', ')} y ${items[items.length - 1]}` : items[0]);

/** Venta por línea: her mix against the network's, the biggest share first, plus the one-line reading. */
export function lineasDe(data) {
  const filas = data.lineas.filter((l) => esNumero(l.pct)).sort((a, b) => b.pct - a.pct);
  const maximo = Math.max(0.3, ...filas.flatMap((l) => [l.pct, l.red_pct ?? 0])) * 1.15;
  const conDif = filas.map((l) => ({ ...l, dif: esNumero(l.red_pct) ? (l.pct - l.red_pct) * 100 : null }));
  const mas = conDif.filter((l) => l.dif >= 1).sort((a, b) => b.dif - a.dif).slice(0, 3).map((l) => nombreLinea(l.linea).toLowerCase());
  const espacio = conDif.filter((l) => l.dif <= -1).sort((a, b) => a.dif - b.dif)[0];
  const partes = [mas.length ? `Vende más ${listar(mas)} que la red` : null, espacio ? `${nombreLinea(espacio.linea).toLowerCase()} es su línea con más espacio` : null].filter(Boolean);
  return {
    filas: conDif.map((l) => ({
      name: nombreLinea(l.linea), w: `${((l.pct / maximo) * 100).toFixed(1)}%`, red: esNumero(l.red_pct) ? `${((l.red_pct / maximo) * 100).toFixed(1)}%` : null,
      tip: `Red ${pct(l.red_pct)}`, pct: pct(l.pct),
      diff: l.dif === null ? null : `${l.dif >= 0 ? '▲' : '▼'} ${decimales(Math.abs(l.dif), 1)} pts`, variant: l.dif === null ? 'flat' : l.dif >= 0 ? 'up' : 'down',
    })),
    nota: partes.length ? `${partes.join('; ')}.` : null,
  };
}

const ZONAS_FONDO = [COLOR.track, '#D3DDEA', '#CFE6E3'];

/** Strip of her compliance among her peers: zones from the tier cuts, the others as dots and her highlighted. */
export function stripDe(data) {
  const { otros, yo, tramos } = data.strip;
  const cortes = tramosDe({ strip: { tramos } }).filter((t) => t.desde_pct > 0).map((t) => t.desde_pct);
  const maximo = Math.max(150, Math.ceil(Math.max(...otros, yo ?? 0, 0) * 100 / 50) * 50);
  const limites = [...cortes, maximo];
  const debajo = esNumero(yo) ? otros.filter((v) => v < yo).length : 0;
  const encima = esNumero(yo) ? otros.filter((v) => v > yo).length : 0;
  return {
    otros, total: otros.length + (esNumero(yo) ? 1 : 0), min: 0, max: maximo, cortes,
    zonas: limites.map((hasta, i) => ({ hasta, bg: ZONAS_FONDO[Math.min(i, ZONAS_FONDO.length - 1)] })),
    ticks: [{ value: 0, label: '0%' }, ...tramosDe({ strip: { tramos } }).filter((t) => t.desde_pct > 0).map((t) => ({ value: t.desde_pct, label: `${t.desde_pct}% ${t.nombre}`, strong: true })), { value: maximo, label: `${maximo}%+` }],
    yo: esNumero(yo) ? { value: yo * 100, label: pct(yo) } : null,
    texto: esNumero(yo)
      ? `Está por encima de ${debajo} ${debajo === 1 ? 'compañero' : 'compañeros'}; ${encima === 0 ? 'nadie supera su cumplimiento' : encima === 1 ? '1 asesor supera su cumplimiento' : `${encima} asesores superan su cumplimiento`}.`
      : 'Sin cumplimiento para comparar este mes.',
  };
}

/** Comparison with her store: her figure, the store average and the network average. */
export function comparacionDe(data) {
  const c = data.comparacion;
  const mes = mesDe(data);
  const n = c.tienda?.asesores ?? 0;
  const fila = (label, d, formato) => ({ label, yo: formato(d.yo), tienda: formato(d.tienda), red: formato(d.red) });
  return {
    sub: `${c.tienda?.nombre && n ? `${c.tienda.nombre} tiene ${n} ${n === 1 ? 'asesor' : 'asesores'} · ` : ''}${mes}, salvo margen y ticket (${periodoDe(data)})`,
    filas: [
      fila(`Venta ${mes}`, c.venta_mes, (v) => millones(v, 1)), fila(`Cumplimiento ${mes}`, c.cumplimiento_mes, pct),
      fila('Ticket promedio', c.ticket, moneda), fila('Margen', c.margen, pct), fila('% Tecnired', c.pct_tecnired, pct),
    ],
  };
}

/** Tecnired card: share against the network, the figures and the top clients by sale. */
export function tecniredDe(data) {
  const t = data.tecnired;
  const maximo = Math.max(1, ...t.top.map((c) => c.venta));
  return {
    chip: esNumero(t.pct) && esNumero(t.red_pct) ? { text: `${t.pct >= t.red_pct ? '▲' : '▼'} ${pct(t.pct)} vs ${pct(t.red_pct)} red`, variant: t.pct >= t.red_pct ? 'up' : 'down' } : null,
    fichas: [{ value: millones(t.venta, 1), label: `venta ${periodoDe(data)}` }, ...(t.clientes > 0 ? [{ value: miles(t.clientes), label: 'talleres atendidos' }] : [])],
    top: t.top.map((c) => ({ name: c.cliente, val: millones(c.venta, 1), w: `${((c.venta / maximo) * 100).toFixed(1)}%` })),
    vacio: !(t.venta > 0) && t.top.length === 0,
  };
}
