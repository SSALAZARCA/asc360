/**
 * Live validators of the Indicadores and Comisiones editors. Each returns a
 * list of Spanish messages (empty = fine). They mirror the backend rules so
 * the person sees the problem before saving; the server stays the judge.
 */
import { etiquetaLinea } from './etiquetas';
import { numeroTexto } from './valor';

const texto = (v) => (v === null || v === undefined ? '' : String(v));
const limpio = (v) => texto(v).trim();

function repetidos(nombres) {
  const vistos = new Set();
  const salida = [];
  nombres.forEach((nombre) => {
    const clave = nombre.trim().toLowerCase();
    if (vistos.has(clave) && !salida.includes(nombre.trim())) salida.push(nombre.trim());
    vistos.add(clave);
  });
  return salida;
}

function mensajesDeFila(fila, i) {
  const n = i + 1;
  const mensajes = [];
  if (!limpio(fila.nombre)) mensajes.push(`Tramo ${n}: escriba un nombre.`);
  if (numeroTexto(fila.desde_pct) === null || numeroTexto(fila.tasa_pct) === null) {
    mensajes.push(`Tramo ${n}: «Desde» y «Tasa» necesitan un número.`);
  }
  return mensajes;
}

function mensajesDeOrden(borrador) {
  const desdes = borrador.map((f) => numeroTexto(f.desde_pct));
  const mensajes = [];
  if (desdes[0] !== null && Number(desdes[0]) !== 0) mensajes.push('El primer tramo debe empezar en 0 %.');
  desdes.forEach((desde, i) => {
    const antes = desdes[i - 1];
    if (i > 0 && desde !== null && antes !== null && Number(desde) <= Number(antes)) {
      mensajes.push(`Tramo ${i + 1}: «Desde» debe ser mayor que el del tramo anterior.`);
    }
  });
  return mensajes;
}

export function validarTramos(borrador) {
  if (!borrador.length) return ['Agregue al menos un tramo.'];
  const mensajes = [...borrador.flatMap(mensajesDeFila), ...mensajesDeOrden(borrador)];
  repetidos(borrador.map((f) => limpio(f.nombre)).filter(Boolean)).forEach((nombre) => {
    mensajes.push(`El nombre «${nombre}» está repetido.`);
  });
  return mensajes;
}

const ETIQUETAS_SEMAFORO = { verde_desde: 'Verde desde', ambar_desde: 'Ámbar desde' };

export function validarSemaforo(borrador) {
  const mensajes = [];
  const numeros = {};
  Object.keys(ETIQUETAS_SEMAFORO).forEach((campo) => {
    const n = numeroTexto(borrador[campo]);
    const nombre = ETIQUETAS_SEMAFORO[campo];
    if (n === null) mensajes.push(`«${nombre}» necesita un número.`);
    else if (Number(n) > 200) mensajes.push(`«${nombre}» debe estar entre 0 y 200.`);
    else numeros[campo] = Number(n);
  });
  const { verde_desde: verde, ambar_desde: ambar } = numeros;
  if (verde !== undefined && ambar !== undefined && ambar >= verde) {
    mensajes.push('«Ámbar desde» debe ser menor que «Verde desde».');
  }
  return mensajes;
}

/** `valores`: the items of a list; options `digitos` and `unicos`. */
export function validarLista(valores, { digitos = false, unicos = false } = {}) {
  if (!valores.length) return ['Agregue al menos un valor.'];
  const mensajes = [];
  if (digitos) {
    valores.filter((v) => !/^[0-9]+$/.test(v)).forEach((v) => mensajes.push(`«${v}» debe tener sólo dígitos.`));
  }
  if (unicos) {
    repetidos(valores).forEach((v) => mensajes.push(`«${v}» está repetido.`));
  }
  return mensajes;
}

function mensajesDeBono(fila) {
  const nombre = etiquetaLinea(fila.linea);
  const mensajes = [];
  const pct = numeroTexto(fila.pct_meta);
  if (pct === null || Number(pct) <= 0 || Number(pct) > 100) {
    mensajes.push(`${nombre}: la meta debe ser un porcentaje mayor que 0 y hasta 100.`);
  }
  if (!/^\d+$/.test(limpio(fila.bono))) mensajes.push(`${nombre}: el bono debe ser un valor entero en pesos, 0 o más.`);
  return mensajes;
}

/**
 * Per-line bonuses (comision_lineas). An empty list is fine. `lineas` (the
 * configured lineas_comerciales plus TECNIRED) enables the unknown-line
 * check; without it the server stays the judge of which lines exist.
 */
export function validarBonosLinea(borrador, lineas = null) {
  const mensajes = borrador.flatMap(mensajesDeBono);
  const codigos = borrador.map((f) => limpio(f.linea));
  if (lineas) {
    codigos.filter((c) => !lineas.includes(c)).forEach((c) => {
      mensajes.push(`La línea «${etiquetaLinea(c)}» no está en las líneas comerciales configuradas.`);
    });
  }
  repetidos(codigos).forEach((c) => mensajes.push(`La línea «${etiquetaLinea(c)}» está repetida.`));
  return mensajes;
}

/** Codes of ventas_tipos_excluidos: letters, digits, dot, dash and underscore. */
const CODIGO_TIPO = /^[A-Z0-9._-]+$/;
export const ETIQUETA_MODO_TIPO = { prefijo: 'Empieza por', exacto: 'Exacto' };

function mensajeDeTipo(fila, i) {
  const codigo = limpio(fila.codigo).toUpperCase();
  if (!codigo) return `Fila ${i + 1}: escriba un código.`;
  if (!CODIGO_TIPO.test(codigo)) {
    return `«${limpio(fila.codigo)}» tiene caracteres no permitidos (use letras, números, punto, guion o guion bajo).`;
  }
  return null;
}

/** ERP inventory types discarded on a VENTAS load. An empty list is fine. */
export function validarTiposExcluidos(borrador) {
  const mensajes = borrador.map(mensajeDeTipo).filter(Boolean);
  const vistos = new Set();
  borrador.forEach((fila) => {
    const codigo = limpio(fila.codigo).toUpperCase();
    const clave = `${codigo}|${fila.modo}`;
    const mensaje = `«${codigo}» (${ETIQUETA_MODO_TIPO[fila.modo] || fila.modo}) está repetido.`;
    if (codigo && vistos.has(clave) && !mensajes.includes(mensaje)) mensajes.push(mensaje);
    vistos.add(clave);
  });
  return mensajes;
}
