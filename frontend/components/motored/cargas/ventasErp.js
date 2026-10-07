/**
 * Pure helpers of the raw ERP VENTAS dry run: which cargas show it, the
 * line options, the business wording of the discard counters, the sort of
 * the "sin línea" table and the Spanish messages of a failed assignment.
 */
import { etiquetaLinea } from '../configuracion/etiquetas';

/** Value the backend takes as "not a parts line": the ref moves to fuera_de_linea. */
export const LINEA_DESCARTAR = 'NO COMERCIAL';
export const ETIQUETA_DESCARTAR = 'No es de repuestos (descartar)';

/** Used when `lineas_comerciales` cannot be read. */
export const LINEAS_POR_DEFECTO = ['REPUESTOS', 'ACCESORIOS', 'LLANTAS', 'LUBRICANTES', 'BATERIAS', 'GPS', 'CASCOS'];

/** The dry run (and its endpoints) only exists for a VENTAS carga waiting for Aplicar. */
export const muestraSimulacionVentas = (carga) => carga?.tipo === 'VENTAS' && carga?.estado === 'VALIDADO';

/** Options of the line selects: `[{ valor, etiqueta }]`, configured lines first. */
export function opcionesDeLinea(configuradas) {
  const limpias = (configuradas || []).map((l) => String(l).trim().toUpperCase()).filter(Boolean);
  const base = limpias.length ? [...new Set(limpias)] : LINEAS_POR_DEFECTO;
  return [
    ...base.map((l) => ({ valor: l, etiqueta: etiquetaLinea(l) })),
    { valor: LINEA_DESCARTAR, etiqueta: ETIQUETA_DESCARTAR },
  ];
}

/** 1234 -> "1.234". */
export const numeroLegible = (n) => String(Math.round(Number(n) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');

/** Whole pesos: "1250000.00" -> "$ 1.250.000". */
export const pesosLegibles = (n) => `$ ${numeroLegible(n)}`;

const cuenta = (n, singular, plural) => `${numeroLegible(n)} ${Number(n) === 1 ? singular : plural}`;

const CONTADORES = [
  ['filas_tipo_excluido', 'fila descartada por tipo (motos, SOAT…)', 'filas descartadas por tipo (motos, SOAT…)'],
  ['filas_fuera_de_linea', 'fila fuera de las líneas de repuestos', 'filas fuera de las líneas de repuestos'],
  ['filas_sin_linea', 'fila de referencias sin línea', 'filas de referencias sin línea'],
  ['filas_co_vacio', 'fila con el C.O. vacío', 'filas con el C.O. vacío'],
];

/** The non-zero counters of `carga.log`, in plain Spanish. */
export function resumenContadores(log) {
  return CONTADORES
    .filter(([clave]) => Number(log?.[clave]) > 0)
    .map(([clave, singular, plural]) => cuenta(log[clave], singular, plural));
}

/** By valor desc, then filas desc (stable fallback of the server order). */
export function ordenarSinLinea(filas) {
  return [...(filas || [])].sort((a, b) => (Number(b.valor) - Number(a.valor)) || (b.filas - a.filas));
}

export const textoBloqueoAplicar = (n) => `Hay ${n} referencias sin línea: asígnelas antes de aplicar`;

export function textoNoEncontradas(noEncontradas) {
  const filas = noEncontradas.reduce((total, r) => total + Number(r.filas || 0), 0);
  return `${numeroLegible(filas)} filas de ${noEncontradas.length} referencias que no están en el catálogo no se cargan; `
    + 'si son repuestos, agréguelas al catálogo y vuelva a validar.';
}

const MENSAJE_409 = 'La referencia ya tiene línea o ya no está en la lista. La tabla se actualizó.';
const MENSAJE_422 = 'La línea elegida no es válida. Elija otra de la lista.';

/** Spanish message of a failed assignment: the server's text when it sent one. */
export function mensajeAsignacion(error) {
  const propio = error?.message && !/^HTTP \d+$/.test(error.message) ? error.message : '';
  if (error?.status === 422) return propio || MENSAJE_422;
  if (error?.status === 409) return propio || MENSAJE_409;
  return propio || 'No se pudo asignar la línea. Intente de nuevo.';
}
