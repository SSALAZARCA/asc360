/** View-models of the commission card and of "Así se calcula tu comisión" (pure, no React). */
import { fechaBogota } from '../../../../lib/motored/fechas';
import { decimales, millones, moneda, pct } from '../format';
import { colorDeTramo, mesLargo, tramosDe } from './detalle';

const esNumero = (v) => typeof v === 'number' && Number.isFinite(v);
const sinDecimalInutil = (v) => decimales(v, Number.isInteger(v) ? 0 : 1);
/** From 1 M on one decimal in millions (`$3,4 M`), below it whole pesos (`$850.000`). */
const pesos = (v) => (v >= 1e6 ? millones(v, 1) : moneda(v));
const tasa = (v) => `${decimales(v, 1)}%`;
const MINIMO = 'Venta mínima de cada línea según tu presupuesto (presupuesto × {umbral}% × meta). El bono se gana cuando la línea llega a su meta % de tu venta real.';

/** Tiers with their rate: the payload's (`comision.tramos`), else the cuts of the strip without a rate. */
export const tramosConTasa = (data) => {
  const con = data.comision?.tramos;
  return con?.length ? [...con].sort((a, b) => a.desde_pct - b.desde_pct) : tramosDe(data);
};
const siguienteDe = (c) => c.siguiente_tramo ?? (c.sig ? { nombre: c.sig.tramo, falta: c.sig.falta, comision_si_llega: c.comision + c.sig.gana } : null);

const faltaDe = (b) => {
  if (!esNumero(b.falta_venta)) return '—';
  if (b.falta_venta === 0 && esNumero(b.pct_real) && esNumero(b.pct_meta)) {
    return `supera el mínimo; le faltan ${decimales(Math.max(0, b.pct_meta - b.pct_real * 100), 1)} pts`;
  }
  return `te faltan ${pesos(b.falta_venta)}`;
};

function paraBonosDe(c) {
  if (!c.gate || !c.bonos) return null;
  const umbral = sinDecimalInutil(c.gate.umbral);
  const tip = MINIMO.replace('{umbral}', umbral);
  if (!c.gate.cumple) {
    const mensaje = esNumero(c.falta_compuerta)
      ? `te faltan ${pesos(c.falta_compuerta)} de venta para activar los bonos`
      : `Necesitas ≥${umbral}% de cumplimiento para activar los bonos`;
    return { tip, filas: [], mensaje };
  }
  const filas = c.bonos.filter((b) => b.activo && !b.cumple)
    .sort((a, b) => (a.falta_venta ?? Infinity) - (b.falta_venta ?? Infinity))
    .map((b) => ({ linea: b.linea, etiqueta: b.etiqueta, falta: faltaDe(b), bono: `+${moneda(b.bono)}` }));
  return { tip, filas, mensaje: filas.length ? null : 'Ya ganaste todos los bonos activos.' };
}

const diasTexto = (dias) => (dias === 0
  ? 'ya no quedan días hábiles este mes'
  : `${dias === 1 ? 'queda 1 día hábil' : `quedan ${dias} días hábiles`} (lun–sáb, sin festivos)`);

function para100De(c) {
  const alcanzo = esNumero(c.cumplimiento_pct) ? c.cumplimiento_pct >= 1 : c.falta_100 === 0;
  if (alcanzo) return { ok: true, texto: `¡Ya superaste tu presupuesto! (${pct(c.cumplimiento_pct)})` };
  const partes = [esNumero(c.falta_100) ? `te faltan ${pesos(c.falta_100)}` : null];
  if (esNumero(c.dias_habiles_restantes)) partes.push(diasTexto(c.dias_habiles_restantes));
  if (esNumero(c.venta_diaria_necesaria)) partes.push(`necesitas ${moneda(c.venta_diaria_necesaria)} por día`);
  return { ok: false, texto: partes.filter(Boolean).join(' · ') };
}

/** Commission card: total, breakdown, tier, earned bonuses, what is missing for more and for the 100 %; null if not liquidated. */
export function comisionDe(data) {
  const c = data.comision;
  if (!c) return null;
  const tramos = tramosDe(data);
  const total = c.total_a_pagar ?? c.comision;
  return {
    titulo: `Comisión estimada · ${mesLargo(c.mes)}`, valor: moneda(total),
    desglose: c.bonos ? `Comisión ${moneda(c.comision)} + bonos ${moneda(c.bono_total)}` : null,
    chip: { texto: `${c.tramo ?? 'Sin tramo'} · ${tasa(c.tasa_pct)}`, color: colorDeTramo(c.tramo, tramos) },
    ganados: (c.bonos ?? []).filter((b) => b.paga).map((b) => ({ linea: b.linea, texto: `Bono ganado: ${b.etiqueta}`, monto: `+ ${moneda(b.bono_pagado)}` })),
    paraBonos: paraBonosDe(c),
    para100: para100De(c),
    datos: c.fecha_datos ? `Datos al ${fechaBogota(c.fecha_datos)} (última venta cargada)` : null,
  };
}

const ventaTip = (c) => {
  const base = c.base_pago === 'sin_hmcl' ? 'sin HMCL' : 'con HMCL';
  if (c.base_pago === 'sin_hmcl' && esNumero(c.venta_hmcl)) {
    return `Venta total ${millones(c.venta_base + c.venta_hmcl, 1)} − venta a HMCL ${millones(c.venta_hmcl, 1)} = ${millones(c.venta_base, 1)}`;
  }
  return `Venta ${base}: ${millones(c.venta_base, 1)}`;
};

function tramoTip(data, c) {
  if (!esNumero(c.cumplimiento_pct)) return 'El % depende de tu cumplimiento del mes.';
  const desde = tramosConTasa(data).find((t) => t.nombre === c.tramo)?.desde_pct;
  const vendida = c.cumplimiento_pct * c.presupuesto;
  const cumple = `Cumplimiento: ${millones(vendida, 1)} ÷ ${millones(c.presupuesto, 1)} = ${pct(c.cumplimiento_pct)}`;
  return c.tramo && esNumero(desde) ? `${cumple} ≥ ${sinDecimalInutil(desde)}% → ${c.tramo} (${tasa(c.tasa_pct)})` : cumple;
}

function bonosTip(c) {
  if (!c.gate) return 'Bonos del mes.';
  const umbral = sinDecimalInutil(c.gate.umbral);
  if (!c.gate.cumple) return `Bonos apagados: ${pct(c.cumplimiento_pct)} < ${umbral}%. Con el ${umbral}% de tu presupuesto se activan.`;
  const ganados = (c.bonos ?? []).filter((b) => b.paga)
    .map((b) => `${b.etiqueta} ${pct(b.pct_real)} de tu venta ≥ ${sinDecimalInutil(b.pct_meta)}% → ${moneda(b.bono_pagado)}`);
  return `Bonos activos: ${pct(c.cumplimiento_pct)} ≥ ${umbral}%. ${ganados.length ? ganados.join('. ') : 'Ninguna línea llegó a su meta.'}`;
}

/** "Así se calcula tu comisión": equation tiles, tier ladder, where she is and what the next tier gives; null if not liquidated. */
export function explicacionDe(data) {
  const c = data.comision;
  if (!c) return null;
  const tramos = tramosDe(data);
  const total = c.total_a_pagar ?? c.comision;
  const bonoTotal = c.bono_total ?? 0;
  const ganados = (c.bonos ?? []).filter((b) => b.paga).map((b) => b.etiqueta);
  const colorTramo = colorDeTramo(c.tramo, tramos);
  const pasos = [
    { id: 'venta', operador: null, label: 'Venta que cuenta', valor: millones(c.venta_base, 1), caption: c.base_pago === 'sin_hmcl' ? 'sin HMCL' : 'con HMCL', tip: ventaTip(c), estilo: 'neutro' },
    { id: 'tramo', operador: '×', label: c.tramo ?? 'Sin tramo', valor: tasa(c.tasa_pct), caption: esNumero(c.cumplimiento_pct) ? `${pct(c.cumplimiento_pct)} de tu meta` : '', tip: tramoTip(data, c), estilo: 'tramo', color: colorTramo },
    { id: 'comision', operador: '=', label: 'Comisión', valor: moneda(c.comision), caption: `${millones(c.venta_base, 1)} × ${tasa(c.tasa_pct)}`, tip: `Comisión: ${moneda(c.venta_base)} × ${tasa(c.tasa_pct)} = ${moneda(c.comision)}`, estilo: 'neutro' },
    { id: 'bonos', operador: '+', label: 'Bonos', valor: moneda(bonoTotal), caption: ganados.length ? ganados.join(', ') : 'sin bonos', tip: bonosTip(c), estilo: 'bono' },
    { id: 'total', operador: '=', label: 'Total', valor: moneda(total), caption: 'comisión + bonos', tip: `${moneda(c.comision)} + ${moneda(bonoTotal)} = ${moneda(total)}`, estilo: 'total' },
  ];
  const sig = siguienteDe(c);
  return {
    titulo: 'Así se calcula tu comisión',
    sub: `${mesLargo(c.mes).replace(/^./, (x) => x.toUpperCase())}${c.fecha_datos ? ` · datos al ${fechaBogota(c.fecha_datos)}` : ''}`,
    pista: 'Pasa el mouse o toca un dato para ver cómo se calculó.',
    pasos,
    tramos: tramosConTasa(data).map((t) => ({
      nombre: t.nombre, tasa: esNumero(t.tasa_pct) ? tasa(t.tasa_pct) : null, desde: `desde ${sinDecimalInutil(t.desde_pct)}%`,
      color: colorDeTramo(t.nombre, tramos), actual: t.nombre === c.tramo,
    })),
    marcador: esNumero(c.cumplimiento_pct) ? `▲ Estás aquí · ${pct(c.cumplimiento_pct)}` : '▲ Estás aquí',
    siguiente: sig
      ? `Te faltan ${pesos(sig.falta)} para ${sig.nombre}; tu comisión pasaría a ${moneda(sig.comision_si_llega)}.`
      : 'Estás en el tramo más alto.',
    nota: 'El % se aplica a toda tu venta.',
  };
}
