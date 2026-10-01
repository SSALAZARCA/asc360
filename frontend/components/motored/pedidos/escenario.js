/**
 * Pure rules of the scenario launcher (ADMIN): the Spanish wording of every
 * engine key, the typed value of each one (bool, opcion, entero, decimal,
 * k_fms), what counts as a change against the value in force, and the
 * `overrides` body of the launch. A draft is what the user edits (a switch,
 * an option, text); a value is what the server receives.
 */
const ETIQUETAS = {
  incluir_demanda_perdida_en_ponderada: {
    titulo: 'Contar las ventas perdidas',
    ayuda: 'Si se activa, las ventas que se perdieron por falta de producto también se suman a la demanda con la que se calcula el pedido. El pedido suele subir.',
  },
  factor_demanda_perdida: {
    titulo: 'Peso de las ventas perdidas',
    ayuda: 'Qué parte de cada venta perdida se cuenta como demanda: 1 es completa y 0,5 es la mitad. Solo tiene efecto si se cuentan las ventas perdidas.',
  },
  consolidar_sustituidas: {
    titulo: 'Sumar las ventas de la referencia sustituida',
    ayuda: 'Si se activa, las ventas de una referencia que fue sustituida se suman a la que la reemplaza, para que la nueva herede el historial de venta.',
  },
  dias_entre_pedidos: {
    titulo: 'Días entre pedidos',
    ayuda: 'Cada cuántos días se hace un pedido. Entre más días, más producto se pide en cada pedido para cubrir ese tiempo.',
  },
  modo_mes_en_curso: {
    titulo: 'Qué hacer con el mes en curso',
    ayuda: 'EXCLUIDO ignora las ventas del mes que va corriendo. PONDERADO las proyecta a mes completo y las suma a la demanda.',
  },
  tope_proyeccion_mes_actual: {
    titulo: 'Tope de la proyección del mes en curso',
    ayuda: 'Cuántas veces el promedio normal puede valer, como máximo, la proyección del mes en curso. Evita que unos pocos días de ventas disparen el pedido. Solo aplica si el mes en curso es PONDERADO.',
  },
  min_dias_mes_actual: {
    titulo: 'Días mínimos del mes en curso',
    ayuda: 'Cuántos días del mes deben haber pasado para tener en cuenta el mes en curso. Antes de eso se ignora.',
  },
  excluir_transito_vencido: {
    titulo: 'Ignorar la mercancía en tránsito vencida',
    ayuda: 'Si se activa, la mercancía en tránsito que ya está vencida (facturada hace demasiado tiempo y sin recibir) no se cuenta como inventario que va a llegar. El pedido suele subir.',
  },
  modo_redondeo_empaque: {
    titulo: 'Redondeo al empaque',
    ayuda: 'CERCANO redondea al empaque completo más cercano. ARRIBA siempre sube al siguiente empaque completo.',
  },
  corte_abc_a: {
    titulo: 'Corte de la clase A',
    ayuda: 'Hasta qué parte acumulada de la demanda una referencia se considera clase A: 0,8 significa el 80 % de la demanda. Un corte más alto deja más referencias en A.',
  },
  corte_abc_b: {
    titulo: 'Corte de la clase B',
    ayuda: 'Hasta qué parte acumulada de la demanda una referencia se considera clase B (debe ser mayor que el corte de A): 0,95 significa el 95 %. Lo que queda después es clase C.',
  },
  umbral_f: {
    titulo: 'Meses con venta para rotación frecuente (F)',
    ayuda: 'Cuántos meses con venta se necesitan para que una referencia se considere de rotación frecuente (F).',
  },
  umbral_m: {
    titulo: 'Meses con venta para rotación media (M)',
    ayuda: 'Cuántos meses con venta se necesitan para que una referencia se considere de rotación media (M). Con menos es de rotación lenta (S).',
  },
  k_fms: {
    titulo: 'Factores de cobertura por rotación',
    ayuda: 'Cuántas veces se cubre el tiempo de reposición según la rotación: F es frecuente, M media y S lenta. Un factor más alto pide más.',
  },
  tolerancia_sobrestock: {
    titulo: 'Tolerancia de sobrestock',
    ayuda: 'Cuánto inventario por encima de lo necesario se tolera antes de marcar la referencia como sobrestock: 0,25 significa un 25 % de más.',
  },
  meses_inventario_muerto: {
    titulo: 'Meses sin venta para inventario muerto',
    ayuda: 'Si una referencia con inventario no se vendió en estos meses, se marca como inventario muerto.',
  },
  max_dias_antiguedad_inventario: {
    titulo: 'Antigüedad máxima del inventario (días)',
    ayuda: 'Si la última carga de inventario tiene más días que este límite, la corrida no se calcula.',
  },
  max_dias_antiguedad_backorder: {
    titulo: 'Antigüedad máxima de los backorders (días)',
    ayuda: 'Si la última carga de backorders tiene más días que este límite, la corrida no se calcula.',
  },
  max_dias_antiguedad_facturas: {
    titulo: 'Antigüedad máxima de las facturas en tránsito (días)',
    ayuda: 'Si la última carga de facturas tiene más días que este límite, la corrida no se calcula.',
  },
  max_dias_antiguedad_ingresos: {
    titulo: 'Antigüedad máxima de los ingresos (días)',
    ayuda: 'Si la última carga de ingresos tiene más días que este límite, la corrida no se calcula.',
  },
};

/** Business title and explanation of an engine key; a key new to the screen shows its technical name. */
export const etiquetaClave = (clave) => ETIQUETAS[clave] || { titulo: clave, ayuda: '' };

const FACTORES = ['F', 'M', 'S'];
const ENTERO = /^\d+$/;
const DECIMAL = /^\d+([.,]\d+)?$/;
const ERROR_ENTERO = 'Escriba un número entero, sin decimales.';
const ERROR_DECIMAL = 'Escriba un número, por ejemplo 0,8.';
const ERROR_K_FMS = 'Escriba los tres factores (F, M y S) como números.';

const aTexto = (valor) => (valor == null ? '' : String(Number(valor)).replace('.', ','));

/** A stored value as the draft the user edits: a switch, an option, or text (k_fms: one text per factor). */
export function borradorDesde(tipo, valor) {
  if (tipo === 'bool') return Boolean(valor);
  if (tipo === 'opcion') return valor == null ? '' : String(valor);
  if (tipo === 'k_fms') return Object.fromEntries(FACTORES.map((f) => [f, aTexto(valor ? valor[f] : null)]));
  return aTexto(valor);
}

const aDecimal = (texto) => String(texto).trim().replace(',', '.');
const esDecimal = (texto) => DECIMAL.test(String(texto).trim());

/** The draft as the value the server receives: `{ valor }`, or `{ error }` in Spanish when it is not valid. */
export function parsearBorrador(tipo, borrador) {
  if (tipo === 'bool' || tipo === 'opcion') return { valor: borrador };
  if (tipo === 'entero') {
    return ENTERO.test(String(borrador).trim()) ? { valor: Number(String(borrador).trim()) } : { error: ERROR_ENTERO };
  }
  if (tipo === 'k_fms') {
    if (!FACTORES.every((f) => esDecimal(borrador[f]))) return { error: ERROR_K_FMS };
    return { valor: Object.fromEntries(FACTORES.map((f) => [f, aDecimal(borrador[f])])) };
  }
  return esDecimal(borrador) ? { valor: aDecimal(borrador) } : { error: ERROR_DECIMAL };
}

/** True when the typed value differs from the one in force (numbers compare by value, not by text). */
export function esCambio(tipo, actual, parseado) {
  if (parseado.error !== undefined) return false;
  const { valor } = parseado;
  if (tipo === 'k_fms') return FACTORES.some((f) => Number(valor[f]) !== Number(actual ? actual[f] : NaN));
  if (tipo === 'entero' || tipo === 'decimal') return Number(valor) !== Number(actual);
  return valor !== actual;
}

/**
 * The launch body of the rows `{ clave, tipo, actual, borrador }`: only the
 * keys that changed, how many changed, and the message of each invalid row.
 */
export function armarOverrides(filas) {
  const overrides = {};
  const errores = {};
  filas.forEach(({ clave, tipo, actual, borrador }) => {
    const parseado = parsearBorrador(tipo, borrador);
    if (parseado.error !== undefined) errores[clave] = parseado.error;
    else if (esCambio(tipo, actual, parseado)) overrides[clave] = parseado.valor;
  });
  return { overrides, errores, cambios: Object.keys(overrides).length };
}

const NUMERO = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 4 });

/** A value in force, or a tested one, in words: Sí / No, the option, a number with a comma, or `F 3 · M 1,5 · S 1`. */
export function textoValor(tipo, valor) {
  if (valor == null || valor === '') return '—';
  if (tipo === 'bool') return valor ? 'Sí' : 'No';
  if (tipo === 'k_fms') return FACTORES.map((f) => `${f} ${NUMERO.format(Number(valor[f]))}`).join(' · ');
  if (tipo === 'entero' || tipo === 'decimal') return NUMERO.format(Number(valor));
  return String(valor);
}

const NUMERICO = /^\d+([.,]\d+)?$/;

/** The tested value of a snapshot, whose type is read from the value itself (the catalog is not loaded there). */
function textoLibre(valor) {
  if (typeof valor === 'boolean') return textoValor('bool', valor);
  if (valor !== null && typeof valor === 'object') return textoValor('k_fms', valor);
  if (typeof valor === 'number' || NUMERICO.test(String(valor))) return textoValor('decimal', valor);
  return String(valor);
}

/** What a scenario tested, one line per parameter (`Título: valor`), from the `overrides` of its detail. */
export function resumenOverrides(overrides) {
  return Object.entries(overrides || {}).map(([clave, valor]) => `${etiquetaClave(clave).titulo}: ${textoLibre(valor)}`);
}
