/**
 * Pure helpers of the Configuración page. A stored value (JSON) becomes an
 * editable DRAFT shaped for its control (`aBorrador`), the draft becomes the
 * JSON the API validates (`desdeBorrador` -> `{ valor }` or `{ error }`), and
 * `formatearValor` writes it for a person. The server stays the judge of
 * ranges and cross-field rules; here only the shape and "is it a number".
 */
const ENTERO = /^-?\d+$/;
const DECIMAL = /^\d+([.,]\d+)?$/;

const textoDe = (valor) => (valor === null || valor === undefined ? '' : String(valor));
const unaLinea = (texto) => texto.split('\n').map((x) => x.trim()).filter(Boolean);

function numeroTexto(texto) {
  const limpio = textoDe(texto).trim();
  return DECIMAL.test(limpio) ? limpio.replace(',', '.') : null;
}

function entero(borrador) {
  const limpio = textoDe(borrador).trim();
  if (!ENTERO.test(limpio)) return { error: 'Ingrese un número entero.' };
  return { valor: Number(limpio) };
}

function decimal(borrador) {
  const numero = numeroTexto(borrador);
  if (numero === null) return { error: 'Ingrese un número (decimales con punto o coma).' };
  return { valor: numero };
}

function objeto(spec, borrador) {
  const valor = {};
  for (const campo of spec.campos) {
    const numero = numeroTexto(borrador[campo]);
    if (numero === null) return { error: `El campo «${campo}» necesita un número.` };
    valor[campo] = numero;
  }
  return { valor };
}

function mapa(borrador) {
  const valor = {};
  for (const fila of borrador) {
    const clave = textoDe(fila.clave).trim();
    if (!clave) continue;
    if (clave in valor) return { error: `El cargo «${clave}» está repetido.` };
    valor[clave] = fila.valor;
  }
  return { valor };
}

function tramos(borrador) {
  const valor = [];
  for (const [i, fila] of borrador.entries()) {
    const desde = numeroTexto(fila.desde_pct);
    const tasa = numeroTexto(fila.tasa_pct);
    if (desde === null || tasa === null) {
      return { error: `Tramo ${i + 1}: «desde_pct» y «tasa_pct» necesitan un número.` };
    }
    valor.push({ nombre: textoDe(fila.nombre).trim(), desde_pct: desde, tasa_pct: tasa });
  }
  return { valor };
}

export function desdeBorrador(spec, borrador) {
  switch (spec.tipo) {
    case 'entero': return entero(borrador);
    case 'decimal': return decimal(borrador);
    case 'lista':
    case 'lista_digitos': return { valor: unaLinea(borrador) };
    case 'k_fms':
    case 'objeto_numerico': return objeto(spec, borrador);
    case 'mapa_opcion': return mapa(borrador);
    case 'tramos': return tramos(borrador);
    default: return { valor: borrador };
  }
}

export function aBorrador(spec, valor) {
  switch (spec.tipo) {
    case 'entero':
    case 'decimal': return textoDe(valor);
    case 'lista':
    case 'lista_digitos': return (valor || []).join('\n');
    case 'k_fms':
    case 'objeto_numerico':
      return Object.fromEntries(spec.campos.map((c) => [c, textoDe((valor || {})[c])]));
    case 'mapa_opcion':
      return Object.entries(valor || {}).map(([clave, v]) => ({ clave, valor: v }));
    case 'tramos':
      return (valor || []).map((t) => ({
        nombre: t.nombre, desde_pct: textoDe(t.desde_pct), tasa_pct: textoDe(t.tasa_pct),
      }));
    default: return valor;
  }
}

export function formatearValor(spec, valor) {
  if (valor === null || valor === undefined) return 'Sin valor';
  switch (spec.tipo) {
    case 'bool': return valor ? 'Sí' : 'No';
    case 'lista':
    case 'lista_digitos': return valor.length ? valor.join(', ') : '(vacía)';
    case 'k_fms':
    case 'objeto_numerico':
      return spec.campos.map((c) => `${c}: ${valor[c]}`).join(' · ');
    case 'mapa_opcion': {
      const pares = Object.entries(valor).map(([k, v]) => `${k} → ${v}`);
      return pares.length ? pares.join(', ') : '(vacío)';
    }
    case 'tramos':
      return valor.map((t) => `${t.nombre}: desde ${t.desde_pct}% → ${t.tasa_pct}%`).join(' · ');
    default: return String(valor);
  }
}

const dosDigitos = (n) => String(n).padStart(2, '0');

/** `YYYY-MM` of a date (the value of an `<input type="month">`). */
export function mesActual(hoy = new Date()) {
  return `${hoy.getFullYear()}-${dosDigitos(hoy.getMonth() + 1)}`;
}

/** The first day of a `YYYY-MM` month: what the API stores as `vigente_desde`. */
export const vigenteDesdeDeMes = (mes) => `${mes}-01`;
