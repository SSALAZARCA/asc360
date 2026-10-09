/** Pure helpers of the Inventario tab: formats, day-color cuts and the shaping of each card's rows. */
import { decimales, miles, pct, VACIO } from '../format';
import { MESES_CORTOS, periodoCorto } from '../periodo';
import { COLOR } from '../tokens';
import { fechaBogota } from '../../../../lib/motored/fechas';

/** Pesos in millions with the board's spacing: `$ 3.842 M`, one decimal under 20 M (`$ 18,9 M`). */
export function pesosM(valor) {
  if (valor === null || valor === undefined || !Number.isFinite(Number(valor))) return VACIO;
  const millones = Number(valor) / 1e6;
  return `$ ${decimales(millones, Math.abs(millones) >= 20 ? 0 : 1)} M`;
}

/** Trend bar label: billions with `mm` (`$3,8mm`), millions when below a billion. */
export const pesosMm = (valor) => (Number(valor) >= 1e9 ? `$${decimales(Number(valor) / 1e9, 1)}mm` : pesosM(valor));

const NEUTRO = { fg: COLOR.muted, bg: COLOR.wash };

/** Colors of a days-of-inventory value by the configured cuts: teal up to green, amber up to amber, violet above. */
export function luzDias(dias, cortes) {
  if (dias === null || dias === undefined) return NEUTRO;
  if (dias <= cortes.verde_hasta) return { fg: COLOR.good, bg: COLOR.goodSoft };
  if (dias <= cortes.ambar_hasta) return { fg: COLOR.mid, bg: COLOR.midSoft };
  return { fg: COLOR.bad, bg: COLOR.badSoft };
}

export const diasTexto = (dias) => (dias === null || dias === undefined ? VACIO : `${decimales(dias, 0)} d`);
export const rotacionTexto = (valor) => (valor === null || valor === undefined ? VACIO : `${decimales(valor, 1)}x`);

const mesesEntre = (desde, hasta) => {
  const lista = [];
  let [a, m] = desde.split('-').map(Number);
  const [af, mf] = hasta.split('-').map(Number);
  while (a < af || (a === af && m <= mf)) {
    lista.push(`${a}-${String(m).padStart(2, '0')}`);
    m += 1;
    if (m > 12) { m = 1; a += 1; }
  }
  return lista;
};

/** `Corte de inventario: 30/09/2026 · costo de ventas jul–sep`. */
export function textoCorte(data) {
  const meses = mesesEntre(data.costo_desde.slice(0, 7), data.costo_hasta.slice(0, 7));
  return `Corte de inventario: ${fechaBogota(data.corte)} · costo de ventas ${periodoCorto(meses)}`;
}

const mesAnterior = (corte) => {
  const [a, m] = corte.slice(0, 7).split('-').map(Number);
  return m === 1 ? `${a - 1}-12` : `${a}-${String(m - 1).padStart(2, '0')}`;
};

/** `▲ 2,1% vs agosto`, or null when there is no previous month value to compare with. */
export function subValor(data) {
  const { valor, valor_mes_anterior: previo } = data.tarjetas;
  if (previo === null || previo === undefined || !Number(previo)) return null;
  const cambio = valor / previo - 1;
  return `${cambio < 0 ? '▼' : '▲'} ${pct(Math.abs(cambio), 1)} vs ${periodoCorto([mesAnterior(data.corte)])}`;
}

/** The six KPI cards, in the board's order. */
export function tarjetas(data) {
  const t = data.tarjetas;
  const umbral = data.sin_movimiento_umbral_dias;
  return [
    { id: 'valor', label: 'Valor del inventario', value: pesosM(t.valor), sub: subValor(data), color: COLOR.ink, tip: 'Existencias del último corte × costo unitario' },
    { id: 'dias', label: 'Días de inventario', value: t.dias === null || t.dias === undefined ? VACIO : `${decimales(t.dias, 0)} días`, sub: `Objetivo: ${t.dias_meta} días`, color: luzDias(t.dias, data.cortes_color).fg, tip: 'Inventario a costo ÷ costo de ventas diario (últimos 3 meses)' },
    { id: 'rotacion', label: 'Rotación', value: t.rotacion === null || t.rotacion === undefined ? VACIO : `${decimales(t.rotacion, 1)} veces`, sub: 'Al año, al ritmo actual', color: COLOR.ink, tip: '365 ÷ días de inventario' },
    { id: 'sin-mov', label: `Sin movimiento +${umbral} d`, value: pesosM(t.sin_movimiento.valor), sub: `${pct(t.sin_movimiento.pct, 1)} del inventario`, color: COLOR.bad, tip: `Valor de referencias sin venta en más de ${umbral} días` },
    { id: 'disp', label: 'Disponibilidad', value: pct(t.disponibilidad.pct, 1), sub: `${miles(t.disponibilidad.agotadas)} referencias agotadas`, color: COLOR.good, tip: 'Referencias vendidas en los últimos 3 meses que hoy tienen existencia' },
    { id: 'transito', label: 'En tránsito', value: pesosM(t.transito.valor), sub: `${miles(t.transito.facturas)} facturas sin ingresar`, color: COLOR.ink, tip: 'Facturas de HMCL pendientes de ingreso (Gestión repuestos)' },
  ];
}

const nombreMes = (mes) => MESES_CORTOS[Number(mes.slice(5, 7)) - 1];

/** Bars of the trend: height proportional to the largest month (180 px max), the last one in the accent blue. */
export function barrasTendencia(data) {
  const lista = data.tendencia;
  const tope = Math.max(...lista.map((m) => m.valor), 1);
  return lista.map((m, i) => ({
    mes: nombreMes(m.mes), valor: pesosMm(m.valor), alto: Math.max(2, Math.round((m.valor / tope) * 180)),
    color: i === lista.length - 1 ? COLOR.info : '#A9BFD9', dias: diasTexto(m.dias), luz: luzDias(m.dias, data.cortes_color),
    tip: `${nombreMes(m.mes)}: ${pesosM(m.valor)} · ${m.dias === null || m.dias === undefined ? 'sin días' : `${decimales(m.dias, 0)} días`}`,
  }));
}

export const COLORES_EDAD = [COLOR.good, COLOR.mid, '#9B6BC9', COLOR.bad];

/** Age bands as legend rows: label, value, share and stacked-bar width. */
export function bandasEdad(data) {
  return data.antiguedad.bandas.map((b, i) => {
    const label = b.hasta === null ? `Más de ${b.desde - 1} días` : `${b.desde} a ${b.hasta} días`;
    return { label, color: COLORES_EDAD[i] ?? COLOR.bad, valor: pesosM(b.valor), pct: pct(b.pct, 1), ancho: `${(b.pct * 100).toFixed(2)}%`, ultima: b.hasta === null };
  });
}

export const TIP_HISTORIAL = (desde) => (desde
  ? `El historial de ventas empieza en ${periodoCorto([desde])} ${desde.slice(0, 4)}: nada puede figurar con más antigüedad que eso hasta que la historia crezca.`
  : 'Todavía no hay historial de ventas para medir esta banda.');

/** Color of an idle bar by days without sale: light above the threshold, mid above 270, dark above 365. */
export const colorQuieta = (dias) => (dias > 365 ? '#5B1E93' : (dias > 270 ? '#8B5CC4' : '#B9A0DA'));

export function filasQuietas(data) {
  const lista = data.sin_movimiento_top;
  const tope = Math.max(...lista.map((q) => q.valor), 1);
  return lista.map((q) => ({
    ...q, id: `${q.sucursal_id}|${q.referencia}`, ancho: Math.max(28, Math.round((q.valor / tope) * 100)), color: colorQuieta(q.dias_sin_venta),
    valorTexto: pesosM(q.valor), diasTexto: `${miles(q.dias_sin_venta)} d`,
    tip: `${q.referencia} · ${pesosM(q.valor)} · ${miles(q.dias_sin_venta)} días sin venta`,
  }));
}

/** Stockout rows: demand bar width vs the largest, covered share (blue) and the right-hand label. */
export function filasAgotadas(items) {
  const tope = Math.max(...items.map((a) => a.demanda), 1);
  return items.map((a) => {
    const cubierto = a.cobertura ?? (a.demanda ? a.transito / a.demanda : 0);
    const enTransito = a.transito > 0;
    return {
      ...a, id: `${a.sucursal_id}|${a.referencia}`, enTransito, ancho: Math.max(18, Math.round((a.demanda / tope) * 100)),
      cubierto: Math.min(100, Math.round(cubierto * 100)),
      detalle: `${miles(a.vendidas)} vendidas + ${miles(a.perdidas)} perdidas = ${miles(a.demanda)} und`,
      etiqueta: enTransito ? `${miles(a.transito)} de ${miles(a.demanda)} und` : `Sin pedir · ${miles(a.demanda)}`,
      tip: `${a.referencia}: demanda ${miles(a.demanda)} und en 3 meses (${miles(a.vendidas)} vendidas + ${miles(a.perdidas)} perdidas) · ${enTransito ? `${miles(a.transito)} und en tránsito` : 'nada en tránsito'}`,
    };
  });
}
