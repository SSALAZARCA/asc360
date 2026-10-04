/**
 * Pure rules of the KPI's header filters: period presets and labels (Spanish, as in the design),
 * month toggling and the store / HMCL labels. Months are `AAAA-MM` strings.
 */
export const MAX_MESES = 12;
export const MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
const MESES_LARGOS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

export const PRESETS = [
  { id: 'ytd', label: 'Año corrido' },
  { id: 'trimestre', label: 'Último trimestre' },
  { id: 'mes', label: 'Último mes' },
];

export const HMCL_OPCIONES = [
  { id: 'incluir', label: 'Incluir HMCL', desc: 'Toda la venta, con garantías' },
  { id: 'excluir', label: 'Excluir HMCL', desc: 'Solo venta a clientes' },
  { id: 'solo', label: 'Solo HMCL', desc: 'Solo garantías facturadas a HMCL' },
];

const anioDe = (mes) => mes.slice(0, 4);
const indiceDe = (mes) => Number(mes.slice(5, 7)) - 1;
const clave = (anio, indice) => `${anio}-${String(indice + 1).padStart(2, '0')}`;

/** The 12 months of the year of `ultimoMes`. */
export function mesesDelAnio(ultimoMes) {
  return MESES_CORTOS.map((_, i) => clave(anioDe(ultimoMes), i));
}

/** Months of a preset, always inside the year of `ultimoMes`. */
export function presetMeses(id, ultimoMes) {
  const ultimo = indiceDe(ultimoMes);
  const desde = { ytd: 0, trimestre: Math.max(0, ultimo - 2), mes: ultimo }[id] ?? 0;
  return mesesDelAnio(ultimoMes).slice(desde, ultimo + 1);
}

const mismos = (a, b) => a.length === b.length && a.every((m, i) => m === b[i]);
const contiguos = (meses) => meses.every((m, i) => i === 0 || Number(m.slice(0, 4)) * 12 + indiceDe(m) === Number(meses[i - 1].slice(0, 4)) * 12 + indiceDe(meses[i - 1]) + 1);
const corto = (mes) => MESES_CORTOS[indiceDe(mes)];

/** `Año corrido`, `Jul 2026`, `Jul – Sep 2026` (contiguous) or `Ene, Jul, Ago 2026`. */
export function etiquetaPeriodo(meses, ultimoMes) {
  const orden = [...(meses || [])].sort();
  if (!orden.length) return 'Elegí meses';
  if (ultimoMes && mismos(orden, presetMeses('ytd', ultimoMes))) return 'Año corrido';
  const anio = anioDe(orden[0]);
  if (orden.length === 1) return `${corto(orden[0])} ${anio}`;
  if (contiguos(orden)) return `${corto(orden[0])} – ${corto(orden[orden.length - 1])} ${anio}`;
  return `${orden.map(corto).join(', ')} ${anio}`;
}

/** Short period for card titles: `julio` for one month, `ene–sep` for a contiguous range. */
export function periodoCorto(meses) {
  const orden = [...(meses || [])].sort();
  if (!orden.length) return '';
  if (orden.length === 1) return MESES_LARGOS[indiceDe(orden[0])];
  const inicio = corto(orden[0]).toLowerCase();
  const fin = corto(orden[orden.length - 1]).toLowerCase();
  return contiguos(orden) ? `${inicio}–${fin}` : `${orden.length} meses`;
}

export const resumenPeriodo = (n) => `${n} ${n === 1 ? 'mes seleccionado' : 'meses seleccionados'}`;

/** Adds or removes `mes`, sorted; adding past `MAX_MESES` is ignored. */
export function alternarMes(meses, mes, max = MAX_MESES) {
  if (meses.includes(mes)) return meses.filter((m) => m !== mes);
  return meses.length >= max ? meses : [...meses, mes].sort();
}

export function etiquetaTiendas(ids, tiendas) {
  if (!ids.length) return 'Toda la red';
  if (ids.length > 1) return `${ids.length} tiendas`;
  return tiendas.find((t) => t.id === ids[0])?.nombre ?? '1 tienda';
}

export const resumenTiendas = (n, total) => (n === 0 ? `Las ${total} tiendas` : `${n} ${n === 1 ? 'tienda seleccionada' : 'tiendas seleccionadas'}`);

export const opcionHmcl = (id) => HMCL_OPCIONES.find((o) => o.id === id) ?? HMCL_OPCIONES[0];
export const etiquetaHmcl = (id) => opcionHmcl(id).label;
